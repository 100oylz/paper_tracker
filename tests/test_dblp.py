"""DBLP 解析、年份过滤、去重与 topic 工具测试。"""

from tracker.dblp import (
    build_topic,
    deduplicate_items_by_ee,
    deduplicate_items_by_title,
    filter_items_by_year,
    get_dblp_items,
    query_short_name,
)


def _hit(info):
    return {"info": info}


def test_get_dblp_items_parses_authors_and_defaults():
    payload = {"result": {"hits": {"hit": [
        _hit({"authors": {"author": [{"text": "A"}, {"text": "B"}]}, "title": "T", "year": "2025"}),
        _hit({"authors": {"author": {"text": "C"}}, "title": "U", "venue": "ICML"}),
        _hit({"title": "V"}),
    ]}}}
    items = get_dblp_items(payload)
    assert items[0]["author"] == "A, B"
    assert items[0]["ee"] == ""
    assert items[1]["author"] == "C"
    assert items[2]["venue"] == ""


def test_filter_items_by_year_no_2020_floor():
    items = [
        {"year": "2020"},
        {"year": "2021"},
        {"year": "2026"},
        {"year": "2027"},
        {"year": "2028"},
        {"year": ""},
        {"year": "abc"},
    ]
    filtered = filter_items_by_year(items, current_year=2026, min_offset=5, max_offset=1)
    years = sorted(int(i["year"]) for i in filtered)
    assert years == [2021, 2026, 2027]


def test_dedup_by_ee_and_title():
    items = [
        {"ee": "https://a", "title": "X"},
        {"ee": "https://a", "title": "Y"},
        {"ee": "", "title": "Y"},
        {"ee": "", "title": "X"},
    ]
    assert len(deduplicate_items_by_ee(items)) == 3
    # 按 title 去重：X 与 Y 各保留第一条，重复的两条被移除
    assert len(deduplicate_items_by_title(items)) == 2


def test_build_topic_and_short_name():
    assert build_topic("document pars", "venue:ICML:") == "document%20pars%20venue%3AICML%3A"
    assert query_short_name("venue:ICML:") == "ICML"
    assert query_short_name("streamid:journals/pami:") == "pami"
