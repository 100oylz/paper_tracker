#!/usr/bin/env python3
"""从缓存生成年度盘点 issue 正文，支持 --fetch-pdf 补充 PDF 链接。"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import requests
import yaml
from fire import Fire
from loguru import logger

from tracker.cache import cache_file, iter_unique_papers
from tracker.venue_meta import pdf_link, venue_badge


MAX_PART_LEN = 60000
FETCH_WORKERS = 8
FETCH_TIMEOUT = 10
CITATION_PDF_RE = re.compile(
    r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE
)
HREF_PDF_RE = re.compile(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']', re.IGNORECASE)


def collect_year_papers(cache, year):
    return [item for item in iter_unique_papers(cache) if str(item.get("year", "")) == str(year)]


def _score_of(item):
    try:
        return int(item.get("triage_score"))
    except (TypeError, ValueError):
        return -1


def resolve_pdf(item, pdf_map):
    pdf = pdf_link(item)
    if pdf:
        return pdf
    ee = (item.get("ee") or "").strip()
    return (pdf_map.get(ee) or "") if ee else ""


def render_paper(item, pdf_map):
    title = (item.get("title") or "").strip()
    score = item.get("triage_score")
    prefix = f"- ★{score} " if score is not None and score != "" else "- "
    line = f"{prefix}{title}."
    badge = venue_badge(item.get("venue", ""))
    if badge:
        line += f" {badge}"
    pdf = resolve_pdf(item, pdf_map)
    if pdf:
        line += f" [[PDF]({pdf})]"
    code = (item.get("related_code") or "").strip()
    if code:
        line += f" [[CODE]({code})]"
    ee = (item.get("ee") or "").strip()
    if ee:
        line += f" [[PUB]({ee})]"
    summary = (item.get("triage_summary") or "").strip()
    if summary:
        line += f"\n  {summary}"
    return line


def group_by_subtopic(papers):
    groups = {}
    for item in papers:
        subtopic = (item.get("subtopic") or "").strip() or "untriaged"
        groups.setdefault(subtopic, []).append(item)
    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    return [(name, sorted(items, key=lambda it: (-_score_of(it), (it.get("title") or ""))))
            for name, items in ordered]


def build_header(year, papers, pdf_map):
    total = len(papers)
    triaged = sum(1 for p in papers if p.get("triage_score") not in (None, ""))
    with_pdf = sum(1 for p in papers if resolve_pdf(p, pdf_map))
    with_code = sum(1 for p in papers if (p.get("related_code") or "").strip())
    pct = lambda n: f"{n / total * 100:.1f}%" if total else "0%"
    return "\n".join([
        f"## {year} 年度盘点", "",
        f"- 总篇数：{total}",
        f"- 分诊覆盖率：{triaged}/{total}（{pct(triaged)}）",
        f"- PDF 链接覆盖率：{with_pdf}/{total}（{pct(with_pdf)}）",
        f"- CODE 链接覆盖率：{with_code}/{total}（{pct(with_code)}）",
        "", "---", "",
    ])


def split_into_parts(header, sections, max_len=MAX_PART_LEN):
    parts = []
    current = header
    for section in sections:
        if len(current) + len(section) > max_len and current.strip() != header.strip():
            parts.append(current)
            current = header + section
        else:
            current += section
    parts.append(current)
    total = len(parts)
    return [f"**Part {i}/{total}**\n\n" + part for i, part in enumerate(parts, 1)]


def build_issue(cache, year, pdf_map, max_len=MAX_PART_LEN):
    papers = collect_year_papers(cache, year)
    header = build_header(year, papers, pdf_map)
    sections = []
    for subtopic, items in group_by_subtopic(papers):
        lines = [f"### {subtopic}（{len(items)} 篇）", ""]
        lines.extend(render_paper(item, pdf_map) for item in items)
        sections.append("\n".join(lines) + "\n")
    return split_into_parts(header, sections, max_len=max_len)


def load_pdf_map(path=None):
    path = path or (cache_file().parent / "pdf_links.json")
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_pdf_map(pdf_map, path=None):
    path = path or (cache_file().parent / "pdf_links.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pdf_map, f, ensure_ascii=False, indent=1, sort_keys=True)


def fetch_pdf_url(ee):
    try:
        resp = requests.get(ee, timeout=FETCH_TIMEOUT, allow_redirects=True,
                            headers={"User-Agent": "FL-paper-update-tracker/1.0"})
        if resp.status_code != 200:
            return ""
        html = resp.text
        match = CITATION_PDF_RE.search(html) or HREF_PDF_RE.search(html)
        if match:
            from urllib.parse import urljoin
            return urljoin(resp.url, match.group(1))
        return ""
    except Exception as exc:
        logger.warning(f"pdf fetch failed for {ee}: {exc}")
        return ""


def fetch_missing_pdfs(papers, pdf_map):
    todo = list(dict.fromkeys(
        (item.get("ee") or "").strip() for item in papers
        if not pdf_link(item) and (item.get("ee") or "").strip() and (item.get("ee") or "").strip() not in pdf_map
    ))
    if not todo:
        return 0
    hits = 0
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        futures = {pool.submit(fetch_pdf_url, ee): ee for ee in todo}
        for future in as_completed(futures):
            ee = futures[future]
            url = future.result()
            pdf_map[ee] = url
            if url:
                hits += 1
    return hits


def run(years, out_dir="/tmp/year_issues", fetch_pdf=False, cache_path=""):
    path = Path(cache_path) if cache_path else cache_file()
    with open(path, "r", encoding="utf-8") as f:
        cache = yaml.safe_load(f) or {}
    if isinstance(years, (tuple, list)):
        year_list = [str(y).strip() for y in years if str(y).strip()]
    else:
        year_list = [y.strip() for y in str(years).split(",") if y.strip()]
    if not year_list:
        logger.error("--years is required, e.g. --years 2025,2026")
        sys.exit(1)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pdf_map = load_pdf_map()
    for year in year_list:
        papers = collect_year_papers(cache, year)
        logger.info(f"year {year}: {len(papers)} papers")
        if fetch_pdf:
            fetch_missing_pdfs(papers, pdf_map)
            save_pdf_map(pdf_map)
        parts = build_issue(cache, year, pdf_map)
        for i, part in enumerate(parts, 1):
            path = out / f"issue_{year}_p{i}.md"
            path.write_text(part, encoding="utf-8")
            print(f"{path} ({len(part)} chars, part {i}/{len(parts)})")


if __name__ == "__main__":
    Fire(run)
