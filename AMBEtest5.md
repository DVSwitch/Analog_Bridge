# AMBEtest5 — AMBE3000 Stress Test & Validation Tool

**Version 5.0** | DVSwitch Project | Based on original work by Mike Zingman N4IRR

---

## Overview

Exercises AMBE3000 series vocoder chips over serial (USB dongle) or UDP (network AMBE server). Originally written by Mike N4IRR as `AMBEtest4.py`, this version is a class-based rewrite with comprehensive test stages and improved error handling.

What it does:
1. **Chip Identification** — Queries PRODID and VERSTRING.
2. **Mixed Rate Encode/Decode** — Randomly switches between AMBE+ 4800 (D-Star rate) and AMBE+ 3600 (DMR rate) mid-stream, stressing rate switching under load.
3. **Error Recovery** — Sends invalid opcodes, truncated packets, and garbage data, verifying the chip recovers without crashing.
4. **Concurrent Encode+Decode** — Exercises both vocoder cores simultaneously.

---

## What Changed from v4

| Feature | AMBEtest4 (original) | AMBEtest5 |
|---|---|---|
| PRODID / VERSTRING | Commented out (byte compares) | Validates `AMBE3000` prefix, prints product & version |
| Rate switching | None | Random AMBE+ 4800/3600 switching (D-Star/DMR rates) |
| Loop count | Hardcoded 1000 per mode | `-c N` option, mixed cycles with random rate switching |
| Serial baud detection | Hardcoded 230400, `-n` flag | Default 460800, configurable via `-b` |
| DTR/RTS handling | None | Handles dongles that need a reset pulse |
| DVMEGA support | Separate fork | `-d` flag uses DVMEGA magic number |
| UDP port | Hardcoded 2460 | `-p` option (default 2460) |
| UDP timeout | Hardcoded 2s | `-t` option (default 0.5s) |
| Loose validation | None | `-l` flag skips strict byte-pattern checks |
| Logging | `print()` | `logging` module, `--logfile <file>` support |
| Serial reads | `port.read(n)` (short-read risk) | `_read_exactly(n)` loops until all bytes arrive |
| Stale packet handling | None | 3-attempt retry with stale detection |
| Architecture | Global functions + module globals | `AMBEClient` class, zero module state |
| Argument parsing | `getopt` (deprecated) | `argparse` with auto-generated `--help` |
| Exit code | Always 0 / `quit()` | 0 on success, 1 on errors (`sys.exit`) |
| Signal handling | None | SIGINT handler cleans up port before exit |
| Port cleanup | Manual | `atexit` + signal handler guarantee cleanup |

---

## Test Stages

1. **Chip Identification** — Queries PRODID (0x30) and VERSTRING (0x31). Validates the chip is an AMBE3000 series (accepts both R and F variants).

2. **Mixed Rate Encode/Decode** — Starts at AMBE+ 4800 (D-Star rate), then randomly switches between 4800 and 3600 (DMR rate) between encode/decode cycles. Alternates between silence and real AMBE frames (from MMDVM-Transcoder test vectors) for richer coefficient coverage. Each cycle decodes an AMBE frame to PCM, validates the format, then encodes it back to AMBE. Reports total cycles and rate switch count.

3. **Error Recovery** — Sends an invalid opcode (0xFF), a truncated packet, and 20 random garbage bytes. After each, verifies the chip still decodes a valid AMBE frame — proving it recovers without crashing or desyncing.

4. **Concurrent Encode+Decode** — Sends a decode and encode command at the same time, exercising both vocoder cores simultaneously. Matches responses by packet type (order-agnostic for UDP).

---

## Usage

```
usage: AMBEtest5 [-h] [--version] [-i <ip>] [-p PORT] [-t TIMEOUT]
                 [-s <port>] [-b <rates>] [-c COUNT] [-e] [-v] [-l] [-d]
                 [--logfile <file>]

AMBE3000 stress test and validation tool

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  -i <ip>               Connect via UDP to AMBE server (default port 2460)
  -p PORT               UDP port (default 2460, used with -i)
  -t TIMEOUT            UDP receive timeout in seconds (default 0.5)
  -s <port>  Serial port (e.g. /dev/ttyUSB0), 460800 baud by default
  -b <rates> Serial baud rate(s), comma-separated (overrides 460800 default)
  -c COUNT              Loop count (default 100)
  -e                    Stop on first error
  -v                    Verbose output
  -l                    Loose validation (skip strict byte-pattern checks)
  -d                    DVMEGA board mode (alternative reset command)
  --logfile <file>      Write log to file (in addition to console)
```

### Examples

```bash
# Test a dongle on USB serial
python3 AMBEtest5.py -s /dev/ttyUSB0 -c 100 -v

# Test a network AMBE server
python3 AMBEtest5.py -i 127.0.0.1 -c 1000

# Test with custom port and longer timeout
python3 AMBEtest5.py -i 127.0.0.1 -p 2460 -t 1 -c 1000

# Loose mode (skip strict byte checks)
python3 AMBEtest5.py -s /dev/ttyUSB0 -l -c 100

# Custom baud rates
python3 AMBEtest5.py -s /dev/ttyUSB0 -b 115200,460800 -c 100

# Log to file for CI
python3 AMBEtest5.py -i 127.0.0.1 -c 1000 --logfile /tmp/test.log

# DVMEGA board
python3 AMBEtest5.py -s /dev/ttyUSB0 -d -c 100
```

### Sample Output

```
AMBEtest5 v5.0  Copyright (C) 2021 N4IRR / 2026 DVSwitch Project
Licensed under GPL v3
--------------------------------------------------
Serial connection on /dev/ttyUSB1 at 460800 baud
Serial port parameters:
  Port name:     /dev/ttyUSB1
  Baudrate:      460800
  Byte size:     8
  Parity:        N
  Stop bits:     1
--------------------------------------------------
Identifying chip...
Product ID: AMBE3000R
Version: V120.E100.XXXX.C106.G514.R009.B0010411.C0020208
--------------------------------------------------
Silent testing mode.....
Mixed rate encode/decode stress test...
  400 cycles, 210 rate switches
Testing error recovery...
  Invalid opcode (0xFF)...
  Chip recovered OK
  Truncated packet...
  Chip recovered OK
  Garbage flood...
  Chip recovered OK
Testing concurrent encode/decode...
Total cycles = 400 + concurrent = 200  Error count = 0
```

---

## Requirements

- Python 3
- `pySerial` for serial connections
- Network access (UDP) for remote AMBE server testing

## License

GPL v3 — same as the original AMBEtest4 by Mike Zingman N4IRR.
