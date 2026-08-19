"""文件上传记录数据访问层（同步）。"""

from typing import Sequence

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from app.models.upload_record import UploadRecord


class UploadRepository:
    """上传记录数据访问层，封装 upload_records 表CRUD（同步）。"""

    def create(
        self,
        db: Session,
        user_id: int,
        file_type: str,
        file_name: str,
        file_size: int,
        content_type: str,
        cos_key: str,
        cos_url: str,
        etag: str,
        status: str = "completed",
    ) -> UploadRecord:
        """创建一条上传记录。

        Args:
            db: 数据库同步会话。
            user_id: 上传用户ID。
            file_type: 文件用途（resume/avatar）。
            file_name: 原始文件名。
            file_size: 文件大小（字节）。
            content_type: MIME类型。
            cos_key: COS对象Key。
            cos_url: COS访问URL。
            etag: 文件ETag。
            status: 上传状态（回调校验通过默认completed）。

        Returns:
            创建的UploadRecord对象（含自增ID）。
        """
        record = UploadRecord(
            user_id=user_id,
            file_type=file_type,
            file_name=file_name,
            file_size=file_size,
            content_type=content_type,
            cos_key=cos_key,
            cos_url=cos_url,
            etag=etag,
            status=status,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def get_by_id(self, db: Session, record_id: int) -> UploadRecord | None:
        """按ID查询上传记录。

        Args:
            db: 数据库同步会话。
            record_id: 上传记录ID。

        Returns:
            UploadRecord对象，不存在返回None。
        """
        return db.get(UploadRecord, record_id)

    def list_by_user(
        self,
        db: Session,
        user_id: int,
        file_type: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[UploadRecord]:
        """分页查询用户上传记录（按时间倒序）。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID。
            file_type: 按用途过滤，None表示全部。
            offset: 偏移量。
            limit: 每页条数。

        Returns:
            UploadRecord列表。
        """
        stmt = select(UploadRecord).where(UploadRecord.user_id == user_id)
        if file_type is not None:
            stmt = stmt.where(UploadRecord.file_type == file_type)
        stmt = stmt.order_by(desc(UploadRecord.id)).offset(offset).limit(limit)
        result = db.execute(stmt)
        return result.scalars().all()

    def count_by_user(self, db: Session, user_id: int, file_type: str | None = None) -> int:
        """统计用户上传记录总数。

        Args:
            db: 数据库同步会话。
            user_id: 用户ID。
            file_type: 按用途过滤，None表示全部。

        Returns:
            记录总数。
        """
        stmt = select(func.count()).where(UploadRecord.user_id == user_id)
        if file_type is not None:
            stmt = stmt.where(UploadRecord.file_type == file_type)
        result = db.execute(stmt)
        return result.scalar_one() or 0

    def delete_by_id(self, db: Session, record_id: int) -> bool:
        """按ID物理删除上传记录。

        Args:
            db: 数据库同步会话。
            record_id: 上传记录ID。

        Returns:
            是否成功删除。
        """
        result = db.execute(delete(UploadRecord).where(UploadRecord.id == record_id))
        db.commit()
        return result.rowcount > 0


upload_repository = UploadRepository()
