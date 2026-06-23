"""Voice Flow License Server — FastAPI 入口"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .api import router as api_router
from .admin import router as admin_router

app = FastAPI(title="Voice Flow License Server", version="1.0.0")

# CORS（允许客户端跨域请求）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(admin_router)


@app.on_event("startup")
def startup():
    init_db()
    print(f"License server started on port {os.environ.get('PORT', '8000')}")


@app.get("/")
def root():
    return {"service": "Voice Flow License Server", "version": "1.0.0"}
