from pathlib import Path

from ware_ops_algos.domain_models import load_and_flatten_data_card

from ware_ops_pipes.synthesis.runner import PipelineRunner


class _Runner(PipelineRunner):
    def discover_instances(self):
        return []

    def load_domain(self, instance_name, file_paths):
        raise NotImplementedError


def test_instance_shards_are_deterministic_and_disjoint(monkeypatch, tmp_path):
    instances = [(f"instance-{index:03}", []) for index in reversed(range(120))]
    runner = _Runner.__new__(_Runner)
    runner.project_root = tmp_path
    runner.instance_set_name = "missing-local-manifest"
    monkeypatch.setenv("BENCHMARK_SAMPLE_SIZE", "100")
    monkeypatch.setenv("BENCHMARK_SHARD_COUNT", "10")

    shards = []
    for shard_index in range(10):
        monkeypatch.setenv("BENCHMARK_SHARD_INDEX", str(shard_index))
        shards.append(runner._select_instances(instances))

    names = [name for shard in shards for name, _ in shard]
    assert len(names) == 100
    assert len(set(names)) == 100
    assert set(names) == {f"instance-{index:03}" for index in range(100)}
    assert all(len(shard) == 10 for shard in shards)


def test_manifest_order_defines_nested_sample(monkeypatch, tmp_path):
    names = [f"instance-{index}" for index in range(10)]
    manifest_path = tmp_path / "samples.json"
    manifest_path.write_text(
        '{"sets":{"set-a":["instance-8","instance-2","instance-5"]}}',
        encoding="utf-8",
    )
    runner = _Runner.__new__(_Runner)
    runner.project_root = tmp_path
    runner.instance_set_name = "set-a"
    monkeypatch.setenv("BENCHMARK_SAMPLE_MANIFEST", str(manifest_path))
    monkeypatch.setenv("BENCHMARK_SAMPLE_SIZE", "2")
    monkeypatch.setenv("BENCHMARK_SHARD_COUNT", "1")
    monkeypatch.setenv("BENCHMARK_SHARD_INDEX", "0")

    assert [name for name, _ in runner._select_instances((n, []) for n in names)] == [
        "instance-8",
        "instance-2",
    ]


def test_current_upstream_configured_local_search_cards_are_registered(tmp_path):
    project_root = Path(__file__).parents[1]
    data_card = load_and_flatten_data_card(
        project_root / "data" / "data_cards" / "foodmart.yaml"
    )
    runner = _Runner(
        instance_set_name="test",
        instances_dir=tmp_path,
        cache_dir=tmp_path / "cache",
        project_root=project_root,
        data_card=data_card,
        verbose=False,
    )

    configured_names = {
        card.algo_name
        for card in runner.algos
        if (card.implementation or {}).get("class_name") == "LocalSearchBatching"
    }
    assert configured_names
    assert configured_names <= runner.repo_class_by_algo_name.keys()
    assert all(
        runner.repo_class_by_algo_name[name].start_batching_cls is not None
        and runner.repo_class_by_algo_name[name].routing_class is not None
        for name in configured_names
    )
