# Architecture

## Overview

```text
ROS application
  |
  | /cmd_vel
  v
tdma_bridge.py
  |
  | UDP port 10000
  v
Openwifi network stack
  |
  v
Openwifi driver TDMA hook
  |
  v
FPGA / RF front end
```

The TDMA management path is separate from the data path:

```text
TDMA_server.py  ->  TDMA_client.py
      |                 |
      v                 v
   userapp          userapp
      |                 |
      v                 v
   /dev/my_misc     /dev/my_misc
      |                 |
      v                 v
   driver slot allocation state
```

## Superframe Model

The implementation exposes two configurable logical sections:

- Session 1: mission-critical TDMA data slots, logical indices `0..5`.
- Session 2: control/synchronization slots, logical indices `0..3`.

The user-space tools convert those logical indices into the 30-bit bitmap used
by the Linux driver integration. Driver-side hook points scan bits `1..19` for
session 1 and bits `20..29` for session 2.

## Packet Classification

The driver-facing convention classifies packets by TCP/UDP port:

- Port `10000`: mission-critical data queue.
- Port `10001`: management/control queue.
- Other ports: best-effort CSMA queue.

The ROS bridge uses UDP port `10000` by default, so command packets enter the TDMA data queue through the normal Linux network stack.

## Synchronization and Protection

The full research prototype includes timestamp scheduling, beacon timestamp
extension, PTP offset estimation, and beacon duration/NAV-style protection
logic. This preview documents the hook points and public interfaces, while the
full board-specific driver patch is deferred to the archival release after
review.

## Reproducibility Scope

This repository provides the preview framework and experiment helpers. It does
not contain raw traces, ROS bags, private testbed logs, full driver patches, or
generated board artifacts. Numeric results from the paper require matching
hardware, traffic configuration, RF conditions, and measurement scripts.
