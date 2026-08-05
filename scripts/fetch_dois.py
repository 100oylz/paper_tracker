#!/usr/bin/env python3
"""为 cached/dblp.yaml 中的论文补充 doi 字段。"""

import argparse
import datetime
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import yaml
from loguru import logger

from tracker.abstracts import fetch_doi_for_papers
from tracker.cache import cache_file


def run(year=None, retry_all=False):
    year = year or str(datetime.date.today().year)
    cache_path = cache_file()
    if not cache_path.exists():
        logger.error(f"cache not found: {cache_path}")
        sys.exit(1)
    with open(cache_path, "r", encoding="utf-8") as f:
        cache = yaml.safe_load(f) or {}

    import os
    contact_email = os.getenv("CONTACT_EMAIL", "")
    targets = []
    for items in cache.values():
        if not isinstance(items, list):
            continue
        for item in items:
            if year != "all" and str(item.get("year", "")) != str(year):
                continue
            if (item.get("doi") or "").strip() and not retry_all:
                continue
            targets.append(item)

    logger.info(f"Total target papers: {len(targets)} (year={year}, retry_all={retry_all})")
    if not targets:
        logger.info("No papers need DOI. Exiting.")
        return

    fetch_doi_for_papers(targets, sleep_sec=2.0, max_retries=4, contact_email=contact_email, overwrite=retry_all)
    if cache_path.exists():
        shutil.copy2(cache_path, cache_path.with_suffix(".yaml.bak"))
    with open(cache_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cache, f, sort_keys=False, indent=2, allow_unicode=True)
    logger.info("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill DOIs for cached papers")
    parser.add_argument("--year", type=str, default=str(datetime.date.today().year),
                        help="Year to process (default: current year, 'all' for all years)")
    parser.add_argument("--retry-all", action="store_true", help="Retry papers that already have a DOI")
    args = parser.parse_args()
    run(year=args.year, retry_all=args.retry_all)
