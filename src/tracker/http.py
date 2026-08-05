"""Rate-limited HTTP helpers and the DBLP search client."""

import random
import time
import urllib.parse

import requests
from loguru import logger


DBLP_MIRROR_HOSTS = ("dblp.uni-trier.de", "dblp.dagstuhl.de")
DBLP_HOST_SWITCH_AFTER_FAILURES = 2
DBLP_RETRY_BASE_SECONDS = 4.0
DBLP_RETRY_CAP_SECONDS = 120.0
DBLP_JITTER_RANGE = (0.5, 2.5)
USER_AGENT = "FL-paper-update-tracker/1.0 (DBLP paper watcher)"


def _sleep_backoff(source, attempt, response=None, base=2.5, cap=90.0):
    wait = None
    if response is not None:
        try:
            wait = float(response.headers.get("Retry-After") or 0)
        except (TypeError, ValueError):
            wait = None
        if wait and wait > 0:
            wait = min(cap, wait)
    if not wait:
        wait = min(cap, base * (2 ** max(0, attempt - 1)))
        wait = min(cap, wait + wait * 0.3 * random.random())
    wait = max(wait, 1.0)
    logger.warning(f"{source}: backoff {wait:.1f}s (attempt {attempt})")
    time.sleep(wait)
    return wait


def request_data(url, retry=10, sleep_time=6.0, timeout=15):
    """请求 DBLP 搜索 API：限速、退避重试、官方镜像轮换。"""
    max_attempts = retry + 1
    parsed = urllib.parse.urlsplit(url)
    hosts = [parsed.netloc] + [h for h in DBLP_MIRROR_HOSTS if h != parsed.netloc]
    host_index = 0
    fail_streak = 0
    current_url = url

    for attempt in range(1, max_attempts + 1):
        try:
            host = hosts[host_index]
            current_url = url if host_index == 0 else urllib.parse.urlunsplit(parsed._replace(netloc=host))
            time.sleep(sleep_time + random.uniform(*DBLP_JITTER_RANGE))
            resp = requests.get(current_url, timeout=timeout, headers={"User-Agent": USER_AGENT})
            if resp.status_code == 429:
                fail_streak += 1
                _sleep_backoff(
                    "DBLP rate limited", attempt, response=resp,
                    base=DBLP_RETRY_BASE_SECONDS, cap=DBLP_RETRY_CAP_SECONDS,
                )
            elif resp.status_code >= 500:
                fail_streak += 1
                _sleep_backoff(
                    f"DBLP HTTP {resp.status_code}", attempt, response=resp,
                    base=DBLP_RETRY_BASE_SECONDS, cap=DBLP_RETRY_CAP_SECONDS,
                )
            else:
                resp.raise_for_status()
                return resp.json()
            if fail_streak >= DBLP_HOST_SWITCH_AFTER_FAILURES and host_index < len(hosts) - 1:
                host_index += 1
                fail_streak = 0
                logger.warning(f"switch DBLP host to {hosts[host_index]}")
        except Exception as exc:
            logger.error(f"DBLP request failed: {exc}")
            fail_streak += 1
            if fail_streak >= DBLP_HOST_SWITCH_AFTER_FAILURES and host_index < len(hosts) - 1:
                host_index += 1
                fail_streak = 0
                logger.warning(f"switch DBLP host to {hosts[host_index]}")
            elif attempt < max_attempts:
                _sleep_backoff(
                    "DBLP request", attempt,
                    base=DBLP_RETRY_BASE_SECONDS, cap=DBLP_RETRY_CAP_SECONDS,
                )
    logger.error(f"Failed to fetch {url}")
    return None


def rate_limited_request(url, last_request_time, min_interval=1.0, timeout=10, jitter=0.2, **kwargs):
    """保证两次请求间隔不小于 min_interval 秒。"""
    now = time.time()
    wait = max(0.0, min_interval - (now - last_request_time))
    if wait > 0:
        time.sleep(wait + random.uniform(0.0, jitter))
    resp = requests.get(url, timeout=timeout, **kwargs)
    return resp, time.time()
