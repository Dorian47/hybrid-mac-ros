# Third-Party Notices

This repository is a cleaned framework preview built on top of open-source SDR,
Wi-Fi, Linux driver, and ROS components. The notes below are provided to make
attribution explicit for public release.

## Openwifi-Derived Components

The selected `sdr_fpga/` interfaces, user-space tooling, configuration
templates, and documentation assets are derived from or designed to work with:

- Openwifi: https://github.com/open-sdr/openwifi
- openwifi-JIT: https://github.com/Leo-Cheung-CUHK/openwifi-JIT
- openwifi-HW: https://github.com/Leo-Cheung-CUHK/openwifi-hw

The top-level license is AGPL-3.0 to match the upstream Openwifi licensing
context used by this artifact. Some low-level interface files also retain
upstream author and license metadata from Linux, Analog Devices, Xilinx, and
Openwifi sources.

## ROS Simulation Components

The `ros_integration/ros_simulation/catkin_ws_src/` directory contains ROS/Gazebo packages used as an integration example for robot-control evaluation. Some files are adapted from common ROS/PurePursuit and vehicle-model examples. Please preserve source comments and license notices when reusing or modifying these components.

## Generated And Board-Specific Artifacts

Generated FPGA bitstreams, boot images, compiled kernel modules, packet traces, ROS bags, and raw experiment logs are intentionally excluded from the public artifact. Users should rebuild these artifacts for their own boards and local RF environment.
