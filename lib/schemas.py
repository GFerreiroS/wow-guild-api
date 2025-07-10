from datetime import datetime
from enum import Enum
from typing import List, Optional

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


class SignUpStatus(str, Enum):
    Assist = "Assist"
    Late = "Late"
    Tentative = "Tentative"
    Absence = "Absence"


class SignUpCreate(BaseModel):
    user_id: int
    status: Optional[SignUpStatus] = SignUpStatus.Assist


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
    signups: List[SignUpRead] = []
