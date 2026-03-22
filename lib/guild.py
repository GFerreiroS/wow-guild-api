import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import dotenv
import requests

import lib.wow as wow

from .auth import get_access_token

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

WOW_API_URL_BASE = f"https://{os.getenv('REGION')}.api.blizzard.com/data/wow"


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

    # Build lookup maps concurrently
    with ThreadPoolExecutor(max_workers=2) as ex:
        classes_fut = ex.submit(wow.get_classes_index)
        races_fut = ex.submit(wow.get_races_index)
        classes = {c["id"]: c["name"] for c in classes_fut.result()}
        races = {r["id"]: r["name"] for r in races_fut.result()}

    bearer = get_access_token()
    resp = requests.get(
        f"{WOW_API_URL_BASE}/guild/{os.getenv('GUILD_SLUG')}"
        f"/{os.getenv('GUILD_NAME')}/roster",
        params={
            "namespace": f"profile-{os.getenv('REGION')}",
            "locale": os.getenv("LOCALE"),
        },
        headers={"Authorization": f"Bearer {bearer}"},
    )
    resp.raise_for_status()
    members = resp.json().get("members", [])

    roster = []
    for m in members:
        char = m.get("character", {})
        lvl = char.get("level", 0)
        if lvl < lvl_cap:
            continue

        char_id = char.get("id")
        if char_id is None:
            logger.warning("Skipping character with no ID: %s", char.get("name"))
            continue

        cls_id = char.get("playable_class", {}).get("id")
        race_id = char.get("playable_race", {}).get("id")
        realm_slug = char.get("realm", {}).get("slug")

        roster.append(
            {
                "id": char_id,
                "name": char.get("name"),
                "realm": realm_slug,
                "level": lvl,
                "class": classes.get(cls_id, "Unknown"),
                "race": races.get(race_id, "Unknown"),
                "faction": char.get("faction", {}).get("type"),
                "rank": m.get("rank"),
            }
        )

    return {"roster": roster}
