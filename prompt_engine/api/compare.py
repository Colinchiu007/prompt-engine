"""文案分句 → 提示词 → 生图对比验证 API（Compare Tab）

三个无状态端点，供前端「对比验证」页签使用：
- POST /v1/compare/split   — 代理 smart-sentence-splitter 分句服务（SPLITTER_BASE_URL）
- POST /v1/compare/prompt  — 单句经 MiniMax LLM（OpenAI 兼容 chat/completions）生成英文生图提示词
- POST /v1/compare/images  — 单提示词经 MiniMax image-01 生成 n 张图（默认 2 张）供对比

API Key 流转（C1）：
- 请求体 api_key（前端输入，浏览器内存/localStorage）优先级最高
- 其次环境变量 MINIMAX_API_KEY（验证/部署场景由宿主注入）
- key 仅存于本次请求的局部变量，不落盘、不进日志（错误消息清洗）

外部契约（对齐 Multi-Publish 运营后台 model-preset）：
- LLM:  POST {base_url}/chat/completions  OpenAI 兼容，Bearer key，模型 MiniMax-M3/M2.7
- 生图: POST {base_url}/image_generation  {"model":"image-01","prompt","response_format":"url","n":2,"aspect_ratio":"1:1"}
"""
from __future__ import annotations

import asyncio
import os
import re
import time

import httpx
from fastapi import APIRouter, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import Literal

from prompt_engine.api.minimax_client import (
    DEFAULT_MINIMAX_BASE_URL,
    MinimaxImageError,
    generate_minimax_images,
)
from prompt_engine_core.text import strip_reasoning_blocks

router = APIRouter(tags=["compare"])

# ── 常量 ────────────────────────────────────────────────
MAX_TEXT_LENGTH = 6000          # 文案上限（需求）
MAX_PROMPT_LENGTH = 2000        # 生图提示词上限
SPLITTER_BASE_URL = os.environ.get("SPLITTER_BASE_URL", "http://127.0.0.1:8002")
SPLITTER_TIMEOUT = 15.0
DEFAULT_LLM_BASE_URL = os.environ.get("MINIMAX_BASE_URL", DEFAULT_MINIMAX_BASE_URL)
DEFAULT_LLM_MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M3")
DEFAULT_LLM_MAX_TOKENS = 1500
DEFAULT_LLM_TIMEOUT = 60.0

# 生图提示词生成的系统提示词（中文文案 → 英文视觉描述）
PROMPT_SYSTEM_PROMPT = (
    "你是一名专业的图片提示词撰写专家。请把用户提供的中文句子转换为适合图片生成模型"
    "（MiniMax image-01）的英文提示词。要求：\n"
    "1. 只输出英文提示词本身，不要任何解释、引号、编号或前后缀；\n"
    "2. 保留原文的核心意象、主体、场景与氛围，不遗漏关键信息；\n"
    "3. 补充视觉细节：构图、光影、色彩、风格、质感、镜头角度等，使画面具体可生成；\n"
    "4. 长度控制在 50~300 个英文单词；\n"
    "5. 不要输出 <think> 等思考过程，直接给最终提示词。"
)


def _get_api_key(body_api_key: str | None) -> str:
    """取 MiniMax API Key：请求体 > 环境变量。"""
    key = (body_api_key or "").strip()
    if key:
        return key
    return (os.environ.get("MINIMAX_API_KEY") or "").strip()


def _validate_base_url(base_url: str | None) -> str:
    """校验 base_url（SSRF 缓解）：

    - 仅允许 http(s)://host[/path]；
    - 拒绝回环/私网/链路本地/云 metadata 地址（127.0.0.1、localhost、10.x、172.16-31.x、
      192.168.x、169.254.x、::1、fc00::/7、fe80::/10 等）；
    - 非回环 host 强制 https（避免 Key 走明文网络）。
    """
    value = (base_url or DEFAULT_LLM_BASE_URL).strip().rstrip("/")
    if not value:
        value = DEFAULT_LLM_BASE_URL
    m = re.match(r"^(https?)://([^/\s]+)(/.*)?$", value)
    if not m:
        raise HTTPException(status_code=422, detail=f"base_url 格式非法：{value}")
    scheme = m.group(1)
    host = m.group(2)
    if any(c in host for c in ("@", " ", "\t", "\r", "\n", "[")):
        raise HTTPException(status_code=422, detail="base_url host 含非法字符")
    hostname = host.split(":")[0].lower()
    is_loopback = hostname in ("localhost", "127.0.0.1", "::1")
    if is_loopback:
        raise HTTPException(status_code=422, detail="base_url 不允许指向本机回环地址（请使用官方域名或远程代理）")
    if _is_private_or_link_local(hostname):
        raise HTTPException(status_code=422, detail="base_url 不允许指向私网/链路本地地址（SSRF 防护）")
    if scheme != "https":
        raise HTTPException(status_code=422, detail="base_url 非回环地址必须使用 https")
    return value


def _is_private_or_link_local(hostname: str) -> bool:
    """判断 hostname（去端口）是否为私网/链路本地/云 metadata 地址。"""
    if not hostname:
        return True
    if re.match(r"^10\.\d{1,3}\.\d{1,3}\.\d{1,3}$", hostname):
        return True
    if re.match(r"^192\.168\.\d{1,3}\.\d{1,3}$", hostname):
        return True
    m = re.match(r"^172\.(\d{1,3})\.\d{1,3}\.\d{1,3}$", hostname)
    if m and 16 <= int(m.group(1)) <= 31:
        return True
    if re.match(r"^169\.254\.\d{1,3}\.\d{1,3}$", hostname):
        return True
    if hostname.startswith(("fc", "fd")) and len(hostname) >= 3 and all(c in "0123456789abcdef" for c in hostname[:2]):
        return True  # fc00::/7 (ULA)
    if hostname.startswith("fe8") or hostname.startswith("fe9") or hostname.startswith("fea") or hostname.startswith("feb"):
        return True  # fe80::/10 (link-local)
    if re.match(r"^\d+\.\d+\.\d+\.\d+$", hostname):
        # 其他数字 IP：保守拒绝（避免 metadata 等特殊段）
        return True
    return False


# ── 请求/响应模型 ───────────────────────────────────────
class SplitRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH, description="待分句文案（≤6000 字）")
    language: Literal["auto", "zh", "en"] = Field(default="auto", description="auto | zh | en")
    mode: Literal["fast", "balanced", "precise"] = Field(default="balanced", description="fast | balanced | precise")


class SplitSentence(BaseModel):
    index: int
    text: str
    language: str
    tier: str
    confidence: float
    char_count: int


class SplitResponse(BaseModel):
    sentences: list[SplitSentence]
    scenes: list[dict] = Field(default_factory=list)
    text_length: int
    language: str
    tier_used: str
    splitter: str
    duration_ms: int


class PromptRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)
    api_key: str | None = Field(default=None, description="MiniMax API Key（可选，缺省用环境变量）")
    base_url: str | None = Field(default=None, description="MiniMax base_url（可选）")
    model: str | None = Field(default=None, description="LLM 模型名（默认 MiniMax-M3）")


class PromptResult(BaseModel):
    prompt: str
    model: str
    duration_ms: int
    retryable: bool = False
    truncated: bool = False


class ImagesRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=MAX_PROMPT_LENGTH)
    api_key: str | None = Field(default=None)
    base_url: str | None = Field(default=None)
    n: int = Field(default=2, ge=1, le=4, description="生成数量（默认 2 张对比）")
    width: int = Field(default=1024, ge=64, le=4096)
    height: int = Field(default=1024, ge=64, le=4096)


class ImagesResult(BaseModel):
    urls: list[str]
    count: int
    model: str
    duration_ms: int
    retryable: bool = False


# ── 端点 ────────────────────────────────────────────────

@router.post("/v1/compare/split", response_model=SplitResponse)
async def compare_split(req: SplitRequest):
    """代理 smart-sentence-splitter 分句。target 由服务端配置，不接受前端传入（防 SSRF）。"""
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="文案不能为空")
    if len(text) > MAX_TEXT_LENGTH:
        raise HTTPException(status_code=422, detail=f"文案超过 {MAX_TEXT_LENGTH} 字上限")

    start = time.perf_counter()
    try:
        # to_thread：避免同步 httpx 阻塞事件循环（复现 61ad3b2 已修复的 Bridge 重启缺陷）
        resp = await asyncio.to_thread(
            httpx.post,
            f"{SPLITTER_BASE_URL}/v1/split",
            json={"text": text, "language": req.language, "mode": req.mode},
            timeout=SPLITTER_TIMEOUT,
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=f"分句服务超时（{SPLITTER_BASE_URL}），请确认 smart-sentence-splitter 已启动")
    except httpx.NetworkError:
        raise HTTPException(
            status_code=503,
            detail=f"无法连接分句服务 {SPLITTER_BASE_URL}，请先启动 smart-sentence-splitter（端口 8002）")

    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail") or resp.text[:200]
        except Exception:  # noqa: BLE001
            detail = resp.text[:200]
        detail = str(detail).replace("\n", " ").replace("\r", " ")[:200]
        raise HTTPException(status_code=resp.status_code, detail=f"分句服务错误：{detail}")

    data = resp.json()
    sentences = [
        SplitSentence(
            index=s.get("index", i),
            text=s.get("text", ""),
            language=s.get("language", req.language),
            tier=s.get("tier", data.get("tier_used", "")),
            confidence=float(s.get("confidence", 0.0)),
            char_count=int(s.get("char_count", len(s.get("text", "")))),
        )
        for i, s in enumerate(data.get("sentences", []))
    ]
    if not sentences:
        raise HTTPException(status_code=422, detail="分句服务返回了空结果，请检查输入文本")

    return SplitResponse(
        sentences=sentences,
        scenes=data.get("scenes", []) or [],
        text_length=data.get("text_length", len(text)),
        language=data.get("language", req.language),
        tier_used=data.get("tier_used", ""),
        splitter=SPLITTER_BASE_URL,
        duration_ms=int((time.perf_counter() - start) * 1000),
    )


@router.post("/v1/compare/prompt", response_model=PromptResult)
async def compare_prompt(req: PromptRequest):
    """单句 → MiniMax LLM 生成英文生图提示词（剥离 <think>，空输出视为可重试错误）。"""
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="分句文本不能为空")

    api_key = _get_api_key(req.api_key)
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="MiniMax API Key 未配置：请在「对比验证」设置区填写，或设置环境变量 MINIMAX_API_KEY")

    base_url = _validate_base_url(req.base_url)
    model = (req.model or DEFAULT_LLM_MODEL).strip() or DEFAULT_LLM_MODEL

    start = time.perf_counter()
    try:
        client = OpenAI(api_key=api_key, base_url=base_url, max_retries=2)
        # to_thread：LLM 单次最长 60s 且含重试，同步调用会阻塞事件循环
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=model,
            messages=[
                {"role": "system", "content": PROMPT_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.8,
            max_tokens=DEFAULT_LLM_MAX_TOKENS,
            timeout=DEFAULT_LLM_TIMEOUT,
        )
    except Exception as e:  # noqa: BLE001 — openai 客户端异常统一映射
        msg = str(e).replace("\n", " ")[:200]
        status = getattr(e, "status_code", None)
        if status in (401, 403):
            raise HTTPException(status_code=400, detail=f"MiniMax 鉴权失败：请检查 API Key（{msg[:80]}）")
        if status == 429:
            raise HTTPException(status_code=429, detail="MiniMax 请求过于频繁，请稍后重试")
        raise HTTPException(status_code=502, detail=f"MiniMax LLM 调用失败：{msg}")

    raw_content = ""
    try:
        raw_content = response.choices[0].message.content or ""
    except Exception:  # noqa: BLE001
        raw_content = ""

    prompt = strip_reasoning_blocks(raw_content)
    if not prompt:
        # 输出 token 被推理耗尽或模型未返回内容 → 可重试
        raise HTTPException(
            status_code=502,
            detail="MiniMax 未返回有效提示词（推理内容已剥离后为空），请重试或增大 max_tokens")

    truncated = False
    if len(prompt) > MAX_PROMPT_LENGTH:
        prompt = prompt[:MAX_PROMPT_LENGTH]
        truncated = True

    return PromptResult(
        prompt=prompt,
        model=model,
        duration_ms=int((time.perf_counter() - start) * 1000),
        retryable=False,
        truncated=truncated,
    )


@router.post("/v1/compare/images", response_model=ImagesResult)
async def compare_images(req: ImagesRequest):
    """单提示词 → MiniMax image-01 生成 n 张图（默认 2 张）供对比。"""
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="提示词不能为空")

    api_key = _get_api_key(req.api_key)
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="MiniMax API Key 未配置：请在「对比验证」设置区填写，或设置环境变量 MINIMAX_API_KEY")

    base_url = _validate_base_url(req.base_url)

    start = time.perf_counter()
    try:
        # to_thread：生图单次最长 60s，同步 httpx 会阻塞事件循环
        result = await asyncio.to_thread(
            generate_minimax_images,
            prompt=prompt,
            api_key=api_key,
            base_url=base_url,
            n=req.n,
            width=req.width,
            height=req.height,
        )
    except MinimaxImageError as e:
        if e.error_type == "auth":
            status = 400
        elif e.error_type in ("content_safety", "empty_result", "invalid_config"):
            status = 422
        elif e.error_type == "rate_limit":
            status = 429
        elif e.error_type == "timeout":
            status = 504
        else:
            status = 502
        raise HTTPException(status_code=status, detail=e.message)

    return ImagesResult(
        urls=result["urls"],
        count=result["count"],
        model=result["model"],
        duration_ms=int((time.perf_counter() - start) * 1000),
        retryable=False,
    )


@router.get("/v1/compare/status")
async def compare_status():
    """对比验证页初始化状态：服务端是否已配置 MiniMax API Key（供前端启用按钮）。"""
    return {
        "has_env_key": bool((os.environ.get("MINIMAX_API_KEY") or "").strip()),
        "splitter": SPLITTER_BASE_URL,
        "default_llm_model": DEFAULT_LLM_MODEL,
    }