import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import dotenv
import requests

from .auth import get_access_token

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

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


def get_classes_index() -> list[dict]:
    bearer = get_access_token()
    params = {
        "namespace": f"static-{os.getenv('REGION')}",
        "locale": os.getenv("LOCALE"),
    }
    headers = {"Authorization": f"Bearer {bearer}"}

    resp = requests.get(
        f"{WOW_API_URL_BASE}/playable-class/index", params=params, headers=headers
    )
    resp.raise_for_status()
    class_list = resp.json().get("classes", [])

    def fetch_class_media(cls: dict) -> dict:
        cls_id = cls["id"]
        media_resp = requests.get(
            f"{WOW_API_URL_BASE}/media/playable-class/{cls_id}",
            params=params,
            headers=headers,
        )
        media_resp.raise_for_status()
        media = media_resp.json()
        icon = next(
            (a["value"] for a in media.get("assets", []) if a.get("key", "").endswith("icon")),
            None,
        )
        return {"id": cls_id, "name": cls["name"], "icon": icon}

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_class_media, cls) for cls in class_list]
        return [f.result() for f in as_completed(futures)]


def get_races_index() -> list[dict]:
    bearer = get_access_token()
    resp = requests.get(
        (
            f"{WOW_API_URL_BASE}/playable-race/index?namespace=static-{os.getenv('REGION')}&"
            f"locale={os.getenv('LOCALE')}"
        ),
        headers={"Authorization": f"Bearer {bearer}"},
    )
    resp.raise_for_status()
    data = resp.json()
    return [{"id": item["id"], "name": item["name"]} for item in data.get("races", [])]
