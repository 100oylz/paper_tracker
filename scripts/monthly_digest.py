#!/usr/bin/env python3
"""月度趋势报告：纯本地统计 cached/dblp.yaml。"""

import datetime
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import yaml
from fire import Fire
from loguru import logger

from tracker.cache import cache_file, iter_unique_papers


MAX_MSG_LEN = 4096
TOP_N_VENUE = 15
TOP_N_AUTHOR = 10


def default_month(today=None):
    today = today or datetime.date.today()
    first = today.replace(day=1)
    prev = first - datetime.timedelta(days=1)
    return prev.strftime("%Y-%m")


def parse_month(month):
    parts = str(month).strip().split("-")
    if len(parts) != 2:
        raise ValueError(f"invalid month format (expect YYYY-MM): {month}")
    year, mon = int(parts[0]), int(parts[1])
    if not (1 <= mon <= 12):
        raise ValueError(f"invalid month value: {month}")
    return year, mon


def parse_date_added(item):
    raw = (item.get("date_added") or "").strip()
    if not raw:
        return None
    try:
        return datetime.date.fromisoformat(raw[:10])
    except ValueError:
        return None


def papers_of_month(cache, year, month):
    return [
        item for item in iter_unique_papers(cache)
        if (added := parse_date_added(item)) and added.year == year and added.month == month
    ]


def count_without_date(cache):
    return sum(1 for item in iter_unique_papers(cache) if parse_date_added(item) is None)


def prev_month(year, month):
    return (year - 1, 12) if month == 1 else (year, month - 1)


def compute_stats(papers):
    venues, subtopics, authors = Counter(), Counter(), Counter()
    for item in papers:
        venues[(item.get("venue") or "").strip() or "unknown"] += 1
        subtopics[(item.get("subtopic") or "").strip() or "untriaged"] += 1
        for author in (item.get("author") or "").split(","):
            author = author.strip()
            if author:
                authors[author] += 1
    return {"count": len(papers), "venues": venues, "subtopics": subtopics, "authors": authors}


def _delta_str(current, previous):
    delta = current - previous
    sign = "+" if delta >= 0 else ""
    return f"{current}（较再上一月 {previous}，{sign}{delta}）"


def build_digest(cache, month):
    year, mon = parse_month(month)
    prev_year, prev_mon = prev_month(year, mon)
    current = compute_stats(papers_of_month(cache, year, mon))
    previous = compute_stats(papers_of_month(cache, prev_year, prev_mon))
    legacy = count_without_date(cache)

    lines = [
        f"## 月度趋势报告 {month}",
        "",
        f"> 口径说明：按 date_added（入库日期）统计 {year}-{mon:02d} 自然月内入库的论文，"
        f"环比对象为 {prev_year}-{prev_mon:02d}。",
        f"> 历史存量（无日期）: {legacy} 篇（早期数据无 date_added，不计入月度统计）。",
        "",
        "### 新增论文数",
        "",
        f"- 本期：{_delta_str(current['count'], previous['count'])}",
        "",
        f"### venue 分布（Top {TOP_N_VENUE}）",
        "",
    ]
    lines.extend([f"- {name}: {count}" for name, count in current["venues"].most_common(TOP_N_VENUE)]
                 or ["- （无数据）"])
    lines += ["", "### subtopic 分布", ""]
    lines.extend([f"- {name}: {count}" for name, count in current["subtopics"].most_common()] or ["- （无数据）"])
    lines += ["", f"### 高产作者 Top {TOP_N_AUTHOR}", ""]
    lines.extend([f"- {name}: {count}" for name, count in current["authors"].most_common(TOP_N_AUTHOR)]
                 or ["- （无数据）"])
    return "\n".join(lines)


def emit_msg(msg, env_file=None):
    msg = msg.replace("'", "")
    if len(msg) > MAX_MSG_LEN:
        msg = msg[:MAX_MSG_LEN - 3] + "..."
    print(msg)
    env_file = env_file if env_file is not None else os.getenv("GITHUB_ENV")
    if env_file:
        env_value = msg.replace("\n", "\\n")
        with open(env_file, "a", encoding="utf-8") as f:
            f.write("MSG=$'" + env_value + "'\n")
    return msg


def run(month="", cache_path=""):
    month = month.strip() or default_month()
    path = Path(cache_path) if cache_path else cache_file()
    if not path.exists():
        logger.error(f"cache not found: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        cache = yaml.safe_load(f) or {}
    if not cache:
        logger.error("empty cache, abort.")
        sys.exit(1)
    emit_msg(build_digest(cache, month))


if __name__ == "__main__":
    Fire(run)
