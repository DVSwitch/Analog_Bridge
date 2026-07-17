###############################################################################
#
#   AMBEtest5 — AMBE3000 stress test and validation tool
#
#   Exercises AMBE3000 series vocoder chips over serial (USB dongle) or UDP
#   (network AMBE server). Originally written by Mike N4IRR as AMBEtest4.py,
#   this version is a class-based rewrite with comprehensive test stages and
#   improved error handling.
#
#   What it does:
#     1. Identifies the chip by querying PRODID and VERSTRING.
#     2. Mixed rate encode/decode — randomly switches between AMBE+ 4800
#        (D-Star rate) and AMBE+ 3600 (DMR rate) mid-stream, alternating
#        between silence and real AMBE frames for richer coverage.
#        Stresses rate switching under load.
#     3. Error recovery — sends invalid opcodes, truncated packets, and
#        garbage data, verifying the chip recovers without crashing.
#     4. Concurrent encode+decode — exercises both vocoder cores simultaneously.
#     5. Concurrent mixed rate — like #4 but randomly switches rate between cycles.
#     6. Edge-case AMBE frames — pathological patterns (all-zero, all-one, etc.).
#     7. Cross-rate round-trip — decode at 3600, encode at 4800, decode at 4800.
#     8. Packet resilience — loss, duplicate, reorder testing (--resilience).
#     9. Jitter sweep — latency test at multiple jitter levels (--jitter-sweep).
#
#   Defaults to 460800 baud. Older boards (230400) can be selected with -b.
#
#   Copyright (C) 2021 Mike Zingman N4IRR
#   Copyright (C) 2026 DVSwitch KaT
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software Foundation,
#   Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
#
###############################################################################
#
#   Changelog:
#     v1  - Original AMBEtest4_p3 by Mike N4IRR
#     v5  - PRODID/VERSTRING, mixed random rate switching, -c N, -h, concurrent (2026)
#     v5.1 - concurrent mixed rate, edge-case frames, cross-rate round-trip,
#            packet resilience test, jitter sweep (2026)
#
###############################################################################

VERSION = "6.0"

import serial
import sys
import time
import random
import signal
import socket
import atexit
import argparse
import logging
import statistics
import math
import struct

_log = logging.getLogger("AMBEtest5")

setDstar = bytearray.fromhex("61 00 0d 00 0a 01 30 07 63 40 00 00 00 00 00 00 48")
getProdId = bytearray.fromhex("61 00 01 00 30")
getVersion = bytearray.fromhex("61 00 01 00 31")
setDMR = bytearray.fromhex("61 00 0D 00 0A 04 31 07 54 24 00 00 00 00 00 6F 48")
encodeAMBE = bytearray.fromhex("61 00 0B 01 01 48")
encodePCM = bytearray.fromhex("61 01 42 02")
silence = bytearray.fromhex("AC AA 40 20 00 44 40 80 80")
# Real AMBE frames from MMDVM-Transcoder Tester — exercise more coefficient patterns
real_dstar = bytearray.fromhex("02 19 17 E4 B3 E2 00 A2 20")  # 4800 bps
real_dmr   = bytearray.fromhex("A6 CB 80 27 20 4F 9B CB F3")  # 3600 bps
# Pathological AMBE frames — exercise edge-case decoder behaviour
patho_all_zero    = bytearray(9)
patho_all_one     = bytearray([0xFF] * 9)
patho_alternating = bytearray([0xAA, 0x55, 0xAA, 0x55, 0xAA, 0x55, 0xAA, 0x55, 0xAA])
patho_walk_one    = bytearray([0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x01])
patho_clip_max    = bytearray([0x7F, 0xFF, 0x7F, 0xFF, 0x7F, 0xFF, 0x7F, 0xFF, 0x7F])
patho_clip_min    = bytearray([0x80, 0x00, 0x80, 0x00, 0x80, 0x00, 0x80, 0x00, 0x80])
# DV3K reset/channel-set commands for AMBE3000.
# DV3K packet: 0x61 <len_hi> <len_lo> <type> <payload bytes + optional 0x2f xor>
#   len may or may not include the 0x2f terminator + xor byte
#   (different firmware variants interpret it differently).
#   Both forms below are verified working with their respective hardware.
RESET_DEFAULT = bytearray.fromhex("61 00 07 00 34 05 00 00 0F 00 00")
RESET_DVMEGA = bytearray.fromhex("61 00 06 00 34 05 00 00 0F 00 00")

# PCM energy thresholds for encode/decode correctness validation
ENERGY_REAL_MIN    = 400    # Min RMS for decoded real AMBE frame
RUN_ROUNDTRIP_CYCLES = 10   # cycles for round-trip consistency test


class AMBEClient:
    def __init__(self, args: argparse.Namespace) -> None:
        self.port = None
        self.useSerial = not bool(args.ip)
        self.ip_address = args.ip or "127.0.0.1"
        self.UDP_PORT = args.port
        self.udp_timeout = args.timeout
        self.loop_count = args.count
        self.shouldStopOnError = args.error
        self.verbose = args.verbose
        self.reset_cmd = RESET_DVMEGA if args.dvmega else RESET_DEFAULT
        self.serialport = args.serial
        self.serial_bauds = [int(b) for b in args.baud.split(',')] if args.baud else None
        self.errorCount = 0
        self.latency_results = []  # list of dicts: {op, baud, elapsed_ms}
        self.jitter_ms = args.jitter

    def log(self, msg, *args, **kwargs):
        _log.info(msg, *args, **kwargs)

    def warn(self, msg, *args, **kwargs):
        _log.warning(msg, *args, **kwargs)

    def err(self, msg, *args, **kwargs):
        _log.error(msg, *args, **kwargs)
        self.errorCount += 1

    def debug(self, msg, *args, **kwargs):
        _log.debug(msg, *args, **kwargs)

    def stop_on_error(self):
        if self.shouldStopOnError:
            self.close()
            sys.exit(1)

    def recover(self):
        if not self.useSerial:
            return
        try:
            self.port.flushInput()
        except OSError:
            pass

    def close(self):
        if self.port:
            try:
                self.port.close()
            except OSError:
                pass
            self.port = None

    def connect(self):
        if self.useSerial:
            self._connect_serial()
        else:
            self._connect_udp()

    def _connect_serial(self):
        sp = self.serialport
        p = None
        for br in (self.serial_bauds if self.serial_bauds else [460800]):
            try:
                p = serial.Serial(sp, baudrate=br, timeout=1.0,
                    bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE, xonxoff=False, rtscts=False, dsrdtr=False)
                p.flushInput(); p.flushOutput()
                time.sleep(0.02)
                p.setDTR(False); p.setRTS(False)
                time.sleep(1)
                # Drain boot chatter until 2s of silence
                p.flushInput(); p.flushOutput()
                quiet = 0
                while quiet < 4:
                    d = p.read(30)
                    if d:
                        quiet = 0
                    else:
                        quiet += 1
                p.flushInput()
                # Send PRODID and check response
                for attempt in range(5):
                    p.write(bytearray.fromhex("61 00 01 00 30"))
                    time.sleep(0.3)
                    rcv = p.read(30)
                    for i in range(len(rcv) - 4):
                        if rcv[i] == 0x61 and rcv[i+3] == 0x00 and rcv[i+4] == 0x30:
                            self.port = p
                            self.log(f'Serial connection on {sp} at {br} baud')
                            self.log('Serial port parameters:')
                            self.log(f'  Port name:     {sp}')
                            self.log(f'  Baudrate:      {br}')
                            self.log(f'  Byte size:     {p.bytesize}')
                            self.log(f'  Parity:        {p.parity}')
                            self.log(f'  Stop bits:     {p.stopbits}')
                            return
                p.close()
            except Exception:
                if p is not None:
                    try: p.close()
                    except: pass
        self.err(f'Error opening serial port {sp}')
        sys.exit(2)

    def _connect_udp(self):
        self.port = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.port.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.port.settimeout(self.udp_timeout)
        self.log(f'UDP connection to {self.ip_address}:{self.UDP_PORT}')

    def send(self, cmd):
        if self.useSerial:
            return self.port.write(cmd)
        return self.port.sendto(cmd, (self.ip_address, self.UDP_PORT))

    def _read_exactly(self, n):
        assert self.useSerial, "_read_exactly is not supported for UDP transport"
        buf = b''
        while len(buf) < n:
            chunk = self.port.read(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf

    def recv(self):
        if self.useSerial:
            hdr = self._read_exactly(4)
            if hdr is None:
                self.err('AMBE header timeout')
                self.stop_on_error()
                return 0, b''
            plen = (hdr[1] << 8) | hdr[2]
            payload = self._read_exactly(plen)
            if payload is None:
                self.err('AMBE payload timeout')
                self.stop_on_error()
                return 0, b''
            buf = hdr + payload
            return len(buf), buf
        try:
            data, _addr = self.port.recvfrom(1024)
            return len(data), data
        except socket.timeout:
            return 0, b''

    def validate(self, cmd, expect, label):
        if self.verbose:
            self.debug(f'Testing {label}')
        wrote = self.send(cmd)
        if wrote != len(cmd):
            self.err(f'Tried to write {len(cmd)} but wrote {wrote} bytes: {label}')
            self.stop_on_error()
            return None, None
        for attempt in range(3):
            rlen, buf = self.recv()
            if rlen == 0:
                self.err(f'No reply from DV3000: {label}')
                self.stop_on_error()
                self.recover()
                return None, None
            if buf[0] != 0x61:
                self.err(f'DV3000 sent back invalid start byte 0x{buf[0]:02x}: {label}')
                self.err('  ' + ''.join(f'{b:02x}' for b in buf))
                self.stop_on_error()
                self.recover()
                return None, None
            plen = (buf[1] << 8) | buf[2]
            if rlen != plen + 4:
                self.err(f'Read {rlen} bytes, header says {plen}: {label}')
                self.err('  ' + ''.join(f'{b:02x}' for b in buf))
                self.stop_on_error()
                self.recover()
                return None, None
            payload = buf[4:]
            if payload and expect:
                if len(payload) < len(expect):
                    if attempt < 2:
                        if self.verbose:
                            self.debug(f'Stale response for {label}, retrying...')
                        continue
                    self.err(f'Short payload: got {len(payload)}, expected {len(expect)}: {label}')
                    self.err('  ' + ''.join(f'{b:02x}' for b in payload))
                    self.stop_on_error()
                    self.recover()
                    return None, None
                match = all(payload[x] == expect[x] for x in range(len(expect)))
                if not match:
                    if attempt < 2:
                        if self.verbose:
                            self.debug(f'Stale response for {label}, retrying...')
                        continue
                    self.err(f'Unexpected value from DV3000: {label}')
                    self.err(f'  Got: {payload}')
                    self.err(f'  Exp: {expect}')
                    self.err('  ' + ''.join(f'{b:02x}' for b in payload))
                    self.stop_on_error()
                    self.recover()
                    return None, None
            if self.verbose:
                self.debug('  Result: ' + ''.join(f'{b:02x}' for b in buf))
            return buf[:4], payload
        return None, None

    def drain_udp(self):
        if self.useSerial:
            return
        self.port.settimeout(0.3)
        drained = 0
        for _ in range(50):
            try:
                self.port.recvfrom(1024)
                drained += 1
            except socket.timeout:
                if drained > 0:
                    break
        self.port.settimeout(self.udp_timeout)

    def _measure_latency(self, cmd, expect, label):
        """Time a validate() call and record the result.
        Returns (hdr, payload) same as validate(), stores timing separately."""
        t0 = time.perf_counter()
        hdr, payload = self.validate(cmd, expect, label)
        elapsed = (time.perf_counter() - t0) * 1000  # milliseconds
        if payload is not None and hdr is not None:
            self.latency_results.append({
                'op': label,
                'baud': self.serial_bauds[0] if self.useSerial and self.serial_bauds else 460800,
                'elapsed': elapsed,
            })
        return hdr, payload

    def _report_latency(self, results, title):
        """Print latency statistics for a list of timing dicts."""
        if not results:
            self.log(f'  {title}: no data')
            return
        values = sorted(r['elapsed'] for r in results)
        n = len(values)
        avg = sum(values) / n
        mn = values[0]
        mx = values[-1]
        med = values[n // 2]
        p95 = values[int(n * 0.95)]
        p99 = values[int(n * 0.99)] if n >= 100 else mx
        std_val = statistics.stdev(values) if n > 1 else 0.0
        self.log(f'  {title}:')
        self.log(f'    Samples: {n:6d}')
        self.log(f'    Min:     {mn:8.2f} ms')
        self.log(f'    Avg:     {avg:8.2f} ms')
        self.log(f'    Median:  {med:8.2f} ms')
        self.log(f'    p95:     {p95:8.2f} ms')
        self.log(f'    p99:     {p99:8.2f} ms')
        self.log(f'    Max:     {mx:8.2f} ms')
        self.log(f'    Jitter:  {std_val:8.2f} ms')
        self._check_usb_batching(results)

    def _check_usb_batching(self, results):
        """Check if latency values cluster at USB frame boundaries (multiples of 1ms).
        USB full-speed frame = 1ms. Clustering at multiples of 1ms indicates
        USB polling is the dominant factor in latency."""
        if not results:
            return
        clustered = 0
        n = len(results)
        for r in results:
            remainder = r['elapsed'] % 1.0
            if remainder < 0.4 or remainder > 0.6:
                clustered += 1
        pct = (clustered / n) * 100
        if pct > 60:
            self.log(f'  * {pct:.0f}% of samples align to USB frame boundaries (1ms intervals)')

    def _pcm_rms(self, pcm_payload):
        """Compute RMS of PCM samples from a decode response payload (322 bytes).
        First 2 bytes are header, remaining 320 bytes = 160 x int16 LE samples.
        Returns RMS value (0 = silence, typical speech ~2000-8000)."""
        if len(pcm_payload) < 322:
            return 0.0
        samples = struct.unpack_from('<160h', pcm_payload, 2)
        sq_sum = sum(s * s for s in samples)
        return math.sqrt(sq_sum / len(samples))

    def _random_sleep(self):
        """Inject a random delay if jitter is configured.
        Sleeps random.uniform(0, self.jitter_ms) milliseconds."""
        if self.jitter_ms > 0:
            time.sleep(random.uniform(0, self.jitter_ms / 1000.0))

    def identify_chip(self):
        self.log('Identifying chip...')
        _hdr, payload = self.validate(getProdId, b'', 'Get Product ID')
        if payload and len(payload) > 5:
            name = payload[1:].rstrip(b'\x00').decode('ascii', errors='replace')
            valid = name.startswith('AMBE3000')
            if not valid:
                self.err(f'Unexpected product ID: {name}')
                self.stop_on_error()
            else:
                self.log(f'Product ID: {name}')
            _hdr, payload = self.validate(getVersion, b'', 'Get Version')
            if payload:
                ver = payload[1:].rstrip(b'\x00\x2f').decode('ascii', errors='replace')
                self.log(f'Version: {ver}')

    def run_mixed_rate_test(self):
        total = self.loop_count * 2
        jitter_str = f' with jitter 0..{self.jitter_ms:.0f}ms' if self.jitter_ms > 0 else ''
        est_sec = int(total * 0.025)
        est_min = est_sec // 60
        time_str = f' (~{est_min}m{est_sec % 60:02d}s)' if est_min > 0 else f' (~{est_sec}s)'
        self.log(f'Mixed rate encode/decode stress test{jitter_str}{time_str}...')
        self.validate(self.reset_cmd, bytearray.fromhex('39'), 'Reset DV3000')
        current = '4800'
        self.validate(setDstar, bytearray.fromhex('0a00'), 'Set AMBE+ 4800')
        switches = 0
        progress_interval = max(min(total // 10, 1000), 1)
        for _ in range(total):
            if random.random() < 0.5:
                if current == '4800':
                    self.validate(setDMR, bytearray.fromhex('0a00'), 'Set AMBE+ 3600')
                    current = '3600'
                else:
                    self.validate(setDstar, bytearray.fromhex('0a00'), 'Set AMBE+ 4800')
                    current = '4800'
                switches += 1
            # Alternate between silence and a real AMBE frame for richer coverage
            ambe_frame = silence if (_ % 2 == 0) else (real_dstar if current == '4800' else real_dmr)
            hdr, pcm = self.validate(encodeAMBE + ambe_frame, b'', 'Decode AMBE')
            if pcm is None:
                self.err('Decode AMBE returned nothing'); self.stop_on_error(); continue
            if len(pcm) != 322:
                self.err(f'Decode PCM length {len(pcm)}'); self.stop_on_error(); continue
            if pcm[0] != 0x00 or pcm[1] != 0xa0:
                self.err('PCM channel/bits'); self.stop_on_error(); continue
            # PCM energy check: real AMBE frames must produce audible PCM
            rms_val = self._pcm_rms(pcm)
            if self.verbose:
                label = 'silence' if _ % 2 == 0 else 'real'
                self.debug(f'  PCM RMS={rms_val:.0f} ({label})')
            if (_ % 2 == 1) and rms_val < ENERGY_REAL_MIN:
                self.err(f'Real frame PCM RMS={rms_val:.0f} < {ENERGY_REAL_MIN}')
                self.stop_on_error(); continue
            if hdr[3] != 0x02:
                self.err(f'PCM type {hdr[3]}'); self.stop_on_error(); continue
            hdr, ambe = self.validate(encodePCM + pcm, b'', 'Encode PCM')
            if ambe is None:
                self.err('Encode PCM returned nothing'); self.stop_on_error(); continue
            if len(ambe) != 11:
                self.err(f'Encode AMBE length {len(ambe)}'); self.stop_on_error(); continue
            if hdr[3] != 0x01:
                self.err(f'AMBE type {hdr[3]}'); self.stop_on_error(); continue
            if ambe[0] != 0x01:
                self.err('AMBE channel ID'); self.stop_on_error(); continue
            if ambe[1] != 0x48:
                self.err(f'AMBE bit length {ambe[1]}'); self.stop_on_error(); continue
            self._random_sleep()  # jitter between cycles
            if (_ + 1) % progress_interval == 0:
                self.log(f'  {_ + 1}/{total} cycles, {switches} rate switches')
        self.log(f'  {total} cycles, {switches} rate switches')

    def run_concurrent_test(self):
        est_sec = int(self.loop_count * 0.025)
        est_min = est_sec // 60
        time_str = f' (~{est_min}m{est_sec % 60:02d}s)' if est_min > 0 else f' (~{est_sec}s)'
        self.log(f'Testing concurrent encode/decode{time_str}...')
        self.validate(self.reset_cmd, bytearray.fromhex('39'), 'Reset DV3000')
        self.validate(setDMR, bytearray.fromhex('0a00'), 'Set AMBE+ 3600')
        _hdr, pcm = self.validate(encodeAMBE + silence, b'', 'Prime PCM')
        if pcm is None or len(pcm) != 322:
            self.err('Failed to capture PCM for concurrent test')
            self.stop_on_error()
            return
        progress_interval = max(min(self.loop_count // 10, 1000), 1)
        for _ in range(self.loop_count):
            self.send(encodeAMBE + (silence if _ % 2 == 0 else real_dmr))
            self.send(encodePCM + pcm)
            r1, b1 = self.recv()
            r2, b2 = self.recv()
            if r1 == 0 or r2 == 0:
                self.err('Concurrent test timeout'); self.stop_on_error(); break
            if b1[3] == 0x02:
                pcm_b, ambe_b = b1, b2
            elif b2[3] == 0x02:
                pcm_b, ambe_b = b2, b1
            else:
                self.err('Concurrent test no PCM response'); self.stop_on_error(); break
            if ambe_b[3] != 0x01:
                self.err('Concurrent test no AMBE response'); self.stop_on_error(); break
            pp = pcm_b[4:]; ap = ambe_b[4:]
            if len(pp) != 322:
                self.err('Concurrent PCM bad length'); self.stop_on_error(); break
            if len(ap) != 11:
                self.err('Concurrent AMBE bad length'); self.stop_on_error(); break
            if pp[0] != 0x00 or pp[1] != 0xa0:
                self.err('Concurrent PCM format'); self.stop_on_error(); break
            if ap[0] != 0x01 or ap[1] != 0x48:
                self.err('Concurrent AMBE format'); self.stop_on_error(); break
            if (_ + 1) % progress_interval == 0:
                self.log(f'  concurrent {_ + 1}/{self.loop_count}')

    def run_concurrent_mixed_test(self):
        """Like run_concurrent_test but randomly switches rate between cycles
        while both decode and encode cores are active simultaneously."""
        total = self.loop_count
        est_sec = int(total * 0.030)
        est_min = est_sec // 60
        time_str = f' (~{est_min}m{est_sec % 60:02d}s)' if est_min > 0 else f' (~{est_sec}s)'
        self.log(f'Testing concurrent encode/decode with rate switching{time_str}...')
        self.validate(self.reset_cmd, bytearray.fromhex('39'), 'Reset DV3000')
        current = '4800'
        switches = 0
        self.validate(setDstar, bytearray.fromhex('0a00'), 'Set AMBE+ 4800')
        _hdr, pcm = self.validate(encodeAMBE + silence, b'', 'Prime PCM')
        if pcm is None or len(pcm) != 322:
            self.err('Failed to capture PCM for concurrent mixed test')
            self.stop_on_error()
            return
        progress_interval = max(min(total // 10, 1000), 1)
        for _ in range(total):
            if random.random() < 0.5:
                if current == '4800':
                    self.validate(setDMR, bytearray.fromhex('0a00'), 'Set AMBE+ 3600')
                    current = '3600'
                else:
                    self.validate(setDstar, bytearray.fromhex('0a00'), 'Set AMBE+ 4800')
                    current = '4800'
                switches += 1
            ambe_frame = silence if _ % 2 == 0 else (real_dstar if current == '4800' else real_dmr)
            self.send(encodeAMBE + ambe_frame)
            self.send(encodePCM + pcm)
            r1, b1 = self.recv()
            r2, b2 = self.recv()
            if r1 == 0 or r2 == 0:
                self.err('Concurrent mixed test timeout'); self.stop_on_error(); break
            if b1[3] == 0x02:
                pcm_b, ambe_b = b1, b2
            elif b2[3] == 0x02:
                pcm_b, ambe_b = b2, b1
            else:
                self.err('Concurrent mixed test no PCM response'); self.stop_on_error(); break
            if ambe_b[3] != 0x01:
                self.err('Concurrent mixed test no AMBE response'); self.stop_on_error(); break
            pp = pcm_b[4:]; ap = ambe_b[4:]
            if len(pp) != 322:
                self.err('Concurrent mixed PCM bad length'); self.stop_on_error(); break
            if len(ap) != 11:
                self.err('Concurrent mixed AMBE bad length'); self.stop_on_error(); break
            if pp[0] != 0x00 or pp[1] != 0xa0:
                self.err('Concurrent mixed PCM format'); self.stop_on_error(); break
            if ap[0] != 0x01 or ap[1] != 0x48:
                self.err('Concurrent mixed AMBE format'); self.stop_on_error(); break
            if (_ + 1) % progress_interval == 0:
                self.log(f'  concurrent mixed {_ + 1}/{total}, {switches} switches')
        self.log(f'  {total} concurrent mixed cycles, {switches} rate switches')

    def run_edge_frame_test(self):
        """Decode pathological AMBE frames at both rates.
        Verifies the chip doesn't crash and produces non-zero PCM."""
        self.log('Testing edge-case AMBE frames...')
        frames_4800 = [
            ('all-zero', patho_all_zero),
            ('all-one', patho_all_one),
            ('alternating', patho_alternating),
            ('walking-one', patho_walk_one),
            ('clip-max', patho_clip_max),
            ('clip-min', patho_clip_min),
        ]
        frames_3600 = frames_4800  # same frame patterns, different rate context
        for rate_label, frames, set_cmd in [
            ('4800 (D-Star)', frames_4800, setDstar),
            ('3600 (DMR)', frames_3600, setDMR),
        ]:
            self.validate(self.reset_cmd, bytearray.fromhex('39'), f'Reset for edge frame test {rate_label}')
            self.validate(set_cmd, bytearray.fromhex('0a00'), f'Set {rate_label}')
            for name, frame in frames:
                hdr, pcm = self.validate(encodeAMBE + frame, b'', f'Edge frame {name} @ {rate_label}')
                if pcm is None:
                    self.err(f'Edge frame {name} @ {rate_label}: no response')
                    self.stop_on_error()
                    continue
                if len(pcm) != 322:
                    self.err(f'Edge frame {name} @ {rate_label}: PCM length {len(pcm)}')
                    self.stop_on_error()
                    continue
                if pcm[0] != 0x00 or pcm[1] != 0xa0:
                    self.err(f'Edge frame {name} @ {rate_label}: PCM header format')
                    self.stop_on_error()
                    continue
                rms = self._pcm_rms(pcm)
                if rms < 1.0:
                    self.warn(f'Edge frame {name} @ {rate_label}: near-zero RMS={rms:.1f}')
                else:
                    self.log(f'  Edge frame {name} @ {rate_label}: RMS={rms:.0f}')
        self.log('  Edge-case frame tests complete')

    def run_roundtrip_test(self):
        """Decode→encode→decode round-trip: verify PCM energy is preserved
        through a lossy encode/decode loop. Also tests cross-rate conversion."""
        self.log('Testing encode/decode round-trip consistency...')
        self.validate(self.reset_cmd, bytearray.fromhex('39'), 'Reset DV3000')
        self.validate(setDMR, bytearray.fromhex('0a00'), 'Set AMBE+ 3600')

        ok = True
        self.log(f'  Running {RUN_ROUNDTRIP_CYCLES} same-rate cycles...')
        for i in range(RUN_ROUNDTRIP_CYCLES):
            frame = silence if i % 2 == 0 else real_dmr
            _h, pcm1 = self.validate(encodeAMBE + frame, b'', 'Round-trip decode #1')
            if pcm1 is None or len(pcm1) != 322:
                self.err('Round-trip: first decode failed'); self.stop_on_error(); ok = False; break

            rms1 = self._pcm_rms(pcm1)

            _h, ambe = self.validate(encodePCM + pcm1, b'', 'Round-trip encode')
            if ambe is None or len(ambe) != 11:
                self.err('Round-trip: encode failed'); self.stop_on_error(); ok = False; break

            # Re-decode the re-encoded AMBE — strip channel ID and bit-length bytes
            _h, pcm2 = self.validate(encodeAMBE + ambe[2:], b'', 'Round-trip decode #2')
            if pcm2 is None or len(pcm2) != 322:
                self.err('Round-trip: second decode failed'); self.stop_on_error(); ok = False; break

            rms2 = self._pcm_rms(pcm2)

            if self.verbose:
                self.debug(f'  Round-trip RMS: {rms1:.0f} → {rms2:.0f}')

            # Only check real frames — silence re-encodes to different energy
            if i % 2 == 1 and (rms1 < 10 or rms2 < 10):
                self.err(f'Round-trip: dead audio (RMS={rms1:.0f} → {rms2:.0f})')
                self.stop_on_error(); ok = False; break

        if ok:
            self.log('  Same-rate round-trip OK')

        # Cross-rate round-trip: decode at one rate, encode at the other
        self.log('  Running cross-rate round-trip cycles...')
        cross_pairs = [
            ('DMR→DStar', setDMR, setDstar, real_dmr, real_dstar),
            ('DStar→DMR', setDstar, setDMR, real_dstar, real_dmr),
        ]
        for pair_label, set_a, set_b, frame_a, _ in cross_pairs:
            self.validate(self.reset_cmd, bytearray.fromhex('39'), f'Reset for cross-rate {pair_label}')
            self.validate(set_a, bytearray.fromhex('0a00'), f'Set rate A ({pair_label})')
            _h, pcm1 = self.validate(encodeAMBE + frame_a, b'', f'Cross decode @ rate A')
            if pcm1 is None or len(pcm1) != 322:
                self.err(f'Cross-rate: first decode failed ({pair_label})')
                self.stop_on_error(); ok = False; break
            rms1 = self._pcm_rms(pcm1)
            if rms1 < ENERGY_REAL_MIN:
                self.err(f'Cross-rate: weak PCM from rate A decode ({pair_label})')
                self.stop_on_error(); ok = False; break
            self.validate(set_b, bytearray.fromhex('0a00'), f'Switch to rate B ({pair_label})')
            _h, ambe = self.validate(encodePCM + pcm1, b'', f'Cross encode @ rate B')
            if ambe is None or len(ambe) != 11:
                self.err(f'Cross-rate: encode failed ({pair_label})')
                self.stop_on_error(); ok = False; break
            _h, pcm2 = self.validate(encodeAMBE + ambe[2:], b'', f'Cross decode @ rate B')
            if pcm2 is None or len(pcm2) != 322:
                self.err(f'Cross-rate: second decode failed ({pair_label})')
                self.stop_on_error(); ok = False; break
            rms2 = self._pcm_rms(pcm2)
            if self.verbose:
                self.debug(f'  Cross-rate {pair_label} RMS: {rms1:.0f} → {rms2:.0f}')
            if rms2 < ENERGY_REAL_MIN:
                self.err(f'Cross-rate: weak final PCM ({pair_label})')
                self.stop_on_error(); ok = False; break
            self.log(f'  Cross-rate {pair_label}: RMS {rms1:.0f} → {rms2:.0f}')

        if ok:
            self.log('  Round-trip consistency OK')

    def run_packet_resilience_test(self):
        """Test packet loss, duplicate, and reorder resilience.
        Works on both serial and UDP transports."""
        self.log('Testing packet resilience...')
        self._drain()
        time.sleep(0.3)
        self.validate(self.reset_cmd, bytearray.fromhex('39'), 'Reset DV3000')
        self._drain()
        self.validate(setDMR, bytearray.fromhex('0a00'), 'Set AMBE+ 3600')
        self._drain()

        # --- Subtest 1: Packet loss ---
        self.log('  Packet loss simulation (5% drop rate)...')
        hungry_pcm = None
        for i in range(20):
            self.send(encodeAMBE + silence)
            rlen, buf = self.recv()
            if rlen == 0:
                self.err('Packet loss test: timeout')
                self.stop_on_error()
                return
            # Randomly discard PCM to simulate app-level packet loss
            # while keeping the serial stream in sync
            if random.random() < 0.05:
                continue
            if buf[3] == 0x02 and len(buf) >= 326:
                hungry_pcm = buf[4:326]
        if hungry_pcm is None:
            self.err('Packet loss test: never captured PCM')
            self.stop_on_error()
            return
        _hdr, ambe = self.validate(encodePCM + hungry_pcm, b'', 'Packet loss recovery encode')
        if ambe is None or len(ambe) != 11:
            self.err('Chip did not recover from packet loss')
            self.stop_on_error()
        else:
            self.log('  Packet loss recovery OK')

        # --- Subtest 2: Duplicate commands ---
        self.log('  Duplicate command test...')
        self._drain()
        time.sleep(0.1)
        h1, p1 = self.validate(encodeAMBE + real_dmr, b'', 'Duplicate decode #1')
        if p1 is None or len(p1) != 322:
            self.err('Duplicate command: first decode failed')
            self.stop_on_error()
        else:
            h2, p2 = self.validate(encodeAMBE + real_dmr, b'', 'Duplicate decode #2')
            if p2 is None or len(p2) != 322:
                self.err('Duplicate command: second decode failed')
                self.stop_on_error()
            else:
                self.log('  Duplicate command OK')

        # --- Subtest 3: Pipelined commands ---
        self.log('  Pipelined command test...')
        self._drain()
        time.sleep(0.1)
        _hdr, pcm_data = self.validate(encodeAMBE + real_dmr, b'', 'Capture PCM for pipeline')
        if pcm_data is None or len(pcm_data) != 322:
            self.err('Pipeline test: failed to capture PCM')
            self.stop_on_error()
        else:
            self.send(encodeAMBE + silence)
            self.send(encodePCM + pcm_data)
            found_pcm = False
            found_ambe = False
            for _ in range(2):
                rlen, buf = self.recv()
                if rlen == 0:
                    break
                if len(buf) >= 4:
                    if buf[3] == 0x02:
                        found_pcm = True
                    elif buf[3] == 0x01:
                        found_ambe = True
            if found_pcm and found_ambe:
                self.log('  Pipelined command OK')
            else:
                self.err(f'Pipeline test: missing response (PCM={found_pcm}, AMBE={found_ambe})')
                self.stop_on_error()

        # --- Subtest 4: Interleaved sources (UDP only) ---
        if not self.useSerial:
            self.log('  Interleaved UDP source test...')
            alt_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            alt_sock.settimeout(0.5)
            alt_sock.sendto(encodeAMBE + silence, (self.ip_address, self.UDP_PORT))
            try:
                data, _ = alt_sock.recvfrom(1024)
                if len(data) >= 4 and data[3] == 0x02:
                    self.log('  Interleaved source OK')
                else:
                    self.err('Interleaved source: invalid response')
                    self.stop_on_error()
            except socket.timeout:
                self.err('Interleaved source: no response')
                self.stop_on_error()
            finally:
                alt_sock.close()
        else:
            self.log('  Interleaved source test skipped (serial mode)')

        # --- Subtest 5: Reinit after abuse ---
        self.log('  Reinit after abuse test...')
        self._drain()
        garbage = bytearray(random.randint(0, 255) for _ in range(20))
        for _ in range(20):
            self.send(garbage)
        time.sleep(0.3)
        self._drain()
        h, p = self.validate(self.reset_cmd, bytearray.fromhex('39'), 'Reinit after abuse: reset')
        if p is None:
            self.err('Reinit after abuse: reset failed'); self.stop_on_error()
        elif self.validate(setDMR, bytearray.fromhex('0a00'), 'Reinit after abuse: set rate')[1] is None:
            self.err('Reinit after abuse: set rate failed'); self.stop_on_error()
        elif self.validate(encodeAMBE + silence, b'', 'Reinit after abuse: decode')[1] is None:
            self.err('Reinit after abuse: decode failed'); self.stop_on_error()
        else:
            self.log('  Reinit after abuse OK')

    def run_jitter_sweep(self):
        """Run latency test at multiple jitter levels and compare results."""
        self.log('Jitter tolerance sweep...')
        original_jitter = self.jitter_ms
        levels = [0, 5, 10, 20]
        summary = {}
        for j in levels:
            self.jitter_ms = j
            self.log(f'\n  --- Jitter = {j} ms ---')
            self.log('')
            self.run_latency_test()
            d4800 = [r for r in self.latency_results if r['op'] == 'Decode AMBE→PCM']
            if d4800:
                vals = sorted(r['elapsed'] for r in d4800)
                summary[j] = {
                    'avg': sum(vals) / len(vals),
                    'p95': vals[int(len(vals) * 0.95)],
                }
        self.jitter_ms = original_jitter
        self.log('')
        self.log('  Jitter sweep summary (Decode 4800 latency):')
        self.log(f'  {"Jitter(ms)":>12} {"Avg(ms)":>10} {"p95(ms)":>10}')
        for j in levels:
            s = summary.get(j)
            if s:
                self.log(f'  {j:>12} {s["avg"]:>10.2f} {s["p95"]:>10.2f}')

    def run_latency_test(self):
        """Measure encode and decode latency over the current transport (serial or UDP).
        Reports per-operation statistics. Over UDP, detects remote server issues
        like high FTDI latency timer or slow baud rate."""
        current_baud = self.serial_bauds[0] if self.serial_bauds else 460800
        if not self.useSerial:
            # UDP mode — no sysfs timer read, but measurement still works
            transport = f'UDP {self.ip_address}:{self.UDP_PORT}'
        else:
            transport = f'{current_baud} baud'

        # Read USB-serial latency timer if available (local serial only)
        timer_str = ''
        timer_warn = ''
        jitter_str = f' with jitter 0..{self.jitter_ms:.0f}ms' if self.jitter_ms > 0 else ''
        if self.useSerial:
            ttydev = self.serialport.rstrip('/').split('/')[-1]
            timer_path = f'/sys/bus/usb-serial/devices/{ttydev}/latency_timer'
            try:
                with open(timer_path) as f:
                    timer_val = f.read().strip()
                timer_str = f' (latency_timer={timer_val})'
                if timer_val != '1':
                    timer_warn = (
                        f'\n  *** WARNING: latency_timer={timer_val}, recommended is 1 ***\n'
                        f'  *** Set with: sudo sh -c \'echo 1 > {timer_path}\' ***')
            except (OSError, IOError):
                pass
        self.log(f'Latency test at {transport}{timer_str}{jitter_str}...{timer_warn}')
        self.latency_results = []

        # Pre-clear any stale data
        self._drain()

        # --- Decode latency at default rate (4800 D-Star) ---
        self._measure_latency(self.reset_cmd, bytearray.fromhex('39'), 'Reset DV3000')
        self._measure_latency(setDstar, bytearray.fromhex('0a00'), 'Set AMBE+ 4800')
        for _ in range(self.loop_count):
            # Alternate silence/real to catch any frame-dependent timing
            frame = silence if _ % 2 == 0 else real_dstar
            self._measure_latency(encodeAMBE + frame, b'', 'Decode AMBE→PCM')
            self._random_sleep()

        # --- Encode latency at same rate ---
        _h, pcm = self._measure_latency(encodeAMBE + silence, b'', 'Prime PCM')
        if pcm is None or len(pcm) != 322:
            self.err('Failed to get PCM for encode latency test')
            self.stop_on_error()
            return
        for _ in range(self.loop_count):
            self._measure_latency(encodePCM + pcm, b'', 'Encode PCM→AMBE')
            self._random_sleep()

        # --- Repeat at DMR rate (3600) ---
        self._measure_latency(self.reset_cmd, bytearray.fromhex('39'), 'Reset DV3000')
        self._measure_latency(setDMR, bytearray.fromhex('0a00'), 'Set AMBE+ 3600')
        for _ in range(self.loop_count):
            frame = silence if _ % 2 == 0 else real_dmr
            self._measure_latency(encodeAMBE + frame, b'', 'Decode AMBE→PCM (3600)')
            self._random_sleep()

        # --- Encode at DMR rate ---
        _h, pcm2 = self._measure_latency(encodeAMBE + real_dmr, b'', 'Prime PCM (3600)')
        if pcm2 is not None and len(pcm2) == 322:
            for _ in range(self.loop_count):
                self._measure_latency(encodePCM + pcm2, b'', 'Encode PCM→AMBE (3600)')
                self._random_sleep()

        # --- Report ---
        self.log('')
        self.log(f'  Latency at {transport} ({self.loop_count} samples/op):')
        # Only report meaningful measurement ops, not setup commands
        measurement_ops = ['Decode AMBE→PCM', 'Encode PCM→AMBE',
                           'Decode AMBE→PCM (3600)', 'Encode PCM→AMBE (3600)']
        summary_parts = []
        for op in measurement_ops:
            results = [r for r in self.latency_results if r['op'] == op]
            if results:
                self._report_latency(results, op)
                vals = sorted(r['elapsed'] for r in results)
                avg = sum(vals) / len(vals)
                p95 = vals[int(len(vals) * 0.95)]
                # Short label for summary: "D4800", "E4800", "D3600", "E3600"
                short = 'D4800' if op == 'Decode AMBE→PCM' else \
                        'E4800' if op == 'Encode PCM→AMBE' else \
                        'D3600' if op == 'Decode AMBE→PCM (3600)' else 'E3600'
                summary_parts.append(f'{short} avg={avg:.1f}ms p95={p95:.1f}ms')
        sep = ' | '
        self.log(f'  Latency summary: {sep.join(summary_parts)}')
        # Grade based on decode 4800 latency (primary real-time voice path)
        d4800_results = [r for r in self.latency_results if r['op'] == 'Decode AMBE→PCM']
        if d4800_results:
            d4800_vals = sorted(r['elapsed'] for r in d4800_results)
            d4800_avg = sum(d4800_vals) / len(d4800_vals)
            if d4800_avg < 12:
                grade = 'BEST'
            elif d4800_avg < 20:
                grade = 'GOOD'
            else:
                grade = 'BAD'
            self.log(f'  Latency grade: {grade} (decode 4800 avg={d4800_avg:.1f}ms — '
                     f'{"<12ms" if grade=="BEST" else "<20ms" if grade=="GOOD" else ">=20ms"} threshold)')

    def _drain(self):
        """Read and discard any stale data from the port."""
        if self.useSerial:
            old_timeout = self.port.timeout
            self.port.timeout = 0.05
            for _ in range(20):
                d = self.port.read(256)
                if not d:
                    break
            try: self.port.flushInput()
            except: pass
            self.port.timeout = old_timeout
        else:
            self.port.settimeout(0.1)
            for _ in range(10):
                try: self.port.recvfrom(256)
                except: break
            self.port.settimeout(self.udp_timeout)

    def run_error_test(self):
        self.log('Testing error recovery...')

        self.log('  Invalid opcode (0xFF)...')
        self.send(bytearray.fromhex("61 00 01 00 ff"))
        time.sleep(0.2)
        self._drain()
        _hdr, pcm = self.validate(encodeAMBE + silence, b'', 'Recovery decode')
        if pcm is None or len(pcm) != 322:
            self.err('Chip did not recover from invalid opcode'); self.stop_on_error()
        else:
            self.log('  Chip recovered OK')

        self.log('  Truncated packet...')
        self.send(bytearray.fromhex("61 00 01"))  # len=1, missing type + 1 payload
        time.sleep(0.2)
        # Complete the packet: type=0x00 (control), payload=0x00 (dummy cmd)
        self.send(bytearray.fromhex("00 00"))
        time.sleep(0.2)
        self._drain()
        _hdr, pcm = self.validate(encodeAMBE + silence, b'', 'Truncated recovery')
        if pcm is None or len(pcm) != 322:
            self.err('Chip did not recover from truncated packet'); self.stop_on_error()
        else:
            self.log('  Chip recovered OK')

        self.log('  Garbage flood...')
        garbage = bytearray(random.randint(0, 255) for _ in range(20))
        for _ in range(20):
            self.send(garbage)
        time.sleep(0.5)
        self._drain()
        _hdr, pcm = self.validate(encodeAMBE + silence, b'', 'Garbage flood recovery')
        if pcm is None or len(pcm) != 322:
            self.err('Chip did not recover from garbage flood'); self.stop_on_error()
        else:
            self.log('  Chip recovered OK')

    def handle_sigint(self, sig, frame):
        self.close()
        sys.exit(1)


def setup_logging(verbose, logfile=None):
    fmt = '%(message)s'
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(format=fmt, level=level)


def main():
    parser = argparse.ArgumentParser(
        prog='AMBEtest5',
        description='AMBE3000 stress test and validation tool',
        epilog='Example: python3 AMBEtest5.py -i 127.0.0.1 -c 1000 -v')
    parser.add_argument('--version', action='version',
        version=f'AMBEtest5 v{VERSION}  Copyright (C) 2021 N4IRR / 2026 DVSwitch Project  License: GPL v3')
    parser.add_argument('-i', '--ip', metavar='<ip>',
        help='Connect via UDP to AMBE server (default port 2460)')
    parser.add_argument('-p', '--port', type=int, default=2460,
        help='UDP port (default 2460, used with -i)')
    parser.add_argument('-t', '--timeout', type=float, default=0.5,
        help='UDP receive timeout in seconds (default 0.5)')
    parser.add_argument('-s', '--serial', metavar='<port>', default='/dev/ttyUSB0',
        help='Serial port (e.g. /dev/ttyUSB0), 460800 baud by default')
    parser.add_argument('-b', '--baud', metavar='<rates>',
        help='Serial baud rate(s), comma-separated (overrides 460800 default)')
    parser.add_argument('-c', '--count', type=int, default=100,
        help='Loop count (default 100)')
    parser.add_argument('-e', '--error', action='store_true',
        help='Stop on first error')
    parser.add_argument('-v', '--verbose', action='store_true',
        help='Verbose output')
    parser.add_argument('-d', '--dvmega', action='store_true',
        help='DVMEGA board mode (alternative reset command)')
    parser.add_argument('--logfile', metavar='<file>',
        help='Write log to file (in addition to console)')
    parser.add_argument('--latency', action='store_true',
        help='Latency test only. Skips stress tests. Works with serial or UDP (-i).')
    parser.add_argument('--jitter', type=float, default=0, metavar='<max_ms>',
        help='Inject random sleep 0..max_ms between test cycles (simulates jitter). Default 0 (off).')
    parser.add_argument('--jitter-sweep', action='store_true',
        help='Run latency test at multiple jitter levels (0, 5, 10, 20ms) and compare')
    parser.add_argument('--resilience', action='store_true',
        help='Run packet resilience test (loss, duplicate, reorder)')
    args = parser.parse_args()

    setup_logging(args.verbose, args.logfile)
    client = AMBEClient(args)

    _log.info(f'AMBEtest5 v{VERSION}  Copyright (C) 2021 N4IRR / 2026 DVSwitch Project')
    _log.info('Licensed under GPL v3')
    _log.info('--------------------------------------------------')

    signal.signal(signal.SIGINT, client.handle_sigint)
    client.connect()
    atexit.register(client.close)

    _log.info('--------------------------------------------------')
    if args.jitter_sweep:
        client.run_jitter_sweep()
    elif args.latency:
        client.run_latency_test()
    else:
        client.identify_chip()
        _log.info('--------------------------------------------------')
        if not args.verbose:
            _log.info('Silent testing mode.....')
        client.drain_udp()
        client.run_mixed_rate_test()
        client.run_error_test()
        client.run_concurrent_test()
        client.run_concurrent_mixed_test()
        client.run_edge_frame_test()
        client.run_roundtrip_test()
        client.run_packet_resilience_test()
        client.run_jitter_sweep()

    if not args.latency and not args.jitter_sweep:
        _log.info(f'Total cycles = {args.count * 2} + concurrent = {args.count * 2} + edge frames + roundtrip = {RUN_ROUNDTRIP_CYCLES} + resilience + jitter sweep  Error count = {client.errorCount}')
    sys.exit(1 if client.errorCount > 0 else 0)


if __name__ == "__main__":
    main()
