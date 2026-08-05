"""消息渲染：venue 徽章 + PDF/CODE/PUB 链接 + subtopic 分组。"""

import urllib.parse

from tracker.venue_meta import pdf_link, venue_badge


def _is_triaged(item):
    score = item.get("triage_score")
    return score is not None and score != ""


def _triage_score(item):
    try:
        return int(item.get("triage_score"))
    except (TypeError, ValueError):
        return 0


def _format_item_line(item, triaged):
    ee = (item.get("ee") or "").strip()
    related_code = (item.get("related_code") or "").strip()
    title = item.get("title", "")
    prefix = f"- ★{_triage_score(item)} " if triaged else "- "
    line = f"{prefix}{title}."
    badge = venue_badge(item.get("venue", ""))
    if badge:
        line += f" {badge}"
    pdf = pdf_link(item)
    if pdf:
        line += f" [[PDF]({pdf})]"
    if related_code:
        line += f" [[CODE]({related_code})]"
    if ee:
        line += f" [[PUB]({ee})]"
    return line


def get_msg(items, topic, aggregated=False):
    """按 venue 生成消息块；返回的换行是字面 \\n（供 GITHUB_ENV $'...' 使用）。"""
    string_topic = urllib.parse.unquote(topic)
    name_topic = string_topic.split(":")[-2]
    msg = f"## [{name_topic}](https://dblp.org/search?q={topic}) [+{len(items)}]\\n\\n"

    if aggregated is False:
        triaged_items = [item for item in items if _is_triaged(item)]
        plain_items = [item for item in items if not _is_triaged(item)]

        if triaged_items:
            groups = {}
            for item in triaged_items:
                subtopic = (item.get("subtopic") or "").strip() or "other"
                groups.setdefault(subtopic, []).append(item)
            group_order = sorted(
                groups.keys(),
                key=lambda g: (-max(_triage_score(it) for it in groups[g]), g),
            )
            for subtopic in group_order:
                msg += f"### {subtopic}\\n"
                for item in sorted(
                    groups[subtopic],
                    key=lambda it: (-_triage_score(it), it.get("title", "")),
                ):
                    msg += _format_item_line(item, triaged=True) + "\\n"
                    summary = (item.get("triage_summary") or "").strip()
                    if summary:
                        msg += f"  {summary}\\n"
                msg += "\\n"

        for item in plain_items:
            msg += _format_item_line(item, triaged=False) + "\\n"
        msg += "\\n"

    return msg.replace("'", "")


def format_title_topics(topics, max_len=80):
    """将 venue 短名列表拼成 Issue 标题；超长时截断为 'a, b, c 等N个'。"""
    if not topics:
        return ""
    full = ", ".join(topics)
    if len(full) <= max_len:
        return full
    for i in range(len(topics) - 1, 0, -1):
        prefix = ", ".join(topics[:i])
        suffix = f"等{len(topics) - i}个"
        candidate = f"{prefix} {suffix}"
        if len(candidate) <= max_len:
            return candidate
    return f"{topics[0]} 等{len(topics) - 1}个"
