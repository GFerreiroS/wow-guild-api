import json
import os
import time

import dotenv
import requests

dotenv.load_dotenv()

TOKEN_URL = "https://oauth.battle.net/token"
CACHE_FILE = ".token_cache.json"


def get_access_token():
    if os.path.exists(CACHE_FILE):
        data = json.load(open(CACHE_FILE))
        if data.get("expires_at", 0) > time.time():
            return data["access_token"]

    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": os.getenv("CLIENT_ID"),
            "client_secret": os.getenv("CLIENT_SECRET"),
        },
    )
    resp.raise_for_status()
    j = resp.json()
    token = j["access_token"]
    expires = time.time() + j.get("expires_in", 3600) - 10

    json.dump({"access_token": token, "expires_at": expires}, open(CACHE_FILE, "w"))
    return token
