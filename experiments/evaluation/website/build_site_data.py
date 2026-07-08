from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
EVALUATION_DIR = SCRIPT_DIR.parent

DF_RESULTS_PATH = EVALUATION_DIR / "df_results.pkl"
SITE_DATA_DIR = SCRIPT_DIR / "site" / "data"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_nonempty(value) -> bool:
    return pd.notna(value) and str(value) not in {"", "None", "nan", "<NA>"}


def short_fp(value, n: int = 8) -> str:
    if not is_nonempty(value):
        return ""
    return str(value)[:n]


def mean_or_none(values: pd.Series):
    values = pd.to_numeric(values, errors="coerce")
    if values.notna().any():
        return float(values.mean())
    return None


def sum_or_zero(values: pd.Series) -> int:
    values = pd.to_numeric(values, errors="coerce")
    if values.notna().any():
        return int(values.sum())
    return 0


def jsonable_records(df: pd.DataFrame) -> list[dict]:
    clean = df.astype(object).where(pd.notna(df), None)
    return clean.to_dict(orient="records")


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def load_df_results(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Run experiments/evaluation/build_results_cache.py first."
        )

    df = pd.read_pickle(path)

    if df.empty:
        raise RuntimeError(f"{path} exists but contains an empty dataframe.")

    return df


def stage_algo(row: pd.Series, stage: str) -> str:
    col = f"{stage}_algo"
    value = row.get(col)
    return str(value) if is_nonempty(value) else "—"


def stage_version(row: pd.Series, stage: str) -> str:
    algo = stage_algo(row, stage)
    if algo == "—":
        return "—"

    own_fp = row.get(f"{stage}_own_fingerprint")
    if not is_nonempty(own_fp):
        own_fp = row.get(f"{stage}_algo_fingerprint")

    fp = short_fp(own_fp)
    return f"{algo}@{fp}" if fp else algo


def stage_display_parts(row: pd.Series) -> list[str]:
    return [
        stage_algo(row, stage)
        for stage in STAGES
        if stage_algo(row, stage) != "—"
    ]


def stage_version_parts(row: pd.Series) -> list[str]:
    return [
        stage_version(row, stage)
        for stage in STAGES
        if stage_version(row, stage) != "—"
    ]


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------

def ensure_required_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    for required in ["instance_set", "instance_name"]:
        if required not in df.columns:
            raise ValueError(f"Missing required column: {required}")

    if "problem_type" not in df.columns:
        df["problem_type"] = ""

    for stage in STAGES:
        algo_col = f"{stage}_algo"
        if algo_col not in df.columns:
            df[algo_col] = pd.NA

        for fp_kind in ["algo", "own", "chain"]:
            fp_col = f"{stage}_{fp_kind}_fingerprint"
            short_col = f"{stage}_{fp_kind}_fp_short"

            if fp_col not in df.columns:
                df[fp_col] = pd.NA

            if short_col not in df.columns:
                df[short_col] = df[fp_col].map(short_fp)

    for metric in METRICS:
        if metric in df.columns:
            df[metric] = pd.to_numeric(df[metric], errors="coerce")

    return df


def add_pipeline_identity(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    def build_pipeline_key(row: pd.Series) -> str:
        return "|".join(stage_algo(row, stage) for stage in STAGES)

    def build_pipeline_label(row: pd.Series) -> str:
        parts = stage_display_parts(row)
        return " · ".join(parts) if parts else "unknown pipeline"

    def build_pipeline_version_key(row: pd.Series) -> str:
        return "|".join(stage_version(row, stage) for stage in STAGES)

    def build_pipeline_version_label(row: pd.Series) -> str:
        parts = stage_version_parts(row)
        return " · ".join(parts) if parts else "unknown version"

    df["pipeline_key"] = df.apply(build_pipeline_key, axis=1)
    df["pipeline_label"] = df.apply(build_pipeline_label, axis=1)
    df["pipeline_version_key"] = df.apply(build_pipeline_version_key, axis=1)
    df["pipeline_version_label"] = df.apply(build_pipeline_version_label, axis=1)

    return df


def add_metric_gaps(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    for metric, direction in METRICS.items():
        if metric not in df.columns:
            continue

        gap_col = f"{metric}_gap_pct"
        best_col = f"{metric}_is_best"

        df[gap_col] = np.nan
        df[best_col] = False

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

        df.loc[valid, gap_col] = gap.clip(lower=0.0)
        df.loc[valid, best_col] = is_best

    return df


def prepare_raw(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_required_columns(df)
    df = add_pipeline_identity(df)
    df = add_metric_gaps(df)
    return df


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def base_group_columns() -> list[str]:
    return [
        "instance_set",
        "problem_type",
        "pipeline_key",
        "pipeline_label",
        "item_assignment_algo",
        "batching_algo",
        "routing_algo",
        "scheduling_algo",
    ]


def make_pipeline_instance_results(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Grain:
      one row = instance_set × pipeline_key × instance_name

    This answers:
      how did this unversioned pipeline configuration perform on each instance?
    """
    group_cols = base_group_columns() + ["instance_name"]
    records = []

    for keys, g in raw.groupby(group_cols, dropna=False):
        record = dict(zip(group_cols, keys))

        record["n_result_rows"] = int(len(g))
        record["n_versions"] = int(g["pipeline_version_key"].nunique())

        for metric in METRICS:
            if metric not in g.columns:
                continue

            record[metric] = mean_or_none(g[metric])
            record[f"{metric}_gap_pct"] = mean_or_none(g[f"{metric}_gap_pct"])
            record[f"{metric}_is_best"] = bool(g[f"{metric}_is_best"].fillna(False).any())

        records.append(record)

    out = pd.DataFrame(records)

    return out.sort_values(
        ["instance_set", "pipeline_label", "instance_name"],
        kind="stable",
    ).reset_index(drop=True)


def make_main_results(pipeline_instances: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    """
    Grain:
      one row = instance_set × pipeline_key

    This answers:
      how does this unversioned pipeline configuration perform over the selected instance set?
    """
    group_cols = base_group_columns()

    version_counts = (
        raw.groupby(["instance_set", "pipeline_key"], dropna=False)["pipeline_version_key"]
        .nunique()
        .reset_index(name="n_versions_total")
    )

    records = []

    for keys, g in pipeline_instances.groupby(group_cols, dropna=False):
        record = dict(zip(group_cols, keys))

        record["n_instances"] = int(g["instance_name"].nunique())
        record["n_result_rows"] = int(g["n_result_rows"].sum())

        for metric in METRICS:
            if metric not in g.columns:
                continue

            record[metric] = mean_or_none(g[metric])
            record[f"{metric}_gap_pct"] = mean_or_none(g[f"{metric}_gap_pct"])
            record[f"{metric}_best_count"] = sum_or_zero(g[f"{metric}_is_best"].astype(int))

        records.append(record)

    out = pd.DataFrame(records)

    if not out.empty:
        out = out.merge(
            version_counts,
            on=["instance_set", "pipeline_key"],
            how="left",
        )
        out["n_versions"] = out["n_versions_total"].fillna(0).astype(int)
        out = out.drop(columns=["n_versions_total"])

    return out.sort_values(
        ["instance_set", "pipeline_label"],
        kind="stable",
    ).reset_index(drop=True)


def make_pipeline_version_results(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Grain:
      one row = instance_set × pipeline_key × pipeline_version_key

    This answers:
      how did different versions of the same unversioned pipeline configuration perform?
    """
    instance_group_cols = base_group_columns() + [
        "pipeline_version_key",
        "pipeline_version_label",
        "item_assignment_own_fp_short",
        "batching_own_fp_short",
        "routing_own_fp_short",
        "scheduling_own_fp_short",
        "instance_name",
    ]

    instance_records = []

    for keys, g in raw.groupby(instance_group_cols, dropna=False):
        record = dict(zip(instance_group_cols, keys))

        record["n_result_rows"] = int(len(g))

        for metric in METRICS:
            if metric not in g.columns:
                continue

            record[metric] = mean_or_none(g[metric])
            record[f"{metric}_gap_pct"] = mean_or_none(g[f"{metric}_gap_pct"])
            record[f"{metric}_is_best"] = bool(g[f"{metric}_is_best"].fillna(False).any())

        instance_records.append(record)

    version_instances = pd.DataFrame(instance_records)

    if version_instances.empty:
        return version_instances

    version_group_cols = [
        c for c in instance_group_cols
        if c != "instance_name"
    ]

    records = []

    for keys, g in version_instances.groupby(version_group_cols, dropna=False):
        record = dict(zip(version_group_cols, keys))

        record["n_instances"] = int(g["instance_name"].nunique())
        record["n_result_rows"] = int(g["n_result_rows"].sum())

        for metric in METRICS:
            if metric not in g.columns:
                continue

            record[metric] = mean_or_none(g[metric])
            record[f"{metric}_gap_pct"] = mean_or_none(g[f"{metric}_gap_pct"])
            record[f"{metric}_best_count"] = sum_or_zero(g[f"{metric}_is_best"].astype(int))

        records.append(record)

    out = pd.DataFrame(records)

    return out.sort_values(
        ["instance_set", "pipeline_label", "pipeline_version_label"],
        kind="stable",
    ).reset_index(drop=True)


def make_overview(raw: pd.DataFrame, main_results: pd.DataFrame) -> dict:
    by_instance_set = (
        raw.groupby("instance_set", dropna=False)
        .agg(
            raw_result_rows=("instance_name", "count"),
            n_instances=("instance_name", "nunique"),
            n_pipeline_versions=("pipeline_version_key", "nunique"),
        )
        .reset_index()
        .merge(
            main_results.groupby("instance_set", dropna=False)
            .size()
            .reset_index(name="n_pipeline_configurations"),
            on="instance_set",
            how="left",
        )
    )

    return {
        "raw_result_rows": int(len(raw)),
        "dashboard_rows": int(len(main_results)),
        "n_instance_sets": int(raw["instance_set"].nunique()),
        "n_instances": int(raw["instance_name"].nunique()),
        "by_instance_set": jsonable_records(by_instance_set),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    df = load_df_results(DF_RESULTS_PATH)
    raw = prepare_raw(df)

    pipeline_instances = make_pipeline_instance_results(raw)
    main_results = make_main_results(pipeline_instances, raw)
    pipeline_versions = make_pipeline_version_results(raw)

    write_json(SITE_DATA_DIR / "results.json", jsonable_records(main_results))
    write_json(SITE_DATA_DIR / "pipeline_instances.json", jsonable_records(pipeline_instances))
    write_json(SITE_DATA_DIR / "pipeline_versions.json", jsonable_records(pipeline_versions))
    write_json(SITE_DATA_DIR / "overview.json", make_overview(raw, main_results))

    print(f"Read raw rows:                  {len(raw)}")
    print(f"Wrote main dashboard rows:       {len(main_results)}")
    print(f"Wrote pipeline-instance rows:    {len(pipeline_instances)}")
    print(f"Wrote pipeline-version rows:     {len(pipeline_versions)}")
    print(f"Wrote: {SITE_DATA_DIR / 'results.json'}")
    print(f"Wrote: {SITE_DATA_DIR / 'pipeline_instances.json'}")
    print(f"Wrote: {SITE_DATA_DIR / 'pipeline_versions.json'}")
    print(f"Wrote: {SITE_DATA_DIR / 'overview.json'}")


if __name__ == "__main__":
    main()