#!/usr/bin/env python3
"""Generate a daily FL paper recommendation list from the tracker cache.

Reads the FL line of cached/dblp.yaml plus a read-titles.txt exported by the
knowledge_wiki (scripts/sync_tracker_status.py), scores every *unread* paper with
an interpretable weighted formula, and writes FL-recommend.md at the repo root.

Rec score:
    0.50 * triage_score / 5
  + 0.20 * has_related_code
  + 0.15 * venue_prestige     (CCF-A=1.0, B=0.7, C=0.4, else 0.3)
  + 0.15 * recency             (year-relative decay)

Pure read-only stdlib(+PyYAML); never touches the cache. Use --dry-run first.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import yaml

from tracker.config import project_root
from tracker.venue_meta import VENUE_INFO, pdf_link

DEFAULT_READ_TITLES = (
    "/home/oylz/Documents/knowledge_wiki/scripts/read-titles.txt"
)

WEIGHTS = {"triage": 0.50, "code": 0.20, "venue": 0.15, "recency": 0.15}
CCF_SCORE = {"A": 1.0, "B": 0.7, "C": 0.4}


def normalize_title(title: str) -> str:
    text = str(title or "").lower()
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "", text, flags=re.UNICODE)
    return text


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def load_cache(path=None):
    path = Path(path) if path else project_root() / "cached" / "dblp.yaml"
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def fl_papers(cache, dedup=True):
    """Yield FL-line papers (optionally deduped by ee/title)."""
    seen_ee = set()
    seen_title = set()
    for key, items in (cache or {}).items():
        if not isinstance(key, str) or not key.startswith("FL:"):
            continue
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            ee = str(item.get("ee") or "").strip()
            title = str(item.get("title") or "").strip()
            if dedup:
                if ee and ee in seen_ee:
                    continue
                if title and title in seen_title:
                    continue
                if ee:
                    seen_ee.add(ee)
                if title:
                    seen_title.add(title)
            yield item


def load_read_titles(path=None):
    path = Path(path) if path else Path(DEFAULT_READ_TITLES)
    if not path.exists():
        return set()
    titles = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if t:
            titles.add(t)
    return titles


def venue_prestige(venue_str: str) -> float:
    val = str(venue_str or "").strip()
    if not val:
        return 0.3
    info = VENUE_INFO.get(val)
    if info is None:
        return 0.3
    ccf = info[1]
    return CCF_SCORE.get(ccf, 0.3) if ccf else 0.3


def recency(year, current_year=None) -> float:
    current = current_year or datetime.now().year
    y = _int(year)
    if y <= 0:
        return 0.0
    delta = max(0, current - y)
    return max(0.0, 1.0 - delta / 5.0)


def score(item):
    triage = _int(item.get("triage_score"))
    triage = triage if triage >= 0 else 0
    triage = min(5, triage)
    has_code = 1.0 if str(item.get("related_code") or "").strip() else 0.0
    venue = venue_prestige(item.get("venue"))
    rec = recency(item.get("year"))
    s = (
        WEIGHTS["triage"] * (triage / 5.0)
        + WEIGHTS["code"] * has_code
        + WEIGHTS["venue"] * venue
        + WEIGHTS["recency"] * rec
    )
    return round(s, 4), triage, has_code


def read_subtopics(cache, read_titles):
    subs = set()
    for item in fl_papers(cache, dedup=True):
        nt = normalize_title(item.get("title"))
        if nt in read_titles:
            st = str(item.get("subtopic") or "").strip()
            if st:
                subs.add(st)
    return subs


def label_of(subtopic, has_code, read_subtopics):
    labels = []
    st = str(subtopic or "").strip()
    if st and st in read_subtopics:
        labels.append("🔁 同方向")
    elif st and st != "other":
        labels.append("🆕 新方向")
    if has_code:
        labels.append("📦 有代码")
    return " / ".join(labels) if labels else "—"


def recommend(cache, read_titles, top_n=15, current_year=None):
    read = {normalize_title(t) for t in read_titles}
    subs = read_subtopics(cache, read_titles)
    candidates = []
    for item in fl_papers(cache, dedup=True):
        nt = normalize_title(item.get("title"))
        if nt in read:
            continue
        s, triage, has_code = score(item)
        candidates.append({
            "title": str(item.get("title") or ""),
            "score": s,
            "triage": triage,
            "has_code": bool(has_code),
            "venue": str(item.get("venue") or ""),
            "year": str(item.get("year") or ""),
            "subtopic": str(item.get("subtopic") or ""),
            "summary": str(item.get("triage_summary") or ""),
            "code": str(item.get("related_code") or ""),
            "ee": str(item.get("ee") or ""),
            "doi": str(item.get("doi") or ""),
            "pdf": pdf_link(item),
            "date_added": str(item.get("date_added") or ""),
        })
    # 已读为 0 时（未同步已读清单）退化为全量排序：在 score 之后按 date_added 降序，
    # 让新入库论文优先打破平局，避免推荐长期停留在同一批高分老论文。
    if read:
        candidates.sort(key=lambda x: -x["score"])
    else:
        candidates.sort(key=lambda x: (x["score"], x["date_added"]), reverse=True)
    return candidates[:top_n], subs


def _md_cell(value):
    return str(value).replace("|", "\\|")


def render_markdown(candidates, read_count, read_subtopics=None):
    read_subtopics = read_subtopics or set()
    out = []
    out.append("# 🎯 FL 每日论文推荐")
    out.append("")
    if read_count == 0:
        out.append("> ⚠️ **已读基线 0 篇：未同步已读清单（READ_TITLES_URL 未配或拉取失败），本次为全量排序，可能重复推荐已读论文。**")
    else:
        out.append(f"> 已读基线 {read_count} 篇；按 triage+代码+venue+时效加权排序的未读推荐。")
    out.append("> 看完点 PUB 链接去 Chrome Zotero 插件加库；回填后用 wiki 的 sync_tracker_status.py 同步。")
    out.append("")
    if not candidates:
        out.append("🎉 暂无新的未读高价值论文。")
        return "\n".join(out) + "\n"
    out.append("| # | 论文 | 分值 | ★ | venue | year | 标签 |")
    out.append("|---|------|------|---|-------|------|------|")
    for i, c in enumerate(candidates, 1):
        pub = c["ee"] or (("https://doi.org/" + c["doi"]) if c["doi"] else "")
        title = _md_cell(c["title"])
        tlink = f"[{title}]({pub})" if pub else title
        code = f" [[CODE]({c['code']})]" if c["code"] else ""
        pdf = f" [[PDF]({c['pdf']})]" if c["pdf"] else ""
        lbl = label_of(c["subtopic"], c["has_code"], read_subtopics)
        out.append(
            f"| {i} | {tlink}{code}{pdf} | {c['score']:.3f} | {c['triage']} | "
            f"{_md_cell(c['venue'])} | {c['year']} | {lbl} |"
        )
    out.append("")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    cache = load_cache(args.cache)
    read_titles = load_read_titles(args.read_titles)
    if not read_titles:
        print("[WARN] 已读清单为空（READ_TITLES_URL 未配置或拉取失败），本次按全量排序并优先新入库论文。")
    candidates, subs = recommend(cache, read_titles, top_n=args.top)
    md = render_markdown(candidates, len(read_titles), subs)
    out = Path(args.out) if args.out else project_root() / "FL-recommend.md"
    if args.dry_run:
        print(f"[dry-run] would write {len(candidates)} recommendations to {out.name}")
        print(md)
    else:
        out.write_text(md, encoding="utf-8")
        print(f"wrote {len(candidates)} recommendations -> {out}")
    return 0


def parse_args(argv) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate FL daily paper recommendations.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--cache", default=None)
    p.add_argument("--read-titles", default=DEFAULT_READ_TITLES)
    p.add_argument("--out", default=None)
    p.add_argument("--top", type=int, default=15)
    return p.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
