"""llm_client 测试：OpenCode Go 配置、多模型 fallback、JSON 提取。"""

from unittest import mock

import pytest

import tracker.llm_client as llm_client


def _completion(content):
    completion = mock.MagicMock()
    completion.choices[0].message.content = content
    return completion


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(llm_client.time, "sleep", lambda *a, **k: None)


@pytest.fixture
def _configured(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_MODELS", raising=False)


def test_is_configured(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert llm_client.is_configured() is False
    monkeypatch.setenv("LLM_API_KEY", "k")
    assert llm_client.is_configured() is True


def test_default_endpoint_and_model(_configured):
    base_url, _, models = llm_client._get_config()
    assert base_url == "https://opencode.ai/zen/go/v1"
    assert models[0] == "deepseek-v4-flash"


def test_chat_success(_configured):
    client = mock.MagicMock()
    client.chat.completions.create.return_value = _completion("hello")
    with mock.patch.object(llm_client, "OpenAI", return_value=client):
        assert llm_client.chat("sys", "user") == "hello"
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "deepseek-v4-flash"
    assert kwargs["messages"][0] == {"role": "system", "content": "sys"}


def test_chat_model_fallback(_configured, monkeypatch):
    monkeypatch.setenv("LLM_MODELS", "qwen3.7-max,glm-5.2")
    client = mock.MagicMock()
    client.chat.completions.create.side_effect = [
        TimeoutError("first model down"),
        _completion("recovered"),
    ]
    with mock.patch.object(llm_client, "OpenAI", return_value=client):
        assert llm_client.chat("", "user", max_retries=1) == "recovered"
    models_tried = [c.kwargs["model"] for c in client.chat.completions.create.call_args_list]
    assert models_tried == ["qwen3.7-max", "glm-5.2"]


def test_chat_all_models_fail(_configured, monkeypatch):
    monkeypatch.setenv("LLM_MODELS", "qwen3.7-max,glm-5.2")
    client = mock.MagicMock()
    client.chat.completions.create.side_effect = TimeoutError("down")
    with mock.patch.object(llm_client, "OpenAI", return_value=client):
        with pytest.raises(llm_client.LLMError):
            llm_client.chat("", "user", max_retries=1)
    assert client.chat.completions.create.call_count == 2


def test_chat_json_fence(_configured):
    client = mock.MagicMock()
    client.chat.completions.create.return_value = _completion('```json\n[{"x": 1}]\n```')
    with mock.patch.object(llm_client, "OpenAI", return_value=client):
        assert llm_client.chat_json("", "user") == [{"x": 1}]


def test_chat_json_bad_raises(_configured):
    client = mock.MagicMock()
    client.chat.completions.create.return_value = _completion("not json")
    with mock.patch.object(llm_client, "OpenAI", return_value=client):
        with pytest.raises(llm_client.LLMError):
            llm_client.chat_json("", "user", max_retries=1)


def test_chat_not_configured_raises(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(llm_client.LLMError):
        llm_client.chat("", "user")
