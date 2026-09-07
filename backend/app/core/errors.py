from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


@dataclass(slots=True)
class AppError(Exception):
    code: str
    message: str
    status_code: int
    details: list[dict[str, Any]] | None = None


def error_payload(
    *, code: str, message: str, request_id: str, details: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": request_id,
    }
    if details:
        error["details"] = details
    return {"error": error}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "req_unknown")


def _contains_schema_version(value: object) -> bool:
    if isinstance(value, dict):
        return "schema_version" in value or any(
            _contains_schema_version(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_schema_version(item) for item in value)
    return False


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                code=exc.code,
                message=exc.message,
                request_id=_request_id(request),
                details=exc.details,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        locations = [tuple(error["loc"]) for error in errors]
        error_types = {error["type"] for error in errors}
        if _contains_schema_version(exc.body) and any(
            location and location[-1] == "schema_version" for location in locations
        ):
            code = "SCHEMA_VERSION_UNSUPPORTED"
            message = "请求使用了当前服务不支持的 schema 版本。"
        elif "rule_invalid" in error_types or any(
            location and location[-1] in {"fact_path", "selector_path"}
            for location in locations
        ):
            code = "RULE_INVALID"
            message = "规则包含不允许的字段路径、重复标识或非法结构。"
        elif any(len(location) > 1 and location[1] == "rule_set" for location in locations):
            code = "RULE_VALIDATION_FAILED"
            message = "规则格式不正确，请检查后重试。"
        elif any(len(location) > 1 and location[1] == "profile" for location in locations):
            code = "INPUT_VALIDATION_FAILED"
            message = "申请事实不完整或格式不正确，请检查后重试。"
        else:
            code = "INPUT_INVALID"
            message = "输入信息不完整或格式不正确，请检查后重试。"
        details = [
            {
                "field": ".".join(str(part) for part in error["loc"] if part != "body"),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in errors
        ]
        return JSONResponse(
            status_code=422,
            content=error_payload(
                code=code,
                message=message,
                request_id=_request_id(request),
                details=details,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request.app.state.logger.exception(
            "unexpected_error request_id=%s error_type=%s",
            _request_id(request),
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content=error_payload(
                code="INTERNAL_ERROR",
                message="服务暂时不可用，请稍后重试。",
                request_id=_request_id(request),
            ),
        )
