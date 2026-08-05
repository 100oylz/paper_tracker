"""enrich 测试：字段写入、批次失败降级、预算截断、开关与兜底。"""

import pytest

import tracker.enrich as enrich
import tracker.llm_client as llm_client


SUBTOPICS = ["personalization", "heterogeneity", "other"]


def _cfg(**overrides):
    section = {"enabled": True, "batch_size": 2, "max_papers_per_run": 50, "subtopics": SUBTOPICS}
    section.update(overrides)
    return {"enrich": section}


def _papers(n):
    return [{"title": f"Paper {i}", "venue": "ICML", "abstract": f"abstract {i}"} for i in range(n)]


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setattr(llm_client, "is_configured", lambda: True)


def test_enrich_writes_fields(monkeypatch):
    papers = _papers(3)
    monkeypatch.setattr(
        llm_client, "chat_json",
        lambda *a, **k: [
            {"triage_score": 4, "triage_summary": "导读", "subtopic": "personalization"}
            for _ in range(2)
        ],
    )
    enrich.enrich_papers(papers, _cfg())
    assert all(p["triage_score"] == 4 for p in papers)


def test_enrich_batch_failure_degrades(monkeypatch):
    papers = _papers(4)
    calls = {"n": 0}

    def fake(system, user, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise llm_client.LLMError("boom")
        return [{"triage_score": 4, "triage_summary": "x", "subtopic": "personalization"}]

    monkeypatch.setattr(llm_client, "chat_json", fake)
    enrich.enrich_papers(papers, _cfg())
    assert "triage_score" not in papers[0]
    assert papers[2]["triage_score"] == 4


def test_enrich_budget(monkeypatch):
    papers = _papers(5)
    monkeypatch.setattr(
        llm_client, "chat_json",
        lambda *a, **k: [
            {"triage_score": 4, "triage_summary": "x", "subtopic": "personalization"}
            for _ in range(3)
        ],
    )
    enrich.enrich_papers(papers, _cfg(max_papers_per_run=3, batch_size=3))
    assert sum("triage_score" in p for p in papers) == 3


def test_enrich_disabled_and_not_configured(monkeypatch):
    papers = _papers(2)
    monkeypatch.setattr(llm_client, "chat_json", lambda *a, **k: pytest.fail("should not call LLM"))
    enrich.enrich_papers(papers, _cfg(enabled=False))
    assert all("triage_score" not in p for p in papers)

    monkeypatch.setattr(llm_client, "is_configured", lambda: False)
    enrich.enrich_papers(papers, _cfg())
    assert all("triage_score" not in p for p in papers)


def test_enrich_invalid_subtopic_falls_back(monkeypatch):
    monkeypatch.setattr(
        llm_client, "chat_json",
        lambda *a, **k: [{"triage_score": 3, "triage_summary": "x", "subtopic": "nope"}],
    )
    papers = _papers(1)
    enrich.enrich_papers(papers, _cfg(batch_size=1))
    assert papers[0]["subtopic"] == "other"


def test_enrich_never_raises():
    enrich.enrich_papers([], None)
    enrich.enrich_papers(None, _cfg())
