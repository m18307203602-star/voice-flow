"""Pydantic request/response models"""
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
    duration_days: int = Field(..., gt=0, le=3650)
    notes: str | None = None


class GenerateResponse(BaseModel):
    license_key: str = ""
    expires_at: str = ""


class HeartbeatRequest(BaseModel):
    machine_code: str = Field(..., min_length=8, max_length=128)
    license_payload: str | None = None
    system_info: dict | None = None


class HistoryRecord(BaseModel):
    id: int = 0
    created_at: str = ""
    duration: float = 0.0
    engines: list = []
    mode: str = ""
    mode_name: str = ""
    transcripts: dict = {}
    result: str = ""
    model_used: str = ""
    status: str = "success"
    stt_engine: str = ""
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0


class HistoryUploadRequest(BaseModel):
    machine_code: str = Field(..., min_length=8, max_length=128)
    license_payload: str | None = None
    records: list[dict] = []


class UpdateNotesRequest(BaseModel):
    notes: str = Field("", max_length=256)


class TrialCardGenerateRequest(BaseModel):
    count: int = Field(1, gt=0, le=100)
    notes: str | None = None


class TrialCardGenerateResponse(BaseModel):
    cards: list[str] = []
    expires_at: str = ""


class PromptsRequest(BaseModel):
    machine_code: str = Field(..., min_length=8, max_length=128)
    license_payload: str = Field(..., min_length=10, max_length=4096)


class PromptsResponse(BaseModel):
    success: bool
    message: str = ""
    prompts: dict | None = None
    version: int = 0
