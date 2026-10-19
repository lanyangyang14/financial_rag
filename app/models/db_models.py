# app/models/db_models.py
from sqlalchemy import Column, String, Integer, DateTime, Text
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class DocumentRecord(Base):
    """文件上传记录表"""
    __tablename__ = 'documents'

    id = Column(String, primary_key=True, index=True)
    filename = Column(String, index=True)
    user_id = Column(String, index=True)
    upload_time = Column(DateTime, default=datetime.utcnow)


class ChatHistory(Base):
    """聊天历史记录表（持久化保存）"""
    __tablename__ = 'chat_histories'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True)
    role = Column(String)  # user 或 assistant
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)