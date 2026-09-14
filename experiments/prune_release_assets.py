from __future__ import annotations

import argparse
import json
import re
import subprocess


def stale_cache_assets(assets, instance_sets: set[str], sample_id: str):
    stale = []
    for asset in assets:
        name = asset["name"]
        for instance_set in instance_sets:
            current_prefix = f"cache__{instance_set}__{sample_id}__"
            generation_prefix = f"cache__{instance_set}__"
            legacy_exact = f"cache-{instance_set}.tar.gz"
            legacy_shard = re.fullmatch(
                rf"cache-{re.escape(instance_set)}-\d+-of-\d+\.tar\.gz",
                name,
            )
            if (
                name.startswith(generation_prefix)
                and not name.startswith(current_prefix)
            ) or name == legacy_exact or legacy_shard:
                stale.append(asset)
                break
    return stale


def gh_json(*args: str):
    completed = subprocess.run(
        ["gh", *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(completed.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete superseded cache assets for sets completed by this run"
    )
    parser.add_argument("--repo", required=True)
    parser.add_argument("--release", default="benchmark-cache")
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--instance-set", action="append", default=[])
    parser.add_argument("--instance-sets-json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--missing-ok", action="store_true")
    args = parser.parse_args()

    try:
        release = gh_json(
            "api",
            f"repos/{args.repo}/releases/tags/{args.release}",
        )
    except subprocess.CalledProcessError:
        if args.missing_ok:
            print(f"Release {args.release!r} does not exist; nothing to prune")
            return
        raise
    assets = gh_json(
        "api",
        "--paginate",
        f"repos/{args.repo}/releases/{release['id']}/assets?per_page=100",
        "--slurp",
    )
    assets = [asset for page in assets for asset in page]

    instance_sets = set(args.instance_set)
    if args.instance_sets_json:
        instance_sets.update(json.loads(args.instance_sets_json))
    if not instance_sets:
        parser.error("provide --instance-set or --instance-sets-json")

    stale = stale_cache_assets(
        assets,
        instance_sets,
        args.sample_id,
    )
    for asset in stale:
        print(f"Deleting stale release asset: {asset['name']}")
        if not args.dry_run:
            subprocess.run(
                [
                    "gh",
                    "api",
                    "--method",
                    "DELETE",
                    f"repos/{args.repo}/releases/assets/{asset['id']}",
                ],
                check=True,
            )

    print(f"Pruned {len(stale)} stale cache assets")


if __name__ == "__main__":
    main()
