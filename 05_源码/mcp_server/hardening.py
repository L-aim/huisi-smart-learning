"""MCP 服务的公网必需机制：API Key 鉴权、限流、访问日志脱敏、健康检查。

对应《推进计划》P0-3「MCP 服务无任何公网必需机制」。

设计原则
--------
1. **全部默认非阻断**。没配 ``MCP_API_KEY`` 就不鉴权；限流阈值默认很宽；
   健康检查与正常请求互不干扰。这样在 AgentArts 运行时（走 IAM 签名、
   不带 API Key）里不会打断已有链路。
2. **纯 ASGI 中间件**，不依赖 Starlette / FastAPI 的具体版本，也不改动
   FastMCP 内部实现。
3. **日志不记请求头和请求体**。只记「方法 + 路径 + 客户端 + 状态码 + 耗时」，
   从结构上避免 Authorization / X-API-Key / AK/SK 落进日志。

环境变量
--------
- ``MCP_API_KEY``            设置后启用 API Key 鉴权；不设则不鉴权。
- ``MCP_RATE_LIMIT_PER_MIN`` 每分钟每客户端允许的请求数，默认 240；``0`` 表示不限。
- ``MCP_HEALTH_PATH``        健康检查路径，默认 ``/healthz``。
- ``MCP_LOG_REQUESTS``       设为 ``0`` 关闭访问日志，默认开启。
- ``MCP_TRANSPORT_DIRECT``   设为 ``1`` 退回到 FastMCP 原生 ``mcp.run()``（应急开关）。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from collections import deque
from typing import Any, Deque, Dict, Tuple

logger = logging.getLogger("ict_mcp.access")

SERVICE_NAME = "ict-mcp-server"
SERVICE_VERSION = "1.0.0"

_STARTED_AT = time.time()

# 健康检查与鉴权豁免路径（FastMCP 的 MCP 端点是 /mcp）
_MCP_PATHS = ("/mcp", "/mcp/")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("环境变量 %s=%r 不是整数，回退为默认值 %d", name, raw, default)
        return default


def _key_fingerprint(value: str) -> str:
    """密钥指纹：只保留 sha256 前 8 位十六进制。

    用于日志与限流分桶——既能区分不同凭据、便于对账，又不可逆，
    不会把 API Key 的任何片段写进日志。
    """
    text = (value or "").strip()
    if not text:
        return "anonymous"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _client_key(scope: Dict[str, Any], api_key: str) -> str:
    """限流分桶键：配了 API Key 用其指纹，否则用对端地址。"""
    if api_key:
        return "key:" + _key_fingerprint(api_key)
    client = scope.get("client") or ("unknown", 0)
    return f"ip:{client[0]}"


def _header(scope: Dict[str, Any], name: bytes) -> str:
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            return value.decode("latin-1")
    return ""


async def _send_json(send, status: int, payload: Dict[str, Any], extra_headers=None) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = [
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    if extra_headers:
        headers.extend(extra_headers)
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": headers,
        }
    )
    await send({"type": "http.response.body", "body": body})


class RateLimiter:
    """滑动窗口限流。每客户端保留最近 60 秒的时间戳。"""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = max(0, per_minute)
        self._hits: Dict[str, Deque[float]] = {}

    def allow(self, key: str) -> Tuple[bool, int]:
        """返回 (是否放行, 建议的 Retry-After 秒数)。"""
        if self.per_minute <= 0:
            return True, 0
        now = time.time()
        window = self._hits.setdefault(key, deque())
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.per_minute:
            retry_after = max(1, int(60 - (now - window[0])) + 1)
            return False, retry_after
        window.append(now)
        # 避免长期运行后字典无限增长
        if len(self._hits) > 4096:
            for stale in [k for k, v in self._hits.items() if not v]:
                self._hits.pop(stale, None)
        return True, 0


class HardeningMiddleware:
    """鉴权 + 限流 + 健康检查 + 访问日志（脱敏）。"""

    def __init__(self, app) -> None:
        self.app = app
        self.api_key = os.environ.get("MCP_API_KEY", "").strip()
        self.limiter = RateLimiter(_env_int("MCP_RATE_LIMIT_PER_MIN", 240))
        self.health_path = os.environ.get("MCP_HEALTH_PATH", "/healthz").strip() or "/healthz"
        self.log_requests = os.environ.get("MCP_LOG_REQUESTS", "1").strip() != "0"
        if self.api_key:
            logger.info("API Key 鉴权已启用（fingerprint=%s）", _key_fingerprint(self.api_key))
        else:
            logger.warning("未配置 MCP_API_KEY，API Key 鉴权未启用（仅依赖平台侧 IAM 签名）")

    # -- 内部动作 ---------------------------------------------------------
    async def _health(self, send) -> None:
        await _send_json(
            send,
            200,
            {
                "ok": True,
                "service": SERVICE_NAME,
                "version": SERVICE_VERSION,
                "uptime_s": round(time.time() - _STARTED_AT, 1),
                "auth": "api_key" if self.api_key else "none",
                "rate_limit_per_min": self.limiter.per_minute,
            },
        )

    def _check_api_key(self, scope: Dict[str, Any]) -> bool:
        if not self.api_key:
            return True
        provided = _header(scope, b"x-api-key")
        if not provided:
            auth = _header(scope, b"authorization")
            if auth.lower().startswith("bearer "):
                provided = auth[7:].strip()
        if not provided:
            return False
        return hmac.compare_digest(provided, self.api_key)

    # -- ASGI 入口 --------------------------------------------------------
    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        path = scope.get("path", "") or ""
        method = scope.get("method", "GET")

        if path in (self.health_path, "/healthz", "/readyz"):
            return await self._health(send)

        started = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapper(message):
            if message.get("type") == "http.response.start":
                raw = message.get("status", 500)
                try:
                    # Starlette 可能传 http.HTTPStatus 枚举，这里统一成整数，
                    # 否则日志里会出现 ``HTTPStatus.NOT_ACCEPTABLE`` 这种写法。
                    status_holder["status"] = int(raw)
                except (TypeError, ValueError):
                    status_holder["status"] = 500
            await send(message)

        if path in _MCP_PATHS and not self._check_api_key(scope):
            status_holder["status"] = 401
            await _send_json(
                send,
                401,
                {
                    "ok": False,
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "缺少或错误的 API Key，请在 X-API-Key 或 Authorization: Bearer 中提供。",
                    },
                },
            )
        else:
            allowed, retry_after = self.limiter.allow(_client_key(scope, self.api_key))
            if not allowed:
                status_holder["status"] = 429
                await _send_json(
                    send,
                    429,
                    {
                        "ok": False,
                        "error": {
                            "code": "RATE_LIMITED",
                            "message": f"超过每分钟 {self.limiter.per_minute} 次的调用上限，请稍后再试。",
                        },
                    },
                    extra_headers=[(b"retry-after", str(retry_after).encode("ascii"))],
                )
            else:
                await self.app(scope, receive, send_wrapper)

        if self.log_requests:
            cost_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "%s %s -> %s %.1fms client=%s",
                method,
                path,
                status_holder["status"],
                cost_ms,
                _client_key(scope, self.api_key),
            )


def _install_logging() -> None:
    level = os.environ.get("MCP_LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level, logging.INFO))
    logger.propagate = False


def build_app(mcp) -> Any:
    """把 FastMCP 的 streamable-http 应用包上加固中间件。"""
    inner = mcp.streamable_http_app()
    return HardeningMiddleware(inner)


def serve(mcp, host: str, port: int) -> None:
    """对外启动入口。

    应急开关：``MCP_TRANSPORT_DIRECT=1`` 时退回 FastMCP 原生启动方式，
    跳过全部加固逻辑（用于加固层本身出问题时快速恢复）。
    """
    _install_logging()

    if os.environ.get("MCP_TRANSPORT_DIRECT", "").strip() == "1":
        logger.warning("MCP_TRANSPORT_DIRECT=1，跳过加固层，使用 FastMCP 原生启动")
        mcp.run(transport="streamable-http")
        return

    try:
        app = build_app(mcp)
    except Exception as exc:  # 加固层不可用时宁可降级也不要让服务起不来
        logger.error("加固层初始化失败，降级为原生启动：%s: %s", type(exc).__name__, exc)
        mcp.run(transport="streamable-http")
        return

    import uvicorn

    logger.info("启动 %s v%s on %s:%s（health=%s）", SERVICE_NAME, SERVICE_VERSION, host, port, os.environ.get("MCP_HEALTH_PATH", "/healthz"))
    uvicorn.run(app, host=host, port=port, log_level="info")
