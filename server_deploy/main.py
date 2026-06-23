"""Voice Flow License Server — FastAPI entry"""
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from database import init_db
from api import router as api_router
from admin import router as admin_router
from prompts_api import router as prompts_router
from update_api import router as update_router

app = FastAPI(title="Voice Flow License Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(admin_router)
app.include_router(prompts_router)
app.include_router(update_router)

# Admin dashboard HTML
ADMIN_HTML = (Path(__file__).parent / "admin.html").read_text(encoding="utf-8")


@app.on_event("startup")
def startup():
    init_db()
    print(f"License server started on port {os.environ.get('PORT', '8000')}")


@app.get("/", response_class=HTMLResponse)
def dashboard():
    """管理后台"""
    return ADMIN_HTML


@app.get("/api/ping")
def ping():
    return {"status": "ok", "version": "1.0.0"}
