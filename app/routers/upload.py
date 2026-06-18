from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional
import os
import uuid
import hashlib
import shutil
from datetime import datetime, timezone

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user
from app.config import settings

router = APIRouter(prefix="/api/upload", tags=["文件上传"])


def ensure_dirs():
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.CHUNK_DIR, exist_ok=True)


def calculate_file_hash(file_path: str) -> str:
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


@router.post("/init", response_model=schemas.ChunkUploadInitResponse)
def init_chunk_upload(
    data: schemas.ChunkUploadInitRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    ensure_dirs()

    if data.file_size > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件大小超过限制，最大支持 {settings.MAX_UPLOAD_SIZE // (1024*1024)}MB"
        )

    if data.chunk_size != settings.CHUNK_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"分块大小必须为 {settings.CHUNK_SIZE // (1024*1024)}MB"
        )

    expected_chunks = (data.file_size + data.chunk_size - 1) // data.chunk_size
    if data.total_chunks != expected_chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"总块数不正确，应为 {expected_chunks}"
        )

    upload_id = str(uuid.uuid4())
    chunk_dir = os.path.join(settings.CHUNK_DIR, upload_id)
    os.makedirs(chunk_dir, exist_ok=True)

    db_upload = models.ChunkUpload(
        upload_id=upload_id,
        file_name=data.file_name,
        file_size=data.file_size,
        total_chunks=data.total_chunks,
        chunk_size=data.chunk_size,
        mime_type=data.mime_type,
        status=models.UploadStatus.UPLOADING,
        user_id=current_user.id,
        case_id=data.case_id
    )
    db.add(db_upload)
    db.commit()
    db.refresh(db_upload)

    return schemas.ChunkUploadInitResponse(
        upload_id=upload_id,
        status=db_upload.status,
        created_at=db_upload.created_at
    )


@router.post("/chunk/{upload_id}/{chunk_number}", response_model=schemas.ChunkUploadResponse)
async def upload_chunk(
    upload_id: str,
    chunk_number: int,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    ensure_dirs()

    db_upload = db.query(models.ChunkUpload).filter(
        models.ChunkUpload.upload_id == upload_id
    ).first()
    if not db_upload:
        raise HTTPException(status_code=404, detail="上传会话不存在")

    if db_upload.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问此上传会话")

    if db_upload.status == models.UploadStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="上传已完成")

    if chunk_number < 0 or chunk_number >= db_upload.total_chunks:
        raise HTTPException(status_code=400, detail="无效的块编号")

    chunk_dir = os.path.join(settings.CHUNK_DIR, upload_id)
    chunk_path = os.path.join(chunk_dir, f"chunk_{chunk_number}")

    contents = await file.read()
    actual_size = len(contents)

    if chunk_number == db_upload.total_chunks - 1:
        expected_size = db_upload.file_size - (db_upload.total_chunks - 1) * db_upload.chunk_size
    else:
        expected_size = db_upload.chunk_size

    if actual_size != expected_size and chunk_number != db_upload.total_chunks - 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"块大小不匹配，期望 {expected_size} 字节，实际 {actual_size} 字节"
        )

    with open(chunk_path, "wb") as f:
        f.write(contents)

    existing_chunks = len([f for f in os.listdir(chunk_dir) if f.startswith("chunk_")])
    db_upload.uploaded_chunks = existing_chunks

    completed = existing_chunks == db_upload.total_chunks
    file_hash = None
    final_path = None

    if completed:
        final_dir = os.path.join(settings.UPLOAD_DIR, "files")
        os.makedirs(final_dir, exist_ok=True)
        ext = os.path.splitext(db_upload.file_name)[1]
        final_filename = f"{upload_id}{ext}"
        final_path = os.path.join(final_dir, final_filename)

        with open(final_path, "wb") as outfile:
            for i in range(db_upload.total_chunks):
                chunk_path_i = os.path.join(chunk_dir, f"chunk_{i}")
                with open(chunk_path_i, "rb") as infile:
                    shutil.copyfileobj(infile, outfile)

        actual_file_size = os.path.getsize(final_path)
        if actual_file_size != db_upload.file_size:
            os.remove(final_path)
            db_upload.status = models.UploadStatus.FAILED
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="合并后的文件大小不匹配，上传失败"
            )

        file_hash = calculate_file_hash(final_path)
        db_upload.file_hash = file_hash
        db_upload.status = models.UploadStatus.COMPLETED
        db_upload.completed_at = datetime.now(timezone.utc)

        shutil.rmtree(chunk_dir, ignore_errors=True)

    db.commit()
    db.refresh(db_upload)

    return schemas.ChunkUploadResponse(
        upload_id=upload_id,
        chunk_number=chunk_number,
        uploaded_chunks=db_upload.uploaded_chunks,
        total_chunks=db_upload.total_chunks,
        status=db_upload.status,
        file_hash=file_hash,
        file_path=final_path,
        completed=completed
    )


@router.get("/status/{upload_id}", response_model=schemas.ChunkUploadStatusResponse)
def get_upload_status(
    upload_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_upload = db.query(models.ChunkUpload).filter(
        models.ChunkUpload.upload_id == upload_id
    ).first()
    if not db_upload:
        raise HTTPException(status_code=404, detail="上传会话不存在")

    if db_upload.user_id != current_user.id and current_user.role not in [models.UserRole.ADMIN, models.UserRole.SECRETARY]:
        raise HTTPException(status_code=403, detail="无权访问此上传会话")

    chunk_dir = os.path.join(settings.CHUNK_DIR, upload_id)
    actual_uploaded = 0
    if os.path.exists(chunk_dir):
        actual_uploaded = len([f for f in os.listdir(chunk_dir) if f.startswith("chunk_")])

    file_path = None
    if db_upload.status == models.UploadStatus.COMPLETED:
        ext = os.path.splitext(db_upload.file_name)[1]
        final_filename = f"{upload_id}{ext}"
        file_path = os.path.join(settings.UPLOAD_DIR, "files", final_filename)

    return schemas.ChunkUploadStatusResponse(
        upload_id=upload_id,
        file_name=db_upload.file_name,
        file_size=db_upload.file_size,
        total_chunks=db_upload.total_chunks,
        uploaded_chunks=max(db_upload.uploaded_chunks, actual_uploaded),
        chunk_size=db_upload.chunk_size,
        status=db_upload.status,
        file_hash=db_upload.file_hash,
        completed_at=db_upload.completed_at,
        file_path=file_path
    )


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_upload(
    upload_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_upload = db.query(models.ChunkUpload).filter(
        models.ChunkUpload.upload_id == upload_id
    ).first()
    if not db_upload:
        raise HTTPException(status_code=404, detail="上传会话不存在")

    if db_upload.user_id != current_user.id and current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="无权取消此上传")

    chunk_dir = os.path.join(settings.CHUNK_DIR, upload_id)
    if os.path.exists(chunk_dir):
        shutil.rmtree(chunk_dir, ignore_errors=True)

    if db_upload.status == models.UploadStatus.COMPLETED:
        ext = os.path.splitext(db_upload.file_name)[1]
        final_filename = f"{upload_id}{ext}"
        final_path = os.path.join(settings.UPLOAD_DIR, "files", final_filename)
        if os.path.exists(final_path):
            os.remove(final_path)

    db.delete(db_upload)
    db.commit()
