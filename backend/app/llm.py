"""模型配置缓存和 OpenRouter 的普通、工具调用与流式接口。"""
import asyncio
import json
import os
import re
from contextlib import aclosing

import httpx
from redis import Redis
from redis.exceptions import RedisError

from .common import logger
from .db import ModelConfig, Session
from .schemas import ModelView

TTL = 60
cache = Redis.from_url(os.getenv("CACHE_URL", "redis://localhost:6379/0"),
                       socket_timeout=1, socket_connect_timeout=1, decode_responses=True)
TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}
API_URL = "https://openrouter.ai/api/v1/chat/completions"


def get_model(model_id):
    key = f"mini:model:{model_id}"
    try:
        cached = cache.get(key)
        if cached:
            return ModelView.model_validate_json(cached)
    except (RedisError, ValueError):
        logger.warning("model_cache_read_failed model_id=%s", model_id)
    with Session() as db:
        row = db.get(ModelConfig, model_id)
        model = ModelView.model_validate(row) if row else None
    if model:
        try:
            cache.setex(key, TTL, model.model_dump_json())
        except RedisError:
            logger.warning("model_cache_write_failed model_id=%s", model_id)
    return model


def invalidate_model(model_id):
    try:
        cache.delete(f"mini:model:{model_id}")
    except RedisError:
        logger.warning("model_cache_invalidate_failed model_id=%s", model_id)


class ModelError(Exception):
    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable


def client():
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise ModelError("未配置 OPENROUTER_API_KEY")
    return httpx.AsyncClient(
        timeout=httpx.Timeout(45, connect=8),
        headers={"Authorization": f"Bearer {key}"},
    )


def request_body(config, messages):
    return {"model": config.model, "messages": messages, "temperature": config.temperature,
            "max_tokens": config.max_tokens}


def check_status(status):
    if status >= 400:
        raise ModelError(f"OpenRouter HTTP {status}", status in TRANSIENT_STATUS)


def check_inband(data):
    if data.get("error"):
        error = data["error"]
        code = str(error.get("code", "")) if isinstance(error, dict) else ""
        if re.fullmatch(r"[45][0-9]{2}", code):
            check_status(int(code))
        raise ModelError("OpenRouter 返回生成错误")


def read_usage(data):
    raw = data.get("usage")
    if not isinstance(raw, dict):
        return None
    fields = ("prompt_tokens", "completion_tokens", "total_tokens")
    return {key: raw[key] for key in fields if type(raw.get(key)) is int} or None


async def complete(config, messages, tools=None):
    """Agent 的普通调用。重试由 Celery 任务统一负责。"""
    body = request_body(config, messages)
    if tools:
        body.update(tools=tools, tool_choice="auto", provider={"require_parameters": True})
    try:
        async with client() as http, asyncio.timeout(60):
            response = await http.post(API_URL, json=body)
            check_status(response.status_code)
            data = response.json()
            check_inband(data)
            choices = data["choices"]
            if choices[0].get("finish_reason") == "error":
                raise ModelError("OpenRouter 返回生成错误")
            return choices[0]["message"], read_usage(data)
    except (httpx.TransportError, TimeoutError):
        raise ModelError("OpenRouter 网络故障或超时", True) from None
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise ModelError("OpenRouter 响应格式异常") from None


async def stream_once(config, messages):
    body = {**request_body(config, messages), "stream": True,
            "stream_options": {"include_usage": True}}
    try:
        async with client() as http, asyncio.timeout(120):
            async with http.stream("POST", API_URL, json=body) as response:
                check_status(response.status_code)
                async for line in response.aiter_lines():
                    # OpenRouter 也会发送以冒号开头的 SSE 注释帧。
                    if not line.startswith("data:"):
                        continue
                    value = line[5:].strip()
                    if value == "[DONE]":
                        return
                    data = json.loads(value)
                    check_inband(data)
                    usage = read_usage(data)
                    if usage:
                        yield ("usage", usage)
                    for choice in data.get("choices") or []:
                        if choice.get("finish_reason") == "error":
                            raise ModelError("OpenRouter 返回生成错误")
                        delta = (choice.get("delta") or {}).get("content")
                        if delta:
                            yield ("delta", delta)
                raise ModelError("OpenRouter 流提前断开", True)
    except (httpx.TransportError, TimeoutError):
        raise ModelError("OpenRouter 网络故障或超时", True) from None
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ModelError("OpenRouter 流格式异常") from None


async def stream(config, messages):
    sent_text = False
    for attempt in range(3):
        try:
            async with aclosing(stream_once(config, messages)) as events:
                async for kind, value in events:
                    sent_text |= kind == "delta"
                    yield kind, value
            return
        except ModelError as exc:
            # 已向浏览器输出文本后重试会使答案重复。
            if sent_text or not exc.retryable or attempt == 2:
                raise
            await asyncio.sleep(0.5 * (attempt + 1))
