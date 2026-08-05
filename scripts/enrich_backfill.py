#!/usr/bin/env python3
"""对缓存中缺分诊字段的存量论文批量跑 enrich。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import yaml
from fire import Fire
from loguru import logger

from tracker.cache import cache_file
from tracker.config import load_config
from tracker.enrich import enrich_papers, needs_enrich

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

import tracker.llm_client as llm_client


DEFAULT_LIMIT = 50
SAVE_EVERY_BATCHES = 20


def _year_of(item):
    try:
        return int(item.get("year", ""))
    except (TypeError, ValueError):
        return 0


def _collect_targets(cache, year=""):
    targets = []
    for items in (cache or {}).values():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or not needs_enrich(item):
                continue
            if year and str(item.get("year", "")) != str(year):
                continue
            targets.append(item)
    targets.sort(key=_year_of, reverse=True)
    return targets


def run(year="", limit=DEFAULT_LIMIT, batch_size=0, dry_run=False, cache_path="", config_path=""):
    resolved = Path(cache_path) if cache_path else cache_file()
    if not resolved.exists():
        logger.error(f"cache not found: {resolved}")
        sys.exit(1)
    with open(resolved, "r", encoding="utf-8") as f:
        cache = yaml.safe_load(f) or {}

    targets = _collect_targets(cache, year)
    if limit and limit > 0:
        targets = targets[:limit]
    logger.info(f"will process {len(targets)} papers (year={year or 'all'}, limit={limit})")

    if dry_run:
        print(f"dry-run: {len(targets)} papers pending enrich (year={year or 'all'}, limit={limit})")
        return
    if not targets:
        logger.info("Nothing to enrich. Exiting.")
        return
    if not llm_client.is_configured():
        logger.warning("LLM not configured, nothing written.")
        return

    config = load_config(Path(config_path)) if config_path else load_config()
    enrich_cfg = dict(config.get("enrich") or {})
    enrich_cfg["enabled"] = True
    if batch_size and batch_size > 0:
        enrich_cfg["batch_size"] = batch_size
    enrich_cfg["max_papers_per_run"] = len(targets)
    config["enrich"] = enrich_cfg

    state = {"batches": 0}

    def _checkpoint(done, total):
        state["batches"] += 1
        if state["batches"] % SAVE_EVERY_BATCHES == 0:
            with open(resolved, "w", encoding="utf-8") as f:
                yaml.safe_dump(cache, f, sort_keys=False, indent=2, allow_unicode=True)
            logger.info(f"checkpoint saved at {done}/{total}")

    enrich_papers(targets, config, on_batch_done=_checkpoint)
    succeeded = sum(1 for item in targets if not needs_enrich(item))
    if succeeded > 0:
        with open(resolved, "w", encoding="utf-8") as f:
            yaml.safe_dump(cache, f, sort_keys=False, indent=2, allow_unicode=True)
        logger.info(f"cache written back: {resolved}")
    else:
        logger.warning("no paper enriched, cache not written.")


if __name__ == "__main__":
    Fire(run)
