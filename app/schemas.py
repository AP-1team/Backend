from pydantic import BaseModel
from typing import Optional, Generic, TypeVar

T = TypeVar("T")

# 공통 응답 구조
class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: Optional[T] = None

# 1-1. 회원가입 요청/응답
class SignUpRequest(BaseModel):
    phone: str
    address: str
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    phone: str
    address: str

    class Config:
        from_attributes = True

class SignUpData(BaseModel):
    user: UserResponse

# 1-2. 로그인 요청/응답
class LoginRequest(BaseModel):
    username: str
    password: str

class UserSimpleResponse(BaseModel):
    id: int
    username: str

    class Config:
        from_attributes = True

class LoginData(BaseModel):
    accessToken: str
    refreshToken: str
    user: UserSimpleResponse