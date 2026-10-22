import contextvars

#定义全局上下文变量
trace_id=contextvars.ContextVar("trace_id",default=None)
user_id=contextvars.ContextVar("user_id",default=None)

def set_trace_id_context(tid:str):
    trace_id.set(tid)

def set_user_id_context(uid:str):
    user_id.set(uid)