#!/usr/bin/env python3
import argparse
import logging
import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

# ——————————————————————————————————————————————
# CONFIGURATION
# ——————————————————————————————————————————————
load_dotenv()  # CLIENT_ID, CLIENT_SECRET, REGION, LOCALE

REGION = os.getenv("REGION", "eu")
GLOBAL_NS = f"static-{REGION}"
GLOBAL_LO = os.getenv("LOCALE", "en_US")

API_BASE = f"https://{REGION}.api.blizzard.com"
TOKEN_URL = "https://oauth.battle.net/token"

BASE_OUTPUT = Path("data/instances")
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / "generate_instances.log"
API_CALL_COUNT = 0

# ——————————————————————————————————————————————
# CURRENT SEASON — update these each season
# ——————————————————————————————————————————————
# journal-instance IDs for the current season raid(s).
# To find the ID: run with --expansion <tww_expansion_id> and check the logs.
CURRENT_SEASON_RAID_IDS: set[int] = {
    1307,
    1314,
    1308,
}

# ——————————————————————————————————————————————
# LOGGER SETUP
# ——————————————————————————————————————————————
logger = logging.getLogger("wow_gen")
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
fh.setLevel(logging.INFO)
fmt = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
ch.setFormatter(fmt)
fh.setFormatter(fmt)
logger.addHandler(ch)
logger.addHandler(fh)


# ——————————————————————————————————————————————
# RATE LIMITER (100 req/sec)
# ——————————————————————————————————————————————
class RateLimiter:
    def __init__(self, max_calls, period):
        self.max_calls = max_calls
        self.period = period
        self.calls = deque()
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            now = time.monotonic()
            while self.calls and now - self.calls[0] > self.period:
                self.calls.popleft()
            if len(self.calls) >= self.max_calls:
                wait = self.period - (now - self.calls[0])
                time.sleep(wait)
            self.calls.append(time.monotonic())


rate_limiter = RateLimiter(100, 1.0)

# ——————————————————————————————————————————————
# HTTP SESSION & MEDIA CACHE
# ——————————————————————————————————————————————
SESSION = requests.Session()
MEDIA_CACHE = {}


# ——————————————————————————————————————————————
# AUTHENTICATION
# ——————————————————————————————————————————————
def get_access_token():
    load_dotenv()
    resp = SESSION.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": os.getenv("CLIENT_ID"),
            "client_secret": os.getenv("CLIENT_SECRET"),
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


# ——————————————————————————————————————————————
# BLIZZARD GET & MEDIA
# ——————————————————————————————————————————————
def blizz_get(path, namespace, locale, **params):
    global API_CALL_COUNT
    API_CALL_COUNT += 1
    url = API_BASE + path
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    qp = {"namespace": namespace, "locale": locale, **params}

    rate_limiter.acquire()
    logger.info(f"CALL #{API_CALL_COUNT} -> {url} params={qp}")
    resp = SESSION.get(url, params=qp, headers=headers)
    if resp.status_code != 200:
        logger.error(f"FAILED <- {resp.status_code} {resp.url}")
        return {}
    logger.info(f"RESP  <- {resp.status_code} {resp.url}")
    return resp.json()


def fetch_media(path, namespace, locale):
    key = (path, namespace, locale)
    if key not in MEDIA_CACHE:
        MEDIA_CACHE[key] = blizz_get(path, namespace, locale)
    return MEDIA_CACHE[key]


# ——————————————————————————————————————————————
# HELPERS
# ——————————————————————————————————————————————
def fetch_raid_instance(inst_id: int) -> dict:
    """
    Fetch a raid instance and all its encounters from the journal API.
    Encounters are fetched sequentially to preserve in-game order.
    """
    inst_detail = blizz_get(f"/data/wow/journal-instance/{inst_id}", GLOBAL_NS, GLOBAL_LO)
    media = fetch_media(f"/data/wow/media/journal-instance/{inst_id}", GLOBAL_NS, GLOBAL_LO)

    raid_rec = {
        "blizzard-id": inst_id,
        "name": inst_detail.get("name"),
        "description": inst_detail.get("description"),
        "img": next(
            (a["value"] for a in media.get("assets", []) if a["key"] == "tile"), None
        ),
        "encounters": [],
    }

    for enc_ref in inst_detail.get("encounters", []):
        eid = enc_ref["id"]
        enc_detail = blizz_get(f"/data/wow/journal-encounter/{eid}", GLOBAL_NS, GLOBAL_LO)
        creatures = enc_detail.get("creatures", [])
        disp = creatures[0].get("creature_display", {}).get("id") if creatures else None
        cimg = None
        if disp:
            cm = fetch_media(
                f"/data/wow/media/creature-display/{disp}", GLOBAL_NS, GLOBAL_LO
            )
            cimg = next(
                (a["value"] for a in cm.get("assets", []) if a["key"] == "zoom"), None
            )
        raid_rec["encounters"].append(
            {
                "blizzard-id": eid,
                "name": enc_ref["name"],
                "description": enc_detail.get("description"),
                "creature_display_id": disp,
                "img": cimg,
            }
        )

    return raid_rec


def write_raids_yaml(exp_name: str, raids: dict) -> None:
    out_dir = BASE_OUTPUT / exp_name
    out_dir.mkdir(parents=True, exist_ok=True)

    seq = 1
    for inst in raids.values():
        inst["id"] = seq
        ec_seq = 1
        for ec in inst["encounters"]:
            ec["id"] = ec_seq
            ec_seq += 1
        seq += 1

    with (out_dir / "raids.yml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(list(raids.values()), f, sort_keys=False, allow_unicode=True)

    logger.info(f"[{exp_name}] wrote {len(raids)} raids")


# ——————————————————————————————————————————————
# MAIN SCRIPT
# ——————————————————————————————————————————————
def main():
    parser = argparse.ArgumentParser(
        description="Generate WoW raid instances YAML data from the Blizzard journal API."
    )
    parser.add_argument(
        "--expansion",
        type=int,
        metavar="ID",
        help="Only generate data for this Blizzard journal-expansion ID.",
    )
    parser.add_argument(
        "--current-season",
        action="store_true",
        help=(
            "Generate a 'Current Season' bucket using CURRENT_SEASON_RAID_IDS. "
            "Without --expansion, only the Current Season YAML is written."
        ),
    )
    args = parser.parse_args()

    load_dotenv()

    # ——————————————————————————————————————————
    # CURRENT SEASON ONLY (no --expansion)
    # ——————————————————————————————————————————
    if args.current_season and not args.expansion:
        raids: dict[int, dict] = {}

        def _fetch_cs_raid(inst_id: int):
            try:
                return inst_id, fetch_raid_instance(inst_id)
            except Exception as e:
                logger.error(f"Error fetching current season raid {inst_id}: {e}")
                return None

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {pool.submit(_fetch_cs_raid, iid): iid for iid in CURRENT_SEASON_RAID_IDS}
            for fut in as_completed(futures):
                res = fut.result()
                if res:
                    inst_id, raid_rec = res
                    raids[inst_id] = raid_rec

        write_raids_yaml("Current Season", raids)
        logger.info(f"Total Blizzard API calls made: {API_CALL_COUNT}")
        return

    # ——————————————————————————————————————————
    # EXPANSION MODE (--expansion, optionally with --current-season)
    # ——————————————————————————————————————————
    exp_index = blizz_get("/data/wow/journal-expansion/index", GLOBAL_NS, GLOBAL_LO)
    exp_refs = [
        e for e in exp_index.get("tiers", [])
        if not args.expansion or e["id"] == args.expansion
    ]

    if args.expansion and not exp_refs:
        logger.error(f"Expansion ID {args.expansion} not found in journal index.")
        return

    # Collect raid tasks from each expansion
    raid_tasks: list[tuple[str, int]] = []  # (exp_name, inst_id)

    for exp_ref in exp_refs:
        exp_detail = blizz_get(
            f"/data/wow/journal-expansion/{exp_ref['id']}", GLOBAL_NS, GLOBAL_LO
        )
        exp_name = exp_detail.get("name")
        if not exp_name or exp_name == "Current Season":
            continue
        for raid_ref in exp_detail.get("raids", []):
            raid_tasks.append((exp_name, raid_ref["id"]))

    # Fetch all raid instances in parallel
    expansions: dict[str, dict[int, dict]] = {}

    def _fetch_raid(exp_name: str, inst_id: int):
        try:
            return exp_name, inst_id, fetch_raid_instance(inst_id)
        except Exception as e:
            logger.error(f"Error fetching raid instance {inst_id}: {e}")
            return None

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_fetch_raid, *task): task for task in raid_tasks}
        for fut in as_completed(futures):
            res = fut.result()
            if not res:
                continue
            exp_name, inst_id, raid_rec = res
            expansions.setdefault(exp_name, {})[inst_id] = raid_rec
            if args.current_season and inst_id in CURRENT_SEASON_RAID_IDS:
                expansions.setdefault("Current Season", {})[inst_id] = raid_rec

    for exp_name, raids in expansions.items():
        write_raids_yaml(exp_name, raids)

    logger.info(f"Total Blizzard API calls made: {API_CALL_COUNT}")


if __name__ == "__main__":
    main()
