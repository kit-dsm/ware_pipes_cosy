import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from ware_ops_pipes.benchmark_results.dashboard import build_dashboard
from ware_ops_pipes.benchmark_results.cli import main as results_cli
from ware_ops_pipes.benchmark_results.features import instance_features, loader_timing
from ware_ops_pipes.benchmark_results.loading import create_summary_dataframe
from ware_ops_pipes.benchmark_results.results import (
    load_new_results, merge_results, read_results, validate_cohort, write_results,
)
from ware_ops_pipes.pipelines.templates.cosy_template import InstanceLoader, file_sha256


def _row(instance="a", distance=10, fingerprint="fp"):
    return {
        "instance_set": "SPRP", "instance_name": instance,
        "pipeline_chain_fingerprint": fingerprint,
        "routing_algo": "SShape", "total_distance": distance,
    }


def test_instance_metadata_is_flattened_and_old_summaries_get_nulls():
    summary = {**_row(), "tours_summary": {"total_distance": 10},
               "instance_features": {"n_orders": 4, "n_aisles": 2},
               "loader_timing": {"instance_load_time": 0.5, "layout_cache_hit": True}}
    frame = create_summary_dataframe([summary, {**_row("old"), "tours_summary": {}}])
    assert frame.loc[0, "n_orders"] == 4
    assert frame.loc[0, "instance_load_time"] == 0.5
    assert bool(frame.loc[0, "layout_cache_hit"])
    assert pd.isna(frame.loc[1, "n_orders"])


def test_features_and_cache_timing_for_two_loader_shapes(tmp_path):
    orders = SimpleNamespace(orders=[SimpleNamespace(order_positions=[1, 2]), SimpleNamespace(order_positions=[3])])
    resources = SimpleNamespace(resources=[1, 2])
    storage = SimpleNamespace(get_type_value=lambda: "dedicated")
    for graph in (SimpleNamespace(n_pick_locations=10, n_aisles=3, n_blocks=2),
                  SimpleNamespace(n_pick_locations=5, n_aisles=1)):
        features = instance_features(orders, resources, storage, SimpleNamespace(graph_data=graph))
        assert features["n_orders"] == 2
        assert features["n_order_lines"] == 3
        assert features["n_resources"] == 2
        assert features["n_aisles"] == graph.n_aisles

    layout = tmp_path / "layout.pkl"
    instance = tmp_path / "orders.pkl"
    Path(f"{layout}.timing.json").write_text(json.dumps({
        "instance_token": "other", "total_time": 7.0,
    }), encoding="utf-8")
    Path(f"{instance}.timing.json").write_text(json.dumps({
        "instance_token": "current", "parse_time": 1.0,
        "build_time": 2.0, "total_time": 3.0,
    }), encoding="utf-8")
    timing = loader_timing(str(layout), str(instance), "current")
    assert timing["layout_cache_hit"] is True
    assert timing["layout_load_time"] == 0
    assert timing["instance_cache_hit"] is False
    assert timing["instance_load_time"] == 3.0


def test_instance_file_hash_changes_with_contents(tmp_path):
    path = tmp_path / "instance.txt"
    path.write_text("first", encoding="utf-8")
    before = file_sha256(path)
    task = SimpleNamespace(pipeline_params=SimpleNamespace(
        instance_set_name="SPRP", instance_name="a", instance_path=str(path),
        loader_cls=type("ExampleLoader", (), {}), loader_kwargs={},
    ))
    before_config = InstanceLoader.config_fingerprint_payload(task)
    path.write_text("second", encoding="utf-8")
    assert file_sha256(path) != before
    assert InstanceLoader.config_fingerprint_payload(task)["instance_file_hash"] != before_config["instance_file_hash"]


def test_partial_history_merge_parquet_and_dashboard(tmp_path):
    old = pd.DataFrame([_row("a", 20), _row("b", 30)])
    old["routing_config"] = [{"limit": 5}, None]
    new = pd.DataFrame([_row("a", 10)])
    new["routing_config"] = [{"limit": 10}]
    new["n_orders"] = [4]
    merged = merge_results(old, new)
    assert list(merged["instance_name"]) == ["a", "b"]
    assert list(merged["total_distance"]) == [10, 30]

    path = tmp_path / "results.parquet"
    write_results(merged, path)
    restored = read_results(path)
    assert json.loads(restored.loc[0, "routing_config"]) == {"limit": 10}
    assert pd.isna(restored.loc[1, "n_orders"])
    build_dashboard(restored, tmp_path / "site")
    for name in ("results", "pipeline_instances", "pipeline_versions", "overview"):
        assert (tmp_path / "site" / f"{name}.json").exists()
    assert len(json.loads((tmp_path / "site/results.json").read_text(encoding="utf-8"))) == 1


def test_cohort_validation_requires_all_selected_instances(tmp_path):
    manifest = tmp_path / "samples.json"
    manifest.write_text(json.dumps({"sets": {"SPRP": ["a", "b"]}}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="missing summaries"):
        validate_cohort(pd.DataFrame([_row("a")]), manifest, ["SPRP"], 2)
    validate_cohort(pd.DataFrame([_row("a"), _row("b")]), manifest, ["SPRP"], 2)


def test_summary_loading_is_sorted_and_requested_sets_are_required(tmp_path):
    for instance in ("b", "a"):
        folder = tmp_path / "SPRP" / instance
        folder.mkdir(parents=True)
        (folder / "routing__fingerprint__summary.json").write_text(
            json.dumps({"instance_set": "SPRP", "instance_name": instance,
                        "tours_summary": {"total_distance": 1}}), encoding="utf-8",
        )
    frame = load_new_results(tmp_path, ["SPRP"])
    assert list(frame["instance_name"]) == ["a", "b"]
    with pytest.raises(RuntimeError, match="No summaries found"):
        load_new_results(tmp_path, ["SPRP", "FoodmartData"])


def test_build_results_command_migrates_legacy_history(tmp_path, monkeypatch):
    summary_dir = tmp_path / "summaries" / "SPRP" / "new"
    summary_dir.mkdir(parents=True)
    (summary_dir / "routing__fingerprint__summary.json").write_text(
        json.dumps({"instance_set": "SPRP", "instance_name": "new",
                    "tours_summary": {"total_distance": 9}}), encoding="utf-8",
    )
    manifest = tmp_path / "samples.json"
    manifest.write_text(json.dumps({"sets": {"SPRP": ["new"]}}), encoding="utf-8")
    legacy = tmp_path / "df_results.pkl"
    pd.DataFrame([_row("old")]).to_pickle(legacy)
    output = tmp_path / "benchmark-results.parquet"
    monkeypatch.setattr(sys, "argv", [
        "benchmark-results", "build-results", "--summaries", str(tmp_path / "summaries"),
        "--instance-sets-json", '["SPRP"]', "--sample-size", "1",
        "--manifest", str(manifest), "--legacy-pickle", str(legacy),
        "--output", str(output),
    ])
    results_cli()
    assert set(read_results(output)["instance_name"]) == {"old", "new"}
