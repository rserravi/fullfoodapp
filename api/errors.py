from __future__ import annotations
from typing import Any, Dict
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

class ErrorResponse(BaseModel):
    code: str = Field(examples=["bad_request"])
    detail: str = Field(examples=["Invalid input"])
    meta: dict | None = Field(default=None, examples=[{"field": "start_date"}])

def install_exception_handlers(app: FastAPI):
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        code_map: Dict[int, str] = {
            400: "bad_request",
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            409: "conflict",
            422: "validation_error",
            429: "rate_limited",
            500: "internal_error",
        }
        payload = ErrorResponse(code=code_map.get(exc.status_code, "error"), detail=str(exc.detail))
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        payload = ErrorResponse(code="validation_error", detail="Validation failed", meta={"errors": exc.errors()})
        return JSONResponse(status_code=422, content=payload.model_dump())
