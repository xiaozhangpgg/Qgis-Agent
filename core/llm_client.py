import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, List, Optional

import requests

logger = logging.getLogger("QgisAgent")


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    models: List[str]
    default_model: str


PROVIDERS: Dict[str, ProviderConfig] = {
    "deepseek": ProviderConfig(
        name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        models=["deepseek-chat", "deepseek-coder"],
        default_model="deepseek-chat",
    ),
    "tongyi": ProviderConfig(
        name="通义千问",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        models=["qwen-plus", "qwen-turbo", "qwen-max"],
        default_model="qwen-plus",
    ),
    "zhipu": ProviderConfig(
        name="智谱",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        models=["glm-4-flash", "glm-4", "glm-4-plus"],
        default_model="glm-4-flash",
    ),
    "custom": ProviderConfig(
        name="自定义",
        base_url="",
        models=[],
        default_model="",
    ),
}

DEFAULT_TIMEOUT = 60


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    finish_reason: str = ""
    error: Optional[str] = None


class LLMClient:
    """OpenAI-compatible LLM client with SSE streaming and function calling."""

    def __init__(self):
        self._provider_key: str = "deepseek"
        self._api_key: str = ""
        self._model: str = "deepseek-chat"
        self._base_url: str = PROVIDERS["deepseek"].base_url
        self._timeout: int = DEFAULT_TIMEOUT
        self._supports_function_calling: bool = True
        self._abort: bool = False

    def configure(self, provider_key: str, api_key: str, model: str,
                  base_url: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT):
        self._provider_key = provider_key
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

        config = PROVIDERS.get(provider_key)
        if config:
            self._base_url = base_url or config.base_url
        else:
            self._base_url = base_url or ""

    def abort(self):
        self._abort = True

    def _reset_abort(self):
        self._abort = False

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key and self._base_url and self._model)

    def get_provider(self, key: str) -> Optional[ProviderConfig]:
        return PROVIDERS.get(key)

    def get_providers(self) -> Dict[str, ProviderConfig]:
        return PROVIDERS

    def test_connection(self) -> tuple:
        if not self._api_key:
            return False, "API Key 未设置"
        if not self._base_url:
            return False, "Base URL 未设置"

        url = f"{self._base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 5,
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            if resp.status_code == 200:
                return True, "连接成功"
            elif resp.status_code == 401:
                return False, "API Key 无效"
            elif resp.status_code == 403:
                return False, "API Key 权限不足或余额不足"
            else:
                return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
        except requests.exceptions.Timeout:
            return False, "连接超时"
        except requests.exceptions.ConnectionError:
            return False, "网络连接失败"
        except Exception as e:
            return False, str(e)

    def fetch_models(self) -> tuple:
        """Fetch available models from the API's /v1/models endpoint."""
        if not self._api_key:
            return False, "API Key 未设置"
        if not self._base_url:
            return False, "Base URL 未设置"

        url = f"{self._base_url.rstrip('/')}/models"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
        }

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                models = sorted([m["id"] for m in data.get("data", [])])
                if models:
                    return True, models
                return False, "API 返回了空的模型列表"
            elif resp.status_code == 401:
                return False, "API Key 无效"
            elif resp.status_code == 403:
                return False, "API Key 权限不足"
            else:
                return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
        except requests.exceptions.Timeout:
            return False, "连接超时"
        except requests.exceptions.ConnectionError:
            return False, "网络连接失败"
        except Exception as e:
            return False, str(e)

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Generator[LLMResponse, None, None]:
        self._reset_abort()

        if self._supports_function_calling and tools:
            yield from self._stream_with_tools(messages, tools)
        else:
            yield from self._stream_plain(messages)

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMResponse:
        result = LLMResponse()
        for chunk in self.chat_stream(messages, tools):
            if chunk.error:
                return chunk
            result.content += chunk.content
            if chunk.tool_calls:
                result.tool_calls = chunk.tool_calls
            if chunk.finish_reason:
                result.finish_reason = chunk.finish_reason
        return result

    def _stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> Generator[LLMResponse, None, None]:
        url = f"{self._base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "stream": True,
        }

        tool_call_buffers: Dict[int, Dict[str, str]] = {}

        try:
            resp = requests.post(
                url, json=payload, headers=headers,
                stream=True, timeout=self._timeout,
            )

            if resp.status_code != 200:
                error_msg = self._parse_error(resp)
                yield LLMResponse(error=error_msg)
                return

            for line in resp.iter_lines(decode_unicode=True):
                if self._abort:
                    resp.close()
                    yield LLMResponse(error="用户中断")
                    return

                if not line or not line.startswith("data: "):
                    continue

                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choices = data.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})
                finish_reason = choices[0].get("finish_reason", "")

                content = delta.get("content", "")
                if content:
                    yield LLMResponse(content=content)

                tool_calls_delta = delta.get("tool_calls", [])
                for tc_delta in tool_calls_delta:
                    idx = tc_delta.get("index", 0)
                    if idx not in tool_call_buffers:
                        tool_call_buffers[idx] = {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}

                    if tc_delta.get("id"):
                        tool_call_buffers[idx]["id"] = tc_delta["id"]
                    if tc_delta.get("function", {}).get("name"):
                        tool_call_buffers[idx]["function"]["name"] += tc_delta["function"]["name"]
                    if tc_delta.get("function", {}).get("arguments"):
                        tool_call_buffers[idx]["function"]["arguments"] += tc_delta["function"]["arguments"]

                if finish_reason == "tool_calls":
                    final_calls = []
                    for idx in sorted(tool_call_buffers.keys()):
                        tc = tool_call_buffers[idx]
                        try:
                            tc["function"]["arguments"] = json.loads(tc["function"]["arguments"])
                        except json.JSONDecodeError:
                            pass
                        final_calls.append(tc)
                    yield LLMResponse(tool_calls=final_calls, finish_reason="tool_calls")
                elif finish_reason == "stop":
                    yield LLMResponse(finish_reason="stop")

        except requests.exceptions.Timeout:
            yield LLMResponse(error=f"请求超时（{self._timeout}秒）")
        except requests.exceptions.ConnectionError:
            yield LLMResponse(error="网络连接失败，请检查网络")
        except Exception as e:
            logger.exception("LLM stream error")
            yield LLMResponse(error=f"请求异常: {str(e)}")

    def _stream_plain(
        self,
        messages: List[Dict[str, Any]],
    ) -> Generator[LLMResponse, None, None]:
        url = f"{self._base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
        }

        try:
            resp = requests.post(
                url, json=payload, headers=headers,
                stream=True, timeout=self._timeout,
            )

            if resp.status_code != 200:
                error_msg = self._parse_error(resp)
                yield LLMResponse(error=error_msg)
                return

            for line in resp.iter_lines(decode_unicode=True):
                if self._abort:
                    resp.close()
                    yield LLMResponse(error="用户中断")
                    return

                if not line or not line.startswith("data: "):
                    continue

                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choices = data.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})
                finish_reason = choices[0].get("finish_reason", "")

                content = delta.get("content", "")
                if content:
                    yield LLMResponse(content=content)

                if finish_reason == "stop":
                    yield LLMResponse(finish_reason="stop")

        except requests.exceptions.Timeout:
            yield LLMResponse(error=f"请求超时（{self._timeout}秒）")
        except requests.exceptions.ConnectionError:
            yield LLMResponse(error="网络连接失败，请检查网络")
        except Exception as e:
            logger.exception("LLM stream error")
            yield LLMResponse(error=f"请求异常: {str(e)}")

    def _parse_error(self, resp: requests.Response) -> str:
        if resp.status_code == 401:
            return "API Key 无效或已过期"
        if resp.status_code == 403:
            return "API Key 权限不足或余额不足"
        if resp.status_code == 429:
            return "请求过于频繁，请稍后重试"
        try:
            err = resp.json()
            msg = err.get("error", {}).get("message", "")
            if msg:
                return f"API 错误: {msg}"
        except Exception:
            pass
        return f"API 错误 (HTTP {resp.status_code})"
