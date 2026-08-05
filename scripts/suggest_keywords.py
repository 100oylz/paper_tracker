#!/usr/bin/env python3
"""基于缓存标题统计 + 可选 DBLP 探测 + 可选 LLM 摘要的关键词建议。"""

import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import yaml
from fire import Fire
from loguru import logger

from tracker.cache import cache_file, iter_unique_papers
from tracker.config import load_config, parse_lines, runtime_settings
from tracker.dblp import build_topic
from tracker.http import request_data
from tracker.llm_client import chat

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


STOPWORDS = {
    "a", "an", "the", "of", "for", "and", "or", "in", "on", "with", "to", "from",
    "using", "based", "via", "toward", "towards", "across", "over", "under",
    "towards", "large", "language", "model", "models", "paper", "learning",
    "deep", "neural", "network", "networks", "new", "novel", "improved",
    "efficient", "efficiently", "toward", "towards", "approach", "method",
    "methods", "framework", "system", "systems", "data", "training", "study",
}
WORD_RE = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")


def _load_cache(path=""):
    path = Path(path) if path else cache_file()
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _tokenize(title):
    tokens = [t for t in WORD_RE.findall(title.lower()) if len(t) >= 4 and t not in STOPWORDS]
    return tokens


def _candidates(cache, min_count=3, limit=20, existing_keywords=None):
    counter = Counter()
    for item in iter_unique_papers(cache):
        counter.update(_tokenize(item.get("title") or ""))
    existing = {k.lower() for k in (existing_keywords or [])}
    candidates = [
        (word, count) for word, count in counter.most_common()
        if count >= min_count and word not in existing
        and not any(word in ex for ex in existing)
    ][:limit]
    return candidates


def _probe(candidates, dblp_url, venues, runtime):
    results = []
    sleep_time = runtime["request"]["sleep_time"]
    timeout = runtime["request"]["timeout"]
    for word, count in candidates:
        topic = build_topic(word, venues[0])
        payload = request_data(dblp_url.format(topic), retry=2, sleep_time=sleep_time, timeout=timeout)
        hit = 0
        if payload:
            try:
                hit = int(payload["result"]["hits"].get("@total", 0) or 0)
            except (KeyError, TypeError, ValueError):
                hit = 0
        results.append((word, count, hit))
    return results


def _build_msg(candidates, probed):
    lines = ["## 关键词建议", ""]
    if probed:
        lines += ["| 候选词 | 缓存标题词频 | DBLP 命中 |", "| --- | --- | --- |"]
        lines += [f"| {word} | {count} | {hit} |" for word, count, hit in probed]
    else:
        lines += ["| 候选词 | 缓存标题词频 |", "| --- | --- |"]
        lines += [f"| {word} | {count} |" for word, count in candidates]
    return "\n".join(lines)


def emit_msg(msg):
    msg = msg.replace("'", "").replace("\n", "\\n")
    env_file = os.getenv("GITHUB_ENV")
    print(msg.replace("\\n", "\n"))
    if env_file:
        with open(env_file, "a", encoding="utf-8") as f:
            f.write("MSG=$'" + msg + "'\n")


def run(min_count=3, limit=20, no_llm=False, no_probe=False, cache_path="", config_path=""):
    cache = _load_cache(cache_path)
    config = load_config(Path(config_path)) if config_path else load_config()
    lines, _, _, _ = parse_lines(config)
    existing_keywords = [kw for line in lines for kw in line["keywords"]]
    candidates = _candidates(cache, min_count=min_count, limit=limit, existing_keywords=existing_keywords)
    if not candidates:
        emit_msg("## 关键词建议\n\n暂无候选关键词。")
        return

    runtime = runtime_settings(config)
    venues = [v for line in lines for v in line["venues"]] or ["venue:NeurIPS:"]
    probed = _probe(candidates, (config.get("dblp") or {})["url"], venues, runtime) if not no_probe else None
    msg = _build_msg(candidates, probed)

    if not no_llm:
        try:
            from tracker.llm_client import is_configured
            if is_configured():
                summary = chat(
                    "你是科研追踪助手，用中文一句话总结以下候选关键词的可用性。",
                    msg + "\n\n请只输出 1-2 句中文总结。",
                    max_retries=2,
                )
                msg = "> " + summary.replace("\n", " ") + "\n\n" + msg
        except Exception as exc:
            logger.warning(f"LLM summary skipped: {exc}")

    emit_msg(msg)


if __name__ == "__main__":
    Fire(run)
