"""论文分诊富化：LLM 打分 + 一句话中文导读 + 子方向标签。"""

from loguru import logger

import tracker.llm_client as llm_client


DEFAULT_SUBTOPICS = [
    "document-parsing", "layout-detection", "table-recognition",
    "inference-scheduling", "pipeline-grading", "sensitivity-detection",
    "privacy-compliance", "resource-allocation", "vision-language-model",
    "model-quantization", "knowledge-distillation", "structured-pruning",
    "edge-deployment", "latency-optimization",
    "federated-learning", "federated-optimization",
    "personalized-federated-learning", "cross-device-federated-learning",
    "cross-silo-federated-learning", "horizontal-federated-learning",
    "vertical-federated-learning", "secure-aggregation", "federated-privacy",
    "federated-unlearning", "communication-efficiency", "data-heterogeneity",
    "federated-distillation", "federated-graph-learning", "survey", "other",
]
DEFAULT_BATCH_SIZE = 5
DEFAULT_MAX_PAPERS_PER_RUN = 50

SCORING_RUBRIC = """评分细则（triage_score，0-5 整数）：
5 = 直接面向文档解析/文档理解流水线、VLM 轻量化/端侧部署或联邦学习核心问题，且涉及隐私保护
4 = 文档解析流水线环节（版面检测、表格结构识别等）、推理调度/隐私合规、VLM 量化/蒸馏/剪枝，或联邦学习（跨设备/跨机构训练、安全聚合、个性化、数据异构、通信效率）等核心技术的方法创新
3 = 文档理解、模型压缩、隐私推理或联邦学习的应用/实验工作
2 = 与文档解析/VLM 轻量化/联邦学习/隐私推理弱相关（如通用高效推理、通用模型压缩）
1 = 仅在 related work 中提及上述方向
0 = 与文档解析数据隐私保护及联邦学习研究无关"""


def _get_enrich_config(cfg):
    section = {}
    if cfg is not None:
        try:
            section = dict(cfg.get("enrich") or {})
        except (AttributeError, TypeError, ValueError):
            section = {}
    if not section:
        try:
            section = dict((cfg.get("runtime") or {}).get("enrich") or {})
        except (AttributeError, TypeError, ValueError):
            section = {}
    enabled = bool(section.get("enabled", False))
    batch_size = int(section.get("batch_size", DEFAULT_BATCH_SIZE) or DEFAULT_BATCH_SIZE)
    max_papers = int(section.get("max_papers_per_run", DEFAULT_MAX_PAPERS_PER_RUN) or DEFAULT_MAX_PAPERS_PER_RUN)
    subtopics = section.get("subtopics") or list(DEFAULT_SUBTOPICS)
    subtopics = [str(s).strip() for s in subtopics if str(s).strip()]
    if "other" not in subtopics:
        subtopics.append("other")
    return enabled, batch_size, max_papers, subtopics


def needs_enrich(paper):
    score = paper.get("triage_score")
    return score is None or score == ""


def _build_prompt(batch, subtopics):
    lines = []
    for i, paper in enumerate(batch, 1):
        title = (paper.get("title") or "").strip()
        venue = (paper.get("venue") or "").strip()
        abstract = (paper.get("abstract") or "").strip()
        if abstract:
            lines.append(f"[{i}] 标题: {title}\n    venue: {venue}\n    摘要: {abstract[:1500]}")
        else:
            lines.append(f"[{i}] 标题: {title}\n    venue: {venue}\n    （无摘要，仅凭标题与 venue 判断）")
    papers_block = "\n".join(lines)
    subtopics_block = " / ".join(subtopics)
    return f"""你是文档智能、数据隐私保护与联邦学习领域的科研助手。本项目聚焦"面向文档解析与联邦学习的数据隐私保护关键技术研究"，包含两条主线：
(1) 文档解析、隐私合规与端侧部署——针对文档解析流水线多模型，依敏感信息分布与实时性需求设计动态推理调度，对版面检测、表格结构识别等环节细粒度分级；同时将视觉-语言等大模型经量化、知识蒸馏、结构化剪枝压缩部署至本地端侧，在隐私合规前提下优化推理资源、延迟与显存占用；
(2) 联邦学习与隐私保护——面向跨设备/跨机构分布式训练，研究个性化联邦学习、安全聚合、数据异构、通信效率与隐私保护等关键技术。

{SCORING_RUBRIC}

对每篇论文输出：
- triage_score: 按上述细则的 0-5 整数分
- triage_summary: 一句话中文导读（不超过 60 字），概括论文做了什么、与本项目哪条主线相关
- subtopic: 子方向标签，必须从以下候选列表中选择一个：{subtopics_block}

论文列表：
{papers_block}

输出格式：JSON 数组，长度必须等于 {len(batch)}，顺序与输入一致，每个元素形如：
{{"triage_score": 4, "triage_summary": "...", "subtopic": "model-quantization"}}"""


def _normalize_entry(entry, subtopics):
    if not isinstance(entry, dict):
        return None
    try:
        score = int(entry.get("triage_score"))
    except (TypeError, ValueError):
        return None
    score = max(0, min(5, score))
    summary = str(entry.get("triage_summary") or "").strip()
    subtopic = str(entry.get("subtopic") or "").strip()
    if subtopic not in subtopics:
        subtopic = "other"
    return {"triage_score": score, "triage_summary": summary, "subtopic": subtopic}


def enrich_papers(papers, cfg=None, on_batch_done=None):
    """批量分诊（原地修改论文 dict），任何失败都不向调用方抛异常。"""
    try:
        enabled, batch_size, max_papers, subtopics = _get_enrich_config(cfg)
        if not enabled:
            logger.info("enrich is disabled in config, skipping.")
            return papers
        if not papers:
            return papers
        if not llm_client.is_configured():
            logger.warning("LLM not configured (LLM_API_KEY missing), skipping enrich.")
            return papers

        # 最旧优先：date_added 越早越先分诊，避免新论文插队导致老论文长期 deferred。
        pending = [p for p in papers if needs_enrich(p)]
        pending.sort(key=lambda p: str(p.get("date_added") or "9999-99-99"))
        targets = pending[:max_papers]
        skipped = len(pending) - len(targets)
        if not targets:
            logger.info("No papers need enrich.")
            return papers
        if skipped > 0:
            logger.warning(f"enrich budget reached: {skipped} papers deferred (max_papers_per_run={max_papers})")

        logger.info(f"Enriching {len(targets)} papers (batch_size={batch_size})...")
        enriched = failed = 0
        system = "你是严谨的文档智能与数据隐私保护领域科研助手，只输出合法 JSON。"
        for start in range(0, len(targets), batch_size):
            batch = targets[start:start + batch_size]
            try:
                result = llm_client.chat_json(system, _build_prompt(batch, subtopics))
            except llm_client.LLMError as exc:
                failed += len(batch)
                logger.warning(f"enrich batch [{start}:{start + len(batch)}] failed: {exc}")
                continue
            if not isinstance(result, list):
                failed += len(batch)
                logger.warning("enrich batch returned non-list JSON, skipped.")
                continue
            for paper, entry in zip(batch, result):
                normalized = _normalize_entry(entry, subtopics)
                if normalized is None:
                    failed += 1
                    continue
                paper["triage_score"] = normalized["triage_score"]
                paper["triage_summary"] = normalized["triage_summary"]
                paper["subtopic"] = normalized["subtopic"]
                enriched += 1
            missed = len(batch) - min(len(batch), len(result))
            if missed > 0:
                failed += missed
            done = min(start + batch_size, len(targets))
            logger.info(f"enrich progress: {done}/{len(targets)} (enriched={enriched}, failed={failed})")
            if on_batch_done is not None:
                on_batch_done(done, len(targets))
        logger.info(f"Enrich done. Enriched: {enriched}, Failed/Deferred: {failed}")
        return papers
    except Exception as exc:  # 兜底：绝不让 enrich 中断主流程
        logger.warning(f"enrich_papers skipped due to unexpected error: {exc}")
        return papers
