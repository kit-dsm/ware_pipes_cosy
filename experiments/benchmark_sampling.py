from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


MANIFEST_VERSION = 1
DEFAULT_SEED = "ware-pipes-cosy-v1"
DEFAULT_SAMPLE_SIZE = 100
DEFAULT_INSTANCE_SETS = (
    "FoodmartData",
    "FoodmartDataTest",
    "SPRP",
    "SPRP-SS",
    "BahceciOencan",
    "MuterOencan",
    "HennWaescherUniform",
    "HennWaescherClassBased",
    "KrisSmallDataCorrected",
    "KrisLargeData",
)

_TRAILING_REPLICATE = re.compile(r"^(.*?)([-_])(\d+)$")
_FACTOR_SPLIT = re.compile(r"[-_]+")


def stable_score(seed: str, instance_set: str, value: str) -> int:
    payload = f"{seed}\0{instance_set}\0{value}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest(), "big")


def _family_candidates(instance_names: Iterable[str]) -> dict[str, str]:
    names = list(instance_names)
    candidates = {}
    counts = Counter()

    for name in names:
        match = _TRAILING_REPLICATE.match(name)
        candidate = match.group(1) if match else name
        candidates[name] = candidate
        counts[candidate] += 1

    # Strip a trailing integer only when it demonstrably is a replication
    # dimension. This avoids treating one-off names such as instances_17_1 as
    # replicated families when no sibling shares the candidate prefix.
    return {
        name: candidate if counts[candidate] > 1 else name
        for name, candidate in candidates.items()
    }


def _factor_levels(family: str) -> set[tuple[int, str]]:
    return {
        (index, token.casefold())
        for index, token in enumerate(_FACTOR_SPLIT.split(family))
        if token
    }


def select_representative_instances(
    instance_set: str,
    instance_names: Iterable[str],
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    seed: str = DEFAULT_SEED,
) -> list[str]:
    """Return a deterministic, family-balanced, coverage-first cohort.

    One replicate is selected from as many configuration families as possible.
    Families are ordered greedily to cover previously unseen filename-factor
    levels, with a stable hash as the deterministic tie breaker. If the budget
    exceeds the number of families, further replicates are added round-robin.
    """
    names = sorted(set(instance_names))
    if sample_size <= 0 or sample_size >= len(names):
        return names

    family_by_name = _family_candidates(names)
    members_by_family: dict[str, list[str]] = defaultdict(list)
    for name in names:
        members_by_family[family_by_name[name]].append(name)

    for family, members in members_by_family.items():
        members.sort(key=lambda name: stable_score(seed, instance_set, name))

    remaining_families = set(members_by_family)
    uncovered = set().union(*(_factor_levels(family) for family in remaining_families))
    family_order = []

    while remaining_families and len(family_order) < sample_size:
        family = min(
            remaining_families,
            key=lambda candidate: (
                -len(_factor_levels(candidate) & uncovered),
                stable_score(seed, instance_set, candidate),
            ),
        )
        family_order.append(family)
        remaining_families.remove(family)
        uncovered -= _factor_levels(family)

    selected = [members_by_family[family][0] for family in family_order]

    # When every family fits, spend remaining slots on additional independent
    # replicates without letting one family consume the remainder.
    replicate_index = 1
    while len(selected) < sample_size:
        added = False
        for family in sorted(
            family_order,
            key=lambda value: stable_score(seed, instance_set, value),
        ):
            members = members_by_family[family]
            if replicate_index < len(members):
                selected.append(members[replicate_index])
                added = True
                if len(selected) == sample_size:
                    break
        if not added:
            break
        replicate_index += 1

    return selected


def build_manifest(
    instances_dir: Path,
    instance_sets: Iterable[str] = DEFAULT_INSTANCE_SETS,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    seed: str = DEFAULT_SEED,
) -> dict:
    sets = {}
    for instance_set in instance_sets:
        directory = instances_dir / instance_set
        names = [path.stem for path in directory.glob("*.txt") if path.is_file()]
        if not names:
            raise FileNotFoundError(f"No instances found for {instance_set}: {directory}")
        sets[instance_set] = select_representative_instances(
            instance_set,
            names,
            sample_size=sample_size,
            seed=seed,
        )

    return {
        "version": MANIFEST_VERSION,
        "seed": seed,
        "maximum_sample_size": sample_size,
        "sets": sets,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the fixed benchmark cohort manifest")
    parser.add_argument(
        "--instances-dir",
        type=Path,
        default=Path(__file__).parents[1] / "data" / "instances",
    )
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--seed", default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest = build_manifest(
        args.instances_dir,
        sample_size=args.sample_size,
        seed=args.seed,
    )
    rendered = json.dumps(manifest, indent=2) + "\n"

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
