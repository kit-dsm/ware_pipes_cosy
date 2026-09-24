"""Commands for preparing the published benchmark and dashboard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .dashboard import build_dashboard, load_df_results
from .results import (
    load_existing_results, load_new_results, merge_results, print_summary,
    validate_cohort, write_results,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    results = commands.add_parser("build-results")
    results.add_argument("--summaries", type=Path, default=Path("experiments/output"))
    results.add_argument("--instance-sets-json", required=True)
    results.add_argument("--sample-size", type=int, required=True)
    results.add_argument("--manifest", type=Path, default=Path("experiments/benchmark_samples.json"))
    results.add_argument("--history-parquet", type=Path)
    results.add_argument("--legacy-pickle", type=Path)
    results.add_argument("--output", type=Path, default=Path("benchmark-results.parquet"))
    site = commands.add_parser("build-site")
    site.add_argument("--input", type=Path, default=Path("benchmark-results.parquet"))
    site.add_argument("--output", type=Path, default=Path("site/data"))
    args = parser.parse_args()

    if args.command == "build-site":
        build_dashboard(load_df_results(args.input), args.output)
        return

    sets = json.loads(args.instance_sets_json)
    if not isinstance(sets, list) or not sets or not all(isinstance(name, str) for name in sets):
        parser.error("--instance-sets-json must be a nonempty JSON list of names")
    history = args.history_parquet if args.history_parquet and args.history_parquet.exists() else args.legacy_pickle
    old = load_existing_results(history) if history and history.exists() else pd.DataFrame()
    new = load_new_results(args.summaries, sets)
    validate_cohort(new, args.manifest, sets, args.sample_size)
    merged = merge_results(old, new)
    write_results(merged, args.output)
    print_summary(merged)


if __name__ == "__main__":
    main()
