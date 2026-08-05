"""辅助脚本测试：月报统计、缓存去重、关键词候选。"""

import sys
import datetime

import pytest

import dedup_cache
import monthly_digest
import suggest_keywords


def _paper(title, year, date_added, venue="ICML", author="A, B"):
    return {"title": title, "year": str(year), "venue": venue, "author": author,
            "ee": f"https://ee/{title}", "date_added": date_added}


def _cache():
    return {
        "DP:venue:ICML:": [
            _paper("Paper One", 2026, "2026-07-10"),
            _paper("Paper Two", 2026, "2026-06-20"),
        ],
        "FL:venue:CVPR:": [
            _paper("Paper Three", 2026, "2026-07-15", venue="CVPR", author="C"),
        ],
    }


def test_monthly_digest_stats():
    cache = _cache()
    digest = monthly_digest.build_digest(cache, "2026-07")
    assert "月度趋势报告 2026-07" in digest
    assert "2（较再上一月 1，+1）" in digest
    assert "ICML: 1" in digest
    assert "CVPR: 1" in digest
    assert "untriaged: 2" in digest


def test_dedup_cache_title_mode(tmp_path, monkeypatch):
    cache_path = tmp_path / "dblp.yaml"
    cache_path.write_text(
        "k1:\n"
        "- {title: A, ee: 'https://1'}\n"
        "- {title: A, ee: 'https://2'}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(dedup_cache, "cache_file", lambda: cache_path)
    monkeypatch.setattr(sys, "argv", ["dedup_cache", "--mode", "title"])
    dedup_cache.main()
    import yaml
    data = yaml.safe_load(cache_path.read_text(encoding="utf-8"))
    assert len(data["k1"]) == 1


def test_suggest_keywords_candidates(tmp_path):
    cache = _cache()
    candidates = suggest_keywords._candidates(cache, min_count=1, limit=10,
                                              existing_keywords=["paper"])
    words = [w for w, _ in candidates]
    assert "three" in words
    assert "paper" not in words


def test_monthly_default_month():
    today = datetime.date(2026, 8, 5)
    assert monthly_digest.default_month(today) == "2026-07"
