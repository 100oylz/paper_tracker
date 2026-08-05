#!/usr/bin/env python3
"""对 cached/dblp.yaml 去重：--mode title（按 topic 内标题）或 --mode global（全局 ee/title）。"""

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import yaml

from tracker.cache import cache_file
from tracker.dblp import deduplicate_items_by_ee, deduplicate_items_by_title


def main():
    parser = argparse.ArgumentParser(description="Deduplicate cached/dblp.yaml")
    parser.add_argument("--mode", choices=("title", "global"), default="title")
    args = parser.parse_args()

    cache_path = cache_file()
    with open(cache_path, "r", encoding="utf-8") as f:
        cache = yaml.safe_load(f) or {}

    removed = 0
    seen_ee, seen_title = set(), set()
    for key in list(cache.keys()):
        items = cache[key]
        if not isinstance(items, list):
            continue
        if args.mode == "title":
            before = len(items)
            items = deduplicate_items_by_title(items)
        else:
            before = len(items)
            cleaned = []
            for item in items:
                ee = (item.get("ee") or "").strip()
                title = (item.get("title") or "").strip()
                if ee and ee in seen_ee:
                    removed += 1
                    continue
                if title and title in seen_title:
                    removed += 1
                    continue
                if ee:
                    seen_ee.add(ee)
                if title:
                    seen_title.add(title)
                cleaned.append(item)
            items = cleaned
        removed += before - len(items)
        cache[key] = items

    if cache_path.exists():
        shutil.copy2(cache_path, cache_path.with_suffix(".yaml.bak"))
    with open(cache_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cache, f, sort_keys=False, indent=2, allow_unicode=True)
    print(f"Removed {removed} duplicate papers (mode={args.mode}).")


if __name__ == "__main__":
    main()
