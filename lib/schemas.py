from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str  # plaintext from client
    character_id: int  # must be one of the fetched roster


class UserRead(BaseModel):
    id: int
    username: str
    role: str


class EventBase(BaseModel):
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime


class EventCreate(EventBase):
    created_by: int  # the user ID of the admin/owner making the event


class EventRead(EventBase):
    id: int
    created_by: int


class SignUpCreate(BaseModel):
    user_id: int


class SignUpRead(BaseModel):
    id: int
    event_id: int
    user_id: int
    signed_at: datetime
