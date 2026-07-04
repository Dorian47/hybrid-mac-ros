#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UDP Echo Server - Round-trip latency measurement tool

Listens for incoming UDP packets and echoes them back immediately.
Used to measure end-to-end round-trip time (RTT) under different
MAC protocol configurations (CSMA / EDCA / Hybrid TDMA-CSMA).

Usage:
    python3 UDP_echo_server.py --port 10000
    python3 UDP_echo_server.py --host 0.0.0.0 --port 10000 --log rtt_log.csv
"""

import argparse
import csv
import os
import socket
import struct
import time


def main():
    parser = argparse.ArgumentParser(description="UDP Echo Server")
    parser.add_argument("--host", default="0.0.0.0",
                        help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=10000,
                        help="Listen port (default: 10000)")
    parser.add_argument("--log", default="",
                        help="CSV log file for received timestamps (optional)")
    parser.add_argument("--bufsize", type=int, default=1024,
                        help="Receive buffer size in bytes (default: 1024)")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))
    print(f"UDP Echo Server listening on {args.host}:{args.port}")

    log_file = None
    csv_writer = None
    if args.log:
        log_file = open(args.log, "w", newline="")
        csv_writer = csv.writer(log_file)
        csv_writer.writerow(["seq", "recv_time_s", "payload_size"])

    seq = 0
    try:
        while True:
            data, addr = sock.recvfrom(args.bufsize)
            recv_time = time.time()
            # Echo back immediately
            sock.sendto(data, addr)
            seq += 1

            if csv_writer is not None:
                csv_writer.writerow([seq, f"{recv_time:.6f}", len(data)])

            if seq % 1000 == 0:
                print(f"  Echoed {seq} packets (last from {addr[0]}:{addr[1]})")
    except KeyboardInterrupt:
        print(f"\nServer stopped. Total packets echoed: {seq}")
    finally:
        if log_file is not None:
            log_file.close()
        sock.close()


if __name__ == "__main__":
    main()
