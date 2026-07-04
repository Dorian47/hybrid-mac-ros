# Release Status

This repository is a preliminary framework release for a manuscript currently
under review.

The goal of this preview is to make the framework structure, public interfaces,
and integration examples visible without publishing the full private experiment
workspace. It is not a complete artifact for reproducing every figure or numeric
result in the manuscript.

## Included In This Preview

- TDMA server/client scripts and Python API.
- Slot bitmap interface for `/dev/my_misc`.
- Openwifi AP/STA and EDCA configuration templates.
- ROS `/cmd_vel` bridge to the TDMA data queue.
- Compact PurePursuit ROS integration example.
- Architecture, citation, license, and third-party attribution notes.

## Deferred Until The Archival Release

- Full paper-specific reproducibility instructions.
- Additional hardware setup notes.
- Expanded experiment automation and analysis scripts.
- Final citation metadata after publication.
- Any updates requested during peer review.

## Excluded By Design

- Raw packet traces, ROS bags, robot logs, and generated datasets.
- Credentials, private network targets, and lab-specific deployment details.
- Generated FPGA bitstreams, boot images, and compiled kernel modules.
- Full upstream Openwifi/openwifi-HW/AD9361/Xilinx source trees.
