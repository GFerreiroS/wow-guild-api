from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

# SignUpStatus lives in db.py — import from there to avoid duplication.
from lib.db import SignUpStatus


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str
    character_id: int


class UserRead(BaseModel):
    id: int
    username: str
    role: str


class EventBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    start_time: datetime
    end_time: datetime

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, v: datetime, info) -> datetime:
        start = info.data.get("start_time")
        if start and v <= start:
            raise ValueError("end_time must be after start_time")
        return v


class EventCreate(EventBase):
    pass


class SignUpCreate(BaseModel):
    user_id: int
    status: Optional[SignUpStatus] = SignUpStatus.Assist


class SignUpUpdate(BaseModel):
    user_id: int
    status: SignUpStatus


class SignUpRead(BaseModel):
    id: int
    event_id: int
    user_id: int
    username: str
    signed_at: datetime
    status: SignUpStatus


class EventRead(BaseModel):
    id: int
    title: str
    description: Optional[str]
    start_time: datetime
    end_time: datetime
    created_by: int
    signups: List[SignUpRead] = Field(default_factory=list)


class Token(BaseModel):
    access_token: str
    token_type: str


class UpdateCheckResponse(BaseModel):
    current_version: str
    latest_version: str
    update_available: bool
    release_url: Optional[str]
    release_notes: Optional[str]


class UpdateApplyResponse(BaseModel):
    updated_to: str
    restarting: bool
