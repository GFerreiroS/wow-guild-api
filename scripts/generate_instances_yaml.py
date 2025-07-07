#!/usr/bin/env python3
import logging
import os
import time
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

# ——————————————————————————————————————————————
# CONFIGURATION
# ——————————————————————————————————————————————

load_dotenv()  # CLIENT_ID, CLIENT_SECRET, REGION, LOCALE

TOKEN_URL = "https://oauth.battle.net/token"
BASE_URL = "https://eu.api.blizzard.com"
NAMESPACE = f"static-{os.getenv('REGION', 'eu')}"
LOCALE = os.getenv("LOCALE", "en_US")
OUTPUT_PATH = Path("data/instances.yml")
LOG_PATH = Path("generate_instances.log")

# ——————————————————————————————————————————————
# LOGGER SETUP
# ——————————————————————————————————————————————

logger = logging.getLogger("instance_generator")
logger.setLevel(logging.INFO)

# Console handler
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

# File handler
fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
fh.setLevel(logging.INFO)

fmt = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
ch.setFormatter(fmt)
fh.setFormatter(fmt)

logger.addHandler(ch)
logger.addHandler(fh)

# ——————————————————————————————————————————————
# AUTHENTICATION (with simple file cache)
# ——————————————————————————————————————————————


def get_access_token() -> str:
    cache = Path(".token_cache.json")
    now = time.time()
    if cache.exists():
        data = yaml.safe_load(cache.read_text())
        if data.get("expires_at", 0) > now:
            logger.debug("Using cached access token")
            return data["access_token"]

    logger.info("Fetching new access token")
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
    expires = now + j.get("expires_in", 3600) - 10

    yaml.safe_dump(
        {"access_token": token, "expires_at": expires},
        cache.open("w"),
    )
    return token


# ——————————————————————————————————————————————
# BLIZZARD GET HELPER
# ——————————————————————————————————————————————


def blizz_get(path: str, **params) -> dict:
    """
    Helper for Blizzard GET with bearer & common params.
    Logs each call URL and response status.
    """
    url = f"{BASE_URL}{path}"
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    full_params = {"namespace": NAMESPACE, "locale": LOCALE, **params}

    # Log the outgoing request
    logger.info(f"CALL → {url}  params={full_params}")

    resp = requests.get(url, params=full_params, headers=headers)
    try:
        resp.raise_for_status()
    except Exception:
        # Log the failure with status and full URL (including querystring)
        logger.error(f"FAILED ← {resp.status_code} {resp.url}")
        raise

    # Log the successful response
    logger.info(f"RESP  ← {resp.status_code} {resp.url}")
    return resp.json()


# ——————————————————————————————————————————————
# MAIN SCRIPT
# ——————————————————————————————————————————————


def main():
    logger.info("Starting instance YAML generation")
    OUTPUT_PATH.parent.mkdir(exist_ok=True)

    # 1) Fetch the journal-instance index
    idx = blizz_get("/data/wow/journal-instance/index")
    instances = idx.get("instances", [])
    logger.info(f"Fetched {len(instances)} instances from index")

    output = []
    inst_custom_id = 1

    for inst in instances:
        bid = inst.get("id")
        index_name = inst.get("name")
        if not bid:
            logger.warning("Skipping instance with no Blizzard ID in index")
            continue

        # 2) Fetch instance detail
        try:
            detail = blizz_get(f"/data/wow/journal-instance/{bid}")
        except Exception as e:
            logger.error(f"Failed to fetch detail for instance {bid}: {e}")
            continue

        inst_name = detail.get("name") or index_name
        if not inst_name:
            logger.error(f"No name found for instance {bid}")
        inst_desc = detail.get("description")

        # 3) Fetch zone image via journal-instance media endpoint
        try:
            media = blizz_get(f"/data/wow/media/journal-instance/{bid}")
            zone_img = next(
                (
                    a["value"]
                    for a in media.get("assets", [])
                    if a["key"] in ("tile", "main", "image", "icon")
                ),
                None,
            )
            if not zone_img:
                logger.warning(f"No zone image found for instance {bid}")
        except Exception as e:
            logger.error(f"Error fetching media for instance {bid}: {e}")
            zone_img = None

        # 4) Process encounters
        encounters = []
        enc_custom_id = 1
        for enc in detail.get("encounters", []):
            ebid = enc.get("id")
            index_enc_name = enc.get("name")
            if not ebid:
                logger.warning(f"Skipping encounter with no ID in instance {bid}")
                continue

            # 5) Fetch encounter detail
            try:
                edetail = blizz_get(f"/data/wow/journal-encounter/{ebid}")
            except Exception as e:
                logger.error(f"  Failed to fetch encounter {ebid}: {e}")
                continue

            enc_name = edetail.get("name") or index_enc_name
            if not enc_name:
                logger.error(f"  No name for encounter {ebid} in instance {bid}")
            enc_desc = edetail.get("description")

            # 6) Process creatures
            creatures = []
            c_custom_id = 1
            for c in edetail.get("creatures", []):
                cid = c.get("id")
                cname = c.get("name")
                if not cid:
                    logger.warning(
                        f"    Skipping creature with no ID in encounter {ebid}"
                    )
                    continue
                if not cname:
                    logger.warning(
                        f"    No creature name for {cid} in encounter {ebid}"
                    )

                disp_id = c["creature_display"]["id"]
                try:
                    cmedia = blizz_get(f"/data/wow/media/creature-display/{disp_id}")
                    cimg = next(
                        (
                            a["value"]
                            for a in cmedia.get("assets", [])
                            if a["key"] == "zoom"
                        ),
                        None,
                    )
                    if not cimg:
                        logger.warning(f"    No image for creature {cid}")
                except Exception as e:
                    logger.error(
                        f"    Error fetching media for creature-display {disp_id}: {e}"
                    )
                    cimg = None

                creatures.append(
                    {
                        "id": c_custom_id,
                        "blizzard_id": cid,
                        "creature_display_id": disp_id,
                        "name": cname,
                        "img": cimg,
                    }
                )
                c_custom_id += 1

            encounters.append(
                {
                    "id": enc_custom_id,
                    "blizzard_id": ebid,
                    "name": enc_name,
                    "description": enc_desc,
                    "creatures": creatures,
                }
            )
            enc_custom_id += 1

        output.append(
            {
                "id": inst_custom_id,
                "blizzard_id": bid,
                "name": inst_name,
                "description": inst_desc,
                "img": zone_img,
                "encounters": encounters,
            }
        )
        inst_custom_id += 1

    # 7) Write YAML
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(output, f, sort_keys=False, allow_unicode=True)
    logger.info(f"Wrote {len(output)} instances to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
