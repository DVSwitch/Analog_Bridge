### Analog_Bridge: Application Overview, Deployment, and Configuration Guide

Analog_Bridge is a core component of the DVSwitch ecosystem. It acts as a bridge that enables interoperability between traditional analog voice sources (such as AllStarLink/ASL) and various digital voice networks (DMR, D-STAR, P25, NXDN, YSF).

---

### 1. Application Overview

Analog_Bridge functions by encapsulating audio and signaling information into a packet protocol called **USRP** (Universal Software Radio Peripheral). It translates analog PCM audio into a format suitable for transmission across digital networks and vice-versa, preserving metadata between these dissimilar environments.

* **Key Capabilities:**
* **Cross-Mode Bridging:** Connects analog systems to DMR, P25, D-STAR, etc.
* **USRP Protocol Support:** Serves as the central point for USRP audio sources.
* **Dynamic Control:** Allows on-the-fly adjustments to talk groups, modes, and audio levels via command-line utilities.



---

### 2. Deployment

Analog_Bridge is typically deployed as part of the `dvswitch-server` suite on Linux-based systems (optimized for Raspberry Pi).

* **Standard Installation:** If you are using a DVSwitch-ready image or adding it to an existing Debian-based installation, the installation is handled via the DVSwitch repository:
```bash
# Ensure repository is added and system is updated
sudo apt-get update
sudo apt-get install analog-bridge

```


* **Service Management:** Analog_Bridge runs as a system service. You can manage it using standard systemd commands:
* `systemctl status analog_bridge`
* `systemctl start analog_bridge`
* `systemctl stop analog_bridge`
* `systemctl restart analog_bridge`



---

### 3. Configuration

The primary configuration for the application is found in `/opt/Analog_Bridge/Analog_Bridge.ini`.

#### A. Key Configuration Sections

* **[USRP]:** Defines network sockets for communication with other components.
* `address`: Usually `127.0.0.1` for local inter-process communication.
* `txPort` / `rxPort`: Ports designated for USRP packet exchange.


* **[AMBE_AUDIO]:** Configures audio processing and mode selection.
* `ambeMode`: Specifies the target digital format (e.g., `DMR`, `P25`, `DSTAR`, `YSFW`).
* `txTg`: Sets the transmit Talk Group used by default.
* `aslAudio` / `dmrAudio`: Defines gain levels (e.g., `AUDIO_UNITY` for no change, or specific gain factors).



#### B. Dynamic Configuration & Management

Rather than manually editing the `.ini` file for every minor change, you should utilize the provided `dvswitch.sh` utility found in `/opt/MMDVM_Bridge/`:

* **Change Digital Mode:** `sudo ./dvswitch.sh mode DMR`
* **Change Talk Group:** `sudo ./dvswitch.sh tune 3100`
* **Query Information:** The script can also query status, verify port owners, and update specific configuration values without requiring a full file edit.

#### C. Audio Level Tuning

To maintain high-quality audio across the bridge, you may need to adjust gain levels within `Analog_Bridge.ini`:

* `agcGain`: Controls the gain for the AGC filter (if used).
* `dmrGain`: Adjusts the factor for audio flowing from the ASL side to the DMR side (0.0–1.0).

---

### 4. Troubleshooting Checklist

* **Connectivity:** If you see "NoNet" on client applications (like hUC), verify that `Analog_Bridge` is running (`systemctl status analog_bridge`) and that the `usrpTxPort` and `usrpRxPort` match the values in your client configuration.
* **Permissions:** Ensure you have root privileges when modifying configuration files or executing management scripts.
* **Logs:** Monitor `/var/log/dvswitch/` for service-specific errors if bridging is failing or audio is not passing.
