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
#
#   Defaults to 460800 baud. Older boards (230400) can be selected with -b.
#
#   Copyright (C) 2021 Mike Zingman N4IRR
#   Copyright (C) 2026 DVSwitch KAT
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
#
###############################################################################

VERSION = "5.0"

import serial
import sys
import time
import random
import signal
import socket
import atexit
import argparse
import logging

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
# DV3K reset/channel-set commands for AMBE3000.
# DV3K packet: 0x61 <len_hi> <len_lo> <type> <payload bytes + optional 0x2f xor>
#   len may or may not include the 0x2f terminator + xor byte
#   (different firmware variants interpret it differently).
#   Both forms below are verified working with their respective hardware.
RESET_DEFAULT = bytearray.fromhex("61 00 07 00 34 05 00 00 0F 00 00")
RESET_DVMEGA = bytearray.fromhex("61 00 06 00 34 05 00 00 0F 00 00")


class AMBEClient:
    def __init__(self, args):
        self.port = None
        self.useSerial = not bool(args.ip)
        self.ip_address = args.ip or "127.0.0.1"
        self.UDP_PORT = args.port
        self.udp_timeout = args.timeout
        self.loop_count = args.count
        self.shouldStopOnError = args.error
        self.verbose = args.verbose
        self.loose = args.loose
        self.reset_cmd = RESET_DVMEGA if args.dvmega else RESET_DEFAULT
        self.serialport = args.serial
        self.serial_bauds = [int(b) for b in args.baud.split(',')] if args.baud else None
        self.errorCount = 0

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
        if self.port and self.useSerial:
            try:
                self.port.close()
            except OSError:
                pass
            self.port = None
        if self.port and not self.useSerial:
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
                if 'p' in dir() and p:
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
        self.log('Mixed rate encode/decode stress test...')
        self.validate(self.reset_cmd, bytearray.fromhex('39'), 'Reset DV3000')
        current = '4800'
        self.validate(setDstar, bytearray.fromhex('0a00'), 'Set AMBE+ 4800')
        switches = 0
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
            if not self.loose:
                if pcm[0] != 0x00 or pcm[1] != 0xa0:
                    self.err('PCM channel/bits'); self.stop_on_error(); continue
            if hdr[3] != 0x02:
                self.err(f'PCM type {hdr[3]}'); self.stop_on_error(); continue
            hdr, ambe = self.validate(encodePCM + pcm, b'', 'Encode PCM')
            if ambe is None:
                self.err('Encode PCM returned nothing'); self.stop_on_error(); continue
            if len(ambe) != 11:
                self.err(f'Encode AMBE length {len(ambe)}'); self.stop_on_error(); continue
            if not self.loose:
                if hdr[3] != 0x01:
                    self.err(f'AMBE type {hdr[3]}'); self.stop_on_error(); continue
                if ambe[0] != 0x01:
                    self.err('AMBE channel ID'); self.stop_on_error(); continue
                if ambe[1] != 0x48:
                    self.err(f'AMBE bit length {ambe[1]}'); self.stop_on_error(); continue
        self.log(f'  {total} cycles, {switches} rate switches')

    def run_concurrent_test(self):
        self.log('Testing concurrent encode/decode...')
        self.validate(self.reset_cmd, bytearray.fromhex('39'), 'Reset DV3000')
        self.validate(setDMR, bytearray.fromhex('0a00'), 'Set AMBE+ 3600')
        _hdr, pcm = self.validate(encodeAMBE + silence, b'', 'Prime PCM')
        if pcm is None or len(pcm) != 322:
            self.err('Failed to capture PCM for concurrent test')
            self.stop_on_error()
            return
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
            if not self.loose:
                if pp[0] != 0x00 or pp[1] != 0xa0:
                    self.err('Concurrent PCM format'); self.stop_on_error(); break
                if ap[0] != 0x01 or ap[1] != 0x48:
                    self.err('Concurrent AMBE format'); self.stop_on_error(); break

    def _drain(self):
        """Read and discard any stale data from the port."""
        if self.useSerial:
            try: self.port.flushInput()
            except: pass
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
    parser.add_argument('-l', '--loose', action='store_true',
        help='Loose validation (skip strict byte-pattern checks)')
    parser.add_argument('-d', '--dvmega', action='store_true',
        help='DVMEGA board mode (alternative reset command)')
    parser.add_argument('--logfile', metavar='<file>',
        help='Write log to file (in addition to console)')
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
    client.identify_chip()

    _log.info('--------------------------------------------------')
    if not args.verbose:
        _log.info('Silent testing mode.....')
    client.drain_udp()
    client.run_mixed_rate_test()
    client.run_error_test()
    client.run_concurrent_test()

    _log.info(f'Total cycles = {args.count * 2} + concurrent = {args.count}  Error count = {client.errorCount}')
    sys.exit(1 if client.errorCount > 0 else 0)


if __name__ == "__main__":
    main()
