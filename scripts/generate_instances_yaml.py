#!/usr/bin/env python3
import logging
import os
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
BASE_OUTPUT = Path("data/instances.yml")
LOG_PATH = Path("generate_instances.log")

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
    """
    Always fetch a fresh OAuth token—no caching to disk or memory.
    """
    logger.info("Fetching new access token from Blizzard")
    resp = requests.post(
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
    load_dotenv()  # load CLIENT_ID, CLIENT_SECRET, REGION, LOCALE from .env

    for exp_name, cfg in EXPANSION_MAP.items():  # iterate over each retail expansion
        dset = set(cfg["dungeons"])  # quick lookup set for dungeon names
        rset = set(cfg["raids"])  # quick lookup set for raid names

        out_dir = BASE_OUTPUT.parent / exp_name
        out_dir.mkdir(parents=True, exist_ok=True)  # ensure expansion folder exists

        d_list, r_list = [], []  # lists to collect dungeon/raid records
        d_id, r_id = 1, 1  # reset custom ID counters for each file

        # 1) Fetch the instance index from Blizzard
        idx = blizz_get(
            "/data/wow/journal-instance/index", namespace=NAMESPACE, locale=LOCALE
        )
        insts = idx.get("instances", [])
        logger.info(f"[{exp_name}] fetched {len(insts)} instances")

        for entry in insts:
            bid = entry.get("id")  # Blizzard’s instance ID
            name = entry.get("name")  # instance name
            if not (bid and name):
                continue  # skip if missing data

            # 2) classify as dungeon or raid based on your manual lists
            if name in dset:
                target_list, next_id = d_list, d_id
            elif name in rset:
                target_list, next_id = r_list, r_id
            else:
                continue  # skip unlisted instances

            # 3) Fetch instance detail
            detail = blizz_get(
                f"/data/wow/journal-instance/{bid}", namespace=NAMESPACE, locale=LOCALE
            )
            desc = detail.get("description")  # optional description

            # 4) Fetch zone image via media endpoint
            media = blizz_get(
                f"/data/wow/media/journal-instance/{bid}",
                namespace=NAMESPACE,
                locale=LOCALE,
            )
            img = next(
                (a["value"] for a in media.get("assets", []) if a["key"] == "tile"),
                None,
            )

            # 5) Process encounters
            encounters, ec_id = [], 1
            for enc in detail.get("encounters", []):
                ebid = enc.get("id")
                enc_name = enc.get("name")
                if not ebid:
                    continue  # skip invalid encounter

                # fetch encounter detail
                edetail = blizz_get(
                    f"/data/wow/journal-encounter/{ebid}",
                    namespace=NAMESPACE,
                    locale=LOCALE,
                )
                enc_desc = edetail.get("description")

                # 6) Process creatures in this encounter
                creatures, c_id = [], 1
                for c in edetail.get("creatures", []):
                    cid = c.get("id")
                    cname = c.get("name")
                    if not cid:
                        continue  # skip invalid creature

                    disp = c["creature_display"]["id"]
                    cmedia = blizz_get(
                        f"/data/wow/media/creature-display/{disp}",
                        namespace=NAMESPACE,
                        locale=LOCALE,
                    )
                    cimg = next(
                        (
                            a["value"]
                            for a in cmedia.get("assets", [])
                            if a["key"] == "zoom"
                        ),
                        None,
                    )

                    creatures.append(
                        {
                            "id": c_id,
                            "blizzard_id": cid,
                            "creature_display_id": disp,
                            "name": cname,
                            "img": cimg,
                        }
                    )
                    c_id += 1

                encounters.append(
                    {
                        "id": ec_id,
                        "blizzard_id": ebid,
                        "name": enc_name,
                        "description": enc_desc,
                        "creatures": creatures,
                    }
                )
                ec_id += 1

            # 7) Build and append the instance record
            record = {
                "id": next_id,
                "blizzard_id": bid,
                "name": name,
                "description": desc,
                "img": img,
                "encounters": encounters,
            }
            target_list.append(record)

            # 8) Increment the proper ID counter
            if target_list is d_list:
                d_id += 1
            else:
                r_id += 1

        # 9) Write out the YAML files for this expansion
        with (out_dir / "dungeons.yml").open("w", encoding="utf-8") as f:
            yaml.safe_dump(d_list, f, sort_keys=False, allow_unicode=True)
        with (out_dir / "raids.yml").open("w", encoding="utf-8") as f:
            yaml.safe_dump(r_list, f, sort_keys=False, allow_unicode=True)

        logger.info(
            f"[{exp_name}] wrote {len(d_list)} dungeons and {len(r_list)} raids"
        )


if __name__ == "__main__":
    main()
