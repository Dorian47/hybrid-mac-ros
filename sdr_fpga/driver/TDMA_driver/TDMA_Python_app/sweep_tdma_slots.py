#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TDMA Slot Sweep Experiment Runner

Automates the tradeoff experiment: sweep N_TDMA from 0 to MAX and
for each configuration:
  1. Reconfigure the AP TDMA slot allocation via SSH
  2. Run the UDP echo measurement for a specified duration
  3. Record non-critical throughput and mission-critical deadline miss rate
  4. Save measured tradeoff data for downstream plotting

Hardware requirements:
  - Openwifi AP (ZC706 + AD9361) accessible via SSH
  - At least 1 Openwifi STA (mission-critical traffic)
  - Background traffic generators (iperf3 on commercial STAs)

Usage:
    python3 sweep_tdma_slots.py \
        --ap_host 192.168.10.1 \
        --ap_user root \
        --sta_host 192.168.10.2 \
        --sta_user root \
        --n_tdma_values 0 1 2 3 4 5 \
        --duration 300 \
        --repeats 3 \
        --output sweep_results.csv
"""

import argparse
import csv
import os
import subprocess
import sys
import time

SESSION1_DRIVER_OFFSET = 1


def ssh_cmd(host, user, cmd, timeout=30):
    """Execute a command on a remote host via SSH."""
    full_cmd = ["ssh", f"{user}@{host}", cmd]
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        print(f"  [WARN] SSH command timed out: {cmd[:60]}...")
        return "", -1


def scp_file(host, user, remote_path, local_path):
    """Copy a file from remote host via SCP."""
    full_cmd = ["scp", f"{user}@{host}:{remote_path}", local_path]
    try:
        subprocess.run(full_cmd, capture_output=True, timeout=30, check=True)
        return True
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
        print(f"  [WARN] SCP failed: {e}")
        return False


def logical_slots_to_driver_bitmap(slots):
    """Map logical session-1 slots 0..5 to the driver's allocation bitmap."""
    value = 0
    for slot in slots:
        if not 0 <= slot < 6:
            raise ValueError(f"TDMA slot {slot} is outside the supported 0..5 range")
        value |= 1 << (SESSION1_DRIVER_OFFSET + slot)
    return value


def configure_tdma_slots(ap_host, ap_user, n_tdma, openwifi_dir):
    """Reconfigure the AP with n_tdma TDMA slots.

    This modifies the FPGA slot allocation:
      - Slots 0..(n_tdma-1) -> TDMA for mission-critical
      - Remaining session-1 slots -> unused
      - Session 2 (control) -> unchanged
    """
    print(f"  Configuring AP with N_TDMA = {n_tdma}...")

    # Build slot assignment string for userapp
    # AP gets even-numbered slots, STA gets odd-numbered slots
    ap_slots = []
    sta_slots = []
    for i in range(n_tdma):
        if i % 2 == 0:
            ap_slots.append(str(i))
        else:
            sta_slots.append(str(i))

    # If no STA slots assigned, give slot 0 to STA for n_tdma=1
    if n_tdma == 1:
        sta_slots = ["0"]
        ap_slots = []
    elif n_tdma == 0:
        sta_slots = []
        ap_slots = []

    ap_slot_str = ",".join(ap_slots) if ap_slots else "none"
    sta_slot_str = ",".join(sta_slots) if sta_slots else "none"

    # Write the config via the misc device driver and apply to FPGA
    bitmap = logical_slots_to_driver_bitmap([int(s) for s in ap_slots])
    config_cmd = (
        f"cd {openwifi_dir}/driver/TDMA_driver/misc_module && "
        f"./userapp /dev/my_misc 1 0 {bitmap} && "
        f"echo 'TDMA config applied: bitmap={bitmap}'"
    )

    output, rc = ssh_cmd(ap_host, ap_user, config_cmd)
    if rc != 0:
        print(f"  [ERROR] Failed to configure TDMA: rc={rc}")
        return False

    print(f"  AP configured: AP={ap_slot_str}, STA={sta_slot_str}")
    return True


def run_background_traffic(bg_hosts, bg_user, ap_host, duration):
    """Start iperf3 background traffic on commercial STAs."""
    pids = []
    for host in bg_hosts:
        cmd = (
            f"nohup iperf3 -c {ap_host} -t {duration} -b 20M "
            f"--logfile /tmp/iperf3_bg.log &"
        )
        ssh_cmd(host, bg_user, cmd, timeout=10)
        pids.append(host)
        print(f"  Started background traffic on {host}")
    return pids


def stop_background_traffic(bg_hosts, bg_user):
    """Stop iperf3 on all background hosts."""
    for host in bg_hosts:
        ssh_cmd(host, bg_user, "pkill -f iperf3", timeout=10)


def run_echo_measurement(sta_host, sta_user, ap_host, port, duration,
                         deadline_ms, dscp, output_file):
    """Run UDP echo client on STA for RTT measurement."""
    cmd = (
        f"cd /tmp && python3 UDP_echo_client.py "
        f"--host {ap_host} --port {port} "
        f"--count {int(duration / 0.1)} "
        f"--interval 0.1 "
        f"--deadline {deadline_ms} "
        f"--dscp {dscp} "
        f"--log {output_file}"
    )
    print(f"  Running echo measurement on STA ({duration}s)...")
    output, rc = ssh_cmd(sta_host, sta_user, cmd, timeout=int(duration + 60))
    return output, rc


def parse_echo_results(sta_host, sta_user, remote_file, local_file):
    """Download and parse UDP echo results."""
    scp_file(sta_host, sta_user, remote_file, local_file)

    if not os.path.exists(local_file):
        return None

    rtts = []
    with open(local_file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if "rtt_ms" in row and row["rtt_ms"]:
                try:
                    rtts.append(float(row["rtt_ms"]))
                except ValueError:
                    pass

    if not rtts:
        return None

    rtts.sort()
    n = len(rtts)
    return {
        "count": n,
        "mean_rtt_ms": sum(rtts) / n,
        "p50_rtt_ms": rtts[min(n // 2, n - 1)],
        "p99_rtt_ms": rtts[min(int(n * 0.99), n - 1)],
        "max_rtt_ms": rtts[-1],
        "min_rtt_ms": rtts[0],
    }


def run_sweep(args):
    """Execute the full sweep experiment."""
    results = []

    print("=" * 70)
    print("  TDMA Slot Sweep Experiment")
    print("=" * 70)
    print(f"  AP:       {args.ap_user}@{args.ap_host}")
    print(f"  STA:      {args.sta_user}@{args.sta_host}")
    print(f"  N_TDMA:   {args.n_tdma_values}")
    print(f"  Duration: {args.duration}s x {args.repeats} repeats")
    print("=" * 70)

    bg_hosts = args.bg_hosts.split(",") if args.bg_hosts else []

    for n_tdma in args.n_tdma_values:
        print(f"\n--- N_TDMA = {n_tdma} ---")

        # 1. Configure AP
        if not args.dry_run:
            configure_tdma_slots(args.ap_host, args.ap_user, n_tdma,
                                 args.openwifi_dir)
            time.sleep(3)  # Wait for config to take effect

        for repeat in range(1, args.repeats + 1):
            print(f"\n  Repeat {repeat}/{args.repeats}:")
            run_id = f"n{n_tdma}_r{repeat}"

            if args.dry_run:
                print(f"  [DRY RUN] Would run measurement for {args.duration}s")
                results.append({
                    "n_tdma": n_tdma,
                    "repeat": repeat,
                    "mean_rtt_ms": 0,
                    "p50_rtt_ms": 0,
                    "p99_rtt_ms": 0,
                    "max_rtt_ms": 0,
                    "miss_rate_pct": 0,
                })
                continue

            # 2. Start background traffic
            if bg_hosts:
                run_background_traffic(bg_hosts, args.bg_user,
                                       args.ap_host, args.duration + 10)
                time.sleep(2)

            # 3. Run echo measurement
            remote_log = f"/tmp/echo_{run_id}.csv"
            local_log = f"echo_{run_id}.csv"
            output, rc = run_echo_measurement(
                args.sta_host, args.sta_user, args.ap_host,
                args.port, args.duration, args.deadline_ms,
                args.dscp, remote_log
            )

            # Parse missed deadline from output
            miss_rate = 0.0
            if output:
                for line in output.split("\n"):
                    if "Missed deadline" in line:
                        # Parse: "Missed deadline rate: X.XX%"
                        try:
                            miss_rate = float(
                                line.split(":")[-1].strip().rstrip("%"))
                        except ValueError:
                            pass

            # 4. Download and parse results
            stats = parse_echo_results(args.sta_host, args.sta_user,
                                       remote_log, local_log)
            if stats is None:
                print(f"  [WARN] Failed to download/parse results for {run_id}")

            # 5. Stop background traffic
            if bg_hosts:
                stop_background_traffic(bg_hosts, args.bg_user)

            if stats:
                results.append({
                    "n_tdma": n_tdma,
                    "repeat": repeat,
                    "mean_rtt_ms": stats["mean_rtt_ms"],
                    "p50_rtt_ms": stats["p50_rtt_ms"],
                    "p99_rtt_ms": stats["p99_rtt_ms"],
                    "max_rtt_ms": stats["max_rtt_ms"],
                    "miss_rate_pct": miss_rate,
                    "packet_count": stats["count"],
                })
            else:
                print(f"  [WARN] No results for run {run_id}")

            time.sleep(5)

    # Save results
    if results and args.output:
        fieldnames = list(results[0].keys())
        with open(args.output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        print(f"\nResults saved to: {args.output}")

    # Print summary
    print("\n" + "=" * 70)
    print("  Sweep Summary")
    print("=" * 70)
    print(f"  {'N_TDMA':>6s}  {'Mean RTT':>10s}  {'P99 RTT':>10s}  {'Miss Rate':>10s}")
    print("-" * 70)

    from collections import defaultdict
    by_ntdma = defaultdict(list)
    for r in results:
        by_ntdma[r["n_tdma"]].append(r)

    for n_tdma in sorted(by_ntdma.keys()):
        runs = by_ntdma[n_tdma]
        avg_rtt = sum(r["mean_rtt_ms"] for r in runs) / len(runs)
        avg_p99 = sum(r["p99_rtt_ms"] for r in runs) / len(runs)
        avg_miss = sum(r["miss_rate_pct"] for r in runs) / len(runs)
        print(f"  {n_tdma:>6d}  {avg_rtt:>9.2f}ms  {avg_p99:>9.2f}ms  "
              f"{avg_miss:>9.2f}%")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="TDMA slot sweep experiment for tradeoff analysis")

    # SSH targets
    parser.add_argument("--ap_host", type=str, default="192.168.10.1",
                        help="AP IP address")
    parser.add_argument("--ap_user", type=str, default="root",
                        help="AP SSH username")
    parser.add_argument("--sta_host", type=str, default="192.168.10.2",
                        help="STA IP address")
    parser.add_argument("--sta_user", type=str, default="root",
                        help="STA SSH username")
    parser.add_argument("--bg_hosts", type=str, default="",
                        help="Comma-separated background traffic hosts")
    parser.add_argument("--bg_user", type=str, default="root",
                        help="Background hosts SSH username")

    # Experiment parameters
    parser.add_argument("--n_tdma_values", type=int, nargs="+",
                        default=[0, 1, 2, 3, 4, 5],
                        help="N_TDMA values to sweep (default: 0 1 2 3 4 5)")
    parser.add_argument("--duration", type=int, default=300,
                        help="Test duration per config in seconds (default: 300)")
    parser.add_argument("--repeats", type=int, default=3,
                        help="Number of repeats per config (default: 3)")
    parser.add_argument("--port", type=int, default=10000,
                        help="UDP echo port (default: 10000)")
    parser.add_argument("--deadline_ms", type=float, default=100.0,
                        help="Deadline threshold in ms (default: 100)")
    parser.add_argument("--dscp", type=int, default=46,
                        help="DSCP value for echo packets (default: 46 = AC_VO)")

    # Paths
    parser.add_argument("--openwifi_dir", type=str,
                        default="/root/openwifi",
                        help="Openwifi install directory on AP")

    # Output
    parser.add_argument("--output", type=str, default="sweep_results.csv",
                        help="Output CSV file")
    parser.add_argument("--dry_run", action="store_true",
                        help="Print commands without executing")

    args = parser.parse_args()
    run_sweep(args)


if __name__ == "__main__":
    main()
