import jwt
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext

from app.core.config import settings

# 生产环境请把这个密钥放进 .env 文件
SECRET_KEY = "your-super-secret-key-12345"
ALGORITHM = "HS256"

# 🌟 核心：把 schemes 换成 argon2
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def get_password_hash(password: str) -> str:
    """把明文密码变成加密哈希 (Argon2 完美支持任意长度密码)"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与数据库里的哈希是否匹配"""
    return pwd_context.verify(plain_password, hashed_password)
# 告诉 FastAPI，客户端应该怎么传 Token（默认在 Header 的 Authorization: Bearer <token> 里）
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

def create_access_token(data: dict):
    """生成 JWT Token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=24) # 24 小时过期
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """从 Token 中解析出真正的 user_id，并校验真伪"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的凭证，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # 解密 Token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        return user_id
    except jwt.PyJWTError:
        raise credentials_exception