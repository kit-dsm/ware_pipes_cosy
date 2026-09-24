"""Compatibility entry point for building the benchmark dashboard."""

from pathlib import Path

from ware_ops_pipes.benchmark_results.dashboard import (
    build_dashboard, load_df_results, prepare_raw, make_pipeline_instance_results,
    make_main_results, make_pipeline_version_results,
)


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    build_dashboard(load_df_results(root / "benchmark-results.parquet"), root / "site/data")


if __name__ == "__main__":
    main()
