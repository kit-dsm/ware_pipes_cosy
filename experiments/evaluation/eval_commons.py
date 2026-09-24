"""Legacy analysis helpers; result loading lives in the installed package."""

import re
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from ware_ops_pipes.benchmark_results.loading import (
    create_summary_dataframe, load_summary_jsons, load_summary_jsons_fast,
)

def build_strategy(row):
    cols = ["item_assignment_algo", "batching_algo", "routing_algo", "scheduling_algo"]
    parts = [str(row[c]) for c in cols if pd.notna(row[c]) and row[c] != ""]
    return "+".join(parts)


def vbs_analysis(df, metric_col="total_distance", strategy_col="strategy", instance_col="instance_name", min_max="min"):
    """
    Performs VBS vs SBS analysis.
    Returns a DataFrame with SBS mean, VBS mean, mean regret, and relative gain.
    """
    results = []
    # VBS per instance
    if min_max == "min":
        vbs_per_instance = df.groupby(instance_col)[metric_col].min()
    else:
        vbs_per_instance = df.groupby(instance_col)[metric_col].max()
    vbs_strategies = df.loc[df.groupby("instance_name")[metric_col].idxmin(), ["instance_name", "strategy"]]
    vbs_mean = vbs_per_instance.mean()

    # SBS (best on average in group)
    avg_by_strategy = df.groupby(strategy_col)[metric_col].mean()
    if min_max == "min":
        sbs_strategy = avg_by_strategy.idxmin()
        sbs_mean = avg_by_strategy.min()
    else:
        sbs_strategy = avg_by_strategy.idxmax()
        sbs_mean = avg_by_strategy.max()
    # SBS performance per instance
    sbs_perf_per_instance = df[df[strategy_col] == sbs_strategy].set_index(instance_col)[metric_col]
    winner_counts = vbs_strategies["strategy"].value_counts()
    if min_max == "min":
        # lower is better
        regret = sbs_perf_per_instance - vbs_per_instance
        rel_gain = 100 * (sbs_mean - vbs_mean) / sbs_mean
    else:
        # higher is better
        regret = vbs_per_instance - sbs_perf_per_instance
        rel_gain = 100 * (vbs_mean - sbs_mean) / sbs_mean

    results.append({
        "instance_set": df["instance_set"].unique()[0],
        "SBS Strategy": sbs_strategy,
        "SBS Mean": sbs_mean,
        "VBS Mean": vbs_mean,
        # "Mean Regret": mean_regret,
        "Relative Gain %": rel_gain
    })

    return pd.DataFrame(results), winner_counts


def grouped_vbs_analysis(df, group_col, metric_col="total_distance", strategy_col="strategy",
                         instance_col="instance_name"):
    """
    Performs VBS vs SBS analysis grouped by a category (e.g., storage policy).
    Returns a DataFrame with SBS mean, VBS mean, mean regret, and relative gain per group.
    """
    results = []
    winner_counts = 0
    for group, subdf in df.groupby(group_col):
        # VBS per instance
        vbs_per_instance = subdf.groupby(instance_col)[metric_col].min()
        vbs_mean = vbs_per_instance.mean()
        vbs_strategies = subdf.loc[
            subdf.groupby("instance_name")["total_distance"].idxmin(), ["instance_name", "strategy"]]

        # SBS (best on average in group)
        avg_by_strategy = subdf.groupby(strategy_col)[metric_col].mean()
        sbs_strategy = avg_by_strategy.idxmin()
        sbs_mean = avg_by_strategy.min()

        # SBS performance per instance
        sbs_perf_per_instance = subdf[subdf[strategy_col] == sbs_strategy].set_index(instance_col)[metric_col]

        # Regret
        regret = sbs_perf_per_instance - vbs_per_instance
        mean_regret = regret.mean()
        rel_gain = 100 * (sbs_mean - vbs_mean) / sbs_mean
        winner_counts = vbs_strategies["strategy"].value_counts()

        results.append({
            group_col: group,
            "SBS Strategy": sbs_strategy,
            "SBS Mean": sbs_mean,
            "VBS Mean": vbs_mean,
            # "Mean Regret": mean_regret,
            "Relative Gain %": rel_gain
        })

    return pd.DataFrame(results), winner_counts


def plot_winners(winner_counts: pd.DataFrame()):
    plt.figure(figsize=(8, 4))
    top_winners = winner_counts.head(10)
    sns.barplot(x=top_winners.values, y=top_winners.index, palette="Blues_r", hue=top_winners.index, legend=False)
    plt.xlabel("Number of Instances Won")
    plt.ylabel("Strategy")
    plt.title("Top Winning Strategies (VBS)")
    plt.tight_layout()
    plt.show()


def plot_winners_pareto(winner_counts: pd.DataFrame()):
    plt.figure(figsize=(8, 6))
    winner_percent = winner_counts / winner_counts.sum() * 100
    winner_percent.sort_values().plot(kind='barh', color='skyblue')
    plt.xlabel("Percentage of Instances Won (%)")
    plt.ylabel("Strategy")
    plt.title("Overall VBS Winner Distribution")
    plt.show()


def parse_solution_file(filepath):
    """Parse a single solution file into batch/order data."""
    text = Path(filepath).read_text()

    # Parse batch lines
    batches = []
    for m in re.finditer(
            r'PickerID\t(\d+)\tBatchID\t(\d+)\tPreviousBatch\t(\d+)\tNoOders\t(\d+)\tNoOderLines\t(\d+)\tBatchDistance\t(\d+)\tBatchComplTime\t(\d+)',
            text):
        batches.append({
            'picker_id': int(m[1]), 'batch_id': int(m[2]),
            'n_orders': int(m[4]), 'n_lines': int(m[5]),
            'distance': int(m[6]), 'completion_time': int(m[7]),
        })

    # Parse order lines
    orders = []
    for m in re.finditer(
            r'OrderID\t(\d+)\tNoOrderLines\t(\d+)\tNextOrderID\t(\d+)\tPickerID\t(\d+)\tBatchID\t(\d+)\tDueTime\t(\d+)\tCompletionTime\t(\d+)',
            text):
        orders.append({
            'order_id': int(m[1]), 'due_time': int(m[6]),
            'completion_time': int(m[7]),
        })

    # Aggregate
    total_distance = sum(b['distance'] for b in batches)
    makespan = max(b['completion_time'] for b in batches)
    tardiness = sum(max(0, o['completion_time'] - o['due_time']) for o in orders)
    max_tardiness = max((max(0, o['completion_time'] - o['due_time']) for o in orders), default=0)
    n_tardy = sum(1 for o in orders if o['completion_time'] > o['due_time'])
    n_on_time = sum(1 for o in orders if o['completion_time'] <= o['due_time'])
    on_time_rate = n_on_time / len(orders) * 100

    return {
        'best_total_distance': total_distance,
        'best_makespan': makespan,
        'best_tardiness': tardiness,
        'best_max_tardiness': max_tardiness,
        'best_on_time_rate': on_time_rate,
        'best_n_tardy': n_tardy,
        'best_n_batches': len(batches),
        'n_orders': len(orders),
        'n_pickers': len(set(b['picker_id'] for b in batches)),
    }


def parse_solution_dir(directory, instance_set="KrisSmallData", glob="*.txt"):
    """Parse all solution files in a directory into a DataFrame."""
    rows = []
    for fp in sorted(Path(directory).glob(glob)):
        split_name = fp.stem.split("_")
        row = parse_solution_file(fp)
        # row['instance_set_'] = instance_set
        row['instance_name'] = f"instances_{split_name[2]}_{split_name[3]}"
        rows.append(row)
    return pd.DataFrame(rows)