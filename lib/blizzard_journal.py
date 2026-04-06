"""
Blizzard Journal API helpers — used by the /admin/instances/seed endpoint.

Uses lib/auth.py (DB-backed token) for authentication.
The standalone generate_instances_yaml.py script has its own auth and is kept
separate for CLI use.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
import yaml

from lib.auth import get_access_token

logger = logging.getLogger(__name__)

REGION = os.getenv("REGION", "eu")
GLOBAL_NS = f"static-{REGION}"
DYNAMIC_NS = f"dynamic-{REGION}"
GLOBAL_LO = os.getenv("LOCALE", "en_US")
API_BASE = f"https://{REGION}.api.blizzard.com"

DATA_DIR = Path("data/instances")

# ——————————————————————————————————————————————
# CURRENT SEASON — update these each season
# ——————————————————————————————————————————————
CURRENT_KEYSTONE_SEASON_ID = 17
CURRENT_SEASON_RAID_IDS: set[int] = {
    1307,
    1314,
    1308,
}


# ——————————————————————————————————————————————
# RATE LIMITER & HTTP
# ——————————————————————————————————————————————
class _RateLimiter:
    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self.calls: deque = deque()
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            now = time.monotonic()
            while self.calls and now - self.calls[0] > self.period:
                self.calls.popleft()
            if len(self.calls) >= self.max_calls:
                time.sleep(self.period - (now - self.calls[0]))
            self.calls.append(time.monotonic())


_rate_limiter = _RateLimiter(100, 1.0)
_session = requests.Session()
_media_cache: dict = {}


# ——————————————————————————————————————————————
# API HELPERS
# ——————————————————————————————————————————————
def _blizz_get(path: str, namespace: str, locale: str, **params) -> dict:
    token = get_access_token()
    _rate_limiter.acquire()
    resp = _session.get(
        API_BASE + path,
        params={"namespace": namespace, "locale": locale, **params},
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code != 200:
        logger.error("Blizzard API error %s: %s", resp.status_code, resp.url)
        return {}
    return resp.json()


def _fetch_media(path: str, namespace: str) -> dict:
    key = (path, namespace)
    if key not in _media_cache:
        _media_cache[key] = _blizz_get(path, namespace, GLOBAL_LO)
    return _media_cache[key]


# ——————————————————————————————————————————————
# RAID FETCHING
# ——————————————————————————————————————————————
def fetch_raid_instance(inst_id: int) -> dict:
    """Fetch a raid instance and all its encounters. Encounters are in API order."""
    inst_detail = _blizz_get(f"/data/wow/journal-instance/{inst_id}", GLOBAL_NS, GLOBAL_LO)
    media = _fetch_media(f"/data/wow/media/journal-instance/{inst_id}", GLOBAL_NS)

    raid_rec: dict = {
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
        enc_detail = _blizz_get(f"/data/wow/journal-encounter/{eid}", GLOBAL_NS, GLOBAL_LO)
        creatures = enc_detail.get("creatures", [])
        disp = creatures[0].get("creature_display", {}).get("id") if creatures else None
        cimg = None
        if disp:
            cm = _fetch_media(f"/data/wow/media/creature-display/{disp}", GLOBAL_NS)
            cimg = next(
                (a["value"] for a in cm.get("assets", []) if a["key"] == "zoom"), None
            )
        raid_rec["encounters"].append({
            "blizzard-id": eid,
            "name": enc_ref["name"],
            "description": enc_detail.get("description"),
            "creature_display_id": disp,
            "img": cimg,
        })

    return raid_rec


# ——————————————————————————————————————————————
# GENERATION
# ——————————————————————————————————————————————
def generate_raids(
    expansion_id: int | None = None,
    include_current_season: bool = True,
) -> dict[str, dict[int, dict]]:
    """
    Fetch raid instances from the Blizzard journal API.

    Args:
        expansion_id: If given, only fetch this expansion. Otherwise fetch all.
        include_current_season: Whether to build a "Current Season" bucket.

    Returns:
        Mapping of expansion_name -> {inst_id -> raid_record}
    """
    _media_cache.clear()
    result: dict[str, dict[int, dict]] = {}

    if include_current_season:
        result["Current Season"] = {}

    # Resolve which expansions to process
    exp_index = _blizz_get("/data/wow/journal-expansion/index", GLOBAL_NS, GLOBAL_LO)
    exp_refs = [
        e for e in exp_index.get("tiers", [])
        if not expansion_id or e["id"] == expansion_id
    ]

    if expansion_id and not exp_refs:
        logger.error("Expansion ID %s not found in journal index.", expansion_id)
        return result

    # Collect all raid tasks: (exp_name, inst_id)
    raid_tasks: list[tuple[str, int]] = []
    for exp_ref in exp_refs:
        exp_detail = _blizz_get(
            f"/data/wow/journal-expansion/{exp_ref['id']}", GLOBAL_NS, GLOBAL_LO
        )
        exp_name = exp_detail.get("name")
        if not exp_name or exp_name == "Current Season":
            continue
        result.setdefault(exp_name, {})
        for raid_ref in exp_detail.get("raids", []):
            raid_tasks.append((exp_name, raid_ref["id"]))

    # Current-season-only mode: fetch only the configured raid IDs directly
    if include_current_season and not expansion_id:
        cs_tasks = [(None, iid) for iid in CURRENT_SEASON_RAID_IDS]
    else:
        cs_tasks = []

    all_tasks = raid_tasks + cs_tasks

    def _fetch(exp_name: str | None, inst_id: int):
        try:
            return exp_name, inst_id, fetch_raid_instance(inst_id)
        except Exception as e:
            logger.error("Error fetching raid instance %s: %s", inst_id, e)
            return None

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_fetch, *t): t for t in all_tasks}
        for fut in as_completed(futures):
            res = fut.result()
            if not res:
                continue
            exp_name, inst_id, raid_rec = res
            if exp_name:
                result[exp_name][inst_id] = raid_rec
            if include_current_season and inst_id in CURRENT_SEASON_RAID_IDS:
                result["Current Season"][inst_id] = raid_rec

    return result


# ——————————————————————————————————————————————
# YAML ARCHIVE
# ——————————————————————————————————————————————
def write_raids_yaml(raids: dict[str, dict[int, dict]]) -> None:
    """Write generated raid data to YAML files as an archive."""
    for exp_name, instances in raids.items():
        if not instances:
            continue
        out_dir = DATA_DIR / exp_name
        out_dir.mkdir(parents=True, exist_ok=True)

        records = list(instances.values())
        for seq, inst in enumerate(records, start=1):
            inst = dict(inst)  # shallow copy to avoid mutating in-memory data
            inst["id"] = seq
            for ec_seq, ec in enumerate(inst.get("encounters", []), start=1):
                ec["id"] = ec_seq

        with (out_dir / "raids.yml").open("w", encoding="utf-8") as f:
            yaml.safe_dump(records, f, sort_keys=False, allow_unicode=True)

        logger.info("[%s] wrote %d raids to YAML", exp_name, len(records))
