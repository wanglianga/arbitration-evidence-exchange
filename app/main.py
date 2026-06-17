from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import os

from app.config import settings
from app.database import Base, engine
from app.routers import (
    auth, cases, parties, agents, catalogs,
    upload, evidences, batches, cross_examinations,
    reviews, supplements, hearings, overdue_reviews
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.CHUNK_DIR, exist_ok=True)
    os.makedirs(os.path.join(settings.UPLOAD_DIR, "files"), exist_ok=True)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="线上仲裁证据交换服务 - 支持案件管理、证据上传、交换批次、质证意见、庭审引用等功能",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["根路径"])
async def root():
    return {
        "service": settings.APP_NAME,
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/health", tags=["健康检查"])
async def health_check():
    return {"status": "healthy", "service": settings.APP_NAME}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误", "message": str(exc)}
    )


app.include_router(auth.router)
app.include_router(cases.router)
app.include_router(parties.router)
app.include_router(agents.router)
app.include_router(catalogs.router)
app.include_router(upload.router)
app.include_router(evidences.router)
app.include_router(batches.router)
app.include_router(cross_examinations.router)
app.include_router(reviews.router)
app.include_router(supplements.router)
app.include_router(hearings.router)
app.include_router(overdue_reviews.router)
