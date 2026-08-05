#!/usr/bin/env python3
"""为 cached/dblp.yaml 中的论文补充 abstract 与 abstract_cn。"""

import argparse
import datetime
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import yaml
from loguru import logger

from tracker.abstracts import clean_abstract, fetch_abstract_for_papers, translate_abstracts_for_papers
from tracker.cache import cache_file

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _save(cache, path):
    if path.exists():
        shutil.copy2(path, path.with_suffix(".yaml.bak"))
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cache, f, sort_keys=False, indent=2, allow_unicode=True)


def run(year=None, retry_failed=False, clean_only=False):
    year = year or str(datetime.date.today().year)
    cache_path = cache_file()
    if not cache_path.exists():
        logger.error(f"cache not found: {cache_path}")
        sys.exit(1)
    with open(cache_path, "r", encoding="utf-8") as f:
        cache = yaml.safe_load(f) or {}

    contact_email = os.getenv("CONTACT_EMAIL", "")

    if clean_only:
        changed = total = 0
        for items in cache.values():
            if not isinstance(items, list):
                continue
            for item in items:
                raw = item.get("abstract")
                if not raw or not str(raw).strip():
                    continue
                total += 1
                cleaned = clean_abstract(raw)
                if cleaned != raw:
                    item["abstract"] = cleaned
                    changed += 1
        logger.info(f"Cleaned {changed}/{total} abstracts.")
        if changed:
            _save(cache, cache_path)
        return

    targets = []
    for items in cache.values():
        if not isinstance(items, list):
            continue
        for item in items:
            if year != "all" and str(item.get("year", "")) != str(year):
                continue
            abstract = (item.get("abstract") or "").strip()
            abstract_cn = (item.get("abstract_cn") or "").strip()
            if (not abstract) or retry_failed or (abstract and not abstract_cn):
                targets.append(item)

    logger.info(f"Total target papers: {len(targets)} (year={year}, retry_failed={retry_failed})")
    if not targets:
        logger.info("No papers need abstract. Exiting.")
        return

    fetch_abstract_for_papers(targets, sleep_sec=2.0, max_retries=4, contact_email=contact_email)
    translate_abstracts_for_papers(targets)
    _save(cache, cache_path)
    logger.info("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch abstracts for cached papers")
    parser.add_argument("--year", type=str, default=str(datetime.date.today().year),
                        help="Year to process (default: current year, 'all' for all years)")
    parser.add_argument("--retry-failed", action="store_true", help="Retry empty abstracts")
    parser.add_argument("--clean-only", action="store_true", help="Only clean existing abstracts")
    args = parser.parse_args()
    run(year=args.year, retry_failed=args.retry_failed, clean_only=args.clean_only)
