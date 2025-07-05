from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str  # plaintext from client
    character_id: int  # must be one of the fetched roster


class UserRead(BaseModel):
    id: int
    username: str
    role: str
