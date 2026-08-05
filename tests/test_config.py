"""配置解析测试：lines/shared 合并、runtime 默认值、旧版 flat 兼容。"""

from tracker.config import parse_lines, runtime_settings


def _cfg():
    return {
        "dblp": {
            "shared": {"venues": ["venue:ICML:", "venue:NeurIPS:"]},
            "lines": [
                {
                    "tag": "DP",
                    "name": "doc parsing",
                    "enabled": True,
                    "keywords": ["document pars", "layout detect"],
                    "venues": ["venue:ICDAR:", "venue:ICML:"],
                    "subtopics": ["document-parsing", "layout-detection"],
                },
                {
                    "tag": "FL",
                    "name": "federated learning",
                    "enabled": False,
                    "keywords": ["federated learning"],
                    "venues": ["venue:AISTATS:"],
                    "subtopics": ["secure-aggregation"],
                },
            ],
        },
        "enrich": {"subtopics": ["survey", "other"]},
        "runtime": {"year": {"min_offset": 3}},
    }


def test_parse_lines_merges_shared_and_dedupes():
    lines, kw_to_line, st_to_line, all_subtopics = parse_lines(_cfg())
    assert len(lines) == 2
    dp = lines[0]
    assert dp["venues"] == ["venue:ICDAR:", "venue:ICML:", "venue:NeurIPS:"]
    assert dp["enabled"] is True
    assert lines[1]["enabled"] is False
    assert kw_to_line["document pars"] == "DP"
    assert st_to_line["secure-aggregation"] == "FL"
    assert all_subtopics[0] == "document-parsing"
    assert all_subtopics[-1] == "other"


def test_runtime_defaults_merge():
    settings = runtime_settings(_cfg())
    assert settings["year"]["min_offset"] == 3
    assert settings["year"]["max_offset"] == 1
    assert settings["request"]["retry"] == 10
    assert settings["enrich"]["batch_size"] == 5


def test_legacy_flat_config_fallback():
    cfg = {"dblp": {"keywords": ["federate"], "queries": ["venue:ICML:"]}}
    lines, _, _, _ = parse_lines(cfg)
    assert lines[0]["tag"] == "DEFAULT"
    assert lines[0]["keywords"] == ["federate"]
    assert lines[0]["venues"] == ["venue:ICML:"]


def test_real_config_is_dp_plus_fl():
    from tracker.config import load_config

    lines, kw_to_line, _, _ = parse_lines(load_config())
    assert [ln["tag"] for ln in lines] == ["DP", "FL"]
    assert kw_to_line["document pars"] == "DP"
    assert kw_to_line["federated learning"] == "FL"
