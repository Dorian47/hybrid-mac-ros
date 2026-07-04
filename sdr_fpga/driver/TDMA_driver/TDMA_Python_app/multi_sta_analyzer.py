#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Multi-STA Results Analyzer

Aggregates per-STA RTT CSV files from the multi-STA orchestrator,
computes cross-configuration comparison metrics, and generates:
  1. Per-configuration summary table (1-STA vs 2-STA vs 3-STA)
  2. Per-flow fairness analysis (Jain's index)
  3. LaTeX table fragment for manuscript-style reporting
  4. CDF data for delay distribution plotting

Usage:
    python3 multi_sta_analyzer.py \
        --results_dir results_multi_sta/ \
        --output metrics_summary.csv

    # Analyze multiple configurations (run orchestrator with different --sta_hosts)
    python3 multi_sta_analyzer.py \
        --results_dirs results_1sta/ results_2sta/ results_3sta/ \
        --output scalability_comparison.csv \
        --latex
"""

import argparse
import csv
import glob
import os
import re
import sys
from collections import defaultdict


def parse_rtt_csv(filepath):
    """Parse a single RTT CSV file and return raw RTT values."""
    rtts = []
    missed = 0
    total = 0
    deadline_misses = 0
    deadline_ms = None

    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            if "rtt_ms" in row and row["rtt_ms"]:
                try:
                    rtt = float(row["rtt_ms"])
                    rtts.append(rtt)
                    # Check deadline if available
                    if "deadline_met" in row:
                        if row["deadline_met"].lower() in ("false", "0", "no"):
                            deadline_misses += 1
                except ValueError:
                    missed += 1
            else:
                missed += 1

    return {
        "rtts": rtts,
        "total": total,
        "received": len(rtts),
        "missed": missed,
        "deadline_misses": deadline_misses,
    }


def compute_stats(rtts, deadline_ms=100.0):
    """Compute comprehensive statistics from RTT values."""
    if not rtts:
        return {
            "count": 0, "mean": 0, "std": 0,
            "min": 0, "p25": 0, "p50": 0, "p75": 0,
            "p95": 0, "p99": 0, "max": 0,
            "deadline_miss_count": 0, "deadline_miss_rate": 0,
        }

    rtts_sorted = sorted(rtts)
    n = len(rtts_sorted)
    mean = sum(rtts_sorted) / n
    variance = sum((x - mean) ** 2 for x in rtts_sorted) / n
    std = variance ** 0.5

    # Count deadline misses
    deadline_misses = sum(1 for r in rtts_sorted if r > deadline_ms)

    def percentile_idx(p):
        return min(int(n * p), n - 1)

    return {
        "count": n,
        "mean": mean,
        "std": std,
        "min": rtts_sorted[0],
        "p25": rtts_sorted[percentile_idx(0.25)],
        "p50": rtts_sorted[percentile_idx(0.50)],
        "p75": rtts_sorted[percentile_idx(0.75)],
        "p95": rtts_sorted[percentile_idx(0.95)],
        "p99": rtts_sorted[percentile_idx(0.99)],
        "max": rtts_sorted[-1],
        "deadline_miss_count": deadline_misses,
        "deadline_miss_rate": deadline_misses / n * 100 if n > 0 else 0,
    }


def compute_jain_fairness(throughputs):
    """Compute Jain's fairness index from a list of throughput values.

    Returns float in [0, 1], or None if undefined (all zero or empty).
    """
    if not throughputs:
        return None
    if all(t == 0 for t in throughputs):
        return None  # Undefined: no traffic received by any flow
    n = len(throughputs)
    sum_t = sum(throughputs)
    sum_t2 = sum(t * t for t in throughputs)
    return (sum_t ** 2) / (n * sum_t2) if sum_t2 > 0 else None


def generate_cdf_data(rtts, output_file, num_points=1000):
    """Generate CDF data points for plotting."""
    if not rtts:
        return

    rtts_sorted = sorted(rtts)
    n = len(rtts_sorted)

    with open(output_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["rtt_ms", "cdf"])
        for i, rtt in enumerate(rtts_sorted):
            cdf = (i + 1) / n
            writer.writerow([f"{rtt:.3f}", f"{cdf:.6f}"])


def analyze_single_dir(results_dir, deadline_ms=100.0):
    """Analyze all echo CSV files in a single results directory."""
    csv_files = glob.glob(os.path.join(results_dir, "echo_sta*.csv"))
    if not csv_files:
        # Also try the aggregated file
        agg_file = os.path.join(results_dir, "multi_sta_results.csv")
        if os.path.exists(agg_file):
            return analyze_aggregated_csv(agg_file, deadline_ms)
        print(f"  [WARN] No echo_sta*.csv files in {results_dir}")
        return None

    # Group by STA and repeat
    sta_data = defaultdict(list)  # sta_id -> [rtts, rtts, ...]
    # Match filenames like: echo_sta0_k3_r1.csv, echo_sta1_r2.csv, echo_sta0.csv
    pattern = re.compile(r'echo_(sta\d+)', re.IGNORECASE)
    for filepath in sorted(csv_files):
        filename = os.path.basename(filepath)
        m = pattern.match(filename)
        sta_id = m.group(1) if m else "unknown"

        data = parse_rtt_csv(filepath)
        sta_data[sta_id].append(data)

    # Compute per-STA aggregate stats
    results = {}
    for sta_id, runs in sta_data.items():
        all_rtts = []
        total_packets = 0
        total_received = 0
        for run in runs:
            all_rtts.extend(run["rtts"])
            total_packets += run["total"]
            total_received += run["received"]

        stats = compute_stats(all_rtts, deadline_ms)
        stats["sta_id"] = sta_id
        stats["total_packets"] = total_packets
        stats["total_received"] = total_received
        stats["num_runs"] = len(runs)
        stats["packet_loss_rate"] = (
            (total_packets - total_received) / total_packets * 100
            if total_packets > 0 else 0
        )
        results[sta_id] = stats

    return results


def analyze_aggregated_csv(filepath, deadline_ms=100.0):
    """Analyze the aggregated multi_sta_results.csv from orchestrator."""
    sta_data = defaultdict(list)

    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sta_id = row.get("sta_id", "unknown")
            sta_data[sta_id].append(row)

    results = {}
    for sta_id, rows in sta_data.items():
        mean_rtts = [float(r.get("mean_rtt_ms", 0)) for r in rows]
        p99_rtts = [float(r.get("p99_rtt_ms", 0)) for r in rows]
        miss_rates = [float(r.get("miss_rate_pct", 0)) for r in rows]
        n = len(rows)

        results[sta_id] = {
            "sta_id": sta_id,
            "count": sum(int(r.get("packets", 0)) for r in rows),
            "mean": sum(mean_rtts) / n if n > 0 else 0,
            "p99": sum(p99_rtts) / n if n > 0 else 0,
            "deadline_miss_rate": sum(miss_rates) / n if n > 0 else 0,
            "num_runs": n,
        }

    return results


def print_comparison_table(all_configs):
    """Print comparison table across configurations."""
    print("\n" + "=" * 80)
    print("  Multi-STA Scalability Comparison")
    print("=" * 80)

    for config_name, sta_results in all_configs.items():
        if not sta_results:
            continue

        num_stas = len(sta_results)
        print(f"\n  --- {config_name} ({num_stas} flow(s)) ---")
        print(f"  {'STA':>8s}  {'Mean RTT':>10s}  {'P50':>8s}  {'P99':>8s}  "
              f"{'Max':>8s}  {'Miss%':>8s}  {'Loss%':>8s}")
        print("  " + "-" * 70)

        throughputs = []
        for sta_id in sorted(sta_results.keys()):
            s = sta_results[sta_id]
            print(f"  {sta_id:>8s}  "
                  f"{s.get('mean', 0):>9.2f}ms  "
                  f"{s.get('p50', 0):>7.2f}ms  "
                  f"{s.get('p99', 0):>7.2f}ms  "
                  f"{s.get('max', 0):>7.2f}ms  "
                  f"{s.get('deadline_miss_rate', 0):>7.2f}%  "
                  f"{s.get('packet_loss_rate', 0):>7.2f}%")
            throughputs.append(s.get("total_received", s.get("count", 0)))

        if num_stas > 1:
            jain = compute_jain_fairness(throughputs)
            if jain is not None:
                print(f"  {'':>8s}  Jain's Fairness Index: {jain:.4f}")
            else:
                print(f"  {'':>8s}  Jain's Fairness Index: N/A (no traffic)")

    print("\n" + "=" * 80)


def print_latex_table(all_configs):
    """Print a LaTeX table fragment for manuscript-style reporting."""
    print("\n% --- LaTeX table fragment ---")
    print(r"\begin{table}[t]")
    print(r"\caption{Scalability: Performance Under Multiple Critical Flows}")
    print(r"\label{tab:scalability}")
    print(r"\centering\small")
    print(r"\begin{tabular}{l|" + "c|" * len(all_configs) + "}")
    print(r"\hline")

    config_names = sorted(all_configs.keys())
    header = r"\textbf{Metric}"
    for name in config_names:
        num = len(all_configs[name]) if all_configs[name] else 0
        header += f" & \\textbf{{{num} Flow(s)}}"
    header += r" \\"
    print(header)
    print(r"\hline")

    # Aggregate metrics per config
    metrics = {}
    for name in config_names:
        sta_results = all_configs[name]
        if not sta_results:
            metrics[name] = {}
            continue
        all_means = [s.get("mean", 0) for s in sta_results.values()]
        all_p99 = [s.get("p99", 0) for s in sta_results.values()]
        all_miss = [s.get("deadline_miss_rate", 0) for s in sta_results.values()]
        throughputs = [s.get("total_received", s.get("count", 0))
                       for s in sta_results.values()]
        metrics[name] = {
            "avg_mean_rtt": sum(all_means) / len(all_means) if all_means else 0,
            "avg_p99_rtt": sum(all_p99) / len(all_p99) if all_p99 else 0,
            "avg_miss_rate": sum(all_miss) / len(all_miss) if all_miss else 0,
            "jain": compute_jain_fairness(throughputs),
        }

    # Print rows
    rows = [
        ("Avg Mean RTT (ms)", "avg_mean_rtt", ".2f"),
        ("Avg P99 RTT (ms)", "avg_p99_rtt", ".2f"),
        ("Missed Deadline (\\%)", "avg_miss_rate", ".2f"),
    ]

    for label, key, fmt in rows:
        row = f"{label}"
        for name in config_names:
            val = metrics[name].get(key, 0)
            row += f" & {val:{fmt}}"
        row += r" \\"
        print(row)

    # Jain's fairness (may be None)
    row = "Jain's Fairness"
    for name in config_names:
        val = metrics[name].get("jain")
        row += f" & {val:.4f}" if val is not None else " & N/A"
    row += r" \\"
    print(row)

    print(r"\hline")
    print(r"\end{tabular}")
    print(r"\end{table}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Multi-STA experiment results analyzer")

    parser.add_argument("--results_dirs", type=str, nargs="+",
                        default=["results_multi_sta"],
                        help="Result directories to analyze (one per config)")
    parser.add_argument("--config_names", type=str, nargs="+",
                        default=None,
                        help="Names for each config (default: dir names)")
    parser.add_argument("--deadline_ms", type=float, default=100.0,
                        help="Deadline threshold in ms (default: 100)")
    parser.add_argument("--output", type=str, default="",
                        help="Output CSV file for aggregated metrics")
    parser.add_argument("--cdf_dir", type=str, default="",
                        help="Directory to save CDF data files")
    parser.add_argument("--latex", action="store_true",
                        help="Print LaTeX table fragment")

    args = parser.parse_args()

    # Assign config names
    if args.config_names and len(args.config_names) == len(args.results_dirs):
        config_names = args.config_names
    else:
        config_names = [os.path.basename(d.rstrip("/"))
                        for d in args.results_dirs]

    # Analyze each configuration
    all_configs = {}
    for name, results_dir in zip(config_names, args.results_dirs):
        print(f"\nAnalyzing: {results_dir} ({name})")
        sta_results = analyze_single_dir(results_dir, args.deadline_ms)
        all_configs[name] = sta_results if sta_results else {}

    # Print comparison
    print_comparison_table(all_configs)

    # LaTeX output
    if args.latex:
        print_latex_table(all_configs)

    # Save to CSV
    if args.output:
        rows = []
        for config_name, sta_results in all_configs.items():
            if not sta_results:
                continue
            for sta_id, stats in sta_results.items():
                row = {"config": config_name, "sta_id": sta_id}
                row.update(stats)
                rows.append(row)

        if rows:
            fieldnames = list(rows[0].keys())
            with open(args.output, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            print(f"\nAggregated metrics saved to: {args.output}")

    # Generate CDF data
    if args.cdf_dir:
        os.makedirs(args.cdf_dir, exist_ok=True)
        for config_name, sta_results in all_configs.items():
            if not sta_results:
                continue
            # Merge all RTTs for this config
            all_rtts = []
            for sta_id, stats in sta_results.items():
                if "rtts" in stats:
                    all_rtts.extend(stats["rtts"])
            if all_rtts:
                cdf_file = os.path.join(args.cdf_dir,
                                        f"cdf_{config_name}.csv")
                generate_cdf_data(all_rtts, cdf_file)
                print(f"CDF data saved to: {cdf_file}")


if __name__ == "__main__":
    main()
