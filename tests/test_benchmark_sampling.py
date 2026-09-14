from experiments.benchmark_sampling import select_representative_instances
from experiments.prune_release_assets import stale_cache_assets


def test_sampling_is_deterministic_nested_and_family_balanced():
    names = [
        f"unit_F{facilities}_C{capacity}_{replicate}"
        for facilities in (1, 5, 10)
        for capacity in (30, 60, 180)
        for replicate in range(20)
    ]

    sample_20 = select_representative_instances("SPRP", names, 20)
    sample_100 = select_representative_instances("SPRP", names, 100)

    assert sample_20 == select_representative_instances("SPRP", reversed(names), 20)
    assert sample_100[:20] == sample_20
    assert len(set(sample_100)) == 100
    assert {name.split("_")[1] for name in sample_20} == {"F1", "F5", "F10"}
    assert {name.split("_")[2] for name in sample_20} == {"C30", "C60", "C180"}


def test_stale_cache_cleanup_is_scoped_to_completed_sets_and_generation():
    assets = [
        {"id": 1, "name": "cache__SPRP__new123__0-of-10.tar.gz"},
        {"id": 2, "name": "cache__SPRP__old456__0-of-10.tar.gz"},
        {"id": 3, "name": "cache-SPRP-0-of-10.tar.gz"},
        {"id": 4, "name": "cache-SPRP.tar.gz"},
        {"id": 5, "name": "cache__SPRP-SS__old456__0-of-10.tar.gz"},
        {"id": 6, "name": "benchmark-results.tar.gz"},
    ]

    stale = stale_cache_assets(assets, {"SPRP"}, "new123")
    assert [asset["id"] for asset in stale] == [2, 3, 4]
