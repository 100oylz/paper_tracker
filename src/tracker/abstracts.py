"""摘要抓取、中文翻译、GitHub 链接提取与 DOI 回填。"""

import re
import time
import urllib.parse
import xml.etree.ElementTree as ET

from loguru import logger

from tracker.http import _sleep_backoff, rate_limited_request
from tracker import llm_client


GITHUB_LINK_RE = re.compile(
    r"https?://github\.com/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+(?:/[^\s\)\]\}>\"'`]*)?"
)
DOI_PATTERN = re.compile(r"^10\.[0-9.]+/[^\s]+$")
DOI_TRAILING_PUNCTUATION = ".,;:)]}>\"'"
OPENREVIEW_FORUM_ID_RE = re.compile(r"(?:forum|pdf)\?id=([A-Za-z0-9_\-]+)")
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}


def clean_abstract(text):
    """清洗 abstract：去 XML 标签、合并不合理换行、压缩空白。"""
    if not text:
        return ""
    text = re.sub(r"<jats:p>(.*?)</jats:p>", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.strip()
    text = re.sub(r"-\n\s*", "", text)
    text = re.sub(r"-\r\n\s*", "", text)
    text = re.sub(r"\n\s*([a-z0-9])", r" \1", text)
    text = re.sub(r"\r\n\s*([a-z0-9])", r" \1", text)
    text = re.sub(r"[\s\t]+", " ", text)
    return text.strip()


def is_title_match(api_title, paper_title, threshold=0.70):
    """标题模糊匹配：先做包含检测，再回退 difflib 相似度。"""
    if not api_title or not paper_title:
        return False
    norm = lambda t: re.sub(r"[^\w]+", "", t.strip().lower(), flags=re.UNICODE)
    n_api, n_paper = norm(api_title), norm(paper_title)
    if not n_api or not n_paper:
        return False
    if n_api in n_paper or n_paper in n_api:
        return True
    import difflib
    return difflib.SequenceMatcher(None, n_api, n_paper).ratio() >= threshold


def extract_github_links(text):
    """提取文本中第一个 GitHub 仓库链接，清理尾部标点；无匹配返回空串。"""
    if not text:
        return ""
    match = GITHUB_LINK_RE.search(text)
    if not match:
        return ""
    return match.group(0).rstrip(".,;:'\")]}>")


def _extract_openreview_forum_id(url):
    match = OPENREVIEW_FORUM_ID_RE.search(url or "")
    return match.group(1) if match else ""


def _or_field(content, key):
    """兼容 OpenReview v1 平铺与 v2 {"value": ...} 两种 content 结构。"""
    if not isinstance(content, dict):
        return None
    val = content.get(key)
    if isinstance(val, dict) and "value" in val:
        return val.get("value")
    return val


def _fetch_openreview_abstract_single(forum_id, last_request_time, min_interval=0.5, max_retries=3):
    if not forum_id:
        return None, last_request_time
    for api_root in ("https://api2.openreview.net", "https://api.openreview.net"):
        url = f"{api_root}/notes?forum={forum_id}"
        for attempt in range(1, max_retries + 1):
            try:
                resp, last_request_time = rate_limited_request(
                    url, last_request_time, min_interval=min_interval, timeout=15
                )
                if resp.status_code in (404, 403):
                    break
                if resp.status_code == 429:
                    _sleep_backoff("Rate limited (OpenReview)", attempt, response=resp)
                    continue
                resp.raise_for_status()
                for note in (resp.json().get("notes") or []):
                    abstract = _or_field(note.get("content") or {}, "abstract")
                    if isinstance(abstract, str) and abstract.strip():
                        return clean_abstract(abstract), last_request_time
                break
            except Exception as exc:
                logger.warning(f"OpenReview single attempt {attempt} failed for {forum_id}: {exc}")
                if attempt < max_retries:
                    _sleep_backoff("OpenReview single", attempt)
    return None, last_request_time


def _batch_fetch_openreview_abstracts(forum_ids, min_interval=0.5, chunk=100,
                                      max_retries=3, enable_single_fallback=True):
    result = {fid: "" for fid in dict.fromkeys(forum_ids) if fid}
    if not result:
        return result
    pending = list(result.keys())
    last_request_time = 0.0

    for i in range(0, len(pending), chunk):
        batch = pending[i:i + chunk]
        url = f"https://api2.openreview.net/notes?ids={','.join(batch)}"
        for attempt in range(1, max_retries + 1):
            try:
                resp, last_request_time = rate_limited_request(
                    url, last_request_time, min_interval=min_interval, timeout=30
                )
                if resp.status_code == 429:
                    _sleep_backoff("Rate limited (OpenReview batch)", attempt, response=resp)
                    continue
                if resp.status_code != 200:
                    break
                for note in (resp.json().get("notes") or []):
                    abstract = _or_field(note.get("content") or {}, "abstract")
                    if not isinstance(abstract, str) or not abstract.strip():
                        continue
                    cleaned = clean_abstract(abstract)
                    for key in {note.get("id"), note.get("forum")}:
                        if key and key in result:
                            result[key] = cleaned
                break
            except Exception as exc:
                logger.warning(f"OpenReview batch attempt {attempt} failed: {exc}")
                if attempt < max_retries:
                    _sleep_backoff("OpenReview batch", attempt)

    if enable_single_fallback:
        missing = [fid for fid, abs_ in result.items() if not abs_]
        last_single = last_request_time
        for fid in missing:
            abs_, last_single = _fetch_openreview_abstract_single(
                fid, last_single, min_interval=min_interval, max_retries=max_retries
            )
            if abs_:
                result[fid] = abs_
    return result


def _prefill_openreview_abstracts(papers, min_interval=0.5, chunk=100,
                                  max_retries=3, enable_single_fallback=True):
    targets = []
    for paper in papers:
        ee = (paper.get("ee") or "").strip()
        if "openreview.net" not in ee:
            continue
        if (paper.get("abstract") or "").strip():
            continue
        fid = _extract_openreview_forum_id(ee)
        if fid:
            targets.append((paper, fid))
    if not targets:
        return 0, 0

    abs_map = _batch_fetch_openreview_abstracts(
        [fid for _, fid in targets], min_interval=min_interval, chunk=chunk,
        max_retries=max_retries, enable_single_fallback=enable_single_fallback,
    )
    filled = 0
    for paper, fid in targets:
        abstract = (abs_map.get(fid) or "").strip()
        if len(abstract) < 5:
            continue
        paper["abstract"] = abstract
        paper["related_code"] = extract_github_links(abstract)
        filled += 1
    return filled, len(targets)


def _fetch_crossref_abstract(doi, last_request_time, min_interval=1.0, max_retries=3, contact_email=""):
    url = f"https://api.crossref.org/works/{doi}"
    agent = f"FL-paper-update-tracker/1.0 (mailto:{contact_email})" if contact_email else "FL-paper-update-tracker/1.0"
    for attempt in range(1, max_retries + 1):
        try:
            resp, last_request_time = rate_limited_request(
                url, last_request_time, min_interval=min_interval, timeout=10,
                headers={"User-Agent": agent},
            )
            if resp.status_code in (404, 403):
                return None, None, last_request_time
            if resp.status_code == 429:
                _sleep_backoff("Rate limited (Crossref)", attempt, response=resp)
                continue
            resp.raise_for_status()
            item = resp.json().get("message", {})
            raw_title = item.get("title")
            if isinstance(raw_title, list) and raw_title:
                api_title = str(raw_title[0]).strip() or None
            elif raw_title:
                api_title = str(raw_title).strip() or None
            else:
                api_title = None
            abstract = clean_abstract(item.get("abstract")) if isinstance(item.get("abstract"), str) else ""
            return (abstract or None), api_title, last_request_time
        except Exception as exc:
            logger.warning(f"Crossref attempt {attempt} failed for {doi}: {exc}")
            if attempt < max_retries:
                _sleep_backoff("Crossref", attempt)
    return None, None, last_request_time


def _fetch_semantic_scholar_abstract(doi, last_request_time, min_interval=1.0, max_retries=3):
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
    params = {"fields": "abstract,title"}
    for attempt in range(1, max_retries + 1):
        try:
            resp, last_request_time = rate_limited_request(
                url, last_request_time, min_interval=min_interval, timeout=10, params=params
            )
            if resp.status_code in (404, 403):
                return None, None, last_request_time
            if resp.status_code == 429:
                _sleep_backoff("Rate limited (Semantic Scholar)", attempt, response=resp)
                continue
            resp.raise_for_status()
            data = resp.json()
            abstract = data.get("abstract")
            api_title = (data.get("title") or "").strip() or None
            if abstract and str(abstract).strip():
                return clean_abstract(abstract), api_title, last_request_time
            return None, api_title, last_request_time
        except Exception as exc:
            logger.warning(f"Semantic Scholar attempt {attempt} failed for {doi}: {exc}")
            if attempt < max_retries:
                _sleep_backoff("Semantic Scholar", attempt)
    return None, None, last_request_time


def _fetch_arxiv_abstract(title, last_request_time, min_interval=1.0, max_retries=3):
    encoded_title = urllib.parse.quote(title)
    url = f"http://export.arxiv.org/api/query?search_query=ti:{encoded_title}&max_results=1"
    for attempt in range(1, max_retries + 1):
        try:
            resp, last_request_time = rate_limited_request(
                url, last_request_time, min_interval=max(min_interval, 3.0), timeout=10
            )
            if resp.status_code in (404, 403):
                return None, None, last_request_time
            if resp.status_code == 429:
                _sleep_backoff("Rate limited (arXiv)", attempt, response=resp)
                continue
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            entry = root.find("atom:entry", ARXIV_NS)
            if entry is None:
                return None, None, last_request_time
            title_elem = entry.find("atom:title", ARXIV_NS)
            api_title = title_elem.text.strip() if title_elem is not None and title_elem.text else None
            summary_elem = entry.find("atom:summary", ARXIV_NS)
            abstract = clean_abstract(summary_elem.text) if summary_elem is not None and summary_elem.text else ""
            return (abstract or None), api_title, last_request_time
        except Exception as exc:
            logger.warning(f"arXiv attempt {attempt} failed for '{title[:60]}...': {exc}")
            if attempt < max_retries:
                _sleep_backoff("arXiv", attempt)
    return None, None, last_request_time


def _reconstruct_abstract_from_inverted_index(inverted_index):
    if not isinstance(inverted_index, dict) or not inverted_index:
        return None
    try:
        max_pos = max(max(positions) for positions in inverted_index.values() if positions)
        words = [""] * (max_pos + 1)
        for word, positions in inverted_index.items():
            for pos in positions:
                if 0 <= pos <= max_pos:
                    words[pos] = word
        abstract = " ".join(words).strip()
        return abstract or None
    except Exception:
        return None


def _fetch_openalex_abstract(doi, last_request_time, min_interval=1.0, max_retries=3, contact_email=""):
    mailto = f"&mailto={urllib.parse.quote(contact_email)}" if contact_email else ""
    url = f"https://api.openalex.org/works/doi:{doi}?select=display_name,abstract_inverted_index{mailto}"
    for attempt in range(1, max_retries + 1):
        try:
            resp, last_request_time = rate_limited_request(
                url, last_request_time, min_interval=min_interval, timeout=10
            )
            if resp.status_code in (404, 403):
                return None, None, last_request_time
            if resp.status_code == 429:
                _sleep_backoff("Rate limited (OpenAlex)", attempt, response=resp)
                continue
            resp.raise_for_status()
            data = resp.json()
            api_title = (data.get("display_name") or "").strip() or None
            abstract = _reconstruct_abstract_from_inverted_index(data.get("abstract_inverted_index"))
            return (clean_abstract(abstract) if abstract else None), api_title, last_request_time
        except Exception as exc:
            logger.warning(f"OpenAlex attempt {attempt} failed for {doi}: {exc}")
            if attempt < max_retries:
                _sleep_backoff("OpenAlex", attempt)
    return None, None, last_request_time


def fetch_abstract_for_papers(papers, sleep_sec=2.0, max_retries=4, contact_email=""):
    """为论文批量补摘要：OpenReview 预填 -> Crossref -> Semantic Scholar -> arXiv -> OpenAlex。"""
    try:
        _prefill_openreview_abstracts(papers, min_interval=0.5, chunk=100, max_retries=3)
    except Exception as exc:
        logger.warning(f"OpenReview prefill skipped: {exc}")

    timers = {"crossref": 0.0, "semanticscholar": 0.0, "arxiv": 0.0, "openalex": 0.0}
    success = failed = skipped = 0

    for i, paper in enumerate(papers, 1):
        if (paper.get("abstract") or "").strip():
            skipped += 1
            continue
        title = (paper.get("title") or "").strip()
        doi = (paper.get("doi") or "").strip()
        logger.info(f"[{i}/{len(papers)}] Fetching abstract: {title[:60]}... (DOI: {doi or 'N/A'})")
        abstract = None

        if doi:
            abstract, api_title, timers["crossref"] = _fetch_crossref_abstract(
                doi, timers["crossref"], min_interval=sleep_sec, max_retries=max_retries,
                contact_email=contact_email,
            )
            if abstract and api_title and not is_title_match(api_title, title):
                abstract = None
            if not abstract:
                abstract, api_title, timers["semanticscholar"] = _fetch_semantic_scholar_abstract(
                    doi, timers["semanticscholar"], min_interval=sleep_sec, max_retries=max_retries
                )
                if abstract and api_title and not is_title_match(api_title, title):
                    abstract = None

        if not abstract and title:
            abstract, api_title, timers["arxiv"] = _fetch_arxiv_abstract(
                title, timers["arxiv"], min_interval=sleep_sec, max_retries=max_retries
            )
            if abstract and api_title and not is_title_match(api_title, title):
                abstract = None

        if not abstract and doi:
            abstract, api_title, timers["openalex"] = _fetch_openalex_abstract(
                doi, timers["openalex"], min_interval=sleep_sec, max_retries=max_retries,
                contact_email=contact_email,
            )
            if abstract and api_title and not is_title_match(api_title, title):
                abstract = None

        if abstract and len(abstract.strip()) >= 5:
            paper["abstract"] = abstract
            paper["related_code"] = extract_github_links(abstract)
            success += 1
            logger.info(f"  -> OK ({len(abstract)} chars)")
        else:
            paper["abstract"] = ""
            failed += 1
            logger.info("  -> Failed")

    logger.info(f"Abstract fetch done. Success: {success}, Failed: {failed}, Skipped: {skipped}")
    return papers


def translate_abstracts_for_papers(papers, sleep_sec=0.5, max_retries=3):
    """通过 OpenCode Go 多模型 fallback 翻译摘要为简体中文。"""
    if not llm_client.is_configured():
        logger.warning("LLM not configured, skipping translation.")
        return papers

    targets = [
        paper for paper in papers
        if (paper.get("abstract") or "").strip() and not (paper.get("abstract_cn") or "").strip()
    ]
    if not targets:
        logger.info("No papers need Chinese translation.")
        return papers

    success = failed = 0
    for i, paper in enumerate(targets, 1):
        title = (paper.get("title") or "").strip()
        logger.info(f"[{i}/{len(targets)}] Translating: {title[:60]}...")
        try:
            translated = llm_client.chat(
                "你是翻译助手，只输出译文，不要解释。",
                f"请把下面的英文摘要翻译成简体中文：\n\n{paper['abstract']}",
                max_retries=max_retries,
            )
            if translated:
                paper["abstract_cn"] = translated
                success += 1
            else:
                paper["abstract_cn"] = ""
                failed += 1
        except llm_client.LLMError as exc:
            logger.warning(f"Translation failed for '{title[:60]}...': {exc}")
            paper["abstract_cn"] = ""
            failed += 1
        if i < len(targets):
            time.sleep(sleep_sec)
    logger.info(f"Translation done. Success: {success}, Failed: {failed}")
    return papers


def _extract_doi_from_ee(ee):
    if not ee:
        return ""
    ee = ee.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if ee.lower().startswith(prefix.lower()):
            doi = ee[len(prefix):].split("?", 1)[0].split("#", 1)[0].rstrip(DOI_TRAILING_PUNCTUATION)
            if DOI_PATTERN.match(doi):
                return doi
    return ""


def _fetch_dblp_doi(key, last_request_time, min_interval=1.0, max_retries=3):
    if not key:
        return None, None, last_request_time
    url = f"https://dblp.org/rec/{key}.xml"
    for attempt in range(1, max_retries + 1):
        try:
            resp, last_request_time = rate_limited_request(
                url, last_request_time, min_interval=min_interval, timeout=10
            )
            if resp.status_code in (404, 403):
                return None, None, last_request_time
            if resp.status_code == 429:
                _sleep_backoff("Rate limited (DBLP)", attempt, response=resp)
                continue
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            if len(root) == 0:
                return None, None, last_request_time
            record = root[0]
            title_elem = record.find("title")
            api_title = title_elem.text.strip() if title_elem is not None and title_elem.text else None
            doi = None
            doi_elem = record.find("doi")
            if doi_elem is not None and doi_elem.text:
                doi = doi_elem.text.strip()
            if not doi:
                ee_elem = record.find("ee")
                if ee_elem is not None and ee_elem.text:
                    doi = _extract_doi_from_ee(ee_elem.text.strip())
            return doi or None, api_title, last_request_time
        except Exception as exc:
            logger.warning(f"DBLP attempt {attempt} failed for key '{key}': {exc}")
            if attempt < max_retries:
                _sleep_backoff("DBLP DOI", attempt)
    return None, None, last_request_time


def _fetch_crossref_doi(title, last_request_time, min_interval=1.0, max_retries=3, contact_email=""):
    url = f"https://api.crossref.org/works?query.title={urllib.parse.quote(title)}&rows=1"
    agent = f"FL-paper-update-tracker/1.0 (mailto:{contact_email})" if contact_email else "FL-paper-update-tracker/1.0"
    for attempt in range(1, max_retries + 1):
        try:
            resp, last_request_time = rate_limited_request(
                url, last_request_time, min_interval=min_interval, timeout=10,
                headers={"User-Agent": agent},
            )
            if resp.status_code in (404, 403):
                return None, None, last_request_time
            if resp.status_code == 429:
                _sleep_backoff("Rate limited (Crossref search)", attempt, response=resp)
                continue
            resp.raise_for_status()
            items = resp.json().get("message", {}).get("items", [])
            if not items:
                return None, None, last_request_time
            item = items[0]
            doi = (item.get("DOI") or "").strip() or None
            raw_title = item.get("title")
            api_title = (str(raw_title[0]).strip() if isinstance(raw_title, list) and raw_title
                         else (str(raw_title).strip() if raw_title else None))
            return doi, api_title, last_request_time
        except Exception as exc:
            logger.warning(f"Crossref search attempt {attempt} failed for '{title[:60]}...': {exc}")
            if attempt < max_retries:
                _sleep_backoff("Crossref search", attempt)
    return None, None, last_request_time


def _fetch_semantic_scholar_doi(title, last_request_time, min_interval=1.0, max_retries=3):
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={urllib.parse.quote(title)}&fields=title,externalIds&limit=1"
    for attempt in range(1, max_retries + 1):
        try:
            resp, last_request_time = rate_limited_request(
                url, last_request_time, min_interval=min_interval, timeout=10
            )
            if resp.status_code in (404, 403):
                return None, None, last_request_time
            if resp.status_code == 429:
                _sleep_backoff("Rate limited (SS search)", attempt, response=resp)
                continue
            resp.raise_for_status()
            papers = resp.json().get("data", [])
            if not papers:
                return None, None, last_request_time
            paper = papers[0]
            api_title = (paper.get("title") or "").strip() or None
            doi = ((paper.get("externalIds") or {}).get("DOI") or "").strip() or None
            return doi, api_title, last_request_time
        except Exception as exc:
            logger.warning(f"SS search attempt {attempt} failed for '{title[:60]}...': {exc}")
            if attempt < max_retries:
                _sleep_backoff("SS search", attempt)
    return None, None, last_request_time


def fetch_doi_for_papers(papers, sleep_sec=2.0, max_retries=4, contact_email="", overwrite=False):
    """批量补 DOI：ee 提取 -> DBLP -> Crossref -> Semantic Scholar。"""
    timers = {"dblp": 0.0, "crossref": 0.0, "semanticscholar": 0.0}
    success = failed = skipped = 0

    for i, paper in enumerate(papers, 1):
        title = (paper.get("title") or "").strip()
        key = (paper.get("key") or "").strip()
        existing_doi = (paper.get("doi") or "").strip()
        if existing_doi and not overwrite:
            skipped += 1
            continue
        if not title:
            failed += 1
            continue

        logger.info(f"[{i}/{len(papers)}] Fetching DOI: {title[:60]}...")
        doi = _extract_doi_from_ee((paper.get("ee") or "").strip())

        if not doi and key:
            doi, api_title, timers["dblp"] = _fetch_dblp_doi(
                key, timers["dblp"], min_interval=sleep_sec, max_retries=max_retries
            )
            if doi and api_title and not is_title_match(api_title, title):
                doi = None
        if not doi:
            doi, api_title, timers["crossref"] = _fetch_crossref_doi(
                title, timers["crossref"], min_interval=sleep_sec, max_retries=max_retries,
                contact_email=contact_email,
            )
            if doi and api_title and not is_title_match(api_title, title):
                doi = None
        if not doi:
            doi, api_title, timers["semanticscholar"] = _fetch_semantic_scholar_doi(
                title, timers["semanticscholar"], min_interval=sleep_sec, max_retries=max_retries
            )
            if doi and api_title and not is_title_match(api_title, title):
                doi = None

        if doi:
            paper["doi"] = doi
            success += 1
        else:
            failed += 1

    logger.info(f"DOI fetch done. Success: {success}, Failed: {failed}, Skipped: {skipped}")
    return papers
