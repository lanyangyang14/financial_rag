class AuthJWTException(Exception):
    """所有 Auth JWT 异常的基类"""
    pass

class InvalidHeaderError(AuthJWTException):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message

class JWTDecodeError(AuthJWTException):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message

class CSRFError(AuthJWTException):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message

class MissingTokenError(AuthJWTException):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message

class RevokedTokenError(AuthJWTException):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message

class AccessTokenRequired(AuthJWTException):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message

class RefreshTokenRequired(AuthJWTException):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message