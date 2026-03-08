#!/usr/bin/env python3
"""
Automated post-processing script for JMeter test results.
Processes tool_evaluations CSV files and generates graphs automatically.
Based on Torrado's approach.
"""
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for Docker
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from pathlib import Path
from typing import List, Optional, Dict
import sys
import os
import shutil

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def compute_mean_std_table(
    df: pd.DataFrame,
    metric_columns: List[str],
    group_col: str = "tool_name",
    title: str = "",
    legend_labels: List[str] = None,
    users: int = None,
    nodes: int = None,
    export_csv_path: str = None,
    max_cv: float = 1.0
) -> pd.DataFrame:
    """Compute mean and std for metrics, grouped by tool_name."""
    # Convert to long format
    df_long = df[[group_col] + metric_columns].melt(
        id_vars=[group_col],
        value_vars=metric_columns,
        var_name="Metric",
        value_name="Value"
    ).dropna(subset=["Value"])

    # Apply custom metric labels if provided
    if legend_labels:
        metric_map = dict(zip(metric_columns, legend_labels))
        df_long['Metric'] = df_long['Metric'].map(metric_map)

    # Group and calculate mean/std
    summary_df = (
        df_long
        .groupby([group_col, "Metric"])
        .agg(
            mean_value=("Value", "mean"),
            std_value=("Value", "std")
        )
        .reset_index()
    )

    # Calculate coefficient of variation (cv) and cap std
    summary_df["mean_value_safe"] = summary_df["mean_value"].replace(0, np.nan)
    summary_df["cv"] = summary_df["std_value"] / summary_df["mean_value_safe"]
    condition = (summary_df["cv"] > max_cv) | (summary_df["cv"].isna()) | (summary_df["cv"] == np.inf)
    summary_df.loc[condition, "std_value"] = summary_df.loc[condition, "mean_value"] * max_cv
    summary_df["std_value"] = summary_df["std_value"].fillna(0).clip(lower=0)
    summary_df.drop(columns=["mean_value_safe"], inplace=True)

    # Add metadata
    if users is not None:
        summary_df["users"] = users
    if nodes is not None:
        summary_df["nodes"] = nodes

    if export_csv_path:
        summary_df.to_csv(export_csv_path, index=False)
        print(f"[INFO] Exported summary to {export_csv_path}")

    return summary_df


def plot_metric_bars_from_summary(
    summary_df: pd.DataFrame,
    output_path: str,
    group_col: str = "tool_name",
    title: str = "",
    ylabel: str = "",
    yunit: str = "",
    tool_order: List[str] = None,
    metric_order: List[str] = None
):
    """Generate bar chart with error bars from summary DataFrame."""
    sns.set(style="whitegrid")
    pastel = sns.color_palette("pastel")

    # Get available tools in the data
    available_tools = summary_df[group_col].unique().tolist()
    
    # Set tool and metric order - filter to only available tools
    if tool_order:
        filtered_tool_order = [t for t in tool_order if t in available_tools]
        if filtered_tool_order:
            summary_df[group_col] = pd.Categorical(summary_df[group_col], categories=filtered_tool_order, ordered=True)
            tool_order = filtered_tool_order
        else:
            tool_order = None
    if metric_order:
        summary_df["Metric"] = pd.Categorical(summary_df["Metric"], categories=metric_order, ordered=True)
    else:
        summary_df["Metric"] = pd.Categorical(summary_df["Metric"], ordered=True)

    # Pivot for plotting
    mean_pivot = summary_df.pivot(index=group_col, columns="Metric", values="mean_value")
    std_pivot = summary_df.pivot(index=group_col, columns="Metric", values="std_value")

    if tool_order:
        # Only select tools that exist in the pivot
        existing_tools = [t for t in tool_order if t in mean_pivot.index]
        mean_pivot = mean_pivot.loc[existing_tools]
        std_pivot = std_pivot.loc[existing_tools]

    fig, ax = plt.subplots(figsize=(10, 6))

    n_metrics = len(mean_pivot.columns)
    bar_width = 0.8 / n_metrics
    x = np.arange(len(mean_pivot.index))
    colors = pastel[:n_metrics]

    for i, metric in enumerate(mean_pivot.columns):
        offset = (i - (n_metrics - 1) / 2) * bar_width
        pos = x + offset
        means = mean_pivot[metric]
        stds = std_pivot[metric]

        ax.bar(
            pos, means, bar_width,
            label=str(metric),
            color=colors[i],
            edgecolor=None,
            zorder=2
        )

        ax.errorbar(
            pos, means, yerr=stds,
            fmt='none', ecolor='black', elinewidth=1.3,
            capsize=0, zorder=3
        )

    # Styling
    ax.set_title(title, fontsize=13)
    ax.set_xlabel(group_col.replace("_", " ").title(), fontsize=10)
    ax.set_ylabel(f"{ylabel} ({yunit})" if yunit else ylabel, fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels(mean_pivot.index, rotation=45, ha='right', fontsize=9)
    ax.tick_params(axis='y', labelsize=9)

    # Black borders
    for spine in ax.spines.values():
        spine.set_edgecolor("black")
        spine.set_linewidth(1.0)

    # Legend
    ax.legend(
        title="Metric", title_fontsize=9, fontsize=8,
        loc='upper right', bbox_to_anchor=(1, 1),
        frameon=True, edgecolor="black"
    )

    ax.grid(axis='y', linestyle='--', alpha=0.6, zorder=1)
    plt.tight_layout(rect=[0.01, 0.01, 0.99, 0.98])
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[INFO] Saved graph to {output_path}")


def process_tool_evaluations(
    csv_path: str,
    output_dir: str,
    users: int,
    nodes: int
):
    """Process tool_evaluations CSV and generate all graphs."""
    print(f"\n[PROCESSING] {csv_path}")
    print(f"[INFO] Users: {users}, Nodes: {nodes}")
    
    # Load data
    try:
        df = pd.read_csv(csv_path)
        print(f"[INFO] Loaded {len(df)} rows from {csv_path}")
    except Exception as e:
        print(f"[ERROR] Failed to load {csv_path}: {e}")
        return

    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Define tool order (matching Torrado's)
    tool_order = ["decide_tool", "lookup_sales_data", "analyzing_data", "a2a_communication", "create_visualization"]

    # --- 1. Energy Analysis ---
    print("\n[ANALYZING] Energy metrics...")
    energy_metrics = ["total_energy", "cpu_energy", "gpu_energy", "ram_energy"]
    available_energy = [m for m in energy_metrics if m in df.columns]
    
    if available_energy:
        energy_summary = compute_mean_std_table(
            df,
            metric_columns=available_energy,
            title="Energy per tool",
            legend_labels=["Total", "CPU", "GPU", "RAM"][:len(available_energy)],
            users=users,
            nodes=nodes,
            export_csv_path=f"{output_dir}/energy_stats.csv",
            max_cv=0.9
        )
        # Also save with Torrado's naming convention
        energy_summary.to_csv(f"{output_dir}/output_energy_stats.csv", index=False)
        
        plot_metric_bars_from_summary(
            energy_summary,
            output_path=f"{output_dir}/energy_consumption.png",
            title=f"Energy Consumption by Tool: {users} users, {nodes} nodes",
            ylabel="Energy",
            yunit="kWh",
            tool_order=tool_order,
            metric_order=["Total", "CPU", "GPU", "RAM"][:len(available_energy)]
        )
        # Create copies with Torrado's naming
        shutil.copy(f"{output_dir}/energy_consumption.png", f"{output_dir}/EnergyperTool.png")

    # --- 2. Utilization Analysis ---
    print("\n[ANALYZING] Utilization metrics...")
    util_metrics = ["cpu_utilization", "gpu_utilization"]
    available_util = [m for m in util_metrics if m in df.columns and df[m].notna().any()]
    
    if available_util:
        util_summary = compute_mean_std_table(
            df,
            metric_columns=available_util,
            title="Utilization per tool",
            legend_labels=["CPU", "GPU"][:len(available_util)],
            users=users,
            nodes=nodes,
            export_csv_path=f"{output_dir}/utilization_stats.csv",
            max_cv=0.9
        )
        # Also save with Torrado's naming convention
        util_summary.to_csv(f"{output_dir}/output_utilization_stats.csv", index=False)
        
        plot_metric_bars_from_summary(
            util_summary,
            output_path=f"{output_dir}/utilization.png",
            title=f"Hardware Utilization by Tool: {users} users, {nodes} nodes",
            ylabel="Utilization",
            yunit="%",
            tool_order=tool_order,
            metric_order=["CPU", "GPU"][:len(available_util)]
        )
        # Create copies with Torrado's naming
        shutil.copy(f"{output_dir}/utilization.png", f"{output_dir}/UtilizationperTool.png")

    # --- 3. Execution Time Analysis ---
    print("\n[ANALYZING] Execution time metrics...")
    if "execution_time" in df.columns and df["execution_time"].notna().any():
        time_summary = compute_mean_std_table(
            df,
            metric_columns=["execution_time"],
            title="Service Time per tool",
            legend_labels=["Service Time"],
            users=users,
            nodes=nodes,
            export_csv_path=f"{output_dir}/execution_time_stats.csv",
            max_cv=0.9
        )
        # Also save with Torrado's naming convention
        time_summary.to_csv(f"{output_dir}/output_execution_stats.csv", index=False)
        
        plot_metric_bars_from_summary(
            time_summary,
            output_path=f"{output_dir}/execution_time.png",
            title=f"Service Time per Tool: {users} users, {nodes} nodes",
            ylabel="Time",
            yunit="Seconds",
            tool_order=tool_order,
            metric_order=["Service Time"]
        )
        # Create copies with Torrado's naming
        shutil.copy(f"{output_dir}/execution_time.png", f"{output_dir}/RespTimeperTool.png")

    print(f"\n[COMPLETE] All tool evaluation graphs generated in {output_dir}/")


def plot_arrival_timeline(results_table_path: str, output_path: str):
    """Generate arrival timeline graph from ResultsTable.csv (like Torrado's graphs.py)."""
    try:
        df = pd.read_csv(results_table_path)
        
        # Convert timestamps to seconds from start
        df['arrival_time'] = (df['timeStamp'] - df['timeStamp'].min()) / 1000.0
        
        # Sort by time
        df = df.sort_values('arrival_time').reset_index(drop=True)
        
        # Calculate inter-arrival times
        df['delta'] = df['arrival_time'].diff()
        
        # Create figure
        fig, ax = plt.subplots(figsize=(16, 4))
        
        # Draw vertical lines for each arrival
        ax.vlines(df['arrival_time'], ymin=0, ymax=1, color='blue', linewidth=8)
        
        # Draw horizontal lines between arrivals with delta labels
        for i in range(1, len(df)):
            x0 = df['arrival_time'].iloc[i-1]
            x1 = df['arrival_time'].iloc[i]
            y = 0.50
            
            # Horizontal line
            ax.hlines(y, x0, x1, color='gray', linestyle='--')
            
            # Delta label
            delta = round(x1 - x0, 2)
            ax.text((x0 + x1) / 2, y + 0.02, f't{i}:{delta}s', ha='center', fontsize=6, rotation=45)
        
        ax.set_xlabel('Time (s)')
        ax.set_title('Arrival Timeline with Inter-arrival Intervals')
        ax.set_yticks([])
        ax.grid(True, axis='x')
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"[INFO] Saved arrival timeline to {output_path}")
    except Exception as e:
        print(f"[WARNING] Failed to generate arrival timeline: {e}")


def format_hhmmss(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format (like Torrado's)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02}:{minutes:02}:{secs:02}"


def convert_time_to_seconds(time_str: str) -> float:
    """Convert HH:MM:SS,mmm or HH:MM:SS.mmm to seconds (like Torrado's)."""
    time_str = str(time_str).replace(',', '.')
    parts = time_str.split(':')
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    return 0


def plot_response_times_over_time(resptime_path: str, output_path: str, users: int = None, nodes: int = None):
    """Generate response time over time graph from RespTime.csv (like Torrado's functionalities.py)."""
    try:
        # Try semicolon delimiter first (Torrado's format), then comma
        try:
            df = pd.read_csv(resptime_path, sep=';')
            if len(df.columns) < 2:
                df = pd.read_csv(resptime_path)
        except:
            df = pd.read_csv(resptime_path)
        
        df.columns = df.columns.str.strip()
        
        # Detect format
        if 'Elapsed time' in df.columns:
            # Torrado's format: Elapsed time;my_test_sampler
            df['Elapsed time'] = df['Elapsed time'].astype(str).str.strip()
            df['time_seconds'] = df['Elapsed time'].apply(convert_time_to_seconds)
            
            # Handle day rollover (when time goes from 23:59:59 to 00:00:00)
            seconds_list = df['time_seconds'].tolist()
            corrected = []
            accumulated = 0
            for i, s in enumerate(seconds_list):
                if i > 0 and s < seconds_list[i-1]:
                    accumulated += 86400  # New day
                corrected.append(s + accumulated)
            
            # Calculate elapsed from start
            df['elapsed_seconds'] = [max(0, s - corrected[0]) for s in corrected]
            
            # Response time column
            resp_cols = [c for c in df.columns if c not in ['Elapsed time', 'time_seconds', 'elapsed_seconds']]
            if resp_cols:
                resp_time_col = resp_cols[0]
                df[resp_time_col] = df[resp_time_col].astype(str).str.replace(',', '.').str.strip()
                df[resp_time_col] = pd.to_numeric(df[resp_time_col], errors='coerce')
            else:
                print(f"[WARNING] No response time column found in {resptime_path}")
                return
                
        elif 'timeStamp' in df.columns and 'elapsed' in df.columns:
            # Raw JMeter format
            df['elapsed_seconds'] = (df['timeStamp'] - df['timeStamp'].min()) / 1000.0
            resp_time_col = 'elapsed'
            df[resp_time_col] = pd.to_numeric(df[resp_time_col], errors='coerce')
        else:
            print(f"[WARNING] Unknown format in {resptime_path}")
            return
        
        df = df.dropna(subset=[resp_time_col, 'elapsed_seconds'])
        
        if df.empty:
            print(f"[WARNING] No valid data in {resptime_path}")
            return
        
        df = df.sort_values('elapsed_seconds').reset_index(drop=True)
        
        # Convert response time to seconds for display
        df['resp_time_seconds'] = df[resp_time_col] / 1000.0
        
        # Create time labels in HH:MM:SS format
        df['time_label'] = df['elapsed_seconds'].apply(format_hhmmss)
        
        # Plot like Torrado
        fig, ax = plt.subplots(figsize=(16, 6))
        ax.plot(df['elapsed_seconds'], df['resp_time_seconds'], linewidth=1, color='blue', marker='o', markersize=4)
        
        # Format x-axis with HH:MM:SS labels at intervals
        total_time = df['elapsed_seconds'].max()
        if total_time > 3600:  # More than 1 hour - show every 30 min
            interval = 1800  # 30 minutes
        elif total_time > 600:  # More than 10 min - show every 5 min
            interval = 300
        else:
            interval = 60  # Every minute
        
        tick_positions = list(range(0, int(total_time) + 1, interval))
        tick_labels = [format_hhmmss(t) for t in tick_positions]
        ax.set_xticks(tick_positions)
        ax.set_xticklabels(tick_labels, rotation=45, ha='right')
        
        title = 'Response Time Over Time'
        if users and nodes:
            title = f'Response Time Over Time: {users} users, {nodes} nodes'
        
        ax.set_xlabel('Elapsed Time (HH:MM:SS)')
        ax.set_ylabel('Response Time (seconds)')
        ax.set_title(title)
        ax.grid(True, axis='y', linestyle='--', alpha=0.5)
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"[INFO] Saved response time graph to {output_path}")
    except Exception as e:
        print(f"[WARNING] Failed to generate response time graph: {e}")
        import traceback
        traceback.print_exc()


def plot_active_threads(activethreads_path: str, output_path: str, users: int = None, nodes: int = None):
    """Generate active threads over time graph from ActiveThreadsOT.csv (like Torrado's style)."""
    try:
        df = pd.read_csv(activethreads_path)
        
        # Check if it's time series format or raw results
        if 'timeStamp' in df.columns and 'allThreads' in df.columns:
            # Raw results format - extract time series
            df['elapsed_seconds'] = (df['timeStamp'] - df['timeStamp'].min()) / 1000.0
            threads_col = 'allThreads'
        elif len(df.columns) >= 2:
            # Time series format
            time_col = df.columns[0]
            threads_col = df.columns[-1]
            
            if df[time_col].dtype == 'object':
                df[time_col] = df[time_col].astype(str).str.strip()
                df['time_seconds'] = df[time_col].apply(convert_time_to_seconds)
                
                # Handle day rollover
                seconds_list = df['time_seconds'].tolist()
                corrected = []
                accumulated = 0
                for i, s in enumerate(seconds_list):
                    if i > 0 and s < seconds_list[i-1]:
                        accumulated += 86400
                    corrected.append(s + accumulated)
                df['elapsed_seconds'] = [max(0, s - corrected[0]) for s in corrected]
            else:
                df['elapsed_seconds'] = df[time_col]
        else:
            print(f"[WARNING] Unknown format in {activethreads_path}")
            return
        
        # Convert threads to numeric
        df[threads_col] = pd.to_numeric(df[threads_col], errors='coerce')
        df = df.dropna(subset=[threads_col, 'elapsed_seconds'])
        
        if df.empty:
            print(f"[WARNING] No valid data in {activethreads_path}")
            return
        
        df = df.sort_values('elapsed_seconds').reset_index(drop=True)
        
        fig, ax = plt.subplots(figsize=(16, 6))
        ax.plot(df['elapsed_seconds'], df[threads_col], linewidth=1, color='green', marker='o', markersize=3)
        
        # Format x-axis with HH:MM:SS labels
        total_time = df['elapsed_seconds'].max()
        if total_time > 3600:
            interval = 1800
        elif total_time > 600:
            interval = 300
        else:
            interval = 60
        
        tick_positions = list(range(0, int(total_time) + 1, interval))
        tick_labels = [format_hhmmss(t) for t in tick_positions]
        ax.set_xticks(tick_positions)
        ax.set_xticklabels(tick_labels, rotation=45, ha='right')
        
        title = 'Active Threads Over Time'
        if users and nodes:
            title = f'Active Threads Over Time: {users} users, {nodes} nodes'
        
        ax.set_xlabel('Elapsed Time (HH:MM:SS)')
        ax.set_ylabel('Active Threads')
        ax.set_title(title)
        ax.grid(True, axis='y', linestyle='--', alpha=0.5)
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"[INFO] Saved active threads graph to {output_path}")
    except Exception as e:
        print(f"[WARNING] Failed to generate active threads graph: {e}")
        import traceback
        traceback.print_exc()


def plot_throughput(throughput_path: str, output_path: str, users: int = None, nodes: int = None):
    """Generate transactions per second graph from TransactionsperSec.csv (like Torrado's style)."""
    try:
        df = pd.read_csv(throughput_path)
        
        # Check if it's time series format or raw results
        if 'timeStamp' in df.columns:
            # Raw results format - calculate throughput over time windows
            df['elapsed_seconds'] = (df['timeStamp'] - df['timeStamp'].min()) / 1000.0
            
            # Group by 10-second windows for smoother throughput line
            df['time_window'] = (df['elapsed_seconds'] // 10) * 10
            throughput_df = df.groupby('time_window').size().reset_index(name='tps')
            throughput_df['tps'] = throughput_df['tps'] / 10.0  # Average per second
            throughput_df.columns = ['elapsed_seconds', 'tps']
        elif len(df.columns) >= 2:
            # Time series format
            time_col = df.columns[0]
            tps_col = df.columns[-1]
            
            if df[time_col].dtype == 'object':
                df[time_col] = df[time_col].astype(str).str.strip()
                df['time_seconds'] = df[time_col].apply(convert_time_to_seconds)
                seconds_list = df['time_seconds'].tolist()
                corrected = []
                accumulated = 0
                for i, s in enumerate(seconds_list):
                    if i > 0 and s < seconds_list[i-1]:
                        accumulated += 86400
                    corrected.append(s + accumulated)
                df['elapsed_seconds'] = [max(0, s - corrected[0]) for s in corrected]
            else:
                df['elapsed_seconds'] = df[time_col]
            
            throughput_df = df[['elapsed_seconds', tps_col]].copy()
            throughput_df.columns = ['elapsed_seconds', 'tps']
            throughput_df['tps'] = pd.to_numeric(throughput_df['tps'], errors='coerce')
        else:
            print(f"[WARNING] Unknown format in {throughput_path}")
            return
        
        throughput_df = throughput_df.dropna()
        
        if throughput_df.empty:
            print(f"[WARNING] No valid data in {throughput_path}")
            return
        
        throughput_df = throughput_df.sort_values('elapsed_seconds').reset_index(drop=True)
        
        fig, ax = plt.subplots(figsize=(16, 6))
        ax.plot(throughput_df['elapsed_seconds'], throughput_df['tps'], linewidth=1, color='orange', marker='o', markersize=3)
        
        # Format x-axis with HH:MM:SS labels
        total_time = throughput_df['elapsed_seconds'].max()
        if total_time > 3600:
            interval = 1800
        elif total_time > 600:
            interval = 300
        else:
            interval = 60
        
        tick_positions = list(range(0, int(total_time) + 1, interval))
        tick_labels = [format_hhmmss(t) for t in tick_positions]
        ax.set_xticks(tick_positions)
        ax.set_xticklabels(tick_labels, rotation=45, ha='right')
        
        title = 'Throughput Over Time'
        if users and nodes:
            title = f'Throughput Over Time: {users} users, {nodes} nodes'
        
        ax.set_xlabel('Elapsed Time (HH:MM:SS)')
        ax.set_ylabel('Transactions per Second')
        ax.set_title(title)
        ax.grid(True, axis='y', linestyle='--', alpha=0.5)
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"[INFO] Saved throughput graph to {output_path}")
    except Exception as e:
        print(f"[WARNING] Failed to generate throughput graph: {e}")
        import traceback
        traceback.print_exc()


def plot_bytes_throughput(bytes_path: str, output_path: str, users: int = None, nodes: int = None):
    """Generate bytes throughput graph from BytesThroughput.persec.csv (like Torrado's style)."""
    try:
        df = pd.read_csv(bytes_path)
        
        # Check if it's time series format or raw results
        if 'timeStamp' in df.columns and 'bytes' in df.columns:
            # Raw results format - calculate bytes per second over time windows
            df['elapsed_seconds'] = (df['timeStamp'] - df['timeStamp'].min()) / 1000.0
            
            df['bytes'] = pd.to_numeric(df['bytes'], errors='coerce')
            
            # Group by 10-second windows for smoother line
            df['time_window'] = (df['elapsed_seconds'] // 10) * 10
            bytes_df = df.groupby('time_window')['bytes'].sum().reset_index(name='bytes_per_sec')
            bytes_df['bytes_per_sec'] = bytes_df['bytes_per_sec'] / 10.0  # Average per second
            bytes_df.columns = ['elapsed_seconds', 'bytes_per_sec']
        elif len(df.columns) >= 2:
            # Time series format
            time_col = df.columns[0]
            bytes_col = df.columns[-1]
            
            if df[time_col].dtype == 'object':
                df[time_col] = df[time_col].astype(str).str.strip()
                df['time_seconds'] = df[time_col].apply(convert_time_to_seconds)
                seconds_list = df['time_seconds'].tolist()
                corrected = []
                accumulated = 0
                for i, s in enumerate(seconds_list):
                    if i > 0 and s < seconds_list[i-1]:
                        accumulated += 86400
                    corrected.append(s + accumulated)
                df['elapsed_seconds'] = [max(0, s - corrected[0]) for s in corrected]
            else:
                df['elapsed_seconds'] = df[time_col]
            
            bytes_df = df[['elapsed_seconds', bytes_col]].copy()
            bytes_df.columns = ['elapsed_seconds', 'bytes_per_sec']
            bytes_df['bytes_per_sec'] = pd.to_numeric(bytes_df['bytes_per_sec'], errors='coerce')
        else:
            print(f"[WARNING] Unknown format in {bytes_path}")
            return
        
        bytes_df = bytes_df.dropna()
        
        if bytes_df.empty:
            print(f"[WARNING] No valid data in {bytes_path}")
            return
        
        bytes_df = bytes_df.sort_values('elapsed_seconds').reset_index(drop=True)
        
        fig, ax = plt.subplots(figsize=(16, 6))
        ax.plot(bytes_df['elapsed_seconds'], bytes_df['bytes_per_sec'], linewidth=1, color='purple', marker='o', markersize=3)
        
        # Format x-axis with HH:MM:SS labels
        total_time = bytes_df['elapsed_seconds'].max()
        if total_time > 3600:
            interval = 1800
        elif total_time > 600:
            interval = 300
        else:
            interval = 60
        
        tick_positions = list(range(0, int(total_time) + 1, interval))
        tick_labels = [format_hhmmss(t) for t in tick_positions]
        ax.set_xticks(tick_positions)
        ax.set_xticklabels(tick_labels, rotation=45, ha='right')
        
        title = 'Bytes Throughput Over Time'
        if users and nodes:
            title = f'Bytes Throughput Over Time: {users} users, {nodes} nodes'
        
        ax.set_xlabel('Elapsed Time (HH:MM:SS)')
        ax.set_ylabel('Bytes per Second')
        ax.set_title(title)
        ax.grid(True, axis='y', linestyle='--', alpha=0.5)
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"[INFO] Saved bytes throughput graph to {output_path}")
    except Exception as e:
        print(f"[WARNING] Failed to generate bytes throughput graph: {e}")
        import traceback
        traceback.print_exc()


def plot_utilization_over_time(utilization_path: str, output_path: str, users: int = None, nodes: int = None):
    """Generate utilization over time graph from Utilization.csv or UtilizationSSHMon.csv (Torrado's format or JMeter format)."""
    try:
        # Try semicolon delimiter first (Torrado's format)
        try:
            df = pd.read_csv(utilization_path, sep=';')
            if len(df.columns) < 2:
                df = pd.read_csv(utilization_path)
        except Exception:
            df = pd.read_csv(utilization_path)
        
        df.columns = df.columns.str.strip()
        
        # --- JMeter format: timeStamp (epoch ms), label (CPU/GPU1/GPU2), value in responseMessage or responseCode ---
        if 'Elapsed time' not in df.columns and 'timeStamp' in df.columns and 'label' in df.columns:
            # JMeter SSHMon stores command output (utilization %) in responseMessage; fallback to responseCode
            for value_col in ('responseMessage', 'responseCode'):
                if value_col in df.columns:
                    break
            else:
                print(f"[WARNING] Utilization CSV has no 'Elapsed time' or value column. Columns: {list(df.columns)}. Skipping utilization-over-time graph.")
                return
            df['value'] = pd.to_numeric(df[value_col].astype(str).str.replace(',', '.'), errors='coerce')
            # Elapsed seconds from start
            ts_min = df['timeStamp'].min()
            df['Tiempo transcurrido'] = (df['timeStamp'].astype(float) - ts_min) / 1000.0
            # Pivot: one row per time bucket, columns CPU, GPU1, GPU2
            df_wide = df.pivot_table(
                index='Tiempo transcurrido',
                columns='label',
                values='value',
                aggfunc='mean'
            ).reset_index()
            # Normalize column names (CPU, GPU1, GPU2)
            rename = {}
            for c in df_wide.columns:
                if c in ('CPU', 'GPU1', 'GPU2'):
                    continue
                if str(c).strip().upper() == 'CPU':
                    rename[c] = 'CPU'
                elif 'GPU' in str(c).upper() and '1' in str(c):
                    rename[c] = 'GPU1'
                elif 'GPU' in str(c).upper() and '2' in str(c):
                    rename[c] = 'GPU2'
            if rename:
                df_wide = df_wide.rename(columns=rename)
            # Bucket every ~10 seconds and aggregate (match Torrado's grouping)
            df_wide['bucket'] = (df_wide['Tiempo transcurrido'] / 10).astype(int)
            agg_dict = {'Tiempo transcurrido': 'first'}
            for col in ['CPU', 'GPU1', 'GPU2']:
                if col in df_wide.columns:
                    agg_dict[col] = 'mean'
            df_grouped = df_wide.groupby('bucket').agg(agg_dict).reset_index(drop=True)
            df_grouped = df_grouped.rename(columns={'GPU1': 'GPU 1', 'GPU2': 'GPU 2'})
        else:
            # --- Torrado format: Elapsed time (HH:MM:SS), columns CPU, GPU1, GPU2 ---
            if 'Elapsed time' not in df.columns:
                print(f"[WARNING] Utilization CSV has no 'Elapsed time' column (columns: {list(df.columns)}). Skipping utilization-over-time graph.")
                return
            df['Elapsed time'] = df['Elapsed time'].astype(str).str.strip()
            df['segundos'] = df['Elapsed time'].apply(convert_time_to_seconds)
            segundos = df['segundos'].tolist()
            segundos_corr = []
            acumulado = 0
            for i in range(len(segundos)):
                if i > 0 and segundos[i] < segundos[i - 1]:
                    acumulado += 86400
                segundos_corr.append(segundos[i] + acumulado)
            tiempo_transcurrido = [max(0, s - segundos_corr[0]) for s in segundos_corr]
            df['Tiempo transcurrido'] = tiempo_transcurrido
            for col in ['CPU', 'GPU1', 'GPU2']:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.replace(',', '.').str.strip()
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.dropna(subset=['Tiempo transcurrido'])
            if df.empty:
                print("❌ No hay datos válidos.")
                return
            agg_dict = {'Tiempo transcurrido': 'first'}
            for col in ['CPU', 'GPU1', 'GPU2']:
                if col in df.columns:
                    agg_dict[col] = 'mean'
            df_grouped = df.groupby(df.index // 10).agg(agg_dict).reset_index(drop=True)
            df_grouped = df_grouped.rename(columns={'GPU1': 'GPU 1', 'GPU2': 'GPU 2'})
        
        if df_grouped.empty:
            print("❌ No hay datos válidos.")
            return
        
        # Convertir segundos a formato HH:MM:SS para etiquetas - exactly like Torrado
        df_grouped['Tiempo'] = df_grouped['Tiempo transcurrido'].apply(format_hhmmss)
        
        # Build value_vars list with only available columns
        value_vars = []
        for col in ['CPU', 'GPU 1', 'GPU 2']:
            if col in df_grouped.columns:
                value_vars.append(col)
        
        if not value_vars:
            print("❌ No hay columnas de utilización válidas.")
            return
        
        # Derretir para graficar - exactly like Torrado
        df_melted = df_grouped.melt(id_vars='Tiempo', value_vars=value_vars,
                                    var_name='Componente', value_name='Uso (%)')
        
        # Graficar - exactly like Torrado
        plt.figure(figsize=(16, 6))
        ax = sns.lineplot(data=df_melted, x='Tiempo', y='Uso (%)', hue='Componente')
        
        # Mostrar etiquetas cada 30 minutos - exactly like Torrado
        total = len(df_grouped)
        intervalo = 180 if total > 180 else max(1, total // 15)
        visibles = df_grouped['Tiempo'].iloc[::intervalo].tolist()
        
        for label in ax.get_xticklabels():
            if label.get_text() not in visibles:
                label.set_visible(False)
        
        title = "Utilization for components over time"
        if users and nodes:
            title = "Utilization for components over time, for {} users and {} nodes".format(users, nodes)
        
        plt.title(title)
        plt.xlabel("Elapsed Time (HH:MM:SS)")
        plt.ylabel("Utilization Percentage")
        plt.xticks(rotation=45)
        plt.grid(axis='y', linestyle='--', alpha=0.5)
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"[INFO] Saved utilization over time graph to {output_path}")
    except Exception as e:
        print(f"[WARNING] Failed to generate utilization over time graph: {e}")
        import traceback
        traceback.print_exc()


def process_jmeter_outputs(base_dir: str = "3Hour_Radu"):
    """Process all JMeter raw output files and generate graphs."""
    base_path = Path(base_dir)
    
    if not base_path.exists():
        print(f"[ERROR] Directory {base_dir} does not exist")
        return
    
    # Find ResultsTable.csv files (indicates a test run directory)
    results_table_files = list(base_path.rglob("ResultsTable.csv"))
    
    if not results_table_files:
        # Also check in root directory
        root_results = base_path / "ResultsTable.csv"
        if root_results.exists():
            results_table_files = [root_results]
    
    if not results_table_files:
        print(f"[WARNING] No ResultsTable.csv files found in {base_dir}")
        return
    
    print(f"[INFO] Found {len(results_table_files)} test result directories")
    
    for results_table_path in results_table_files:
        output_dir = results_table_path.parent
        print(f"\n[PROCESSING JMeter Outputs] {output_dir}")
        
        # 1. Arrival Timeline
        plot_arrival_timeline(
            str(results_table_path),
            str(output_dir / "ArrivalTimeline.png")
        )
        
        # 2. Response Times
        resptime_path = output_dir / "RespTime.csv"
        if resptime_path.exists():
            plot_response_times_over_time(
                str(resptime_path),
                str(output_dir / "ResponseTime.png")
            )
        
        # 3. Active Threads
        activethreads_path = output_dir / "ActiveThreadsOT.csv"
        if activethreads_path.exists():
            plot_active_threads(
                str(activethreads_path),
                str(output_dir / "ActiveThreads.png")
            )
        
        # 4. Throughput
        throughput_path = output_dir / "TransactionsperSec.csv"
        if throughput_path.exists():
            plot_throughput(
                str(throughput_path),
                str(output_dir / "Throughput.png")
            )
        
        # 5. Bytes Throughput
        bytes_path = output_dir / "BytesThroughput.persec.csv"
        if bytes_path.exists():
            plot_bytes_throughput(
                str(bytes_path),
                str(output_dir / "BytesThroughput.png")
            )
        
        # 6. Utilization Over Time (from SSH monitoring if available)
        utilization_path = output_dir / "Utilization.csv"
        if not utilization_path.exists():
            utilization_path = output_dir / "UtilizationSSHMon.csv"
        if utilization_path.exists():
            plot_utilization_over_time(
                str(utilization_path),
                str(output_dir / "Utilization.png")
            )
        
        print(f"[COMPLETE] JMeter output graphs generated in {output_dir}/")


def move_jmeter_outputs_to_subfolder(base_dir: str, target_subfolder: str = None):
    """
    Move JMeter output files from the main folder to the appropriate subfolder.
    If target_subfolder is not specified, tries to detect from existing subfolders.
    """
    base_path = Path(base_dir)
    
    # JMeter output files that should be in subfolders, not main folder
    jmeter_files = [
        "ActiveThreadsOT.csv", "ActiveThreadsOT2.csv",
        "BytesThroughput.persec.csv", "BytesThroughput.perSec2.csv",
        "RespTime.csv", "ResponseTime.csv",
        "Results.csv", "Results10.csv",
        "ResultsTable.csv",
        "SummaryReport.csv", "SummaryReport2.csv",
        "TransactionsperSec.csv", "TransactionsperSec2.csv",
        "Utilization.csv", "UtilizationSSHMon.csv",
        # PNG files
        "ActiveThreads.png", "ArrivalTimeline.png",
        "BytesThroughput.png", "ResponseTime.png",
        "Throughput.png", "Utilization.png",
        "UtilizationSSH.png"
    ]
    
    # Find files to move
    files_to_move = []
    for jmeter_file in jmeter_files:
        file_path = base_path / jmeter_file
        if file_path.exists():
            files_to_move.append(file_path)
    
    if not files_to_move:
        return
    
    # Determine target subfolder
    if target_subfolder:
        target_dir = base_path / target_subfolder
    else:
        # Try to find existing subfolders with tool_evaluations files
        subfolders = [d for d in base_path.iterdir() if d.is_dir() and "_" in d.name]
        if subfolders:
            # Use the most recently modified subfolder
            target_dir = max(subfolders, key=lambda x: x.stat().st_mtime)
        else:
            print(f"[WARNING] No target subfolder found for JMeter outputs in {base_dir}")
            return
    
    # Create target directory if needed
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Move files
    print(f"\n[MOVING] JMeter outputs from {base_dir}/ to {target_dir}/")
    for file_path in files_to_move:
        target_path = target_dir / file_path.name
        shutil.move(str(file_path), str(target_path))
        print(f"  Moved: {file_path.name}")
    
    print(f"[COMPLETE] Moved {len(files_to_move)} JMeter files to {target_dir}/")


def generate_summary_files(base_dir: str = "3Hour_Radu"):
    """Generate summary files that aggregate stats across all configurations (like Torrado's)."""
    base_path = Path(base_dir)
    
    if not base_path.exists():
        print(f"[ERROR] Directory {base_dir} does not exist")
        return
    
    print(f"\n[GENERATING] Summary files for {base_dir}...")
    
    # Collect all stats from subfolders
    all_energy_stats = []
    all_util_stats = []
    all_time_stats = []
    
    # Find all output_*_stats.csv files (only in subfolders, not main folder)
    for stats_file in base_path.rglob("output_energy_stats.csv"):
        # Skip if in main folder
        if stats_file.parent == base_path:
            continue
        try:
            df = pd.read_csv(stats_file)
            all_energy_stats.append(df)
        except Exception as e:
            print(f"[WARNING] Could not read {stats_file}: {e}")
    
    for stats_file in base_path.rglob("output_utilization_stats.csv"):
        if stats_file.parent == base_path:
            continue
        try:
            df = pd.read_csv(stats_file)
            all_util_stats.append(df)
        except Exception as e:
            print(f"[WARNING] Could not read {stats_file}: {e}")
    
    for stats_file in base_path.rglob("output_execution_stats.csv"):
        if stats_file.parent == base_path:
            continue
        try:
            df = pd.read_csv(stats_file)
            all_time_stats.append(df)
        except Exception as e:
            print(f"[WARNING] Could not read {stats_file}: {e}")
    
    # Torrado's summary format: tool_name,nodes,users,Metric,mean_value,std_value
    # (no cv column, different column order)
    summary_columns = ["tool_name", "nodes", "users", "Metric", "mean_value", "std_value"]
    
    # Concatenate and save summary files with Torrado's column order
    if all_energy_stats:
        summary_energy = pd.concat(all_energy_stats, ignore_index=True)
        # Reorder columns and drop cv if present
        available_cols = [c for c in summary_columns if c in summary_energy.columns]
        summary_energy = summary_energy[available_cols]
        summary_energy.to_csv(f"{base_dir}/summary_energy_stats.csv", index=False)
        print(f"[INFO] Generated {base_dir}/summary_energy_stats.csv ({len(summary_energy)} rows)")
    
    if all_util_stats:
        summary_util = pd.concat(all_util_stats, ignore_index=True)
        available_cols = [c for c in summary_columns if c in summary_util.columns]
        summary_util = summary_util[available_cols]
        summary_util.to_csv(f"{base_dir}/summary_util_stats.csv", index=False)
        print(f"[INFO] Generated {base_dir}/summary_util_stats.csv ({len(summary_util)} rows)")
    
    if all_time_stats:
        summary_time = pd.concat(all_time_stats, ignore_index=True)
        available_cols = [c for c in summary_columns if c in summary_time.columns]
        summary_time = summary_time[available_cols]
        summary_time.to_csv(f"{base_dir}/summary_time_stats.csv", index=False)
        print(f"[INFO] Generated {base_dir}/summary_time_stats.csv ({len(summary_time)} rows)")
    
    print(f"[COMPLETE] Summary files generated in {base_dir}/")


def find_and_process_all_results(base_dir: str = "3Hour_Radu"):
    """Automatically find all tool_evaluations CSV files and process them."""
    base_path = Path(base_dir)
    
    if not base_path.exists():
        print(f"[ERROR] Directory {base_dir} does not exist")
        return

    # Find all tool_evaluations_*.csv files
    csv_files = list(base_path.rglob("tool_evaluations_*.csv"))
    
    if not csv_files:
        print(f"[WARNING] No tool_evaluations CSV files found in {base_dir}")
        return

    print(f"[INFO] Found {len(csv_files)} tool_evaluations CSV files")
    
    for csv_file in csv_files:
        # Extract users and nodes from path
        # Format: 3Hour_Radu/{users}_{nodes}/tool_evaluations_{nodes}.csv
        parts = csv_file.parts
        folder_name = parts[-2] if len(parts) > 1 else ""
        
        # Parse users_nodes format
        if "_" in folder_name:
            try:
                users_str, nodes_str = folder_name.split("_", 1)
                users = int(users_str)
                nodes = int(nodes_str)
            except ValueError:
                print(f"[WARNING] Could not parse users/nodes from {folder_name}, skipping {csv_file}")
                continue
        else:
            # Try to extract from filename: tool_evaluations_{nodes}.csv
            try:
                nodes = int(csv_file.stem.split("_")[-1])
                users = 1  # Default
            except ValueError:
                print(f"[WARNING] Could not parse nodes from {csv_file.name}, skipping")
                continue

        # Output directory is same as CSV location
        output_dir = csv_file.parent
        
        process_tool_evaluations(
            str(csv_file),
            str(output_dir),
            users,
            nodes
        )
    
    # Generate summary files after processing all
    generate_summary_files(base_dir)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Process JMeter test results and generate graphs")
    parser.add_argument(
        "--csv",
        type=str,
        help="Path to specific tool_evaluations CSV file"
    )
    parser.add_argument(
        "--users",
        type=int,
        help="Number of users (required if --csv specified)"
    )
    parser.add_argument(
        "--nodes",
        type=int,
        help="Number of nodes (required if --csv specified)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all tool_evaluations CSV files in 3Hour_Radu/"
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        default="3Hour_Radu",
        help="Base directory to search (default: 3Hour_Radu)"
    )
    parser.add_argument(
        "--jmeter-only",
        action="store_true",
        help="Only process JMeter raw output files (ResultsTable.csv, RespTime.csv, etc.)"
    )
    
    args = parser.parse_args()
    
    if args.jmeter_only:
        # Move JMeter outputs from main folder to subfolders first
        move_jmeter_outputs_to_subfolder(args.base_dir)
        # Process only JMeter outputs
        process_jmeter_outputs(args.base_dir)
    elif args.all:
        # Move JMeter outputs from main folder to subfolders first
        move_jmeter_outputs_to_subfolder(args.base_dir)
        # Process both tool evaluations and JMeter outputs
        find_and_process_all_results(args.base_dir)
        process_jmeter_outputs(args.base_dir)
    elif args.csv:
        if not args.users or not args.nodes:
            print("[ERROR] --users and --nodes required when using --csv")
            sys.exit(1)
        output_dir = Path(args.csv).parent
        base_dir = str(output_dir.parent)
        # Move JMeter outputs from main folder to this subfolder
        move_jmeter_outputs_to_subfolder(base_dir, output_dir.name)
        process_tool_evaluations(args.csv, str(output_dir), args.users, args.nodes)
        # Also process JMeter outputs in the same directory
        process_jmeter_outputs(str(output_dir))
    else:
        # Default: process all (both tool evaluations and JMeter outputs)
        # Move JMeter outputs from main folder to subfolders first
        move_jmeter_outputs_to_subfolder(args.base_dir)
        find_and_process_all_results(args.base_dir)
        process_jmeter_outputs(args.base_dir)

