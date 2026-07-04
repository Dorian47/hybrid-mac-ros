# Driver Hook Points

This preview does not publish the full Openwifi-derived driver tree. It documents
the framework-facing hook points used by the hybrid TDMA/CSMA implementation so
that the public TDMA management scripts and ROS bridge have a clear integration
contract.

## Queue Convention

Packets are classified by UDP/TCP port:

- Port `10000`: mission-critical TDMA data queue.
- Port `10001`: management/control queue.
- Other ports: best-effort CSMA queue.

The ROS bridge sends command traffic to UDP port `10000` by default.

## Slot Allocation Interface

`TDMA_server.py`, `TDMA_client.py`, and `tdma_api.py` compute a 30-bit slot
bitmap and write it through `/dev/my_misc`. The kernel-side misc module stores:

- `user_ID`: AP/STA logical node identifier.
- `allo_vec`: 30-bit allocation bitmap.

The Openwifi driver integration reads this bitmap and updates the AP or STA slot
arrays used by the timestamp scheduler.

## Timing And Protection

The full research prototype integrates the following mechanisms into the
Openwifi driver/hardware path:

- Superframe timing with TDMA, CSMA-control, and CSMA-general sections.
- Timestamp scheduling for protected TDMA transmissions.
- Beacon timestamp extension for synchronization.
- PTP-style offset estimation.
- Beacon duration/NAV protection for the TDMA and control sections.

The full driver patch and additional board-specific instructions are deferred to
the archival release after review.
