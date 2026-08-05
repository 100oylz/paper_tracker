"""OpenCode Go 的 OpenAI 兼容 LLM 客户端，支持多模型按序 fallback。"""

import json
import os
import re
import time

from loguru import logger

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


DEFAULT_BASE_URL = "https://opencode.ai/zen/go/v1"
DEFAULT_MODELS = ["deepseek-v4-flash", "mimo-v2.5", "hy3", "kimi-k2.7-code"]
REQUEST_TIMEOUT_SECONDS = 30


class LLMError(Exception):
    """LLM 调用失败（网络、超时、JSON 解析、全部模型失败等）。"""


def _get_config():
    base_url = os.getenv("LLM_BASE_URL", "").strip() or DEFAULT_BASE_URL
    api_key = os.getenv("LLM_API_KEY", "").strip()
    models = [m.strip() for m in os.getenv("LLM_MODELS", "").split(",") if m.strip()]
    single = os.getenv("LLM_MODEL", "").strip()
    if single and single not in models:
        models.append(single)
    if not models:
        models = list(DEFAULT_MODELS)
    return base_url, api_key, models


def is_configured():
    _, api_key, _ = _get_config()
    return bool(api_key)


def _make_client():
    if OpenAI is None:
        raise LLMError("openai package is not installed. Run: pip install openai")
    base_url, api_key, _ = _get_config()
    if not api_key:
        raise LLMError("LLM API key not configured (LLM_API_KEY)")
    return OpenAI(api_key=api_key, base_url=base_url, timeout=REQUEST_TIMEOUT_SECONDS)


def chat(system, user, temperature=0.2, max_retries=3):
    """调用 /chat/completions，按 LLM_MODELS 顺序逐个模型重试；全部失败抛 LLMError。"""
    client = _make_client()
    _, _, models = _get_config()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    last_err = None
    for model in models:
        for attempt in range(1, max_retries + 1):
            try:
                completion = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                )
                content = completion.choices[0].message.content
                if content and content.strip():
                    return content.strip()
                last_err = LLMError("empty response content")
                logger.warning(f"LLM empty content, model={model}, attempt {attempt}/{max_retries}")
            except LLMError:
                raise
            except Exception as exc:
                last_err = exc
                logger.warning(f"LLM attempt {attempt}/{max_retries} failed (model={model}): {exc}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
        logger.warning(f"LLM model exhausted retries: {model}, trying next model if any")
    raise LLMError(f"LLM chat failed for all models {models}: {last_err}")


def _extract_json(text):
    if not text:
        raise ValueError("empty text")
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, flags=re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        for open_ch, close_ch in (("[", "]"), ("{", "}")):
            start = cleaned.find(open_ch)
            end = cleaned.rfind(close_ch)
            if start != -1 and end > start:
                try:
                    return json.loads(cleaned[start:end + 1])
                except json.JSONDecodeError:
                    continue
        raise


def chat_json(system, user, temperature=0.2, max_retries=3):
    json_user = user + "\n\n请只输出合法的 JSON，不要输出任何其他文字或 markdown 代码围栏。"
    last_err = None
    for attempt in range(1, 4):
        try:
            content = chat(system, json_user, temperature=temperature, max_retries=max_retries)
            return _extract_json(content)
        except LLMError:
            raise
        except Exception as exc:
            last_err = exc
            logger.warning(f"LLM JSON parse failed, attempt {attempt}/3: {exc}")
    raise LLMError(f"LLM returned invalid JSON after 3 attempts: {last_err}")
