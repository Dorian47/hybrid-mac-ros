#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Multi-STA TDMA Experiment Orchestrator

Automates the multi-STA scalability experiment:
  1. Configure AP with N TDMA slots (one per STA)
  2. SSH into each STA and start TDMA_client.py
  3. Start UDP echo measurement on each STA
  4. Start background iperf3 traffic
  5. Collect per-STA results after test completes
  6. Aggregate metrics

Hardware requirements:
  - 1 Openwifi AP (ZC706 + AD9361)
  - N Openwifi STAs (ZC706 + AD9361), N = 1..3
  - Background traffic generators (commercial STAs via iperf3)

Usage:
    python3 multi_sta_orchestrator.py \
        --ap_host 192.168.10.1 \
        --sta_hosts 192.168.10.2,192.168.10.3,192.168.10.4 \
        --duration 300 \
        --repeats 3 \
        --output_dir results_multi_sta/
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from collections import defaultdict


def ssh_cmd(host, user, cmd, timeout=30):
    """Execute a command on a remote host via SSH."""
    full_cmd = ["ssh", f"{user}@{host}", cmd]
    try:
        result = subprocess.run(
            full_cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        print(f"    [WARN] SSH timeout: {host}: {cmd[:50]}...")
        return "", -1


def scp_file(host, user, remote_path, local_path):
    """Copy a file from remote host via SCP."""
    full_cmd = ["scp", f"{user}@{host}:{remote_path}", local_path]
    try:
        subprocess.run(full_cmd, capture_output=True, timeout=30, check=True)
        return True
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return False


def ssh_cmd_bg(host, user, cmd):
    """Execute a command on remote host in background (non-blocking)."""
    full_cmd = ["ssh", f"{user}@{host}", f"nohup {cmd} > /dev/null 2>&1 &"]
    subprocess.Popen(full_cmd, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


def check_connectivity(host_user_pairs):
    """Verify SSH is reachable on all hosts.

    Args:
        host_user_pairs: list of (host, user) tuples
    """
    print("  Checking connectivity...")
    all_ok = True
    for host, user in host_user_pairs:
        output, rc = ssh_cmd(host, user, "echo ok", timeout=10)
        status = "OK" if output == "ok" else "FAIL"
        print(f"    {user}@{host}: {status}")
        if status == "FAIL":
            all_ok = False
    return all_ok


def configure_ap_slots(ap_host, ap_user, num_stas, openwifi_dir, tdma_app_dir):
    """Configure AP TDMA slots: assign 1 TDMA slot per STA."""
    print(f"  Configuring AP for {num_stas} STA(s)...")
    if num_stas > 6:
        raise ValueError("This demo allocator supports at most 6 TDMA data slots.")

    # Slot assignment strategy:
    # - Slots 0..(num_stas-1) assigned to STAs (one each)
    # - AP gets no TDMA slots in this experiment (receives in STA slots)
    # - Session 2 (control) unchanged
    slot_assignment = {}
    for i in range(num_stas):
        slot_assignment[f"sta_{i}"] = [i]

    # Start TDMA_server.py on AP. It is interactive, so provide the AP and STA
    # slot allocation through stdin before leaving it running in the background.
    server_input = ["", "", str(num_stas)]
    for i in range(num_stas):
        server_input.append(str(i))
        server_input.append("")
    input_blob = "\\n".join(server_input) + "\\n"
    cmd = (
        f"cd {tdma_app_dir} && "
        f"pkill -f TDMA_server.py; "
        f"printf '{input_blob}' | nohup python3 TDMA_server.py "
        f"--host 0.0.0.0 --port 10001 "
        f"> /tmp/tdma_server.log 2>&1 &"
    )
    ssh_cmd(ap_host, ap_user, cmd, timeout=15)
    print(f"  TDMA_server started, expecting {num_stas} client(s)")
    time.sleep(2)
    return slot_assignment


def start_sta_tdma_client(sta_host, sta_user, ap_host, tdma_app_dir):
    """Start TDMA_client.py on a STA to receive slot assignment."""
    cmd = (
        f"cd {tdma_app_dir} && "
        f"python3 TDMA_client.py --host {ap_host} --port 10001"
    )
    print(f"    Starting TDMA_client on {sta_host}...")
    output, rc = ssh_cmd(sta_host, sta_user, cmd, timeout=30)
    return rc == 0


def start_echo_server(ap_host, ap_user, port, tdma_app_dir):
    """Start UDP echo server on AP."""
    cmd = (
        f"cd {tdma_app_dir} && "
        f"pkill -f UDP_echo_server.py; "
        f"nohup python3 UDP_echo_server.py --port {port} "
        f"> /tmp/echo_server.log 2>&1 &"
    )
    ssh_cmd(ap_host, ap_user, cmd, timeout=10)
    print(f"  Echo server started on port {port}")


def start_echo_client(sta_host, sta_user, ap_host, port, duration,
                      deadline_ms, dscp, log_file, tdma_app_dir):
    """Start UDP echo client on a STA (background)."""
    count = int(duration / 0.1)
    cmd = (
        f"cd {tdma_app_dir} && "
        f"nohup python3 UDP_echo_client.py "
        f"--host {ap_host} --port {port} "
        f"--count {count} --interval 0.1 "
        f"--deadline {deadline_ms} "
        f"--dscp {dscp} "
        f"--log {log_file} "
        f"> /tmp/echo_client.log 2>&1 &"
    )
    ssh_cmd(sta_host, sta_user, cmd, timeout=10)
    print(f"    Echo client started on {sta_host}")


def start_background_traffic(bg_hosts, bg_user, target_host, duration):
    """Start iperf3 on background traffic generators."""
    for host in bg_hosts:
        cmd = (
            f"pkill -f iperf3; "
            f"nohup iperf3 -c {target_host} -t {duration + 10} -b 20M "
            f"--logfile /tmp/iperf3.log &"
        )
        ssh_cmd_bg(host, bg_user, cmd)
        print(f"    Background traffic on {host}")
    time.sleep(2)


def stop_background_traffic(bg_hosts, bg_user):
    """Stop iperf3 on all background hosts."""
    for host in bg_hosts:
        ssh_cmd(host, bg_user, "pkill -f iperf3", timeout=10)


def collect_results(sta_hosts, sta_user, output_dir, run_id, tdma_app_dir):
    """Download echo results from all STAs."""
    results = {}
    for i, host in enumerate(sta_hosts):
        remote_file = f"/tmp/echo_sta{i}_{run_id}.csv"
        local_file = os.path.join(output_dir, f"echo_sta{i}_{run_id}.csv")
        ok = scp_file(host, sta_user, remote_file, local_file)
        if ok and os.path.exists(local_file):
            results[f"sta_{i}"] = parse_rtt_csv(local_file)
        else:
            print(f"    [WARN] Could not collect results from {host}")
            results[f"sta_{i}"] = None
    return results


def parse_rtt_csv(filepath):
    """Parse a UDP echo CSV log file and compute statistics."""
    rtts = []
    missed = 0
    total = 0

    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            if "rtt_ms" in row and row["rtt_ms"]:
                try:
                    rtt = float(row["rtt_ms"])
                    rtts.append(rtt)
                except ValueError:
                    missed += 1
            else:
                missed += 1

    if not rtts:
        return {"count": total, "received": 0, "missed": total,
                "miss_rate_pct": 100.0}

    rtts.sort()
    n = len(rtts)
    return {
        "count": total,
        "received": n,
        "missed": missed,
        "miss_rate_pct": missed / total * 100 if total > 0 else 0,
        "mean_rtt_ms": sum(rtts) / n,
        "p50_rtt_ms": rtts[min(n // 2, n - 1)],
        "p95_rtt_ms": rtts[min(int(n * 0.95), n - 1)],
        "p99_rtt_ms": rtts[min(int(n * 0.99), n - 1)],
        "max_rtt_ms": rtts[-1],
        "min_rtt_ms": rtts[0],
    }


def run_experiment(args):
    """Execute the full multi-STA experiment."""
    sta_hosts = args.sta_hosts.split(",")
    num_stas = len(sta_hosts)
    bg_hosts = args.bg_hosts.split(",") if args.bg_hosts else []

    print("=" * 70)
    print("  Multi-STA TDMA Scalability Experiment")
    print("=" * 70)
    print(f"  AP:           {args.ap_user}@{args.ap_host}")
    print(f"  STAs ({num_stas}):     {', '.join(sta_hosts)}")
    print(f"  Background:   {', '.join(bg_hosts) if bg_hosts else 'none'}")
    print(f"  Duration:     {args.duration}s x {args.repeats} repeats")
    print(f"  Deadline:     {args.deadline_ms} ms")
    print("=" * 70)

    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)

    # Check connectivity (use correct user per host type)
    host_user_pairs = [(args.ap_host, args.ap_user)]
    host_user_pairs += [(h, args.sta_user) for h in sta_hosts]
    host_user_pairs += [(h, args.bg_user) for h in bg_hosts]
    if not args.dry_run:
        if not check_connectivity(host_user_pairs):
            print("[ERROR] Not all hosts are reachable. Aborting.")
            sys.exit(1)

    all_results = []

    for repeat in range(1, args.repeats + 1):
        print(f"\n{'='*70}")
        print(f"  REPEAT {repeat}/{args.repeats}")
        print(f"{'='*70}")

        run_id = f"k{num_stas}_r{repeat}"

        if args.dry_run:
            print(f"  [DRY RUN] Would run {args.duration}s test with {num_stas} STAs")
            all_results.append({
                "num_stas": num_stas,
                "repeat": repeat,
                "sta_id": "all",
                "mean_rtt_ms": 0,
                "p99_rtt_ms": 0,
                "miss_rate_pct": 0,
            })
            continue

        # 1. Configure AP TDMA slots
        slot_assignment = configure_ap_slots(
            args.ap_host, args.ap_user, num_stas,
            args.openwifi_dir, args.tdma_app_dir)
        time.sleep(2)

        # 2. Connect each STA to get slot assignment
        for i, host in enumerate(sta_hosts):
            ok = start_sta_tdma_client(host, args.sta_user,
                                       args.ap_host, args.tdma_app_dir)
            if not ok:
                print(f"    [WARN] STA {host} TDMA client failed")
            time.sleep(1)

        # 3. Start echo server on AP
        start_echo_server(args.ap_host, args.ap_user, args.port,
                          args.tdma_app_dir)
        time.sleep(1)

        # 4. Start background traffic
        if bg_hosts:
            start_background_traffic(bg_hosts, args.bg_user,
                                     args.ap_host, args.duration)

        # 5. Start echo clients on all STAs
        for i, host in enumerate(sta_hosts):
            log_file = f"/tmp/echo_sta{i}_{run_id}.csv"
            # Each STA uses a slightly different port to avoid collision
            sta_port = args.port + i
            # Start a separate echo server for each STA port
            if i > 0:
                start_echo_server(args.ap_host, args.ap_user,
                                  sta_port, args.tdma_app_dir)
                time.sleep(2)  # Wait for socket binding before next server
            start_echo_client(host, args.sta_user, args.ap_host,
                              args.port + i, args.duration,
                              args.deadline_ms, args.dscp, log_file,
                              args.tdma_app_dir)

        # 6. Wait for test to complete
        print(f"\n  Waiting {args.duration}s for test to complete...")
        # We can't sleep here in practice, but the SSH calls above
        # launch background processes. We need to wait.
        wait_time = args.duration + 30
        print(f"  (Total wait: {wait_time}s)")
        time.sleep(wait_time)

        # 7. Stop background traffic
        if bg_hosts:
            stop_background_traffic(bg_hosts, args.bg_user)

        # 8. Collect results
        print("  Collecting results...")
        per_sta = collect_results(sta_hosts, args.sta_user,
                                  args.output_dir, run_id,
                                  args.tdma_app_dir)

        # 9. Record results
        for sta_id, stats in per_sta.items():
            if stats:
                all_results.append({
                    "num_stas": num_stas,
                    "repeat": repeat,
                    "sta_id": sta_id,
                    "packets": stats.get("count", 0),
                    "received": stats.get("received", 0),
                    "missed": stats.get("missed", 0),
                    "miss_rate_pct": stats.get("miss_rate_pct", 0),
                    "mean_rtt_ms": stats.get("mean_rtt_ms", 0),
                    "p50_rtt_ms": stats.get("p50_rtt_ms", 0),
                    "p95_rtt_ms": stats.get("p95_rtt_ms", 0),
                    "p99_rtt_ms": stats.get("p99_rtt_ms", 0),
                    "max_rtt_ms": stats.get("max_rtt_ms", 0),
                })

        # 10. Cleanup
        ssh_cmd(args.ap_host, args.ap_user,
                "pkill -f UDP_echo_server.py; pkill -f TDMA_server.py",
                timeout=10)
        for host in sta_hosts:
            ssh_cmd(host, args.sta_user,
                    "pkill -f UDP_echo_client.py", timeout=10)

        time.sleep(5)

    # Save aggregated results
    if all_results:
        output_csv = os.path.join(args.output_dir, "multi_sta_results.csv")
        fieldnames = list(all_results[0].keys())
        with open(output_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_results)
        print(f"\nResults saved to: {output_csv}")

    # Print summary
    print_summary(all_results, num_stas)


def print_summary(results, num_stas):
    """Print experiment summary table."""
    print("\n" + "=" * 70)
    print("  Multi-STA Experiment Summary")
    print("=" * 70)
    print(f"  {'STA':>6s}  {'Mean RTT':>10s}  {'P99 RTT':>10s}  "
          f"{'Miss Rate':>10s}  {'Pkts':>8s}")
    print("-" * 70)

    by_sta = defaultdict(list)
    for r in results:
        by_sta[r.get("sta_id", "all")].append(r)

    for sta_id in sorted(by_sta.keys()):
        runs = by_sta[sta_id]
        avg_rtt = sum(r.get("mean_rtt_ms", 0) for r in runs) / len(runs)
        avg_p99 = sum(r.get("p99_rtt_ms", 0) for r in runs) / len(runs)
        avg_miss = sum(r.get("miss_rate_pct", 0) for r in runs) / len(runs)
        total_pkts = sum(r.get("packets", 0) for r in runs)
        print(f"  {sta_id:>6s}  {avg_rtt:>9.2f}ms  {avg_p99:>9.2f}ms  "
              f"{avg_miss:>9.2f}%  {total_pkts:>8d}")

    # Cross-flow fairness (Jain's fairness index)
    if num_stas > 1:
        throughputs = []
        for sta_id in sorted(by_sta.keys()):
            runs = by_sta[sta_id]
            avg_recv = sum(r.get("received", 0) for r in runs) / len(runs)
            throughputs.append(avg_recv)

        if all(t > 0 for t in throughputs):
            n = len(throughputs)
            sum_t = sum(throughputs)
            sum_t2 = sum(t * t for t in throughputs)
            jain = (sum_t ** 2) / (n * sum_t2)
            print(f"\n  Jain's Fairness Index: {jain:.4f}")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Multi-STA TDMA scalability experiment orchestrator")

    # SSH targets
    parser.add_argument("--ap_host", type=str, default="192.168.10.1",
                        help="AP IP address")
    parser.add_argument("--ap_user", type=str, default="root",
                        help="AP SSH username")
    parser.add_argument("--sta_hosts", type=str,
                        default="192.168.10.2",
                        help="Comma-separated STA IP addresses")
    parser.add_argument("--sta_user", type=str, default="root",
                        help="STA SSH username")
    parser.add_argument("--bg_hosts", type=str, default="",
                        help="Comma-separated background traffic hosts")
    parser.add_argument("--bg_user", type=str, default="root",
                        help="Background hosts SSH username")

    # Experiment parameters
    parser.add_argument("--duration", type=int, default=300,
                        help="Test duration per repeat in seconds (default: 300)")
    parser.add_argument("--repeats", type=int, default=3,
                        help="Number of repeats (default: 3)")
    parser.add_argument("--port", type=int, default=10000,
                        help="Base UDP echo port (default: 10000)")
    parser.add_argument("--deadline_ms", type=float, default=100.0,
                        help="Deadline threshold in ms (default: 100)")
    parser.add_argument("--dscp", type=int, default=46,
                        help="DSCP for mission-critical packets (default: 46)")

    # Paths on remote hosts
    parser.add_argument("--openwifi_dir", type=str,
                        default="/root/openwifi",
                        help="Openwifi install directory on AP/STAs")
    parser.add_argument("--tdma_app_dir", type=str,
                        default="/root/openwifi/driver/TDMA_driver/TDMA_Python_app",
                        help="TDMA Python app directory on remote hosts")

    # Output
    parser.add_argument("--output_dir", type=str,
                        default="results_multi_sta",
                        help="Output directory for results")
    parser.add_argument("--dry_run", action="store_true",
                        help="Print plan without executing")

    args = parser.parse_args()
    run_experiment(args)


if __name__ == "__main__":
    main()
