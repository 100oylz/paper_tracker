"""双主线 DBLP 论文追踪主流程。"""

import datetime
import os

from fire import Fire
from loguru import logger

from tracker.abstracts import fetch_abstract_for_papers, translate_abstracts_for_papers
from tracker.cache import load_cache, save_cache
from tracker.config import load_config, parse_lines, runtime_settings
from tracker.dblp import (
    build_topic,
    deduplicate_items_by_ee,
    deduplicate_items_by_title,
    filter_items_by_year,
    get_dblp_items,
    query_short_name,
)
from tracker.enrich import enrich_papers
from tracker.format import format_title_topics, get_msg
from tracker.http import request_data

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


MAX_MSG_LEN = 4096


class Scaffold:
    def run(self, env="dev", cfg="./../config.yaml", primary_only=False, all_years=False,
            skip_enrich=False):
        config = load_config(cfg)
        lines, keyword_to_line, subtopic_to_line, all_subtopics = parse_lines(config)
        runtime = runtime_settings(config)

        # 把 runtime.enrich 与汇总后的 subtopics 合并进 enrich 配置
        enrich_cfg = dict(config.get("enrich") or {})
        enrich_cfg["enabled"] = runtime["enrich"]["enabled"]
        enrich_cfg["batch_size"] = runtime["enrich"]["batch_size"]
        enrich_cfg["max_papers_per_run"] = runtime["enrich"]["max_papers_per_run"]
        enrich_cfg["subtopics"] = all_subtopics
        config["enrich"] = enrich_cfg

        dblp_cfg = config.get("dblp") or {}
        dblp_url = dblp_cfg["url"]
        contact_email = os.getenv("CONTACT_EMAIL", "")
        cache = load_cache()

        logger.info(
            f"running with env: {env}, primary_only: {primary_only}, "
            f"all_years: {all_years}, skip_enrich: {skip_enrich}"
        )
        logger.info(f"lines: {[(ln['tag'], ln['name'], len(ln['venues'])) for ln in lines]}")

        line_msgs = {ln["tag"]: "" for ln in lines}
        line_flags = {ln["tag"]: False for ln in lines}
        line_active_topics = {ln["tag"]: [] for ln in lines}
        line_seen = {ln["tag"]: {"ee": set(), "title": set()} for ln in lines}

        # 用缓存中已有论文初始化各线全局去重集合
        for key, items in cache.items():
            tag = key.split(":", 1)[0] if ":" in key else ""
            if tag not in line_seen:
                if len(lines) == 1:
                    tag = lines[0]["tag"]
                else:
                    continue
            for item in items:
                ee = (item.get("ee") or "").strip()
                title = (item.get("title") or "").strip()
                if ee:
                    line_seen[tag]["ee"].add(ee)
                if title:
                    line_seen[tag]["title"].add(title)

        all_new_collected = []  # [(items, kw_tag, topic_str, cache_key)]
        line_topic_new = {ln["tag"]: {} for ln in lines}
        line_topic_first = {ln["tag"]: {} for ln in lines}
        line_topic_order = {ln["tag"]: [] for ln in lines}

        def _add_to_line(tag, cache_key, topic_str, item):
            if cache_key not in line_topic_new[tag]:
                line_topic_new[tag][cache_key] = []
                line_topic_first[tag][cache_key] = topic_str
                line_topic_order[tag].append(cache_key)
            existing_ee = {it.get("ee", "") for it in line_topic_new[tag][cache_key] if it.get("ee", "")}
            existing_title = {it.get("title", "").strip() for it in line_topic_new[tag][cache_key] if it.get("title", "")}
            ee = (item.get("ee") or "").strip()
            title = (item.get("title") or "").strip()
            if (not ee or ee not in existing_ee) and (not title or title not in existing_title):
                line_topic_new[tag][cache_key].append(item)
                if ee:
                    existing_ee.add(ee)
                if title:
                    existing_title.add(title)

        def _route_tags(item, kw_tag):
            subtopic = (item.get("subtopic") or "").strip()
            if subtopic and subtopic in subtopic_to_line:
                return [subtopic_to_line[subtopic]]
            return [kw_tag] if kw_tag else [lines[0]["tag"]]

        def _process_topic(keyword, query, tag):
            topic = build_topic(keyword, query)
            payload = request_data(
                dblp_url.format(topic),
                retry=runtime["request"]["retry"],
                sleep_time=runtime["request"]["sleep_time"],
                timeout=runtime["request"]["timeout"],
            )
            if payload is None:
                logger.error(f"dblp_data is None, topic: {topic}")
                return 0

            items = get_dblp_items(payload)
            if not all_years:
                items = filter_items_by_year(
                    items,
                    min_offset=runtime["year"]["min_offset"],
                    max_offset=runtime["year"]["max_offset"],
                )
            items = deduplicate_items_by_ee(items)
            items = deduplicate_items_by_title(items)

            cache_key = f"{tag}:{query}"
            cached_items = cache.get(cache_key, [])
            cached_ee = {it.get("ee", "") for it in cached_items if it.get("ee", "")}
            cached_title = {it.get("title", "").strip() for it in cached_items if it.get("title", "")}
            gseen = line_seen[tag]
            new_items = [
                item for item in items
                if item.get("ee", "") not in cached_ee
                and item.get("title", "").strip() not in cached_title
                and item.get("ee", "") not in gseen["ee"]
                and item.get("title", "").strip() not in gseen["title"]
            ]
            for item in new_items:
                ee = (item.get("ee") or "").strip()
                title = (item.get("title") or "").strip()
                if ee:
                    gseen["ee"].add(ee)
                if title:
                    gseen["title"].add(title)

            if cache_key not in cache:
                cache[cache_key] = []

            if new_items and not all_years and not skip_enrich:
                if runtime["abstracts"]["enabled"]:
                    fetch_abstract_for_papers(
                        new_items,
                        sleep_sec=runtime["abstracts"]["sleep_sec"],
                        max_retries=runtime["abstracts"]["max_retries"],
                        contact_email=contact_email,
                    )
                if runtime["translate"]["enabled"]:
                    translate_abstracts_for_papers(
                        new_items,
                        sleep_sec=runtime["translate"]["sleep_sec"],
                        max_retries=runtime["translate"]["max_retries"],
                    )
                enrich_papers(new_items, config)

            date_added = datetime.date.today().isoformat()
            for item in new_items:
                item["date_added"] = date_added
            cache[cache_key].extend(new_items)

            if new_items:
                all_new_collected.append((new_items, tag, topic, cache_key))
                logger.info(f"new_items ({tag}): {len(new_items)} for {cache_key}")
            return len(new_items)

        # ---------- 主扫描循环 ----------
        for line in lines:
            if not line["enabled"]:
                logger.info(f"line {line['tag']} disabled, skip.")
                continue
            if primary_only and line["keywords"]:
                primary = line["keywords"][0]
                active_queries = []
                for query in line["venues"]:
                    if _process_topic(primary, query, line["tag"]) > 0:
                        active_queries.append(query)
                for keyword in line["keywords"][1:]:
                    for query in active_queries:
                        _process_topic(keyword, query, line["tag"])
            else:
                for keyword in line["keywords"]:
                    for query in line["venues"]:
                        _process_topic(keyword, query, line["tag"])

        save_cache(cache)

        # ---------- enrich 后按 subtopic 归线并生成消息 ----------
        for new_items, kw_tag, topic_str, cache_key in all_new_collected:
            for item in new_items:
                for route_tag in _route_tags(item, kw_tag):
                    _add_to_line(route_tag, cache_key, topic_str, item)
                    short_name = query_short_name(cache_key.split(":", 1)[1])
                    if short_name not in line_active_topics[route_tag]:
                        line_active_topics[route_tag].append(short_name)
                    line_flags[route_tag] = True

        for line in lines:
            tag = line["tag"]
            for cache_key in line_topic_order[tag]:
                line_msgs[tag] += get_msg(line_topic_new[tag][cache_key], line_topic_first[tag][cache_key])

        if env == "prod":
            env_file = os.getenv("GITHUB_ENV")
            if not env_file:
                logger.warning("GITHUB_ENV not set, skipping env write.")
            else:
                for line in lines:
                    tag = line["tag"]
                    msg = line_msgs[tag]
                    if len(msg) > MAX_MSG_LEN:
                        msg = msg[:MAX_MSG_LEN - 3] + "..."
                    if line_flags[tag]:
                        prefix = tag.upper()
                        with open(env_file, "a") as f:
                            f.write(f"MSG_{prefix}=$'{msg}'\n")
                            f.write(f"ISSUE_TITLE_TOPICS_{prefix}={format_title_topics(line_active_topics[tag])}\n")
        else:
            for line in lines:
                tag = line["tag"]
                logger.info(f"===== {tag} ({line['name']}) msg =====")
                logger.info(line_msgs[tag] or "(no new papers)")


if __name__ == "__main__":
    Fire(Scaffold)
