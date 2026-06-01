from __future__ import annotations

import html
import json
import traceback
import uuid
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any

from fastapi import Request, status
from fastapi.responses import HTMLResponse, JSONResponse


@dataclass(frozen=True)
class ErrorCodeDefinition:
    code: str
    http_status: int
    title: str
    description: str
    troubleshooting: str


ERROR_CODE_CATALOG = [
    ErrorCodeDefinition(
        code="SYS-000",
        http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        title="INTERNAL_SERVER_ERROR",
        description="未捕获的服务端异常。",
        troubleshooting="检查 recent_errors 中的 stack_trace、request_id 和入参。",
    ),
    ErrorCodeDefinition(
        code="SYS-001",
        http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        title="REQUEST_VALIDATION_ERROR",
        description="请求参数缺失、类型错误或表单格式不正确。",
        troubleshooting="核对接口必填字段、Content-Type、字段名和数据类型。",
    ),
    ErrorCodeDefinition(
        code="SYS-002",
        http_status=status.HTTP_400_BAD_REQUEST,
        title="HTTP_EXCEPTION",
        description="显式抛出的通用 HTTP 错误。",
        troubleshooting="查看 message 与 details，确认业务参数是否合法。",
    ),
    ErrorCodeDefinition(
        code="REC-001",
        http_status=status.HTTP_400_BAD_REQUEST,
        title="PRICE_RANGE_INVALID",
        description="推荐接口的价格区间非法，例如最小值大于最大值。",
        troubleshooting="确保 price_min <= price_max。",
    ),
    ErrorCodeDefinition(
        code="REC-002",
        http_status=status.HTTP_502_BAD_GATEWAY,
        title="GEMINI_REQUEST_FAILED",
        description="调用 Gemini 进行图像分析失败。当前实现会自动回退规则推断。",
        troubleshooting="检查 gemini_api_key、模型名、网络连通性和配额。",
    ),
    ErrorCodeDefinition(
        code="DBG-001",
        http_status=status.HTTP_403_FORBIDDEN,
        title="DEBUG_PAGE_DISABLED",
        description="调试页或调试接口被环境变量禁用。",
        troubleshooting="将 ENABLE_DEBUG_PAGES=true 后再访问。",
    ),
    ErrorCodeDefinition(
        code="LAB-001",
        http_status=status.HTTP_404_NOT_FOUND,
        title="STYLE_LAB_PRODUCT_NOT_FOUND",
        description="自定义搭配页中选中的商品不存在。",
        troubleshooting="确认 product_id 是否来自最新商品列表，并检查本地数据库是否已初始化。",
    ),
]
ERROR_CODE_MAP = {item.code: item for item in ERROR_CODE_CATALOG}
RECENT_ERROR_EVENTS: deque[dict[str, Any]] = deque(maxlen=200)


class AppError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def get_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        return request_id

    request_id = uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    return request_id


def get_error_catalog() -> list[dict[str, Any]]:
    return [asdict(item) for item in ERROR_CODE_CATALOG]


def get_recent_errors(limit: int = 50) -> list[dict[str, Any]]:
    return list(RECENT_ERROR_EVENTS)[:limit]


def build_error_payload(
    *,
    code: str,
    message: str,
    request_id: str,
    details: Any | None = None,
) -> dict[str, Any]:
    payload = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        },
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


def record_error_event(
    *,
    request: Request,
    code: str,
    status_code: int,
    message: str,
    details: Any | None = None,
    stack_trace: str | None = None,
) -> dict[str, Any]:
    event = {
        "timestamp": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "request_id": get_request_id(request),
        "code": code,
        "status_code": status_code,
        "message": message,
        "method": request.method,
        "path": request.url.path,
        "query": dict(request.query_params),
        "details": details,
        "stack_trace": stack_trace,
    }
    RECENT_ERROR_EVENTS.appendleft(event)
    return event


def build_debug_page_html(base_url: str) -> str:
    catalog_rows = "".join(
        (
            "<tr>"
            f"<td>{html.escape(item.code)}</td>"
            f"<td>{item.http_status}</td>"
            f"<td>{html.escape(item.title)}</td>"
            f"<td>{html.escape(item.description)}</td>"
            f"<td>{html.escape(item.troubleshooting)}</td>"
            "</tr>"
        )
        for item in ERROR_CODE_CATALOG
    )

    recent_errors = get_recent_errors(limit=50)
    recent_rows = "".join(
        (
            "<tr>"
            f"<td>{html.escape(str(item['timestamp']))}</td>"
            f"<td>{html.escape(str(item['request_id']))}</td>"
            f"<td>{html.escape(str(item['code']))}</td>"
            f"<td>{html.escape(str(item['status_code']))}</td>"
            f"<td>{html.escape(str(item['method']))}</td>"
            f"<td>{html.escape(str(item['path']))}</td>"
            f"<td><pre>{html.escape(json.dumps(item.get('details'), ensure_ascii=False, indent=2))}</pre></td>"
            f"<td><pre>{html.escape((item.get('stack_trace') or '')[:6000])}</pre></td>"
            "</tr>"
        )
        for item in recent_errors
    )

    return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Backend Error Debug</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #111827; background: #f9fafb; }}
    h1, h2 {{ margin-bottom: 12px; }}
    p, li {{ line-height: 1.6; }}
    code {{ background: #e5e7eb; padding: 2px 6px; border-radius: 4px; }}
    table {{ width: 100%; border-collapse: collapse; background: #ffffff; margin-bottom: 24px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 10px; text-align: left; vertical-align: top; font-size: 14px; }}
    th {{ background: #f3f4f6; }}
    pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; }}
  </style>
</head>
<body>
  <h1>全局错误码调试页</h1>
  <p>错误码接口：<code>{html.escape(base_url.rstrip('/'))}/api/debug/error-codes</code></p>
  <p>最近错误接口：<code>{html.escape(base_url.rstrip('/'))}/api/debug/errors/recent</code></p>

  <h2>错误码目录</h2>
  <table>
    <thead>
      <tr>
        <th>Code</th>
        <th>HTTP</th>
        <th>Title</th>
        <th>Description</th>
        <th>Troubleshooting</th>
      </tr>
    </thead>
    <tbody>{catalog_rows}</tbody>
  </table>

  <h2>最近错误记录</h2>
  <table>
    <thead>
      <tr>
        <th>Timestamp</th>
        <th>Request ID</th>
        <th>Code</th>
        <th>Status</th>
        <th>Method</th>
        <th>Path</th>
        <th>Details</th>
        <th>Stack Trace</th>
      </tr>
    </thead>
    <tbody>{recent_rows}</tbody>
  </table>
</body>
</html>
""".strip()


def debug_page_response(base_url: str) -> HTMLResponse:
    return HTMLResponse(content=build_debug_page_html(base_url), status_code=status.HTTP_200_OK)


def app_error_response(request: Request, exc: AppError) -> JSONResponse:
    record_error_event(
        request=request,
        code=exc.code,
        status_code=exc.status_code,
        message=exc.message,
        details=exc.details,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=build_error_payload(
            code=exc.code,
            message=exc.message,
            request_id=get_request_id(request),
            details=exc.details,
        ),
    )


def unexpected_error_response(request: Request, exc: Exception) -> JSONResponse:
    stack_trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    record_error_event(
        request=request,
        code="SYS-000",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message="服务器内部异常",
        details={"exception_type": type(exc).__name__},
        stack_trace=stack_trace,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=build_error_payload(
            code="SYS-000",
            message="服务器内部异常",
            request_id=get_request_id(request),
            details={"exception_type": type(exc).__name__},
        ),
    )
