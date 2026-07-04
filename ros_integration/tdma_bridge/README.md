# TDMA ROS Bridge

`tdma_bridge.py` connects ROS control commands to the TDMA data queue exposed by the Openwifi driver.

## Data Path

```text
/cmd_vel
  -> tdma_bridge.py
  -> UDP destination port 10000
  -> Openwifi driver data queue
  -> TDMA scheduled transmission
```

The bridge does not write command payloads to `/dev/my_misc`. That device is reserved for slot allocation by `TDMA_server.py`, `TDMA_client.py`, and `userapp`.

## Usage

Start the TDMA slot server separately, then run the bridge on a ROS node:

```bash
python3 tdma_bridge.py \
  --sdr-ip 192.168.13.1 \
  --sdr-port 9999 \
  --tx-host 192.168.13.1 \
  --tx-port 10000 \
  --robot-id 1 \
  --use-ros
```

For a non-ROS smoke test, use `--no-ros`. In that mode the bridge connects to the TDMA management server and starts its loop, but it does not expose a TCP command server.

## Statistics

On shutdown the bridge prints:

- `tx_total`: commands dequeued for transmission
- `tx_success`: UDP sends completed without local socket error
- `missed_deadline`: queued commands that expired before transmission
- `queued_dropped`: reserved for queue-overflow accounting

## Notes

The bridge is an integration example for ROS command traffic. The exact over-the-air scheduling is handled by the SDR driver and hardware.
