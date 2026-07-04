#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TDMA Server - AP-side TDMA slot allocation manager.

This script runs on the Openwifi AP. It assigns logical TDMA slots to the AP
and each STA, writes the AP bitmap to the FPGA through /dev/my_misc, and
distributes STA assignments over TCP.

Superframe structure:
    - Session 1 logical slots 0..5: mission-critical TDMA traffic
    - Session 2 logical slots 0..3: control / synchronization traffic
"""

import argparse
import socket
import struct
import subprocess
from typing import Dict, List, Tuple


TOTAL_SLOTS = 30
SESSION1_SLOTS = 6
SESSION2_SLOTS = 4
SESSION1_DRIVER_OFFSET = 1
SESSION2_DRIVER_OFFSET = 20
MISC_DEVICE = "/dev/my_misc"
USERAPP_PATH = "./userapp"


def get_ip_address(ifname: str) -> str:
    """Return the IPv4 address assigned to *ifname* (Linux only)."""
    import fcntl

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(
        fcntl.ioctl(
            sock.fileno(),
            0x8915,
            struct.pack("256s", ifname[:15].encode()),
        )[20:24]
    )


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


def parse_slot_input(prompt: str, max_index: int) -> List[int]:
    """Prompt user for space-separated slot indices."""
    raw = input(prompt)
    if not raw.strip():
        return []
    slots = [int(item) for item in raw.split()]
    for slot in slots:
        if not (0 <= slot < max_index):
            raise ValueError(f"Slot index {slot} out of range [0, {max_index - 1}]")
    return slots


def main() -> None:
    parser = argparse.ArgumentParser(description="TDMA Server - AP-side slot allocation")
    parser.add_argument("--host", default="192.168.13.1",
                        help="Server listen address (default: 192.168.13.1).")
    parser.add_argument("--port", type=int, default=9999,
                        help="Server listen port (default: 9999).")
    args = parser.parse_args()

    print("=" * 60)
    print("  Hybrid TDMA/CSMA - Slot Allocation Server (AP)")
    print("=" * 60)
    print(f"Superframe: {SESSION1_SLOTS} TDMA slots (session 1)"
          f" + {SESSION2_SLOTS} control slots (session 2)")
    print()

    print("[AP Configuration]")
    ap_s1 = parse_slot_input(
        f"  Session-1 slot indices (0..{SESSION1_SLOTS - 1}): ",
        SESSION1_SLOTS,
    )
    ap_s2 = parse_slot_input(
        f"  Session-2 slot indices (0..{SESSION2_SLOTS - 1}): ",
        SESSION2_SLOTS,
    )
    ap_bitmap = slots_to_bitmap(ap_s1, ap_s2)
    print_slot_assignment(ap_s1, ap_s2, label="AP assigned slots:")
    write_to_fpga(node_id=0, bitmap_value=ap_bitmap)

    raw = input("\nNumber of TDMA clients (STAs): ")
    try:
        num_clients = int(raw)
    except ValueError:
        print("ERROR: invalid number")
        return
    if num_clients <= 0:
        print("ERROR: at least 1 client required")
        return

    sta_configs: Dict[int, Tuple[List[int], List[int]]] = {}
    for idx in range(num_clients):
        print(f"\n[STA {idx} Configuration]")
        s1 = parse_slot_input(
            f"  Session-1 slot indices (0..{SESSION1_SLOTS - 1}): ",
            SESSION1_SLOTS,
        )
        s2 = parse_slot_input(
            f"  Session-2 slot indices (0..{SESSION2_SLOTS - 1}): ",
            SESSION2_SLOTS,
        )
        sta_configs[idx] = (s1, s2)
        print_slot_assignment(s1, s2, label=f"STA {idx} assigned slots:")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen(5)

    print(f"\nServer listening on {args.host}:{args.port}")
    print("Waiting for STA connections...")

    next_node_id = 0
    while True:
        conn, addr = server.accept()
        node_id = next_node_id % num_clients
        next_node_id += 1
        print(f"  STA connected: {addr[0]}:{addr[1]} -> assigned ID {node_id}")

        s1_slots, s2_slots = sta_configs[node_id]
        conn.sendall((str(node_id) + "\n").encode())
        conn.sendall((" ".join(str(slot) for slot in s1_slots) + "\n").encode())
        conn.sendall((" ".join(str(slot) for slot in s2_slots) + "\n").encode())
        conn.close()


if __name__ == "__main__":
    main()
