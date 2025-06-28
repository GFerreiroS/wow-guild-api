import os

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

# Header name clients must use:
API_KEY_NAME = "X-API-Key"

# Load the key once, from the environment
API_KEY = os.getenv("ADMIN_API_KEY", "changeme")

# FastAPI “security” object
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def get_api_key(api_key_header_value: str = Security(api_key_header)) -> str:
    if not api_key_header_value or api_key_header_value != API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")
    return api_key_header_value
