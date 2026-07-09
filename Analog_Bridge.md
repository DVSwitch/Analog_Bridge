# Analog_Bridge

**Analog_Bridge** is a high-performance, real-time audio routing and transcoding engine designed as a core modular building block of the DVSwitch ecosystem. It facilitates the deterministic transfer of voice data between analog sources (using uncompressed PCM via the USRP protocol) and digital networks (using compressed TLV frames). By acting as a software bridge, it allows analog clients like **AllStarLink** or **DVSwitch Mobile** to interoperate seamlessly with digital modes including **DMR, P25, NXDN, D-Star, and System Fusion**.

## Deployment

Download the specific binary for your architecture (armhf, i386, or amd64) and place it in the recommended working directory:

```
/opt/Analog_Bridge/Analog_Bridge
```

## Configuration

Define your operational parameters in the primary initialization file. This file manages audio levels, vocoder selection, and network port assignments:

```
/opt/Analog_Bridge/Analog_Bridge.ini
```

### Vocoder Selection

Configure the system to use either hardware (DV3000/AMBEServer) or software (md380-emu) for digital voice transcoding. Hardware is recommended for production-grade downlink audio:

```ini
[GENERAL]
useEmulator = true
```

### Port Mapping

Implement the "Three-Pipe" architecture by ensuring the `txPort` and `rxPort` in the `[AMBE_AUDIO]` stanza correctly cross-over with your digital bridge partner, such as **MMDVM_Bridge**:

```
AB txPort (31103) <-> Partner rxPort (31103)
```

### Service Management

Control the binary via systemd for persistent operation and automated recovery:

```bash
sudo systemctl start analog_bridge
```

## Features

- **Protocol Support** — Native handling of USRP (8 kHz signed 16-bit PCM) for analog and TLV (Tag-Length-Value) for digital streams.
- **Dynamic Control** — Supports runtime parameter injection (mode changes, tuning, gain adjustments) via the `dvswitch.sh` CLI utility without requiring service restarts.
- **Extensibility** — Includes a powerful macro engine capable of executing external Linux scripts based on received dial strings.
- **Telemetry** — Generates deterministic diagnostic logs in `/var/log/dvswitch/` to monitor PTT transitions and vocoder health.

---

> *AI-Generated DVSwitch Guidance. Use at your own risk.*
