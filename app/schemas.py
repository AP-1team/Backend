from datetime import datetime
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: Optional[T] = None


class SignUpRequest(BaseModel):
    phone: str = Field(min_length=1, max_length=20)
    address: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=72)


class UserResponse(BaseModel):
    id: int
    username: str
    phone: str
    address: str

    class Config:
        from_attributes = True


class UserSimpleResponse(BaseModel):
    id: int
    username: str

    class Config:
        from_attributes = True


class SignUpData(BaseModel):
    user: UserResponse


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=72)


class LoginData(BaseModel):
    accessToken: str
    user: UserSimpleResponse


class UserData(BaseModel):
    user: UserResponse


class UserUpdateRequest(BaseModel):
    phone: str | None = Field(default=None, min_length=1, max_length=20)
    address: str | None = Field(default=None, min_length=1, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=72)


class GroupCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    category: str = Field(min_length=1, max_length=50)
    price: int = Field(gt=0)
    targetCount: int = Field(gt=0)
    deadline: datetime


class GroupUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    category: str | None = Field(default=None, min_length=1, max_length=50)
    price: int | None = Field(default=None, gt=0)
    targetCount: int | None = Field(default=None, gt=0)
    deadline: datetime | None = None


class MessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class CoinChargeRequest(BaseModel):
    amount: int = Field(ge=1)
