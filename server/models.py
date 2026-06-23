"""Pydantic 请求/响应模型"""
from pydantic import BaseModel, Field


class ActivateRequest(BaseModel):
    machine_code: str = Field(..., min_length=8, max_length=128)
    license_key: str = Field(..., min_length=10, max_length=64)


class ActivateResponse(BaseModel):
    success: bool
    message: str = ""
    license_payload: str | None = None


class ValidateResponse(BaseModel):
    valid: bool
    expires_at: str = ""
    message: str = ""
    renewed_payload: str | None = None


class AdminLoginRequest(BaseModel):
    password: str = Field(..., min_length=1)


class AdminLoginResponse(BaseModel):
    token: str | None = None


class GenerateRequest(BaseModel):
    machine_code: str = Field(..., min_length=8, max_length=128)
    duration_days: int = Field(..., gt=0, le=3650)  # max 10 years
    notes: str | None = None


class GenerateResponse(BaseModel):
    license_key: str = ""
    expires_at: str = ""


class UpdateNotesRequest(BaseModel):
    notes: str = Field("", max_length=256)
