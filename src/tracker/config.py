"""Configuration loading and research-line resolution."""

from pathlib import Path

import yaml


DEFAULT_RUNTIME = {
    "year": {"min_offset": 5, "max_offset": 1},
    "request": {"retry": 10, "sleep_time": 6.0, "timeout": 15},
    "abstracts": {"enabled": True, "sleep_sec": 2.0, "max_retries": 4},
    "translate": {"enabled": True, "sleep_sec": 0.5, "max_retries": 3},
    "enrich": {"enabled": True, "batch_size": 5, "max_papers_per_run": 50},
}


def project_root():
    """仓库根目录（src/tracker/config.py -> 项目根）。"""
    return Path(__file__).resolve().parent.parent.parent


def load_config(path=None):
    path = Path(path) if path else project_root() / "config.yaml"
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _deep_merge(defaults, overrides):
    merged = dict(defaults)
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def runtime_settings(cfg):
    """合并 runtime 默认值与配置覆盖。"""
    return _deep_merge(DEFAULT_RUNTIME, cfg.get("runtime") or {})


def _str_list(values):
    return [str(v).strip() for v in (values or []) if str(v).strip()]


def parse_lines(cfg):
    """解析主线定义，返回 (lines, keyword_to_line, subtopic_to_line, all_subtopics)。

    - 每条主线合并自身 venues 与 dblp.shared.venues（按字符串去重）。
    - subtopics 汇总后追加 enrich.subtopics 与 survey/other 兜底。
    - 兼容旧版 flat dblp.keywords / dblp.queries：退化为单条主线。
    """
    dblp_cfg = cfg.get("dblp") or {}
    raw_lines = dblp_cfg.get("lines")
    shared_venues = _str_list((dblp_cfg.get("shared") or {}).get("venues"))

    lines = []
    if raw_lines:
        for i, raw in enumerate(raw_lines, 1):
            tag = str(raw.get("tag") or f"LINE{i}").strip() or f"LINE{i}"
            name = str(raw.get("name") or tag).strip()
            keywords = _str_list(raw.get("keywords"))
            venues = _str_list(raw.get("venues")) + shared_venues
            venues = list(dict.fromkeys(venues))
            subtopics = _str_list(raw.get("subtopics"))
            lines.append({
                "tag": tag,
                "name": name,
                "enabled": bool(raw.get("enabled", True)),
                "keywords": keywords,
                "venues": venues,
                "subtopics": subtopics,
            })
    else:
        keywords = _str_list(dblp_cfg.get("keywords"))
        queries = _str_list(dblp_cfg.get("queries"))
        lines = [{
            "tag": "DEFAULT",
            "name": "Legacy",
            "enabled": True,
            "keywords": keywords,
            "venues": queries,
            "subtopics": [],
        }]

    keyword_to_line = {kw: ln["tag"] for ln in lines for kw in ln["keywords"]}
    subtopic_to_line = {st: ln["tag"] for ln in lines for st in ln["subtopics"]}

    all_subtopics = []
    seen = set()
    for ln in lines:
        for st in ln["subtopics"]:
            if st not in seen:
                all_subtopics.append(st)
                seen.add(st)
    for st in _str_list((cfg.get("enrich") or {}).get("subtopics")):
        if st not in seen:
            all_subtopics.append(st)
            seen.add(st)
    for fallback in ("survey", "other"):
        if fallback not in seen:
            all_subtopics.append(fallback)
            seen.add(fallback)

    return lines, keyword_to_line, subtopic_to_line, all_subtopics
