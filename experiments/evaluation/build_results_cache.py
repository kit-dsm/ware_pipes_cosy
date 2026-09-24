"""Compatibility entry point for local benchmark result builds."""

from pathlib import Path

from ware_ops_pipes.benchmark_results.results import (
    SETS_TO_LOAD, load_existing_results, load_new_results, merge_results,
    print_summary, write_results,
)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    available = [name for name in SETS_TO_LOAD if next((root / "output" / name).glob("*/*__summary.json"), None)]
    old = load_existing_results(Path(__file__).with_name("df_results.parquet"))
    new = load_new_results(root / "output", available) if available else old.iloc[0:0].copy()
    merged = merge_results(old, new)
    if merged.empty:
        raise RuntimeError("No benchmark summaries found")
    output = Path(__file__).with_name("df_results.parquet")
    write_results(merged, output)
    print_summary(merged)
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
