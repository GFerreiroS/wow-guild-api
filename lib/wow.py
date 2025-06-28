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


def get_classes_index() -> list[dict]:
    bearer = get_access_token()
    params = {
        "namespace": f"static-{os.getenv('REGION')}",
        "locale": os.getenv("LOCALE"),
    }
    headers = {"Authorization": f"Bearer {bearer}"}

    # 1) Fetch the index of classes
    resp = requests.get(
        f"{WOW_API_URL_BASE}/playable-class/index", params={**params}, headers=headers
    )
    resp.raise_for_status()
    data = resp.json()

    classes = []
    # 2) Loop through each entry in the index
    for cls in data.get("classes", []):
        cls_id = cls["id"]
        cls_name = cls["name"]

        # 3) Fetch the media (to get the icon)
        media_resp = requests.get(
            f"{WOW_API_URL_BASE}/media/playable-class/{cls_id}",
            params={**params},
            headers=headers,
        )
        media_resp.raise_for_status()
        media = media_resp.json()

        # 4) Find the icon asset
        #    Blizzard returns a list under "assets"; often the first is the icon
        icon = None
        for asset in media.get("assets", []):
            # usually asset["key"] ends with "icon"
            if asset.get("key", "").endswith("icon"):
                icon = asset.get("value")
                break

        classes.append({"id": cls_id, "name": cls_name, "icon": icon})

    return classes


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

    races = []
    for item in data.get("races", []):
        races.append({"id": item["id"], "name": item["name"]})

    return races
