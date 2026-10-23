import jwt
import re
import uuid
import hmac
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Union, Sequence
from fastapi import Request, Response
from app.auth.auth_config import AuthConfig
from app.auth.exceptions import (
    InvalidHeaderError, JWTDecodeError, MissingTokenError,
    AccessTokenRequired, RefreshTokenRequired, RevokedTokenError
)
import redis
from app.core.config import settings

# 初始化 Redis 黑名单客户端
redis_client = redis.from_url(settings.REDIS_URL)


class AuthJWT(AuthConfig):
    def __init__(self, req: Request = None, res: Response = None):
        if req:
            if self.jwt_in_headers:
                auth = req.headers.get(self._header_name.lower())
                if auth:
                    try:
                        self._get_jwt_from_headers(auth)
                    except InvalidHeaderError:
                        # 🌟 请求头格式不合法时不在这里抛异常，交给 jwt_required() 统一返回 401，
                        # 否则异常发生在依赖构造阶段，会变成 500 而不是 401
                        self._token = None

    def _get_jwt_from_headers(self, auth: str) -> "AuthJWT":
        header_name, header_type = self._header_name, self._header_type
        parts = auth.split()
        if not header_type:
            if len(parts) != 1:
                raise InvalidHeaderError(status_code=422,
                                         message="Bad {} header. Expected value '<JWT>'".format(header_name))
            self._token = parts[0]
        else:
            if not re.match(r"{}\s".format(header_type), auth) or len(parts) != 2:
                raise InvalidHeaderError(status_code=422,
                                         message="Bad {} header. Expected value '{} <JWT>'".format(header_name,
                                                                                                   header_type))
            self._token = parts[1]

    def _get_jwt_identifier(self) -> str:
        return str(uuid.uuid4())

    def _get_int_from_datetime(self, value: datetime) -> int:
        return int(value.timestamp())

    def _create_token(self, subject: Union[str, int], type_token: str, exp_time: Optional[int],
                      fresh: Optional[bool] = False, algorithm: Optional[str] = None,
                      headers: Optional[Dict] = None) -> str:
        reserved_claims = {
            "sub": subject,
            "iat": self._get_int_from_datetime(datetime.now(timezone.utc)),
            "nbf": self._get_int_from_datetime(datetime.now(timezone.utc)),
            "jti": self._get_jwt_identifier()
        }
        custom_claims = {"type": type_token}
        if type_token == 'access':
            custom_claims['fresh'] = fresh
        if exp_time:
            reserved_claims['exp'] = exp_time

        algorithm = algorithm or self._algorithm
        return jwt.encode({**reserved_claims, **custom_claims}, self._secret_key, algorithm=algorithm, headers=headers)

    def create_access_token(self, subject: Union[str, int], fresh: Optional[bool] = False,
                            expires_time: Optional[timedelta] = None) -> str:
        expires_time = expires_time or self._access_token_expires
        exp_timestamp = self._get_int_from_datetime(datetime.now(timezone.utc) + expires_time)
        return self._create_token(subject, "access", exp_timestamp, fresh)

    def create_refresh_token(self, subject: Union[str, int], expires_time: Optional[timedelta] = None) -> str:
        expires_time = expires_time or self._refresh_token_expires
        exp_timestamp = self._get_int_from_datetime(datetime.now(timezone.utc) + expires_time)
        return self._create_token(subject, "refresh", exp_timestamp)

    def _check_token_is_revoked(self, raw_token: Dict) -> None:
        if not self._denylist_enabled:
            return
        # 检查 Redis 是否有该 jti 记录
        jti = raw_token.get('jti')
        if jti and redis_client.exists(f"blacklist:{jti}"):
            raise RevokedTokenError(status_code=401, message="Token has been revoked")

    def _verified_token(self, encoded_token: str) -> Dict:
        try:
            unverified_headers = jwt.get_unverified_header(encoded_token)
            token_data = jwt.decode(encoded_token, self._secret_key, algorithms=[unverified_headers['alg']])
            self._check_token_is_revoked(token_data)
            return token_data
        except Exception as err:
            raise JWTDecodeError(status_code=422, message=str(err))

    def _verify_jwt_in_request(self, token: str, type_token: str, token_from: str,
                               fresh: Optional[bool] = False) -> None:
        if not token:
            if token_from == 'headers':
                raise MissingTokenError(status_code=401, message="Missing {} Header".format(self._header_name))

        raw_token = self._verified_token(token)
        if raw_token['type'] != type_token:
            msg = "Only {} tokens are allowed".format(type_token)
            raise AccessTokenRequired(status_code=422, message=msg) if type_token == 'access' else RefreshTokenRequired(
                status_code=422, message=msg)

        if fresh and not raw_token.get('fresh'):
            raise JWTDecodeError(status_code=401, message="Fresh token required")

    def jwt_required(self) -> None:
        """核心校验方法：验证 Header 中的 Token 是否合法且未被吊销"""
        self._verify_jwt_in_request(self._token, 'access', 'headers')

    def get_raw_jwt(self) -> Optional[Dict]:
        if self._token:
            return self._verified_token(self._token)
        return None

    def get_jwt_subject(self) -> Optional[Union[str, int]]:
        if self._token:
            return self._verified_token(self._token)['sub']
        return None