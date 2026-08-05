#!/usr/bin/env python3
"""从 abstract 中提取 GitHub 代码链接写入 related_code。"""

import argparse
import datetime
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import yaml
from loguru import logger

from tracker.abstracts import extract_github_links
from tracker.cache import cache_file


def run(year=None, retry_failed=False):
    year = year or str(datetime.date.today().year)
    cache_path = cache_file()
    if not cache_path.exists():
        logger.error(f"cache not found: {cache_path}")
        sys.exit(1)
    with open(cache_path, "r", encoding="utf-8") as f:
        cache = yaml.safe_load(f) or {}

    found = 0
    for items in cache.values():
        if not isinstance(items, list):
            continue
        for item in items:
            if year != "all" and str(item.get("year", "")) != str(year):
                continue
            abstract = (item.get("abstract") or "").strip()
            if not abstract:
                continue
            related_code = (item.get("related_code") or "").strip()
            if not retry_failed and "related_code" in item:
                continue
            if retry_failed and related_code:
                continue
            code = extract_github_links(abstract)
            item["related_code"] = code
            if code:
                found += 1

    logger.info(f"related_code extraction done, found: {found}")
    if cache_path.exists():
        shutil.copy2(cache_path, cache_path.with_suffix(".yaml.bak"))
    with open(cache_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cache, f, sort_keys=False, indent=2, allow_unicode=True)
    logger.info("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract GitHub links from abstracts")
    parser.add_argument("--year", type=str, default=str(datetime.date.today().year),
                        help="Year to process (default: current year, 'all' for all years)")
    parser.add_argument("--retry-failed", action="store_true", help="Retry empty related_code")
    args = parser.parse_args()
    run(year=args.year, retry_failed=args.retry_failed)
