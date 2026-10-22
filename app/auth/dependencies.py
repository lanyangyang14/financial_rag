from fastapi import Request, Depends, HTTPException
from app.auth.auth_jwt import AuthJWT
from app.auth.exceptions import AuthJWTException
from app.core.contexts import set_user_id_context

# 🌟 1. 实例化鉴权引擎的依赖项
def get_authjwt(req: Request) -> AuthJWT:
    return AuthJWT(req=req)


# 🌟 2. 封装一个专门用于 FastAPI 的依赖，获取当前登录用户
def get_current_user_dep(auth: AuthJWT = Depends(get_authjwt)) -> str:
    try:
        # 验证 Header 中的 Token
        auth.jwt_required()
        username = auth.get_jwt_subject()
        set_user_id_context(username)  # 🌟 核心：把用户塞入日志上下文
        if not username:
            raise HTTPException(status_code=401, detail="无效的凭证，无法获取用户信息")
        return username
    except AuthJWTException as e:
        # 捕获我们自定义的异常，转成标准的 HTTP 401/422
        raise HTTPException(status_code=e.status_code, detail=e.message)