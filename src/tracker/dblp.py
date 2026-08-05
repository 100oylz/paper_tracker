"""DBLP API payload parsing, year filtering and deduplication."""

import datetime
import urllib.parse

from tracker.http import request_data


DEFAULT_YEAR_MIN_OFFSET = 5
DEFAULT_YEAR_MAX_OFFSET = 1


def build_topic(keyword, query):
    """构造 DBLP 搜索 topic（URL 编码的 keyword + query）。"""
    encoded_keyword = urllib.parse.quote(keyword, safe="")
    encoded_query = urllib.parse.quote(query, safe="")
    return f"{encoded_keyword}%20{encoded_query}"


def query_short_name(query):
    """venue:ICML: -> ICML ; streamid:journals/pami: -> pami。"""
    cleaned = (query or "").strip().rstrip(":")
    parts = [p for p in cleaned.split(":") if p]
    if not parts:
        return cleaned
    return parts[-1].split("/")[-1]


def get_dblp_items(payload):
    """把 DBLP JSON 结果解析为论文 dict 列表。"""
    try:
        hits = payload["result"]["hits"]["hit"]
    except (KeyError, TypeError):
        return []

    items = []
    for hit in hits:
        info = hit.get("info") or {}
        authors = info.get("authors") or {}
        author_value = authors.get("author") if isinstance(authors, dict) else None
        if isinstance(author_value, list):
            names = [a.get("text", "") for a in author_value if isinstance(a, dict)]
        elif isinstance(author_value, dict):
            names = [author_value.get("text", "")]
        else:
            names = []
        item = {"author": ", ".join(n for n in names if n)}
        for key in ("title", "venue", "year", "type", "access", "key", "doi", "ee", "url", "abstract"):
            value = info.get(key, "")
            item[key] = value if value else ""
        items.append(item)
    return items


def filter_items_by_year(items, current_year=None, min_offset=DEFAULT_YEAR_MIN_OFFSET,
                         max_offset=DEFAULT_YEAR_MAX_OFFSET):
    """按年份窗口过滤，默认 current_year-5 到 current_year+1，无绝对下限。"""
    current_year = current_year or datetime.date.today().year
    min_year = current_year - min_offset
    max_year = current_year + max_offset
    filtered = []
    for item in items:
        try:
            year = int(item.get("year", ""))
        except (TypeError, ValueError):
            continue
        if min_year <= year <= max_year:
            filtered.append(item)
    return filtered


def deduplicate_items_by_ee(items):
    """按 ee 去重，保留第一条；空 ee 始终保留。"""
    seen = set()
    result = []
    for item in items:
        ee = (item.get("ee") or "").strip()
        if ee and ee in seen:
            continue
        if ee:
            seen.add(ee)
        result.append(item)
    return result


def deduplicate_items_by_title(items):
    """按 title 去重，保留第一条；空 title 始终保留。"""
    seen = set()
    result = []
    for item in items:
        title = (item.get("title") or "").strip()
        if title and title in seen:
            continue
        if title:
            seen.add(title)
        result.append(item)
    return result
