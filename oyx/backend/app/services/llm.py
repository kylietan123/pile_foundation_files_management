"""LLM 提供方抽象。

**这是为了把"院内如何部署"从代码问题降成配置问题。**

设计要点（对应《公共层契约》§1 与 §4.3）：

1. **可切换**：`none` / `cloud` / `local` 三种模式，同一套接口。
   院内项目默认走本地模型（`local`），不出内网。
   没配密钥时自动降级到 `none`，**不阻塞其它功能**。

2. **降级要诚实**：`none` 模式下不能假装回答了。
   返回结构里明确标注 `degraded=True` 与原因，
   前端显示"AI 未配置"，而不是编一段话糊弄用户。

3. **模型只负责组织语言，不负责提供事实**。
   事实由检索结果提供（见 retrieval.py），模型只做归纳。
   这样"AI 幻觉"从机制上被压到最低 —— 引用是硬要求的。

**为什么要做成抽象**：三方会议还没定院内是自建还是调云端 API。
如果直接把某个厂商 SDK 写进业务代码，会上定了另一种就得重写。
现在只需改 `.env`。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import settings

logger = logging.getLogger("app.ai")


@dataclass
class LLMReply:
    """模型返回。**必须带引用**，否则上层不允许展示给用户。"""

    text: str
    model: str | None = None
    provider: str = "none"
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int | None = None
    # 是否降级（未配置模型 / 调用失败）
    degraded: bool = False
    degrade_reason: str | None = None
    citations_used: list[dict] = field(default_factory=list)


class LLMProvider(Protocol):
    """提供方接口。实现只需满足这个协议。"""

    name: str

    def available(self) -> bool: ...

    def complete(self, *, system: str, user: str, max_tokens: int = 1200) -> LLMReply: ...


# ============================================================
# 未配置模式（默认）
# ============================================================


class NullProvider:
    """未配置模型时的降级实现。

    **它不编造答案**，只返回检索到的原始片段，
    并明确告知"AI 未配置，以下是检索到的原文"。
    这比编一段像模像样的话诚实得多，也不会污染设计判断。
    """

    name = "none"

    def available(self) -> bool:
        return False

    def complete(self, *, system: str, user: str, max_tokens: int = 1200) -> LLMReply:
        return LLMReply(
            text="",
            provider="none",
            degraded=True,
            degrade_reason=(
                "未配置 AI 模型（LLM_PROVIDER=none）。"
                "当前仅返回检索到的原文片段，不生成归纳性回答。"
            ),
        )


# ============================================================
# OpenAI 兼容提供方（云端与院内本地部署共用）
# ============================================================


class OpenAICompatProvider:
    """OpenAI 兼容接口的提供方。

    **云端 API 与院内本地部署（vLLM / Ollama / LMStudio 等）都用这一个类**，
    只是 base_url 与 model 不同 —— 这正是把部署方式降成配置的关键。

    刻意不引入第三方 SDK：用标准库 urllib 发请求，
    少一个依赖，另外两位的环境配置成本更低（与 security.py 同一取舍）。
    """

    name = "openai_compat"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def available(self) -> bool:
        # 本地部署常常不校验密钥，所以只要求有 base_url 和 model
        return bool(self.base_url and self.model)

    def complete(self, *, system: str, user: str, max_tokens: int = 1200) -> LLMReply:
        import time
        import urllib.error
        import urllib.request

        if not self.available():
            return NullProvider().complete(system=system, user=user)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,   # 工程问答要稳定，不要发挥
            "max_tokens": max_tokens,
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
            method="POST",
        )

        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            logger.warning("LLM 调用失败：%s", exc)
            return LLMReply(
                text="",
                provider=self.name,
                model=self.model,
                degraded=True,
                degrade_reason=f"模型调用失败：{exc}",
            )

        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            logger.warning("LLM 返回格式异常：%s", body)
            return LLMReply(
                text="",
                provider=self.name,
                model=self.model,
                degraded=True,
                degrade_reason=f"模型返回格式异常：{exc}",
            )

        usage = body.get("usage") or {}
        return LLMReply(
            text=text,
            provider=self.name,
            model=self.model,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            latency_ms=int((time.time() - t0) * 1000),
            degraded=False,
        )


# ============================================================
# 工厂
# ============================================================


def get_provider() -> LLMProvider:
    """按配置返回提供方。

    切换部署方式只需改 .env：
        LLM_PROVIDER=none    未配置（默认，降级为只返回检索原文）
        LLM_PROVIDER=cloud   云端 API
        LLM_PROVIDER=local   院内本地部署
    cloud 与 local 走同一个 OpenAICompatProvider，
    区别只是 LLM_BASE_URL 指向哪里。
    """
    mode = (settings.LLM_PROVIDER or "none").strip().lower()

    if mode in ("none", "", "off", "disabled"):
        return NullProvider()

    if mode in ("cloud", "local", "openai_compat"):
        if not settings.LLM_BASE_URL or not settings.LLM_MODEL:
            logger.warning(
                "LLM_PROVIDER=%s 但未配置 LLM_BASE_URL / LLM_MODEL，降级为 none",
                mode,
            )
            return NullProvider()
        return OpenAICompatProvider(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL,
        )

    logger.warning("未知的 LLM_PROVIDER=%s，降级为 none", mode)
    return NullProvider()


def provider_status() -> dict:
    """提供方状态，供前端显示与运维排查。"""
    p = get_provider()
    return {
        "mode": settings.LLM_PROVIDER or "none",
        "available": p.available(),
        "model": settings.LLM_MODEL or None,
        "base_url_configured": bool(settings.LLM_BASE_URL),
        "allow_cross_project": settings.AI_ALLOW_CROSS_PROJECT,
        "log_retention_days": settings.AI_LOG_RETENTION_DAYS,
        "note": (
            "未配置模型：仅返回检索到的原文片段，不生成归纳性回答"
            if not p.available()
            else "已配置模型：回答基于检索结果生成，必须带引用"
        ),
    }
