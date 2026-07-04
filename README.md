# Hybrid TDMA/CSMA MAC for Robotic Communication

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)

This repository is a preliminary framework release for the manuscript:

> Deadline-Aware MAC Design for Real-Time Robotic Communication on Open-Source WiFi SDR

The manuscript is currently under review. This public repository is intentionally
released as a lightweight framework preview rather than a complete reproduction
package. An earlier preprint is available on [arXiv:2509.06119](https://arxiv.org/abs/2509.06119).

## Release Status

This preview includes the cleaned core structure needed to understand and extend
the framework:

- TDMA slot-management scripts and Python API.
- The `/dev/my_misc` userspace/kernel interface used for slot bitmap updates.
- Openwifi AP/STA and WMM/EDCA configuration templates.
- A ROS-to-UDP bridge for mapping `/cmd_vel` traffic to the TDMA data queue.
- A compact PurePursuit ROS example used as an integration scaffold.
- Architecture and attribution notes.

The full experimental artifact will be expanded after the review process. Planned
additions include more detailed hardware setup notes, fuller reproducibility
scripts, release metadata, and any paper-specific updates required after review.

## Scope

This is a lightweight framework preview. It publishes the core TDMA/CSMA
interfaces, configuration templates, and integration examples needed to
understand the architecture. Full experimental artifacts, driver patches, and
board-specific build flows are deferred until the archival release — see
[docs/release_status.md](docs/release_status.md) for details.

For the SDR hardware baseline, use the upstream Openwifi toolchain (see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).

## Repository Structure

```text
.
  docs/
    architecture.md
    release_status.md
  sdr_fpga/
    README.md
    setup.sh
    user_space/
      hostapd-openwifi.conf
      hostapd-openwifi-edca.conf
      connect.conf.example
      wpa-connect.conf.example
    driver/
      README.md
      tdma_struct.h
      TDMA_driver/
        misc_module/
        TDMA_Python_app/
  ros_integration/
    README.md
    tdma_bridge/
    ros_simulation/catkin_ws_src/purepursuit/
  LICENSE
  CITATION.cff
  THIRD_PARTY_NOTICES.md
```

## Quick Start

### 1. Configure local paths

Edit `sdr_fpga/setup.sh` for your local Openwifi and Xilinx/Vivado paths:

```bash
cd sdr_fpga
source setup.sh
```

### 2. Configure TDMA slots

On the AP:

```bash
cd sdr_fpga/driver/TDMA_driver/TDMA_Python_app
python3 TDMA_server.py --host 192.168.13.1 --port 9999
```

On each STA:

```bash
cd sdr_fpga/driver/TDMA_driver/TDMA_Python_app
python3 TDMA_client.py --host 192.168.13.1 --port 9999
```

The public slot indices are compact logical indices: session 1 uses `0..5`,
and session 2 uses `0..3`. The scripts convert these to the 30-bit bitmap used
by the driver-side `/dev/my_misc` interface.

### 3. Use the Python API

```python
from tdma_api import TDMAClient

client = TDMAClient(server_host="192.168.13.1")
client.connect_and_configure()

print(client.node_id)
print([slot.slot_id for slot in client.slots])
print(f"bitmap=0x{client.bitmap_value():08x}")
```

### 4. Bridge ROS commands

The driver-facing convention maps UDP/TCP port `10000` to mission-critical TDMA
data traffic. The bridge subscribes to `/cmd_vel` and sends compact command
payloads to that port:

```bash
python3 ros_integration/tdma_bridge/tdma_bridge.py \
  --sdr-ip 192.168.13.1 \
  --sdr-port 9999 \
  --tx-host 192.168.13.1 \
  --tx-port 10000 \
  --robot-id 1 \
  --use-ros
```

## Relationship To The Paper

This repository supports the paper narrative at the framework level:

- Hybrid TDMA/CSMA scheduling is exposed through slot-management APIs and driver
  hook documentation.
- TDMA allocation is represented by a compact bitmap written through
  `/dev/my_misc`.
- EDCA/CSMA configuration templates are included for baseline-style experiments.
- ROS integration code shows how mission-critical command traffic is routed into
  the TDMA data queue.
- Experiment helper scripts show how similar measurements can be automated on a
  user-provided Openwifi testbed.

The exact numerical results in the paper depend on the original hardware setup,
RF environment, traffic generators, ROS/Gazebo version, and logged measurements.
Those environment-specific artifacts are intentionally not included in this
preview release.

## Security And Privacy

- Wi-Fi credential files are provided only as `.example` templates.
- Deployment scripts require users to pass their own local host and board values.
- IP addresses such as `192.168.13.1` and `192.168.10.1` are private testbed
  defaults, not public endpoints.
- This repository does not include private credentials, personal datasets, raw
  experiment traces, or robot logs.

## Citation

If you use this framework, please cite the arXiv preprint:

```bibtex
@misc{xu2025hybridtdmacsma,
  title={A Hybrid TDMA/CSMA Protocol for Time-Sensitive Traffic in Robot Applications},
  author={Xu, Shiqi and Zhang, Lihao and Du, Yuyang and Yang, Qun and Liew, Soung Chang},
  year={2025},
  eprint={2509.06119},
  archivePrefix={arXiv},
  primaryClass={cs.RO},
  url={https://arxiv.org/abs/2509.06119},
}
```

Final publication metadata will be updated after the review process.

## License

AGPL-3.0, following the upstream Openwifi licensing context. See [LICENSE](LICENSE).
