from datetime import timedelta
from typing import Optional, Union, List
from pydantic import BaseModel, validator, StrictBool, StrictInt, StrictStr


class LoadConfig(BaseModel):
    authjwt_token_location: Optional[List[StrictStr]] = {'headers'}
    authjwt_secret_key: Optional[StrictStr] = None
    authjwt_public_key: Optional[StrictStr] = None
    authjwt_private_key: Optional[StrictStr] = None
    authjwt_algorithm: Optional[StrictStr] = "HS256"
    authjwt_decode_algorithms: Optional[List[StrictStr]] = None
    authjwt_decode_leeway: Optional[Union[StrictInt, timedelta]] = 0
    authjwt_encode_issuer: Optional[StrictStr] = None
    authjwt_decode_issuer: Optional[StrictStr] = None
    authjwt_decode_audience: Optional[Union[StrictStr, List[StrictStr]]] = None
    authjwt_denylist_enabled: Optional[StrictBool] = False
    authjwt_denylist_token_checks: Optional[List[StrictStr]] = {'access', 'refresh'}
    authjwt_header_name: Optional[StrictStr] = "Authorization"
    authjwt_header_type: Optional[StrictStr] = "Bearer"
    # 这里我们遵循大厂的 15 分钟和 30 天配置
    authjwt_access_token_expires: Optional[Union[StrictBool, StrictInt, timedelta]] = timedelta(minutes=15)
    authjwt_refresh_token_expires: Optional[Union[StrictBool, StrictInt, timedelta]] = timedelta(days=30)

    # Cookie 选项 (如果以后要做浏览器直连，这些必配)
    authjwt_access_cookie_key: Optional[StrictStr] = "access_token_cookie"
    authjwt_refresh_cookie_key: Optional[StrictStr] = "refresh_token_cookie"
    authjwt_access_cookie_path: Optional[StrictStr] = "/"
    authjwt_refresh_cookie_path: Optional[StrictStr] = "/"
    authjwt_cookie_max_age: Optional[StrictInt] = None
    authjwt_cookie_domain: Optional[StrictStr] = None
    authjwt_cookie_secure: Optional[StrictBool] = False
    authjwt_cookie_samesite: Optional[StrictStr] = None
    authjwt_cookie_csrf_protect: Optional[StrictBool] = True
    authjwt_access_csrf_cookie_key: Optional[StrictStr] = "csrf_access_token"
    authjwt_refresh_csrf_cookie_key: Optional[StrictStr] = "csrf_refresh_token"
    authjwt_access_csrf_cookie_path: Optional[StrictStr] = "/"
    authjwt_refresh_csrf_cookie_path: Optional[StrictStr] = "/"
    authjwt_access_csrf_header_name: Optional[StrictStr] = "X-CSRF-Token"
    authjwt_refresh_csrf_header_name: Optional[StrictStr] = "X-CSRF-Token"
    authjwt_csrf_methods: Optional[List[StrictStr]] = {'POST', 'PUT', 'PATCH', 'DELETE'}

    @validator('authjwt_access_token_expires')
    def validate_access_token_expires(cls, v):
        if v is True:
            raise ValueError("The 'authjwt_access_token_expires' only accept value False (bool)")
        return v

    @validator('authjwt_refresh_token_expires')
    def validate_refresh_token_expires(cls, v):
        if v is True:
            raise ValueError("The 'authjwt_refresh_token_expires' only accept value False (bool)")
        return v

    @validator('authjwt_denylist_token_checks', each_item=True)
    def validate_denylist_token_checks(cls, v):
        if v not in ['access', 'refresh']:
            raise ValueError("The 'authjwt_denylist_token_checks' must be between 'access' or 'refresh'")
        return v

    @validator('authjwt_token_location', each_item=True)
    def validate_token_location(cls, v):
        if v not in ['headers', 'cookies']:
            raise ValueError("The 'authjwt_token_location' must be between 'headers' or 'cookies'")
        return v

    @validator('authjwt_cookie_samesite')
    def validate_cookie_samesite(cls, v):
        if v not in ['strict', 'lax', 'none']:
            raise ValueError("The 'authjwt_cookie_samesite' must be between 'strict', 'lax', 'none'")
        return v

    @validator('authjwt_csrf_methods', each_item=True)
    def validate_csrf_methods(cls, v):
        if v.upper() not in {"GET", "HEAD", "POST", "PUT", "DELETE", "PATCH"}:
            raise ValueError("The 'authjwt_csrf_methods' must be between http request methods")
        return v.upper()

    class Config:
        str_min_length = 1
        str_strip_whitespace = True


from app.core.config import settings
from typing import Callable, List, Tuple


class AuthConfig:
    """接管全局状态的配置类"""
    _token = None
    _token_location = {'headers'}
    # 🌟 直接取 settings.SECRET_KEY；此前依赖 load_config() 赋值，但它从未被调用，导致签发 token 时密钥为 None
    _secret_key = settings.SECRET_KEY
    _algorithm = "HS256"
    _decode_algorithms = None
    _decode_leeway = 0
    _encode_issuer = None
    _decode_issuer = None
    _decode_audience = None
    _denylist_enabled = True  # 🌟 强制开启黑名单
    _denylist_token_checks = {'access', 'refresh'}
    _header_name = "Authorization"
    _header_type = "Bearer"
    _access_token_expires = timedelta(minutes=15)
    _refresh_token_expires = timedelta(days=30)

    @property
    def jwt_in_cookies(self) -> bool:
        return 'cookies' in self._token_location

    @property
    def jwt_in_headers(self) -> bool:
        return 'headers' in self._token_location

    @classmethod
    def load_config(cls, settings_provider: Callable[..., List[Tuple]]) -> "AuthConfig":
        try:
            # 把 FastAPI config 或者环境变量里的设置加载进来
            raw_settings = dict(settings_provider())
            config = LoadConfig(**{key.lower(): value for key, value in raw_settings.items()})

            # 把 LoadConfig 的属性赋给这个全局单例类
            for attr, value in config.dict().items():
                setattr(cls, f"_{attr.replace('authjwt_', '')}", value)

            cls._secret_key = config.authjwt_secret_key or getattr(settings, "SECRET_KEY", "fallback-secret-key")
        except Exception as e:
            raise TypeError(f"Config must be pydantic 'BaseSettings' or list of tuple. Error: {e}")
        return cls