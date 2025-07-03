import os
import time

import dotenv
import requests
from sqlmodel import Session, select

import lib.db as db

dotenv.load_dotenv()

TOKEN_URL = "https://oauth.battle.net/token"


def get_access_token() -> str:
    with Session(db.engine) as session:
        # 1) Try to load the single token row
        statement = select(db.OAuthToken).where(db.OAuthToken.id == 1)
        result = session.exec(statement).first()

        if result and result.expires_at > time.time():
            return result.access_token

        # 2) Otherwise fetch a new token
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

        # 3) Upsert into DB
        if result:
            result.access_token = token
            result.expires_at = expires
            session.add(result)
        else:
            session.add(db.OAuthToken(id=1, access_token=token, expires_at=expires))
        session.commit()
        return token
