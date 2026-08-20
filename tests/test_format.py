"""get_msg 与 Issue 标题格式化测试。"""

from tracker.format import format_title_topics, get_msg


TOPIC = "document%20pars%20venue%3AICML%3A"


def _plain_items():
    return [
        {"title": "Paper A", "venue": "ICML", "ee": "https://ee/a",
         "related_code": "https://github.com/x/y"},
        {"title": "Paper B", "venue": "NeurIPS", "ee": "https://ee/b"},
        {"title": "Paper C", "venue": "", "ee": ""},
    ]


def test_plain_items_real_newline_format():
    msg = get_msg(_plain_items(), TOPIC)
    assert msg == (
        "## [ICML](https://dblp.org/search?q=document%20pars%20venue%3AICML%3A) [+3]\n\n"
        "- Paper A. **[ICML · CCF-A]** [[CODE](https://github.com/x/y)] [[PUB](https://ee/a)]\n"
        "- Paper B. **[NeurIPS · CCF-A]** [[PUB](https://ee/b)]\n"
        "- Paper C.\n"
        "\n"
    )


def test_pdf_link_before_code_and_pub():
    items = [{
        "title": "PMLR paper", "venue": "ICML",
        "ee": "https://proceedings.mlr.press/v202/foo23a/",
    }]
    msg = get_msg(items, TOPIC)
    assert "[[PDF](https://proceedings.mlr.press/v202/foo23a/foo23a.pdf)]" in msg
    assert msg.index("PDF") < msg.index("PUB")


def test_triaged_grouping_and_sorting():
    items = [
        {"title": "Low", "venue": "IJCAI", "ee": "https://low",
         "triage_score": 2, "triage_summary": "低分", "subtopic": "application"},
        {"title": "High", "venue": "ICML", "ee": "https://high",
         "related_code": "https://github.com/a/b",
         "triage_score": 5, "triage_summary": "高分", "subtopic": "personalization"},
        {"title": "Mid", "venue": "EuroMLSys@EuroSys", "ee": "https://mid",
         "triage_score": 4, "triage_summary": "中分", "subtopic": "personalization"},
    ]
    msg = get_msg(items, TOPIC)
    assert "### personalization\n" in msg
    assert "### application\n" in msg
    assert msg.index("### personalization") < msg.index("### application")
    assert msg.index("★5 High.") < msg.index("★4 Mid.")
    assert "  高分\n" in msg
    assert "- ★2 Low. **[IJCAI · CCF-B · 第七版由A降B]]**" not in msg  # 括号完整性由下一行校验
    assert "- ★2 Low. **[IJCAI · CCF-B · 第七版由A降B]** [[PUB](https://low)]\n" in msg


def test_mixed_triaged_and_plain():
    items = _plain_items()[:1] + [
        {"title": "Triaged", "venue": "NeurIPS", "ee": "https://t",
         "triage_score": 3, "triage_summary": "导读", "subtopic": "other"},
    ]
    msg = get_msg(items, TOPIC)
    assert "### other\n" in msg
    assert "- Paper A. **[ICML · CCF-A]]**" not in msg
    assert "- ★3 Triaged. **[NeurIPS · CCF-A]** [[PUB](https://t)]\n" in msg


def test_single_quotes_preserved():
    # GITHUB_ENV 用 heredoc(_FL_TRACKER_MSG_EOF_) 写入，无需转义单引号；
    # 标题中的撇号应原样保留，不得被全局删除。
    items = [{"title": "It's a paper", "venue": "ICML", "ee": "https://x",
              "triage_score": 3, "triage_summary": "导读", "subtopic": "other"}]
    msg = get_msg(items, TOPIC)
    assert "It's a paper." in msg


def test_aggregated_header_only():
    items = _plain_items() + [{"title": "T", "venue": "ICML", "triage_score": 3}]
    msg = get_msg(items, TOPIC, aggregated=True)
    assert "[+4]" in msg
    assert "###" not in msg
    assert "★" not in msg


def test_format_title_topics_truncation():
    topics = ["a", "b", "c", "d"]
    assert format_title_topics(topics) == "a, b, c, d"
    truncated = format_title_topics(["a"] * 30, max_len=40)
    assert len(truncated) <= 40
    assert "等" in truncated
    assert truncated.startswith("a, a")
