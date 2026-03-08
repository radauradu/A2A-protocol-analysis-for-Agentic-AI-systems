#!/usr/bin/env python3


import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_CSV_PATHS = {
    1: "3Hour_Radu/1_1/tool_evaluations_1.csv",
    3: "3Hour_Radu/1_3/tool_evaluations_3.csv",
    5: "3Hour_Radu/1_5/tool_evaluations_5.csv",
}
DEFAULT_OUTDIR = "3Hour_Radu"

SCENARIO_LABELS = {1: "1 node", 3: "3 nodes", 5: "5 nodes"}
SCENARIO_COLORS = {1: "steelblue", 3: "salmon", 5: "lightgreen"}

# Match thesis colour palette
BAR_COLORS_METRIC = ["steelblue", "salmon", "lightgreen"]  # Request, Response, Total


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_a2a_rows(csv_path: str, nodes: int) -> pd.DataFrame:
    """Load tool_evaluations CSV and return only a2a_communication rows."""
    p = Path(csv_path)
    if not p.exists():
        print(f"[WARNING] File not found, skipping nodes={nodes}: {csv_path}")
        return pd.DataFrame()

    df = pd.read_csv(p, low_memory=False)
    a2a = df[df["tool_name"] == "a2a_communication"].copy()

    if a2a.empty:
        print(f"[WARNING] No 'a2a_communication' rows found in {csv_path} (nodes={nodes})")
        return pd.DataFrame()

    required = ["a2a_request_size_bytes", "a2a_response_size_bytes",
                "a2a_total_size_bytes", "execution_time"]
    for col in required:
        if col not in a2a.columns:
            a2a[col] = np.nan

    for col in required:
        a2a[col] = pd.to_numeric(a2a[col], errors="coerce")

    a2a["nodes"] = nodes
    print(f"[INFO] nodes={nodes}: {len(a2a)} a2a_communication rows loaded from {csv_path}")
    return a2a[["nodes"] + required]


def collect_stats(csv_map: dict) -> pd.DataFrame:
    """
    Returns a DataFrame indexed by nodes with columns:
        req_mean, req_std, resp_mean, resp_std,
        total_mean, total_std, net_mean, net_std
    """
    rows = []
    for nodes, csv_path in sorted(csv_map.items()):
        df = load_a2a_rows(csv_path, nodes)
        if df.empty:
            rows.append({
                "nodes": nodes,
                "req_mean": np.nan, "req_std": np.nan,
                "resp_mean": np.nan, "resp_std": np.nan,
                "total_mean": np.nan, "total_std": np.nan,
                "net_mean": np.nan, "net_std": np.nan,
            })
        else:
            rows.append({
                "nodes": nodes,
                "req_mean":   df["a2a_request_size_bytes"].mean(),
                "req_std":    df["a2a_request_size_bytes"].std(ddof=1),
                "resp_mean":  df["a2a_response_size_bytes"].mean(),
                "resp_std":   df["a2a_response_size_bytes"].std(ddof=1),
                "total_mean": df["a2a_total_size_bytes"].mean(),
                "total_std":  df["a2a_total_size_bytes"].std(ddof=1),
                "net_mean":   df["execution_time"].mean(),
                "net_std":    df["execution_time"].std(ddof=1),
            })
    return pd.DataFrame(rows).set_index("nodes")


# ---------------------------------------------------------------------------
# Figure 4.37 — grouped by scenario, bars = metric
# ---------------------------------------------------------------------------

def plot_fig437(stats: pd.DataFrame, outdir: Path, users: int = 1):
    scenarios = [n for n in [1, 3, 5] if n in stats.index and not np.isnan(stats.loc[n, "req_mean"])]
    if not scenarios:
        print("[WARNING] No data for Figure 4.37, skipping.")
        return

    x = np.arange(len(scenarios))
    width = 0.25

    fig, ax = plt.subplots(figsize=(8, 5))

    for i, (col_mean, col_std, label, color) in enumerate([
        ("req_mean",   "req_std",   "Request",  BAR_COLORS_METRIC[0]),
        ("resp_mean",  "resp_std",  "Response", BAR_COLORS_METRIC[1]),
        ("total_mean", "total_std", "Total",    BAR_COLORS_METRIC[2]),
    ]):
        means = [stats.loc[n, col_mean] for n in scenarios]
        stds  = [stats.loc[n, col_std]  for n in scenarios]
        stds  = [s if not np.isnan(s) else 0 for s in stds]
        ax.bar(x + (i - 1) * width, means, width,
               label=label, color=color, alpha=0.85,
               yerr=stds, capsize=4, error_kw={"elinewidth": 1.2, "capthick": 1.2})

    ax.set_title(f"A2A Message Size Distribution by Scenario ({users} user)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Scenario", fontsize=11)
    ax.set_ylabel("Size (bytes)", fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels([SCENARIO_LABELS[n] for n in scenarios])
    ax.legend(loc="upper left", fontsize=10)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)
    ax.set_ylim(bottom=0)
    plt.tight_layout()

    out_path = outdir / "A2A_MessageSize_ByScenario.png"
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"[INFO] Saved Figure 4.37 → {out_path}")


# ---------------------------------------------------------------------------
# Figure 4.38 — grouped by metric, bars = scenario
# ---------------------------------------------------------------------------

def plot_fig438(stats: pd.DataFrame, outdir: Path, users: int = 1):
    scenarios = [n for n in [1, 3, 5] if n in stats.index and not np.isnan(stats.loc[n, "req_mean"])]
    if not scenarios:
        print("[WARNING] No data for Figure 4.38, skipping.")
        return

    metrics = [
        ("req_mean",   "req_std",   "Request size"),
        ("resp_mean",  "resp_std",  "Response size"),
        ("total_mean", "total_std", "Total bytes"),
    ]

    x = np.arange(len(metrics))
    n_scenarios = len(scenarios)
    width = 0.25

    fig, ax = plt.subplots(figsize=(8, 5))

    for i, nodes in enumerate(scenarios):
        means = [stats.loc[nodes, m] for m, _, _ in metrics]
        stds  = [stats.loc[nodes, s] for _, s, _ in metrics]
        stds  = [v if not np.isnan(v) else 0 for v in stds]
        offset = (i - (n_scenarios - 1) / 2) * width
        ax.bar(x + offset, means, width,
               label=SCENARIO_LABELS[nodes],
               color=list(SCENARIO_COLORS.values())[i], alpha=0.85,
               yerr=stds, capsize=4, error_kw={"elinewidth": 1.2, "capthick": 1.2})

    ax.set_title(f"A2A Byte Exchange by Metric and Scenario ({users} user)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Metric", fontsize=11)
    ax.set_ylabel("Size (bytes)", fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels([label for _, _, label in metrics])
    ax.legend(title="Scenario", fontsize=10, title_fontsize=10)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)
    ax.set_ylim(bottom=0)
    plt.tight_layout()

    out_path = outdir / "A2A_ByteExchange_ByMetric.png"
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"[INFO] Saved Figure 4.38 → {out_path}")


# ---------------------------------------------------------------------------
# Figure 4.39 — network overhead per scenario
# ---------------------------------------------------------------------------

def plot_fig439(stats: pd.DataFrame, outdir: Path, users: int = 1):
    scenarios = [n for n in [1, 3, 5] if n in stats.index and not np.isnan(stats.loc[n, "net_mean"])]
    if not scenarios:
        print("[WARNING] No data for Figure 4.39, skipping.")
        return

    means = [stats.loc[n, "net_mean"] for n in scenarios]
    stds  = [stats.loc[n, "net_std"]  for n in scenarios]
    stds  = [s if not np.isnan(s) else 0 for s in stds]
    colors = [SCENARIO_COLORS[n] for n in scenarios]

    fig, ax = plt.subplots(figsize=(7, 5))
    x = np.arange(len(scenarios))
    ax.bar(x, means, color=colors, alpha=0.85,
           yerr=stds, capsize=5, error_kw={"elinewidth": 1.5, "capthick": 1.5})

    ax.set_title(f"A2A Network Overhead by Scenario ({users} user)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Scenario", fontsize=11)
    ax.set_ylabel("Network Overhead (s)", fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels([SCENARIO_LABELS[n] for n in scenarios])
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)
    ax.set_ylim(bottom=0)
    plt.tight_layout()

    out_path = outdir / "A2A_NetworkOverhead_ByScenario.png"
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"[INFO] Saved Figure 4.39 → {out_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate A2A network analysis figures (4.37, 4.38, 4.39)")
    parser.add_argument("--csv1",   default=DEFAULT_CSV_PATHS[1], help="tool_evaluations CSV for 1-node scenario")
    parser.add_argument("--csv3",   default=DEFAULT_CSV_PATHS[3], help="tool_evaluations CSV for 3-node scenario")
    parser.add_argument("--csv5",   default=DEFAULT_CSV_PATHS[5], help="tool_evaluations CSV for 5-node scenario")
    parser.add_argument("--outdir", default=DEFAULT_OUTDIR,       help="Directory to write output PNG files")
    parser.add_argument("--users",  type=int, default=1,           help="Number of users (label only, default: 1)")
    args = parser.parse_args()

    csv_map = {1: args.csv1, 3: args.csv3, 5: args.csv5}
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Loading a2a_communication data from:")
    for n, p in csv_map.items():
        print(f"  nodes={n}: {p}")

    stats = collect_stats(csv_map)

    if stats["req_mean"].isna().all():
        print("[ERROR] No usable data found in any CSV. "
              "Ensure the 3-hour A2A experiments have been run and "
              "tool_evaluations_*.csv files contain 'a2a_communication' rows.")
        sys.exit(1)

    print("\n[INFO] Summary statistics:")
    print(stats.to_string())
    print()

    plot_fig437(stats, outdir, users=args.users)
    plot_fig438(stats, outdir, users=args.users)
    plot_fig439(stats, outdir, users=args.users)

    print(f"\n[INFO] Done. All figures written to: {outdir.resolve()}")


if __name__ == "__main__":
    main()
