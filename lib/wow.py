import os

import dotenv
import requests

from .auth import get_access_token

dotenv.load_dotenv()

WOW_API_URL_BASE = f"https://{os.getenv('REGION')}.api.blizzard.com/data/wow"


def get_wow_token() -> str:
    bearer = get_access_token()
    resp = requests.get(
        (
            f"{WOW_API_URL_BASE}/token/?namespace=dynamic-{os.getenv('REGION')}&"
            f"locale={os.getenv('LOCALE')}"
        ),
        headers={"Authorization": f"Bearer {bearer}"},
    )
    resp.raise_for_status()
    return resp.json()["price"]


def get_guild_info() -> dict:
    bearer = get_access_token()
    resp = requests.get(
        (
            f"{WOW_API_URL_BASE}/guild/{os.getenv('GUILD_SLUG')}/{os.getenv('GUILD_NAME')}"
            f"?namespace=profile-{os.getenv('REGION')}&locale={os.getenv('LOCALE')}"
        ),
        headers={"Authorization": f"Bearer {bearer}"},
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "name": data["name"],
        "realm": data["realm"]["name"],
        "faction": data["faction"]["name"],
    }


def get_guild_roster() -> dict:
    lvl_cap = 80
    bearer = get_access_token()
    resp = requests.get(
        (
            f"{WOW_API_URL_BASE}/guild/{os.getenv('GUILD_SLUG')}/{os.getenv('GUILD_NAME')}/roster"
            f"?namespace=profile-{os.getenv('REGION')}&locale={os.getenv('LOCALE')}"
        ),
        headers={"Authorization": f"Bearer {bearer}"},
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        # TODO: Process the roster data as needed
    }
