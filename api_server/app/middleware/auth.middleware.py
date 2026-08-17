from fastapi import middleware

@middleware("http")
async def auth_middleware(request, call_next):  
    # 在这里可以添加身份验证逻辑，例如检查请求头中的令牌
    # 如果验证失败，可以返回一个响应，例如：
    # return JSONResponse(status_code=401, content={"message": "Unauthorized"})
    
    response = await call_next(request)
    return response 
