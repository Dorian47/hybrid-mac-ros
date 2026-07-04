#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UDP Echo Client - Round-trip latency measurement tool

Sends periodic UDP packets to the echo server and measures RTT.
Supports configurable packet size, interval, and DSCP marking
for EDCA priority experiments.

Usage:
    python3 UDP_echo_client.py --host 192.168.13.1 --port 10000
    python3 UDP_echo_client.py --host 192.168.13.1 --port 10000 --dscp 46 --interval 0.1
    python3 UDP_echo_client.py --host 192.168.13.1 --port 10000 --count 10000 --log rtt_results.csv
"""

import argparse
import csv
import socket
import struct
import time


def set_dscp(sock, dscp_value):
    """Set DSCP field on the socket for EDCA priority mapping.

    DSCP-to-802.11e mapping (common):
        DSCP 0  (BE)  -> AC_BE (Best Effort)
        DSCP 26 (AF31)-> AC_VI (Video)
        DSCP 34 (AF41)-> AC_VI (Video)
        DSCP 46 (EF)  -> AC_VO (Voice) - use for mission-critical
    """
    # TOS field = DSCP << 2
    tos = dscp_value << 2
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, tos)


def main():
    parser = argparse.ArgumentParser(description="UDP Echo Client - RTT measurement")
    parser.add_argument("--host", default="192.168.13.1",
                        help="Echo server address (default: 192.168.13.1)")
    parser.add_argument("--port", type=int, default=10000,
                        help="Echo server port (default: 10000)")
    parser.add_argument("--count", type=int, default=10000,
                        help="Number of echo requests (default: 10000)")
    parser.add_argument("--interval", type=float, default=0.1,
                        help="Interval between packets in seconds (default: 0.1)")
    parser.add_argument("--payload", type=int, default=25,
                        help="Payload size in bytes (default: 25, matches mission-critical)")
    parser.add_argument("--dscp", type=int, default=0,
                        help="DSCP value for EDCA priority (0=BE, 46=EF/Voice)")
    parser.add_argument("--timeout", type=float, default=1.0,
                        help="Socket recv timeout in seconds (default: 1.0)")
    parser.add_argument("--log", default="rtt_results.csv",
                        help="Output CSV file for RTT results")
    parser.add_argument("--deadline", type=float, default=0.0,
                        help="Deadline in seconds; if >0, report missed-deadline rate")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(args.timeout)

    if args.dscp > 0:
        set_dscp(sock, args.dscp)
        print(f"DSCP set to {args.dscp} (TOS=0x{args.dscp << 2:02X})")

    server_addr = (args.host, args.port)
    print(f"Sending {args.count} echo requests to {args.host}:{args.port}")
    print(f"  Payload: {args.payload}B, Interval: {args.interval}s"
          f", DSCP: {args.dscp}")
    if args.deadline > 0:
        print(f"  Deadline: {args.deadline*1000:.1f} ms")

    results = []
    sent = 0
    received = 0
    missed_deadline = 0

    try:
        for seq in range(args.count):
            # Build payload: [seq_number (4B)] + [send_timestamp (8B)] + padding
            send_time = time.time()
            payload = struct.pack("!Id", seq, send_time)
            if args.payload > len(payload):
                payload += b'\x00' * (args.payload - len(payload))

            sock.sendto(payload, server_addr)
            sent += 1

            try:
                data, _ = sock.recvfrom(1024)
                recv_time = time.time()
                rtt = recv_time - send_time

                received += 1
                if args.deadline > 0 and rtt > args.deadline:
                    missed_deadline += 1

                results.append({
                    "seq": seq,
                    "send_time": send_time,
                    "rtt_ms": rtt * 1000,
                    "missed": 1 if (args.deadline > 0 and rtt > args.deadline) else 0
                })
            except socket.timeout:
                results.append({
                    "seq": seq,
                    "send_time": send_time,
                    "rtt_ms": -1,  # timeout
                    "missed": 1
                })
                if args.deadline > 0:
                    missed_deadline += 1

            if args.interval > 0:
                # Compensate for processing time
                elapsed = time.time() - send_time
                sleep_time = args.interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

            if (seq + 1) % 1000 == 0:
                print(f"  Progress: {seq + 1}/{args.count}")

    except KeyboardInterrupt:
        print(f"\nInterrupted after {sent} packets")

    # Write results to CSV
    with open(args.log, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["seq", "send_time", "rtt_ms", "missed"])
        writer.writeheader()
        writer.writerows(results)

    # Print summary
    valid_rtts = [r["rtt_ms"] for r in results if r["rtt_ms"] > 0]
    lost = sent - received
    print(f"\n{'='*50}")
    print(f"  Results Summary")
    print(f"{'='*50}")
    print(f"  Sent:     {sent}")
    print(f"  Received: {received}")
    print(f"  Lost:     {lost} ({100*lost/max(sent,1):.2f}%)")
    if valid_rtts:
        print(f"  RTT min:  {min(valid_rtts):.3f} ms")
        print(f"  RTT avg:  {sum(valid_rtts)/len(valid_rtts):.3f} ms")
        print(f"  RTT max:  {max(valid_rtts):.3f} ms")
    if args.deadline > 0:
        print(f"  Deadline: {args.deadline*1000:.1f} ms")
        print(f"  Missed:   {missed_deadline} ({100*missed_deadline/max(sent,1):.2f}%)")
    print(f"  Log saved to: {args.log}")

    sock.close()


if __name__ == "__main__":
    main()
