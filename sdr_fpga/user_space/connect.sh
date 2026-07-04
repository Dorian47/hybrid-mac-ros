#!/bin/bash
# PREVIEW: This script requires the full Openwifi upstream build
# (sdrctl, wgd.sh, kernel modules).  See ../driver/README.md
# and https://github.com/open-sdr/openwifi for the complete toolchain.
echo "[PREVIEW] This script requires the upstream Openwifi build." >&2
echo "[PREVIEW] See sdr_fpga/driver/README.md for details." >&2
exit 1

PROG=sdr
rmmod $PROG

insmod misc.ko 

killall hostapd
killall webfsd

service network-manager stop
./wgd.sh 
iwconfig sdr0 mode managed
ifconfig sdr0 up
iwconfig sdr0 essid openwifi
./sdrctl dev sdr0 set reg drv_rx 7 2
