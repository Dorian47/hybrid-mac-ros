# SDR/Openwifi Framework Preview

This directory contains the SDR-facing portion of the preview release. It is not
a full Openwifi hardware or driver source tree. Instead, it publishes the pieces
needed to understand and reuse the framework-level TDMA/CSMA integration.

## Included

| Path | Purpose |
| --- | --- |
| `driver/README.md` | Driver hook points and queue/slot conventions |
| `driver/tdma_struct.h` | Small TDMA helper structures used by the driver-side integration |
| `driver/TDMA_driver/misc_module/` | `/dev/my_misc` slot-bitmap interface and userspace helper |
| `driver/TDMA_driver/TDMA_Python_app/` | TDMA server, client, Python API, and experiment helper scripts |
| `user_space/hostapd-openwifi.conf` | CSMA-style AP configuration example |
| `user_space/hostapd-openwifi-edca.conf` | WMM/EDCA AP configuration example |
| `user_space/connect.conf.example` | Minimal open-network STA example |
| `user_space/wpa-connect.conf.example` | Credential template; copy locally before use |

## Slot Bitmap Convention

User-facing scripts expose:

- Session 1 TDMA data slots: logical indices `0..5`.
- Session 2 control slots: logical indices `0..3`.

The driver-side bitmap uses 30 bits:

- Logical session-1 slot `i` maps to driver bit `1 + i`.
- Logical session-2 slot `i` maps to driver bit `20 + i`.

Use the provided Python scripts or `tdma_api.py` instead of writing binary data
directly to `/dev/my_misc`.

## Hardware Scope

Generated bitstreams, boot images, compiled kernel modules, and full Vivado/HDL
projects are intentionally excluded from this preview release. Rebuild board
artifacts locally using the upstream Openwifi/openwifi-HW flow and adapt the hook
points described in `driver/README.md`.

No site-specific SSH targets or credentials are stored in this repository.
