"""Small, loader-independent instance descriptors for result analysis."""

from __future__ import annotations

import json
from pathlib import Path


def instance_features(orders, resources, storage, layout) -> dict:
    order_rows = getattr(orders, "orders", ())
    graph = getattr(layout, "graph_data", None)
    return {
        "n_orders": len(order_rows),
        "n_pick_locations": getattr(graph, "n_pick_locations", None),
        "n_aisles": getattr(graph, "n_aisles", None),
        "n_blocks": getattr(graph, "n_blocks", None),
        "n_resources": len(getattr(resources, "resources", ())),
        "storage_type": getattr(storage, "get_type_value", lambda: None)(),
        "n_order_lines": sum(len(getattr(order, "order_positions", ())) for order in order_rows),
    }


def loader_timing(layout_path: str, orders_path: str, instance_token: str | None) -> dict:
    """Report timing only for loader tasks executed for this instance."""
    result = {}
    for kind, path in (("layout", layout_path), ("instance", orders_path)):
        sidecar = Path(f"{path}.timing.json")
        timing = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
        ran_here = bool(instance_token) and timing.get("instance_token") == instance_token
        result[f"{kind}_cache_hit"] = not ran_here
        for source, field in (("parse_time", "parse_time"), ("build_time", "build_time"), ("total_time", "load_time")):
            result[f"{kind}_{field}"] = timing.get(source, 0.0) if ran_here else 0.0
    return result
