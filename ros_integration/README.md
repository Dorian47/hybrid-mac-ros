# ROS Integration

This directory contains the ROS-facing portion of the preview release.

## Included

- `tdma_bridge/`: subscribes to `/cmd_vel` and sends compact command payloads to
  the TDMA data queue over UDP port `10000`.
- `ros_simulation/catkin_ws_src/purepursuit/`: compact PurePursuit integration
  scaffold for path-tracking experiments.

Large Gazebo model assets, raw ROS bags, robot logs, and paper-specific
measurement data are intentionally excluded from this preview.
