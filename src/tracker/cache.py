"""Cache read/write helpers for cached/dblp.yaml."""

from pathlib import Path

import yaml

from tracker.config import project_root


def cache_file(root=None):
    return (Path(root) if root else project_root()) / "cached" / "dblp.yaml"


def load_cache(path=None):
    path = Path(path) if path else cache_file()
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def save_cache(data, path=None):
    path = Path(path) if path else cache_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, indent=2, allow_unicode=True)
    return path


def iter_unique_papers(cache):
    """遍历缓存论文，按 ee/title 全局去重（与主流程口径一致）。"""
    seen_ee, seen_title = set(), set()
    for _key, items in (cache or {}).items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            ee = (item.get("ee") or "").strip()
            title = (item.get("title") or "").strip()
            if ee and ee in seen_ee:
                continue
            if title and title in seen_title:
                continue
            if ee:
                seen_ee.add(ee)
            if title:
                seen_title.add(title)
            yield item
