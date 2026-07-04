#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TDMA Client - STA-side TDMA slot receiver.

This script runs on an Openwifi STA. It receives a logical slot assignment from
the AP TDMA server and writes the corresponding driver bitmap to /dev/my_misc.
"""

import argparse
import socket
import subprocess
from typing import List


TOTAL_SLOTS = 30
SESSION1_SLOTS = 6
SESSION2_SLOTS = 4
SESSION1_DRIVER_OFFSET = 1
SESSION2_DRIVER_OFFSET = 20
MISC_DEVICE = "/dev/my_misc"
USERAPP_PATH = "./userapp"


def slots_to_bitmap(session1_slots: List[int], session2_slots: List[int]) -> int:
    """Convert public logical slot indices to the driver's 30-bit bitmap."""
    bitmap = [0] * TOTAL_SLOTS
    for idx in session1_slots:
        if 0 <= idx < SESSION1_SLOTS:
            bitmap[SESSION1_DRIVER_OFFSET + idx] = 1
    for idx in session2_slots:
        if 0 <= idx < SESSION2_SLOTS:
            bitmap[SESSION2_DRIVER_OFFSET + idx] = 1

    value = 0
    for idx, bit in enumerate(bitmap):
        if bit:
            value |= 1 << idx
    return value


def print_slot_assignment(session1_slots: List[int], session2_slots: List[int],
                          label: str = "") -> None:
    """Pretty-print the public logical slot assignment grid."""
    session1 = ["_"] * SESSION1_SLOTS
    session2 = ["_"] * SESSION2_SLOTS
    for idx in session1_slots:
        if 0 <= idx < SESSION1_SLOTS:
            session1[idx] = "*"
    for idx in session2_slots:
        if 0 <= idx < SESSION2_SLOTS:
            session2[idx] = "*"

    if label:
        print(f"\n{label}")
    print("Session 1 (TDMA):    " + "".join(f"| {mark} " for mark in session1) + "|")
    print("Session 2 (Control): " + "".join(f"| {mark} " for mark in session2) + "|")


def write_to_fpga(node_id: int, bitmap_value: int) -> None:
    """Write slot assignment to the FPGA via the misc device driver."""
    result = subprocess.run(
        [USERAPP_PATH, MISC_DEVICE, "1", str(node_id), str(bitmap_value)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"ERROR: FPGA write failed (rc={result.returncode}): {result.stderr.strip()}")


def parse_slot_line(line: str) -> List[int]:
    """Parse a space-separated slot line from the TDMA server."""
    if not line.strip():
        return []
    return [int(item) for item in line.split()]


def main() -> None:
    parser = argparse.ArgumentParser(description="TDMA Client - STA-side slot receiver")
    parser.add_argument("--host", default="192.168.13.1",
                        help="TDMA server address (default: 192.168.13.1).")
    parser.add_argument("--port", type=int, default=9999,
                        help="TDMA server port (default: 9999).")
    args = parser.parse_args()

    print("=" * 60)
    print("  Hybrid TDMA/CSMA - Slot Configuration Client (STA)")
    print("=" * 60)
    print(f"Connecting to TDMA server at {args.host}:{args.port} ...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((args.host, args.port))
    fileobj = sock.makefile("r")

    node_id_line = fileobj.readline()
    s1_line = fileobj.readline()
    s2_line = fileobj.readline()
    sock.close()

    if not node_id_line:
        print("ERROR: empty response from TDMA server")
        return

    node_id = int(node_id_line.strip())
    s1_slots = parse_slot_line(s1_line)
    s2_slots = parse_slot_line(s2_line)
    bitmap_value = slots_to_bitmap(s1_slots, s2_slots)

    print(f"Received node ID: {node_id}")
    print_slot_assignment(s1_slots, s2_slots, label="Received assigned slots:")
    print(f"Driver bitmap value: {bitmap_value}")
    write_to_fpga(node_id=node_id, bitmap_value=bitmap_value)


if __name__ == "__main__":
    main()
