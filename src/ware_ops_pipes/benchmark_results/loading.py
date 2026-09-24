import os
from pathlib import Path
import json
import pandas as pd
import numpy as np
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed
import orjson
from tqdm.auto import tqdm
_USE_TQDM = True

def _path_metadata(path: Path, base: Path) -> dict:
    rel = path.relative_to(base)
    parts = rel.parts

    if len(parts) != 3:
        return {
            "_path_instance_set": None,
            "_path_instance_name": None,
            "_path_pipeline_chain_fingerprint": None,
            "_path_result_aggregation": None,
        }

    filename = parts[2]
    suffix = "__summary.json"

    if not filename.endswith(suffix):
        return {
            "_path_instance_set": None,
            "_path_instance_name": None,
            "_path_pipeline_chain_fingerprint": None,
            "_path_result_aggregation": None,
        }

    prefix = filename[:-len(suffix)]
    component_key, chain_fingerprint = prefix.rsplit("__", 1)

    return {
        "_path_instance_set": parts[0],
        "_path_instance_name": parts[1],
        "_path_pipeline_chain_fingerprint": chain_fingerprint,
        "_path_result_aggregation": component_key,
    }


def _collect_paths_by_set(base_path: str, sets_to_load: list[str]) -> dict[str, list[Path]]:
    base = Path(base_path)
    by_set: dict[str, list[Path]] = {}

    for instance_set in sets_to_load:
        inst_set_dir = base / instance_set
        print(f"Searching: {inst_set_dir.resolve()}")

        if not inst_set_dir.is_dir():
            continue

        paths = sorted(inst_set_dir.glob("*/*__summary.json"))

        print(f"  found {len(paths)} summary files")

        if paths:
            by_set[instance_set] = paths

    return by_set

def load_summary_jsons(base_path: str, sets_to_load: list[str]) -> list[dict]:
    base = Path(base_path)
    by_set = _collect_paths_by_set(base_path, sets_to_load)

    data = []

    for paths in by_set.values():
        for path in paths:
            row = _load_one(path, base)
            if row is not None:
                data.append(row)

    return data


def create_summary_dataframe(summary_data: List[Dict]) -> pd.DataFrame:
    rows = []

    stage_to_field = {
        "item_assignment": "item_assignment_algo",
        "batching": "batching_algo",
        "routing": "routing_algo",
        "scheduling": "scheduling_algo",
    }

    for data in summary_data:
        row = {
            "file_path": data.get("file_path"),
            "instance_name": data.get("instance_name") or data.get("_path_instance_name"),
            "instance_set": data.get("instance_set") or data.get("_path_instance_set"),
            "pipeline_chain_fingerprint": (
                data.get("pipeline_chain_fingerprint")
                or data.get("_path_pipeline_chain_fingerprint")
            ),
            "result_aggregation": (
                data.get("result_aggregation")
                or data.get("_path_result_aggregation")
            ),
            "total_distance": data.get("tours_summary", {}).get("total_distance", 0),
            "makespan": data.get("makespan", None),
            "on_time_rate": data.get("on_time_rate", None),
            "avg_tardiness": data.get("avg_tardiness", None),
            "max_lateness": data.get("max_lateness", None),
            "max_tardiness": data.get("max_tardiness", None),
            "avg_lateness": data.get("avg_lateness", None),
        }

        for name in (
            "n_orders", "n_pick_locations", "n_aisles", "n_blocks",
            "n_resources", "storage_type", "n_order_lines",
        ):
            row[name] = data.get("instance_features", {}).get(name)
        for name in (
            "layout_parse_time", "layout_build_time", "layout_load_time", "layout_cache_hit",
            "instance_parse_time", "instance_build_time", "instance_load_time", "instance_cache_hit",
        ):
            row[name] = data.get("loader_timing", {}).get(name)

        provenance = data.get("provenance", [])
        prov_lookup = {
            e["stage"]: e
            for e in provenance
            if isinstance(e, dict) and "stage" in e
        }

        for stage, algo_col in stage_to_field.items():
            entry = prov_lookup.get(stage, {})

            row[algo_col] = (
                    entry.get("algo")
                    or data.get(algo_col)
                    or entry.get("task_class")
            )
            row[f"{stage}_task_class"] = entry.get("task_class")
            row[f"{stage}_time"] = entry.get("time", data.get(f"{stage}_time"))

            row[f"{stage}_algo_fingerprint"] = entry.get(
                "algo_fingerprint",
                data.get(f"{stage}_algo_fingerprint"),
            )
            row[f"{stage}_own_fingerprint"] = entry.get(
                "own_fingerprint",
                data.get(f"{stage}_own_fingerprint"),
            )
            row[f"{stage}_chain_fingerprint"] = entry.get(
                "chain_fingerprint",
                data.get(f"{stage}_chain_fingerprint"),
            )
            row[f"{stage}_config"] = entry.get(
                "config",
                data.get(f"{stage}_config"),
            )
            row[f"{stage}_target_path"] = entry.get("target_path")

        # Keep old compatibility columns.
        batching_entry = prov_lookup.get("batching", {})
        row["routing_input_time"] = batching_entry.get(
            "time",
            data.get("tours_summary", {}).get("routing_input_time", 0),
        )

        batch_times = data.get("tours_summary", {}).get("time_per_tour", {})
        if batch_times:
            times = list(batch_times.values())
            row["total_route_time"] = sum(times)
            row["min_route_time"] = min(times)
            row["max_route_time"] = max(times)
            row["avg_route_time"] = sum(times) / len(times)
            row["median_route_time"] = np.median(times)
            row["std_route_time"] = np.std(times)
        else:
            routing_entry = prov_lookup.get("routing", {})
            row["total_route_time"] = routing_entry.get(
                "time",
                data.get("tours_summary", {}).get("execution_time", 0),
            )

        batch_distances = data.get("tours_summary", {}).get("tour_distances", {})
        if batch_distances:
            distances = list(batch_distances.values())
            row.update({
                "num_batches": len(distances),
                "min_batch_distance": min(distances),
                "max_batch_distance": max(distances),
                "avg_batch_distance": sum(distances) / len(distances),
                "median_batch_distance": np.median(distances),
                "std_batch_distance": np.std(distances),
            })

        rows.append(row)

    return pd.DataFrame(rows)


def _load_one(path: Path, base: Path) -> dict | None:
    try:
        data = orjson.loads(path.read_bytes())
        data["file_path"] = str(path)
        data.update(_path_metadata(path, base))
        return data
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return None


def load_summary_jsons_fast(base_path: str, sets_to_load: list[str]) -> list[dict]:
    base = Path(base_path)
    by_set = _collect_paths_by_set(base_path, sets_to_load)

    all_data: list[dict] = []
    total_sets = len(by_set)

    for done_sets, (instance_set, paths) in enumerate(by_set.items(), start=1):
        ok = 0
        errs = 0
        desc = f"{instance_set} ({len(paths)} files)"

        pbar = tqdm(total=len(paths), desc=desc, leave=False) if _USE_TQDM else None

        with ThreadPoolExecutor(max_workers=os.cpu_count() or 8) as ex:
            futures = {ex.submit(_load_one, p, base): p for p in paths}

            for fut in as_completed(futures):
                res = fut.result()
                if res is None:
                    errs += 1
                else:
                    ok += 1
                    all_data.append(res)

                if pbar is not None:
                    pbar.update(1)

        if pbar is not None:
            pbar.close()

        print(f"[{done_sets}/{total_sets}] Finished {instance_set}: {ok} ok, {errs} errors")

        if errs:
            raise RuntimeError(f"{instance_set}: {errs} summary files could not be loaded")

    return sorted(all_data, key=lambda row: row["file_path"])
