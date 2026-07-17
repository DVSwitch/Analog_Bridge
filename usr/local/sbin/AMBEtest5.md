# AMBEtest5 — AMBE3000 Dongle Tester

**Version 6.0** | DVSwitch Project | Based on original work by Mike Zingman N4IRR

---

## Quick Start

### Test your USB dongle
```bash
python3 AMBEtest5.py -s /dev/ttyUSB0 -c 100
```

### Test a network AMBE server
```bash
python3 AMBEtest5.py -i 192.168.1.100 -c 100
```

That runs all nine tests. No extra flags needed. If your dongle is on a
different port, change the name (like `/dev/ttyUSB1`).

---

## The USB Latency Timer — Easy to Miss, Easy to Fix

Audio quality problems almost always come down to one setting: the **latency
timer** on your USB dongle's FTDI chip.

This setting controls how long the chip waits before sending data to your
computer. The factory default is **16 milliseconds**. That means every
single operation — decode, encode, everything — gets 16ms of delay before
the data even reaches the AMBE chip.

Voice frames arrive every **20 milliseconds**. If just getting data into
the chip takes 16ms, you only have 4ms left to do the actual work. One
slow USB poll and you miss the frame. Audio stutters, packets pile up,
and your audio quality falls apart.

**You want this set to 1 millisecond.**

### How to Check It

Run any test and look at the first line of the latency report:

```
Latency test at 460800 baud (latency_timer=1)...
```

If it says `latency_timer=1`, you're good. If it says anything else, you
get a warning with the exact command to fix it.

### How to Fix It

The tool already shows the exact command for your dongle in the warning
message — just copy and paste it:

```
  *** WARNING: latency_timer=16, recommended is 1 ***
  *** Set with: sudo sh -c 'echo 1 > /sys/bus/usb-serial/devices/ttyUSB0/latency_timer' ***
```

If you want to run it manually:

```bash
sudo sh -c 'echo 1 > /sys/bus/usb-serial/devices/ttyUSB0/latency_timer'
```

Replace `ttyUSB0` with the name your dongle shows up as. To find it:

```bash
ls /dev/ttyUSB*
```

It's usually `ttyUSB0` if you have one dongle, `ttyUSB1` for the second,
and so on. The change takes effect immediately and lasts until you unplug
the dongle or reboot.

To make it permanent across reboots, add the command to `/etc/rc.local`
or your startup scripts.

### What the Difference Sounds Like

We tested every timer setting from 1 to 16. The result is dead simple:
each step up adds about 1ms of delay.

```
Timer | Decode D-Star | Encode D-Star | Grade
------+---------------+---------------+-------
   1  |    10.0 ms    |    12.0 ms    | BEST
   2  |    10.7 ms    |    12.0 ms    | BEST
   3  |    11.2 ms    |    12.0 ms    | BEST
   4  |    12.7 ms    |    12.0 ms    | GOOD
   5  |    13.7 ms    |    15.0 ms    | GOOD
   6  |    15.0 ms    |    12.0 ms    | GOOD
   7  |    16.0 ms    |    14.0 ms    | GOOD
   8  |    16.7 ms    |    16.0 ms    | GOOD
   9  |    17.8 ms    |    18.0 ms    | GOOD
  10  |    19.0 ms    |    20.0 ms    | GOOD
  11  |    19.9 ms    |    21.5 ms    | BAD
  12  |    20.8 ms    |    12.0 ms    | BAD
  13  |    21.8 ms    |    13.0 ms    | BAD
  14  |    22.8 ms    |    14.0 ms    | BAD
  15  |    24.0 ms    |    15.0 ms    | BAD
  16  |    24.9 ms    |    16.0 ms    | BAD
```

At the factory default of 16, decode takes 25ms. That's 5ms past your
20ms voice frame. Every decode pushes into the next frame. Over a few
seconds, that becomes audible problems — choppy audio, missed packets,
delayed transmissions.

At 1, decode takes 10ms. You've got room for network jitter, USB
scheduling, and everything else.

---

## Latency Test & Grading

The latency test runs automatically as part of every normal test run.
It measures how long data takes to go through the dongle.

### What It Times

| Operation | Direction |
|---|---|
| Decode D-Star (4800 bps) | AMBE frame → audio |
| Encode D-Star (4800 bps) | audio → AMBE frame |
| Decode DMR (3600 bps) | AMBE frame → audio |
| Encode DMR (3600 bps) | audio → AMBE frame |

### The Grade

The tool grades your dongle on the D-Star decode speed — that's the path
voice takes in a real system:

| Grade | Threshold | What it means |
|---|---|---|
| **BEST** | Under 12ms | Plenty of room — even with network delays |
| **GOOD** | 12 to 19ms | Fits in one frame — tight but usable |
| **BAD** | 20ms or more | Too slow — you'll get audio delays |

### What the Numbers Mean

| Stat | What it tells you |
|---|---|
| **Avg** | What you'll normally see |
| **p95** | The worst 5% of trips |
| **Max** | The slowest trip |
| **Jitter** | How much the timing varies |

A small number next to each stat also shows what percentage of samples
line up with USB frame boundaries. If that number is high (80-100%),
your dongle is operating normally — USB timing is the bottleneck, not
the AMBE chip.

### Test Over the Network

The latency test works with remote AMBE servers too:

```bash
python3 AMBEtest5.py -i 192.168.1.100 -c 200 --latency -t 1
```

We tested through [marrold/AMBEServer](https://github.com/marrold/AMBEServer)
and the numbers came back the same — the network path adds essentially zero
delay over a local connection.

If a remote server comes back BAD, the problem is almost certainly that
dongle's latency timer setting, not the network.

### Run Latency By Itself

```bash
python3 AMBEtest5.py -s /dev/ttyUSB0 -c 200 --latency
```

---

## What Each Test Does

The tool runs all of these by default. Here's what they check and why.

### 1. Chip Identification
Asks the chip "who are you?" and checks it's an AMBE3000 series. Prints
the model and firmware version.

### 2. Mixed Rate Stress Test
Randomly switches between D-Star (4800 bps) and DMR (3600 bps) rates
between every cycle. Each cycle decodes an AMBE frame to audio, checks
the audio is real and not zeros, then encodes it back.

The chip can respond with valid headers and correct packet lengths but
still produce silence. This test catches that.

### 3. Error Recovery
Throws bad data at the chip three ways — an invalid command, a truncated
packet, and 400 bytes of random garbage — and checks the chip still
responds after each one.

### 4. Concurrent Test
Sends a decode and an encode command at exactly the same time. Proves
both vocoder channels work in parallel without interfering.

### 5. Concurrent with Rate Switching
Like the concurrent test, but also switches between D-Star and DMR
rates mid-stream while both channels are busy. This is what happens
in a real multi-mode radio system.

### 6. Edge-Case AMBE Frames
Feeds the chip six unusual 9-byte patterns at both rates:

| Pattern | What it is |
|---|---|
| All zeros | Nothing — but the vocoder should still produce non-zero audio |
| All ones | Opposite of silence |
| Alternating bits | Every other bit flips — a digital worst case |
| Walking one | A single 1 bit marches across the frame |
| Maximum volume | Every sample at the loudest possible value |
| Minimum volume | Every sample at the quietest possible value |

None of these should crash the chip.

### 7. Round-Trip Check
Decodes audio, encodes it back, decodes again. Now also does this
cross-rate — decodes DMR then re-encodes at D-Star, and vice versa.

### 8. Resilience Test
Simulates real-world glitches: drops 5% of packets, sends duplicate
commands, sends commands back-to-back without waiting, and floods the
chip with garbage then does a full reset to prove it comes back.

### 9. Jitter Sweep
Latency test at four jitter levels (0, 5, 10, 20ms) so you can see
how network timing noise affects your numbers. The chip handles all
of these with zero errors.

---

## Options

### `--jitter <max_ms>`

Adds a random delay (0 to max_ms) between operations, simulating
network jitter:

```bash
python3 AMBEtest5.py -s /dev/ttyUSB0 -c 200 --jitter 20
```

### `--jitter-sweep`

Runs latency at 0, 5, 10, and 20ms jitter and shows a comparison.
Already part of the normal run, but you can run it standalone:

```bash
python3 AMBEtest5.py -s /dev/ttyUSB0 -c 100 --jitter-sweep
```

### `-d` DVMEGA Mode
Different reset command for DVMEGA boards.

### `-b <baud>`
Serial speed. Default is 460800. Older boards may need 230400:
```bash
python3 AMBEtest5.py -s /dev/ttyUSB0 -b 230400 -c 100
```

### `-e` Stop on First Error
Stop immediately when any test fails.

### `-v` Verbose Output
Shows raw bytes and audio energy level (RMS) for each frame. Useful
for debugging but noisy.

### `--logfile <file>`
Save output to a file as well as the screen:
```bash
python3 AMBEtest5.py -i 192.168.1.100 -c 500 --logfile /tmp/test.log
```

### Progress During Long Tests
Every 10% shows a progress line with cycle count and rate switches:
```
  100/1000 cycles, 51 rate switches
```

---

## Requirements

- Python 3
- `pySerial` (`pip install pyserial`) for USB dongles
- Network access to reach a remote AMBE server (if testing one)

---

## License

GPL v3 — same as the original AMBEtest4 by Mike Zingman N4IRR.
