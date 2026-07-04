#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Protocol Overhead Measurement Tool

Computes the superframe channel efficiency and overhead breakdown for the
Hybrid TDMA/CSMA protocol based on configurable protocol parameters.
Uses provided/default protocol parameters for offline analysis.

Outputs:
  - Overhead breakdown table (terminal + CSV)
  - LaTeX table fragment for manuscript-style reporting

Usage (offline, with example protocol parameters):
    python3 measure_overhead.py

Usage (custom parameters):
    python3 measure_overhead.py \
        --hw_frame_us 4000 \
        --slot_us 100 \
        --n_tdma 6 \
        --n_control 4 \
        --beacon_us 200 \
        --guard_us 10 \
        --sw_frame_us 20000

Usage (sweep TDMA slots):
    python3 measure_overhead.py --sweep --n_tdma_range 0 8
"""

import argparse
import csv
import sys


def compute_overhead(hw_frame_us, slot_us, n_tdma, n_control, beacon_us,
                     guard_us, sw_frame_us):
    """Compute overhead breakdown for a given protocol configuration.

    Returns a dict with all timing components and efficiency metrics.
    """
    # TDMA section duration
    t_tdma = n_tdma * slot_us

    # Control section duration
    t_control = n_control * slot_us

    # Guard intervals (one per TDMA slot boundary)
    t_guard = n_tdma * guard_us if n_tdma > 0 else 0

    # CSMA section = remaining time in HW frame
    t_csma = hw_frame_us - t_tdma - t_control - t_guard

    # Beacon overhead amortized per HW frame
    # Beacon is sent once per SW frame (beacon interval)
    hw_frames_per_sw = sw_frame_us / hw_frame_us if hw_frame_us > 0 else 1
    beacon_per_hw = beacon_us / hw_frames_per_sw if hw_frames_per_sw > 0 else 0

    # Total protocol overhead per HW frame
    t_overhead = t_tdma + t_control + t_guard + beacon_per_hw

    # Effective CSMA time (available for general-purpose traffic)
    t_csma_effective = hw_frame_us - t_overhead

    # Channel efficiency
    eta = t_csma_effective / hw_frame_us if hw_frame_us > 0 else 0

    return {
        "hw_frame_us": hw_frame_us,
        "sw_frame_us": sw_frame_us,
        "slot_us": slot_us,
        "n_tdma": n_tdma,
        "n_control": n_control,
        "t_tdma_us": t_tdma,
        "t_control_us": t_control,
        "t_guard_us": t_guard,
        "t_csma_us": t_csma,
        "beacon_us": beacon_us,
        "beacon_per_hw_us": beacon_per_hw,
        "t_overhead_us": t_overhead,
        "t_csma_effective_us": t_csma_effective,
        "eta": eta,
        "overhead_pct": (1 - eta) * 100,
        "tdma_pct": t_tdma / hw_frame_us * 100,
        "control_pct": t_control / hw_frame_us * 100,
        "guard_pct": t_guard / hw_frame_us * 100,
        "beacon_pct": beacon_per_hw / hw_frame_us * 100,
        "csma_pct": t_csma_effective / hw_frame_us * 100,
    }


def print_table(result):
    """Print overhead breakdown table to terminal."""
    print("=" * 60)
    print("  Protocol Overhead Breakdown per HW Frame")
    print("=" * 60)
    print(f"  HW Frame Duration:     {result['hw_frame_us']:>8.1f} us")
    print(f"  SW Frame (beacon int): {result['sw_frame_us']:>8.1f} us")
    print(f"  Slot Duration:         {result['slot_us']:>8.1f} us")
    print(f"  N_TDMA Slots:          {result['n_tdma']:>8d}")
    print(f"  N_Control Slots:       {result['n_control']:>8d}")
    print("-" * 60)
    print(f"  {'Component':<30s} {'Duration (us)':>14s} {'Fraction':>10s}")
    print("-" * 60)
    print(f"  {'TDMA Section':<30s} {result['t_tdma_us']:>14.1f} {result['tdma_pct']:>9.1f}%")
    print(f"  {'Control Section':<30s} {result['t_control_us']:>14.1f} {result['control_pct']:>9.1f}%")
    print(f"  {'Guard Intervals':<30s} {result['t_guard_us']:>14.1f} {result['guard_pct']:>9.1f}%")
    print(f"  {'Beacon (amortized)':<30s} {result['beacon_per_hw_us']:>14.1f} {result['beacon_pct']:>9.1f}%")
    print("-" * 60)
    print(f"  {'Total Overhead':<30s} {result['t_overhead_us']:>14.1f} {result['overhead_pct']:>9.1f}%")
    print(f"  {'Available CSMA':<30s} {result['t_csma_effective_us']:>14.1f} {result['csma_pct']:>9.1f}%")
    print("=" * 60)
    print(f"  Channel Efficiency eta = {result['eta']:.4f} ({result['csma_pct']:.1f}%)")
    print("=" * 60)


def print_latex(result):
    """Print a LaTeX table fragment for manuscript-style reporting."""
    print()
    print("% --- LaTeX table fragment ---")
    print(r"\begin{table}[t]")
    print(r"\caption{Protocol Overhead Breakdown per Superframe}")
    print(r"\label{tab:overhead}")
    print(r"\centering\small")
    print(r"\begin{tabular}{l|c|c}")
    print(r"\hline")
    print(r"\textbf{Component} & \textbf{Duration} & \textbf{Fraction of $T_f$} \\")
    print(r"\hline")
    print(f"TDMA Section ($N_{{TDMA}}={result['n_tdma']}$) & "
          f"{result['t_tdma_us']:.0f}~$\\mu$s & {result['tdma_pct']:.1f}\\% \\\\")
    print(f"Control Section & "
          f"{result['t_control_us']:.0f}~$\\mu$s & {result['control_pct']:.1f}\\% \\\\")
    print(f"Guard Intervals & "
          f"{result['t_guard_us']:.0f}~$\\mu$s & {result['guard_pct']:.1f}\\% \\\\")
    print(f"Beacon (amortized) & "
          f"{result['beacon_per_hw_us']:.0f}~$\\mu$s & {result['beacon_pct']:.1f}\\% \\\\")
    print(r"\hline")
    print(f"\\textbf{{Total Overhead}} & "
          f"\\textbf{{{result['t_overhead_us']:.0f}}}~$\\mu$s & "
          f"\\textbf{{{result['overhead_pct']:.1f}}}\\% \\\\")
    print(f"\\textbf{{Available CSMA}} & "
          f"\\textbf{{{result['t_csma_effective_us']:.0f}}}~$\\mu$s & "
          f"\\textbf{{{result['csma_pct']:.1f}}}\\% \\\\")
    print(r"\hline")
    print(r"\end{tabular}")
    print(r"\end{table}")
    print()


def sweep_tdma(hw_frame_us, slot_us, n_control, beacon_us, guard_us,
               sw_frame_us, n_range, output_csv):
    """Sweep N_TDMA from n_range[0] to n_range[1] and output results."""
    results = []
    for n_tdma in range(n_range[0], n_range[1] + 1):
        r = compute_overhead(hw_frame_us, slot_us, n_tdma, n_control,
                             beacon_us, guard_us, sw_frame_us)
        results.append(r)

    # Print sweep table
    print()
    print("=" * 80)
    print("  TDMA Slot Sweep: Overhead vs N_TDMA")
    print("=" * 80)
    print(f"  {'N_TDMA':>6s}  {'T_TDMA(us)':>11s}  {'T_Guard(us)':>12s}  "
          f"{'T_CSMA(us)':>11s}  {'Overhead%':>10s}  {'eta':>8s}")
    print("-" * 80)
    for r in results:
        print(f"  {r['n_tdma']:>6d}  {r['t_tdma_us']:>11.1f}  {r['t_guard_us']:>12.1f}  "
              f"{r['t_csma_effective_us']:>11.1f}  {r['overhead_pct']:>9.1f}%  "
              f"{r['eta']:>8.4f}")
    print("=" * 80)

    # Max critical flows calculation
    print()
    print("  Maximum Critical Flows (N_max) Analysis:")
    print(f"    Assuming minimum 50% CSMA capacity preserved:")
    min_csma_50 = hw_frame_us * 0.5
    n_max_50 = int((hw_frame_us - n_control * slot_us - beacon_us / (sw_frame_us / hw_frame_us) - min_csma_50) / (slot_us + guard_us))
    print(f"    N_max (50% CSMA) = {n_max_50}")
    min_csma_30 = hw_frame_us * 0.3
    n_max_70 = int((hw_frame_us - n_control * slot_us - beacon_us / (sw_frame_us / hw_frame_us) - min_csma_30) / (slot_us + guard_us))
    print(f"    N_max (30% CSMA) = {n_max_70}")

    # Save to CSV
    if output_csv:
        fieldnames = ["n_tdma", "t_tdma_us", "t_control_us", "t_guard_us",
                       "t_csma_effective_us", "overhead_pct", "eta"]
        with open(output_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in results:
                writer.writerow({k: r[k] for k in fieldnames})
        print(f"\n  Sweep results saved to: {output_csv}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Protocol overhead calculator for Hybrid TDMA/CSMA")

    # Example protocol parameters; override these to match a specific testbed.
    parser.add_argument("--hw_frame_us", type=float, default=4000.0,
                        help="HW frame duration in us (default: 4000)")
    parser.add_argument("--sw_frame_us", type=float, default=20000.0,
                        help="SW frame / beacon interval in us (default: 20000)")
    parser.add_argument("--slot_us", type=float, default=100.0,
                        help="TDMA slot duration in us (default: 100)")
    parser.add_argument("--n_tdma", type=int, default=6,
                        help="Number of TDMA slots in session 0 (default: 6)")
    parser.add_argument("--n_control", type=int, default=4,
                        help="Number of control slots in session 1 (default: 4)")
    parser.add_argument("--beacon_us", type=float, default=200.0,
                        help="Beacon frame duration in us (default: 200)")
    parser.add_argument("--guard_us", type=float, default=10.0,
                        help="Guard interval per TDMA slot in us (default: 10)")

    # Sweep mode
    parser.add_argument("--sweep", action="store_true",
                        help="Sweep N_TDMA values and show tradeoff")
    parser.add_argument("--n_tdma_range", type=int, nargs=2, default=[0, 8],
                        help="Range of N_TDMA for sweep (default: 0 8)")

    # Output
    parser.add_argument("--output", type=str, default="",
                        help="Output CSV file for sweep results")
    parser.add_argument("--latex", action="store_true",
                        help="Print LaTeX table fragment")

    args = parser.parse_args()

    if args.sweep:
        sweep_tdma(args.hw_frame_us, args.slot_us, args.n_control,
                   args.beacon_us, args.guard_us, args.sw_frame_us,
                   args.n_tdma_range, args.output)
    else:
        result = compute_overhead(
            args.hw_frame_us, args.slot_us, args.n_tdma, args.n_control,
            args.beacon_us, args.guard_us, args.sw_frame_us)
        print_table(result)
        if args.latex:
            print_latex(result)
        if args.output:
            fieldnames = list(result.keys())
            with open(args.output, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow(result)
            print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
