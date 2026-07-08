from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
EVALUATION_DIR = SCRIPT_DIR.parent

DF_RESULTS_PATH = EVALUATION_DIR / "df_results.pkl"
SITE_DATA_DIR = SCRIPT_DIR / "site" / "data"


STAGES = [
    "item_assignment",
    "batching",
    "routing",
    "scheduling",
]

METRICS = {
    "total_distance": "min",
    "total_cpu_time": "min",
    "makespan": "min",
    "on_time_rate": "max",
    "max_tardiness": "min",
    "avg_tardiness": "min",
    "avg_lateness": "min",
    "max_lateness": "min",
}


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def to_jsonable_records(df: pd.DataFrame) -> list[dict]:
    clean = df.replace({np.nan: None})
    return clean.to_dict(orient="records")


def load_df_results(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run build_results_cache.py first.")

    df = pd.read_pickle(path)

    if df.empty:
        raise RuntimeError(f"{path} exists but contains an empty dataframe.")

    return df


def add_metric_gaps(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    for metric, direction in METRICS.items():
        if metric not in df.columns:
            continue

        df[metric] = pd.to_numeric(df[metric], errors="coerce")
        valid = df[metric].notna()

        if not valid.any():
            continue

        grouped = df.loc[valid].groupby(
            ["instance_set", "instance_name"],
            dropna=False,
        )[metric]

        if direction == "min":
            best = grouped.transform("min")
            gap = ((df.loc[valid, metric] - best) / best.abs().clip(lower=1e-9)) * 100.0
            is_best = df.loc[valid, metric].eq(best)
        else:
            best = grouped.transform("max")
            gap = ((best - df.loc[valid, metric]) / best.abs().clip(lower=1e-9)) * 100.0
            is_best = df.loc[valid, metric].eq(best)

        df.loc[valid, f"{metric}_gap_pct"] = gap.clip(lower=0.0)
        df.loc[valid, f"{metric}_is_best"] = is_best

    return df


def make_dashboard_results(df: pd.DataFrame) -> pd.DataFrame:
    df = add_metric_gaps(df)

    group_cols = [
        "instance_set",
        "problem_type",
        "strategy",
        "strategy_versioned",
        "item_assignment_algo",
        "batching_algo",
        "routing_algo",
        "scheduling_algo",
    ]

    group_cols = [c for c in group_cols if c in df.columns]

    records = []

    for keys, g in df.groupby(group_cols, dropna=False):
        record = dict(zip(group_cols, keys))
        record["config_label"] = "-".join(
            str(x)
            for x in [
                record.get("item_assignment_algo"),
                record.get("batching_algo"),
                record.get("routing_algo"),
                record.get("scheduling_algo"),
            ]
            if pd.notna(x) and str(x) not in {"", "None", "nan"}
        )
        record["n_instances"] = int(g["instance_name"].nunique())
        record["n_result_rows"] = int(len(g))

        for metric in METRICS:
            if metric not in g.columns:
                continue

            values = pd.to_numeric(g[metric], errors="coerce")
            record[metric] = float(values.mean()) if values.notna().any() else None

            gap_col = f"{metric}_gap_pct"
            if gap_col in g.columns:
                gaps = pd.to_numeric(g[gap_col], errors="coerce")
                record[f"{metric}_gap_pct"] = float(gaps.mean()) if gaps.notna().any() else None

            best_col = f"{metric}_is_best"
            if best_col in g.columns:
                best_count = g.loc[g[best_col].fillna(False), "instance_name"].nunique()
                record[f"{metric}_best_count"] = int(best_count)

        records.append(record)

    out = pd.DataFrame(records)

    return out.sort_values(
        ["instance_set", "strategy_versioned"],
        kind="stable",
    ).reset_index(drop=True)


def make_overview(raw: pd.DataFrame, dashboard: pd.DataFrame) -> dict:
    return {
        "raw_result_rows": int(len(raw)),
        "dashboard_rows": int(len(dashboard)),
        "n_instance_sets": int(raw["instance_set"].nunique()),
        "n_instances": int(raw["instance_name"].nunique()),
        "by_instance_set": (
            raw.groupby("instance_set", dropna=False)
            .agg(
                raw_result_rows=("instance_name", "count"),
                n_instances=("instance_name", "nunique"),
            )
            .reset_index()
            .merge(
                dashboard.groupby("instance_set", dropna=False)
                .size()
                .reset_index(name="pipeline_configurations"),
                on="instance_set",
                how="left",
            )
            .to_dict(orient="records")
        ),
    }


def main() -> None:
    raw = load_df_results(DF_RESULTS_PATH)
    dashboard = make_dashboard_results(raw)

    write_json(SITE_DATA_DIR / "results.json", to_jsonable_records(dashboard))
    write_json(SITE_DATA_DIR / "overview.json", make_overview(raw, dashboard))

    print(f"Read raw rows:       {len(raw)}")
    print(f"Wrote dashboard rows: {len(dashboard)}")
    print(f"Wrote: {SITE_DATA_DIR / 'results.json'}")
    print(f"Wrote: {SITE_DATA_DIR / 'overview.json'}")


if __name__ == "__main__":
    main()