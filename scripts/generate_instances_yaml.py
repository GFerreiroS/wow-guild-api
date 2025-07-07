#!/usr/bin/env python3
import os
import time
import threading
import requests
import yaml
import logging
from pathlib import Path
from dotenv import load_dotenv
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

# ——————————————————————————————————————————————
# CONFIGURATION
# ——————————————————————————————————————————————

load_dotenv()  # CLIENT_ID, CLIENT_SECRET, REGION, LOCALE

REGION      = os.getenv("REGION", "eu")
GLOBAL_NS   = f"static-{REGION}"
GLOBAL_LO   = os.getenv("LOCALE", "en_US")
API_BASE    = "https://eu.api.blizzard.com"
TOKEN_URL   = "https://oauth.battle.net/token"
LOG_PATH    = Path("generate_instances.log")
BASE_OUTPUT = Path("data/instances")

# ——————————————————————————————————————————————
# EXPANSION MAP
# ——————————————————————————————————————————————

EXPANSION_MAP = {
    "classic": {
        "dungeons": [
            "Blackfathom Deeps",
            "Blackrock Depths",
            "Deadmines",
            "Dire Maul - Capital Gardens",
            "Dire Maul - Gordok Commons",
            "Dire Maul - Warpwood Quarter",
            "Gnomeregan",
            "Lower Blackrock Spire",
            "Maraudon",
            "Ragefire Chasm",
            "Razorfen Downs",
            "Razorfen Kraul",
            "Scarlet Halls",
            "Scarlet Monastery",
            "Scholomance",
            "The Stockade",
            "The Temple of Atal'Hakkar",
            "Uldaman",
            "Wailing Caverns",
            "Zul'Farrak"
        ],
        "raids": [
            "Molten Core",
            "Blackwing Lair",
            "Ruins of Ahn'Qiraj",
            "Temple of Ahn'Qiraj",
            "Blackrock Depths"
        ],
    },
    "burning crusade": {
        "dungeons": [
            "Auchenai Crypts",
            "Hellfire Ramparts",
            "Magisters' Terrace",
            "Mana Tombs",
            "Old Hillsbrad Foothills",
            "Sethekk Halls",
            "Shadow Labyrinth",
            "The Alcatraz",
            "The Black Moras",
            "The Blood Furnace",
            "The Botanica",
            "The Mechanar",
            "The Shattered Halls",
            "The Slave Pens",
            "The Steamvault",
            "The Underbog"
        ],
        "raids": [
            "Karazhan",
            "Gruul's Lair",
            "Magtheridon's Lair",
            "Serpentshrine Cavern",
            "The Eye",
            "The Battle For Mount Hyjal",
            "Black Temple",
            "Sunwell Plateau"
        ],
    },
    "wrath of the lich king": {
        "dungeons": [
            "Ahn'kahet: The Old Kingdom",
            "Azjol-Nerub",
            "Drak'Tharon Keep",
            "Gundrak",
            "Halls of Lightning",
            "Halls of Reflection",
            "Halls of Stone",
            "Pit of Saron",
            "The Culling of Stratholme",
            "The Forge of Souls",
            "The Nexus",
            "The Oculus",
            "The Violet Hold",
            "Trial of the Champion",
            "Utgarde Keep",
            "Utgarde Pinnacle"
        ],
        "raids": [
            "Vault of Archavon",
            "Naxxramas",
            "The Obsidian Sanctum",
            "The Eye of Eternity",
            "Ulduar",
            "Trial of the Crusader",
            "Onyxia's Lair",
            "Icecrown Citadel",
            "The Ruby Sanctum"
        ],
    },
    "cataclysm": {
        "dungeons": [
            "Blackrock Caverns",
            "Deadmines",
            "End Time",
            "Grim Batol",
            "Halls of Orgination",
            "Hour of Twilight",
            "Lost City of the Tol'vir",
            "Shadowfang Keep",
            "The Stonecore",
            "The Vortex Pinnacle",
            "Throne of the Tides",
            "Well of Eternity",
            "Zul'Aman",
            "Zul'Gurub"
        ],
        "raids": [
            "Baradin Hold",
            "Blackwing Descent",
            "The Bastion of Twilight",
            "Throne of the Four Winds",
            "Firelands",
            "Dragon Soul"
        ],
    },
    "mists of pandaria": {
        "dungeons": [
            "Gate of the Setting Sun",
            "Mogun'shan Palace",
            "Scarlet Halls",
            "Scarlet Monastery",
            "Scholomance",
            "Shado-Pan Monastery",
            "Siege of Niuzao Temple",
            "Stormstout Brewery",
            "Temple of the Jade Serpent"
        ],
        "raids": [
            "Mogu'shan Vaults",
            "Heart of Fear",
            "Terrace of Endless Spring",
            "Throne of Thunder",
            "Siege of Orgrimmar"
        ],
    },
    "warlords of draenor": {
        "dungeons": [
            "Auchidoun",
            "Bloodmaul Slag Mines",
            "Grimrail Depot",
            "Iron Docks",
            "Shadowmoon Burial Grounds",
            "Skyreach",
            "The Everbloom",
            "Upper Blackrock Spire"
        ],
        "raids": [
            "Highmaul",
            "Blackrock Foundry",
            "Hellfire Citadel"
        ],
    },
    "legion": {
        "dungeons": [
            "Assault Violet Hold",
            "Black Rook Hold",
            "Cathedral of Eternal Night",
            "Court of Stars",
            "Darkheart Thicket",
            "Eye of Azshara",
            "Halls of Valor",
            "Maw of Souls",
            "Neltharion's Lair",
            "Return to Karazhan",
            "Seat of the Triumvirate",
            "The Arcway",
            "Vault of the Wardens"
        ],
        "raids": [
            "The Emerald Nightmare",
            "Trial of Valor",
            "The Nighthold",
            "Tomb of Sargeras",
            "Antorus the Burnin Throne",
        ],
    },
    "battle for azeroth": {
        "dungeons": [
            "Atal'Dazar",
            "Freehold",
            "Kings' Rest",
            "Operation: Mechagon",
            "Shrine of the Storm",
            "Siege of Boralus",
            "Temple of Sethraliss",
            "The MOTHERLODE!!",
            "The Underrot",
            "Tol Dagor",
            "Waycrest Manor"
        ],
        "raids": [
            "Uldir",
            "Battle of Dazar'alor",
            "Crucible of Storms",
            "The Eternal Palace",
            "Ny'alotha the Waking City"
        ],
    },
    "shadowlands": {
        "dungeons": [
            "De Other Side",
            "Halls of Atonement",
            "Mists of Tirna Scithe",
            "Plaguefall",
            "Sanguine Depths",
            "Spires of Ascension",
            "Tazavesh, the Veiled Market",
            "The Necrotic Wake",
            "Theater of Pain"
        ],
        "raids": [
            "Castle Nathria",
            "Sanctum of Domination",
            "Sepulcher of the First Ones"
        ],
    },
    "dragonflight": {
        "dungeons": [
            "Algeth'ar Academy",
            "Brackenhide Hollow",
            "Halls of Infunsion",
            "Neltharus",
            "Ruby Life Pools",
            "The Azure Vault",
            "The Nokhud Offensive",
            "Uldaman: Legacy of Tyr",
            "Dawn of the Infinite"
        ],
        "raids": [
            "Vault of the Incarnates",
            "Aberrus, the Shadowed Crucible",
            "Amirdrassil, the Dream's Hope"
        ],
    },
    "the war within": {
        "dungeons": [
            "Ara-Kara, City of Echoes",
            "Cinderbrew Meadery",
            "City of Threads",
            "Darkflame Cleft",
            "Priory of the Sacred Flame",
            "The Dawnbreaker",
            "The Rookery",
            "The Stonevault",
            "OPERATION: FLOODGATE"
        ],
        "raids": [
            "Nerub-ar Palace"
            "Liberation of Undermine"
        ],
    },
    "current season": {
        "dungeons": [
            "Cinderbrew Meadery",
            "Darkflame Cleft",
            "Priory of the Sacred Flame",
            "The Rookery",
            "OPERATION: FLOODGATE",
            "Theater of Pain",
            "Operation: Mechagon",
            "The MOTHERLODE!!"
        ],
        "raids": [
            "Liberation of Undermine"
        ],
    },
}

# ——————————————————————————————————————————————
# LOGGER SETUP
# ——————————————————————————————————————————————

logger = logging.getLogger("by_expansion")
logger.setLevel(logging.INFO)

ch = logging.StreamHandler();    ch.setLevel(logging.INFO)

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
# RATE LIMITER
# ——————————————————————————————————————————————
class RateLimiter:
    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self.calls = deque()
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            now = time.monotonic()
            # remove old calls
            while self.calls and now - self.calls[0] > self.period:
                self.calls.popleft()
            # if we're at limit, wait
            if len(self.calls) >= self.max_calls:
                wait = self.period - (now - self.calls[0])
                time.sleep(wait)
                now = time.monotonic()
                while self.calls and now - self.calls[0] > self.period:
                    self.calls.popleft()
            self.calls.append(now)

rate_limiter = RateLimiter(max_calls=100, period=1.0)

# ——————————————————————————————————————————————
# HTTP SESSION & MEDIA CACHE
# ——————————————————————————————————————————————
SESSION = requests.Session()
MEDIA_CACHE = {}

# ——————————————————————————————————————————————
# AUTH (no caching needed)
# ——————————————————————————————————————————————
def get_access_token() -> str:
    load_dotenv()
    logger.info("Fetching new access token")
    resp = SESSION.post(TOKEN_URL, data={
        "grant_type":    "client_credentials",
        "client_id":     os.getenv("CLIENT_ID"),
        "client_secret": os.getenv("CLIENT_SECRET"),
    })
    resp.raise_for_status()
    return resp.json()["access_token"]

# ——————————————————————————————————————————————
# BLIZZARD GET HELPER
# ——————————————————————————————————————————————
def blizz_get(path: str, namespace: str, locale: str, **params) -> dict:
    url = API_BASE + path
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    qp = {"namespace": namespace, "locale": locale, **params}

    rate_limiter.acquire()
    logger.info(f"CALL → {url} params={qp}")
    resp = SESSION.get(url, params=qp, headers=headers)
    try:
        resp.raise_for_status()
    except Exception:
        logger.error(f"FAILED ← {resp.status_code} {resp.url}")
        return {}
    logger.info(f"RESP  ← {resp.status_code} {resp.url}")
    return resp.json()

def fetch_media(path: str, namespace: str, locale: str) -> dict:
    key = (path, namespace, locale)
    if key in MEDIA_CACHE:
        return MEDIA_CACHE[key]
    data = blizz_get(path, namespace, locale)
    MEDIA_CACHE[key] = data
    return data

# ——————————————————————————————————————————————
# INSTANCE PROCESSING FUNCTION
# ——————————————————————————————————————————————
def process_instance(name: str, bid: int, kind: str, namespace: str, locale: str):
    """
    Fetch detail, media, encounters, creatures for one instance.
    Returns a dict record or None on error.
    """
    try:
        detail = blizz_get(f"/data/wow/journal-instance/{bid}", namespace, locale)
        desc   = detail.get("description")

        media = fetch_media(f"/data/wow/media/journal-instance/{bid}", namespace, locale)
        img   = next((a["value"] for a in media.get("assets", []) if a["key"] == "tile"), None)

        encounters = []
        ec_id = 1
        for enc in detail.get("encounters", []):
            ebid = enc.get("id"); enc_name = enc.get("name")
            if not ebid:
                continue
            edetail = blizz_get(f"/data/wow/journal-encounter/{ebid}", namespace, locale)
            enc_desc = edetail.get("description")

            creatures = []
            c_id = 1
            for c in edetail.get("creatures", []):
                cid = c.get("id"); cname = c.get("name")
                if not cid:
                    continue
                disp = c["creature_display"]["id"]
                cmedia = fetch_media(f"/data/wow/media/creature-display/{disp}", namespace, locale)
                cimg = next((a["value"] for a in cmedia.get("assets", []) if a["key"] == "zoom"), None)
                creatures.append({
                    "id": c_id,
                    "blizzard_id": cid,
                    "creature_display_id": disp,
                    "name": cname,
                    "img": cimg,
                })
                c_id += 1

            encounters.append({
                "id": ec_id,
                "blizzard_id": ebid,
                "name": enc_name,
                "description": enc_desc,
                "creatures": creatures,
            })
            ec_id += 1

        return {
            "kind": kind,
            "record": {
                "blizzard_id": bid,
                "name":        name,
                "description": desc,
                "img":         img,
                "encounters":  encounters,
            }
        }
    except Exception as e:
        logger.error(f"Error processing instance {name} ({bid}): {e}")
        return None

# ——————————————————————————————————————————————
# MAIN DRIVER
# ——————————————————————————————————————————————
def main():
    load_dotenv()
    for exp_name, cfg in EXPANSION_MAP.items():
        namespace, locale = GLOBAL_NS, GLOBAL_LO
        dset, rset = set(cfg["dungeons"]), set(cfg["raids"])

        out_dir = BASE_OUTPUT / exp_name
        out_dir.mkdir(parents=True, exist_ok=True)

        d_list, r_list, u_list = [], [], []
        d_id = r_id = u_id = 1

        idx = blizz_get("/data/wow/journal-instance/index", namespace, locale)
        insts = idx.get("instances", [])
        logger.info(f"[{exp_name}] fetched {len(insts)} instances")

        # classify upfront
        to_process = []
        for entry in insts:
            bid = entry.get("id"); name = entry.get("name")
            if not (bid and name):
                continue
            if name in dset:
                to_process.append((name, bid, "dungeon"))
            elif name in rset:
                to_process.append((name, bid, "raid"))
            else:
                logger.error(f"[{exp_name}] Unmatched instance: '{name}' (ID: {bid})")
                u_list.append({"id": u_id, "blizzard_id": bid, "name": name})
                u_id += 1

        # parallel fetch
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {
                pool.submit(process_instance, name, bid, kind, namespace, locale): (name, bid)
                for name, bid, kind in to_process
            }
            for fut in as_completed(futures):
                res = fut.result()
                if not res:
                    continue
                kind = res["kind"]
                rec  = res["record"]
                if kind == "dungeon":
                    rec["id"] = d_id; d_list.append(rec); d_id += 1
                else:
                    rec["id"] = r_id; r_list.append(rec); r_id += 1

        # write YAML
        with (out_dir / "dungeons.yml").open("w", encoding="utf-8") as f:
            yaml.safe_dump(d_list, f, sort_keys=False, allow_unicode=True)
        with (out_dir / "raids.yml").open("w", encoding="utf-8") as f:
            yaml.safe_dump(r_list, f, sort_keys=False, allow_unicode=True)
        with (out_dir / "unsorted.yml").open("w", encoding="utf-8") as f:
            yaml.safe_dump(u_list, f, sort_keys=False, allow_unicode=True)

        logger.info(
            f"[{exp_name}] wrote {len(d_list)} dungeons, {len(r_list)} raids, "
            f"{len(u_list)} unsorted to {out_dir}"
        )


if __name__ == "__main__":
    main()
