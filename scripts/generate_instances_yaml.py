#!/usr/bin/env python3
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

API_BASE = "https://eu.api.blizzard.com"
TOKEN_URL = "https://oauth.battle.net/token"

BASE_OUTPUT = Path("data/instances")
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / "generate_instances.log"
API_CALL_COUNT = 0

# List all the encounter NAMES you want to include under raids
TARGET_ENCOUNTERS = [
    "High Interrogator Gerstahn",
    "Lord Roccor",
    "Houndmaster Grebmar",
    "Ring of Law",
    "Pyromancer Loregrain",
    "Lord Incendius",
    "Warder Stilgiss",
    "Fineous Darkvire",
    "Bael'Gar",
    "General Angerforge",
    "Golem Lord Argelmach",
    "Hurley Blackbreath",
    "Phalanx",
    "Plugger Spazzring",
    "Ambassador Flamelash",
    "The Seven",
    "Magmus",
    "Emperor Dagran Thaurissan",
    "Magmadar",
    "Gehennas",
    "Garr",
    "Shazzrah",
    "Baron Geddon",
    "Sulfuron Harbinger",
    "Golemagg the Incinerator",
    "Majordomo Executus",
    "Ragnaros",
    "Razorgore the Untamed",
    "Vaelastrasz the Corrupt",
    "Broodlord Lashlayer",
    "Firemaw",
    "Ebonroc",
    "Flamegor",
    "Chromaggus",
    "Nefarian",
    "Kurinnaxx",
    "General Rajaxx",
    "Moam",
    "Buru the Gorger",
    "Ayamiss the Hunter",
    "Ossirian the Unscarred",
    "The Prophet Skeram",
    "Silithid Royalty",
    "Battleguard Sartura",
    "Fankriss the Unyielding",
    "Viscidus",
    "Princess Huhuran",
    "Executioner Gore",
    "The Twin Emperors",
    "Ouro",
    "C'Thun",
    "Servant's Quarters",
    "Attumen the Huntsman",
    "Moroes",
    "Maiden of Virtue",
    "Opera Hall",
    "The Curator",
    "Terestian Illhoof",
    "Netherspite",
    "Prince Malchezaar",
    "High King Maulgar",
    "Gruul the Dragonkiller",
    "Magtheridon",
    "Hydross the Unstable",
    "The Lurker Below",
    "Leotheras the Blind",
    "Fathom-Lord Karathress",
    "Morogrim Tidewalker",
    "Lady Vashj",
    "Al'ar",
    "Void Reaver",
    "High Astromancer Solarian",
    "Kael'thas Sunstrider",
    "Rage Winterchill",
    "Anetheron",
    "Kaz'rogal",
    "Azgalor",
    "Archimonde",
    "High Warlord Naj'entus",
    "Supremus",
    "Shade of Akama",
    "Teron Gorefiend",
    "Gurtogg Bloodboil",
    "Reliquary of Souls",
    "Mother Shahraz",
    "The Illidari Council",
    "Illidan Stormrage",
    "Kalecgos",
    "Brutallus",
    "Felmyst",
    "The Eredar Twins",
    "M'uru",
    "Kil'jaeden",
    "Archavon the Stone Watcher",
    "Emalon the Storm Watcher",
    "Koralon the Flame Watcher",
    "Toravon the Ice Watcher",
    "Anub'Rekhan",
    "Grand Widow Faerlina",
    "Maexxna",
    "Noth the Plaguebringer",
    "Heigan the Unclean",
    "Loatheb",
    "Instructor Razuvious",
    "Gothik the Harvester",
    "The Four Horsemen",
    "Patchwerk",
    "Grobbulus",
    "Gluth",
    "Thaddius",
    "Sapphiron",
    "Kel'Thuzad",
    "Sartharion",
    "Malygos",
    "Flame Leviathan",
    "Ignis the Furnace Master",
    "Razorscale",
    "XT-002 Deconstructor",
    "The Assembly of Iron",
    "Kologarn",
    "Auriaya",
    "Hodir",
    "Thorim",
    "Freya",
    "Mimiron",
    "General Vezax",
    "Yogg-Saron",
    "Algalon the Observer",
    "The Northrend Beasts",
    "Lord Jaraxxus",
    "Champions of the Alliance",
    "Champions of the Horde",
    "Twin Val'kyr",
    "Anub'arak",
    "Onyxia",
    "Lord Marrowgar",
    "Lady Deathwhisper",
    "Icecrown Gunship Battle",
    "Deathbringer Saurfang",
    "Festergut",
    "Rotface",
    "Professor Putricide",
    "Blood Prince Council",
    "Blood-Queen Lana'thel",
    "Valithria Dreamwalker",
    "Sindragosa",
    "The Lich King",
    "Halion",
    "Argaloth",
    "Occu'thar",
    "Alizabal, Mistress of Hate",
    "Omnotron Defense System",
    "Magmaw",
    "Atramedes",
    "Chimaeron",
    "Maloriak",
    "Nefarian's End",
    "Halfus Wyrmbreaker",
    "Theralion and Valiona",
    "Ascendant Council",
    "Cho'gall",
    "Sinestra",
    "The Conclave of Wind",
    "Al'Akir",
    "Beth'tilac",
    "Lord Rhyolith",
    "Alysrazor",
    "Shannox",
    "Baleroc, the GateKeeper",
    "Majordomo Staghelm",
    "Ragnaros",
    "Morchok",
    "Warlord Zon'ozz",
    "Yor'sahj the Unsleeping",
    "Hagara the Stormbinder",
    "Ultraxion",
    "Warmaster Blackhorn",
    "Spine of Deathwing",
    "Madness of Deathwing",
    "The Stone Guard",
    "Feng the Accursed",
    "Gara'jal the Spiritbinder",
    "The Spirit Kings",
    "Elegon",
    "Will of the Emperor",
    "Imperial Vizier Zor'lok",
    "Blade Lord Ta'yak",
    "Garalon",
    "Wind Lord Mel'jarak",
    "Amber-Shaper Un'sok",
    "Grand Empress Shek'zeer",
    "Protectors of the Endless",
    "Tsulong",
    "Lei Shi",
    "Sha of Fear",
    "Jin'rokh the Breaker",
    "Horridon",
    "Council of Elders",
    "Tortos",
    "Megaera",
    "Ji-Kun",
    "Durumu the Forgotten",
    "Primordius",
    "Dark Animus",
    "Iron Qon",
    "Twin Empyreans",
    "Lei Shen",
    "Ra-den",
    "Immerseus",
    "The Fallen Protectors",
    "Norushen",
    "Sha of Pride",
    "Galakras",
    "Iron Juggernaut",
    "Kor'kron Dark Shaman",
    "General Nazgrim",
    "Malkorok",
    "Spoils of Pandaria",
    "Thok the Bloodthirsty",
    "Siegecrafter Blackfuse",
    "Paragons of the Klaxxi",
    "Garrosh Hellscream",
    "Kargath Bladefist",
    "The Butcher",
    "Tectus",
    "Brackenspore",
    "Twin Ogron",
    "Ko'ragh",
    "Imperator Mar'gok",
    "Oregorger",
    "Hans'gar and Franzok",
    "Beastlord Darmac",
    "Gruul",
    "Flamebender Ka'graz",
    "Operator Thogar",
    "The Blast Furnace",
    "Kromog",
    "The Iron Maidens",
    "Blackhand",
    "Hellfire Assault",
    "Iron Reaver",
    "Kormrok",
    "Hellfire High Council",
    "Kilrogg Deadeye",
    "Gorefiend",
    "Shadow-Lord Iskar",
    "Socrethar the Eternal",
    "Fel Lord Zakuun",
    "Xhul'horac",
    "Tyrant Velhari",
    "Mannoroth",
    "Archimonde",
    "Nythendra",
    "Il'gynoth, Heart of Corruption",
    "Elerethe Renferal",
    "Ursoc",
    "Dragons of Nightmare",
    "Cenarius",
    "Xavius",
    "Odyn",
    "Guarm",
    "Helya",
    "Skorpyron",
    "Chronomatic Anomaly",
    "Trilliax",
    "Spellblade Aluriel",
    "Tichondrius",
    "Krosus",
    "High Botanist Tel'arn",
    "Star Augur Etraeus",
    "Grand Magistrix Elisande",
    "Gul'dan",
    "Goroth",
    "Demonic Inquisition",
    "Harjatan",
    "Sisters of the Moon",
    "Mistress Sassz'ine",
    "The Desolate Host",
    "Maiden of Vigilance",
    "Fallen Avatar",
    "Kil'jaeden",
    "Garothi Worldbreaker",
    "Felhounds of Sargeras",
    "Antoran High Command",
    "Portal Keeper Hasabel",
    "Eonar the Life-Binder",
    "Imonar the Soulhunter",
    "Kin'garoth",
    "Varimathras",
    "The Coven of Shivarra",
    "Aggramar",
    "Argus the Unmaker",
    "Taloc",
    "MOTHER",
    "Fetid Devourer",
    "Zek'voz, Herald of N'zoth",
    "Vectis",
    "Zul, Reborn",
    "Mythrax the Unraveler",
    "G'huun",
    "Champion of the Light",
    "Grong, the Jungle Lord",
    "Grong, the Revenant",
    "Jadefire Masters",
    "Opulence",
    "Conclave of the Chosen",
    "King Rastakhan",
    "High Tinker Mekkatorque",
    "Stormwall Blockade",
    "Lady Jaina Proudmoore",
    "The Restless Cabal",
    "Uu'nat, Harbinger of the void",
    "Abyssal Commander Sivara",
    "Blackwater Behemoth",
    "Radiance of Azshara",
    "Lady Ashvane",
    "Orgozoa",
    "The Queen's Court",
    "Za'qul, Harbinger of Ny'alotha",
    "Queen Azshara",
    "Wrathion, the Black Emperor",
    "Maut",
    "The Prophet Skitra",
    "Dark Inquisitor Xanesh",
    "The Hivemind",
    "Shad'har the insatiable",
    "Drest'agath",
    "Il'gynoth, Corruption Reborn",
    "Vexiona",
    "Ra-den the Despoiled",
    "Carapace of N'Zoth",
    "N'Zoth the Corruptor",
    "Shriekwing",
    "Huntsman Altimor",
    "Sun King's Salvation",
    "Artificer Xy'mox",
    "Hungering Destroyer",
    "Lady Inerva Darkvein",
    "The Council of Blood",
    "Sludgefist",
    "Stone Legion Generals",
    "Sire Denathrius",
    "The Tarragrue",
    "The Eye of the Jailer",
    "The Nine",
    "Remnant of Ner'zhul",
    "Soulrender Dormazain",
    "Painsmith Raznal",
    "Guardian of the First Ones",
    "Fatescribe Roh-Kalo",
    "Kel'Thuzad",
    "Sylvanas Windrunner",
    "Vigilant Guardian",
    "Skolex, the Insatiable Ravener",
    "Artificer Xy'mox",
    "Dausegne, the Fallen Oracle",
    "Prototype Pantheon",
    "Lihuvim, Principal Architect",
    "Halondrus the Reclaimer",
    "Anduin Wrynn",
    "Lords of Dread",
    "Rygelon",
    "The Jailer",
    "Eranog",
    "Terros",
    "The Primal Council",
    "Sennarth, the Cold Breath",
    "Dathea, Ascended",
    "Kurog Grimtotem",
    "Broodkeeper Diurna",
    "Raszageth the Storm-Eater",
    "Kazzara, the Hellforged",
    "The Amalgamation Chamber",
    "The Forgotten Experiments",
    "Assault of the Zaqali",
    "Rashok, the Elder",
    "The Vigilant Steward, Zskarn",
    "Magmorax",
    "Echo of Neltharion",
    "Scalecommander Sarkareth",
    "Gnarlroot",
    "Igira the Cruel",
    "Volcoross",
    "Council of Dreams",
    "Larodar, Keeper of the Flame",
    "Nymue, Weaver of the Cycle",
    "Smolderon",
    "Tindral Sageswift, Seer of the Flame",
    "Fyrakk the Blazing",
    "Ulgrax the Devourer",
    "The Bloodbound Horror",
    "Sikran, Captain of the Sureki",
    "Rasha'nan",
    "Broodtwister Ovi'nax",
    "Nexus-Princess Ky'veza",
    "The Silken Court",
    "Queen Ansurek",
    "Vexie and the Geargrinders",
    "Cauldron of Carnage",
    "Rik Reverb",
    "Stix Bunkjunker",
    "Sprocketmonger Lockenstock",
    "The One-Armed Bandit",
    "Mug'Zee, Heads of Security",
    "Chrome King Gallywix",
]

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
            # drop old
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
    API_CALL_COUNT += 1  # ← count this call
    url = API_BASE + path
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    qp = {"namespace": namespace, "locale": locale, **params}

    rate_limiter.acquire()
    logger.info(f"CALL #{API_CALL_COUNT} → {url} params={qp}")  # include count in log
    resp = SESSION.get(url, params=qp, headers=headers)
    if resp.status_code != 200:
        logger.error(f"FAILED ← {resp.status_code} {resp.url}")
        return {}
    logger.info(f"RESP  ← {resp.status_code} {resp.url}")
    return resp.json()


def fetch_media(path, namespace, locale):
    key = (path, namespace, locale)
    if key not in MEDIA_CACHE:
        MEDIA_CACHE[key] = blizz_get(path, namespace, locale)
    return MEDIA_CACHE[key]


def process_encounter(enc_name, eid):
    """
    Fetch a single encounter’s detail and return a tuple of
    (expansion_name, instance_id, encounter_record) if it's a RAID,
    or None if it's not a RAID or on error.
    """
    try:
        detail = blizz_get(f"/data/wow/journal-encounter/{eid}", GLOBAL_NS, GLOBAL_LO)
        exp_name = detail.get("expansion", {}).get("name")
        cat = detail.get("category", {}).get("type")
        if cat != "RAID":
            # skip all dungeon encounters
            return None

        inst = detail["instance"]
        inst_id = inst["id"]
        inst_name = inst["name"]

        # build encounter record
        creatures = detail.get("creatures", [])
        first = creatures[0] if creatures else {}
        disp = first.get("creature_display", {}).get("id")
        cimg = None
        if disp:
            media = fetch_media(
                f"/data/wow/media/creature-display/{disp}", GLOBAL_NS, GLOBAL_LO
            )
            cimg = next(
                (a["value"] for a in media.get("assets", []) if a["key"] == "zoom"),
                None,
            )

        enc_rec = {
            "blizzard-id": eid,
            "name": enc_name,
            "description": detail.get("description"),
            "creature_display_id": disp,
            "img": cimg,
        }
        return exp_name, inst_id, inst_name, enc_rec
    except Exception as e:
        logger.error(f"Error loading encounter '{enc_name}' ({eid}): {e}")
        return None


# ——————————————————————————————————————————————
# MAIN SCRIPT
# ——————————————————————————————————————————————
def main():
    load_dotenv()  # load CLIENT_ID, CLIENT_SECRET, REGION, LOCALE

    # 0) Prepare container per expansion, including “Current Season”
    expansions: dict[str, dict[str, dict[int, dict]]] = {
        "Current Season": {"raids": {}, "dungeons": {}}
    }

    # 1) Fetch the Current Season expansion (ID 505) to collect its instance IDs
    season_data = blizz_get("/data/wow/journal-expansion/505", GLOBAL_NS, GLOBAL_LO)
    season_dungeons = {i["id"] for i in season_data.get("dungeons", []) if i.get("id")}
    season_raids = {i["id"] for i in season_data.get("raids", []) if i.get("id")}
    season_inst_ids = season_dungeons | season_raids

    # 2) Build name→encounter_id map
    enc_idx = blizz_get("/data/wow/journal-encounter/index", GLOBAL_NS, GLOBAL_LO)
    name_to_eid = {
        e["name"]: e["id"] for e in enc_idx.get("encounters", []) if e.get("name")
    }

    # 3) Parallel fetch of TARGET_ENCOUNTERS (only include RAID)
    def fetch_enc(enc_name: str):
        eid = name_to_eid.get(enc_name)
        if not eid:
            logger.error(f"Encounter not in index: '{enc_name}'")
            return None
        detail = blizz_get(f"/data/wow/journal-encounter/{eid}", GLOBAL_NS, GLOBAL_LO)
        if detail.get("category", {}).get("type") != "RAID":
            return None

        inst_ref = detail.get("instance", {})
        inst_id = inst_ref.get("id")
        inst_name = inst_ref.get("name")
        if not (inst_id and inst_name):
            logger.error(f"Missing instance info for '{enc_name}' ({eid})")
            return None

        # fetch instance detail to know its real expansion
        inst_detail = blizz_get(
            f"/data/wow/journal-instance/{inst_id}", GLOBAL_NS, GLOBAL_LO
        )
        exp_name = inst_detail.get("expansion", {}).get("name")
        if not exp_name:
            logger.error(
                f"Missing expansion for instance {inst_id} of encounter '{enc_name}'"
            )
            return None

        return enc_name, eid, exp_name, inst_id, inst_name, detail

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(fetch_enc, name): name for name in TARGET_ENCOUNTERS}
        for fut in as_completed(futures):
            res = fut.result()
            if not res:
                continue
            enc_name, eid, exp_name, inst_id, inst_name, detail = res

            # ensure real expansion bucket exists
            exp = expansions.setdefault(exp_name, {"raids": {}, "dungeons": {}})
            raid_bucket = exp["raids"].setdefault(
                inst_id,
                {
                    "blizzard-id": inst_id,
                    "name": inst_name,
                    "description": None,
                    "img": None,
                    "encounters": [],
                },
            )

            # on first creation, fetch instance description & media
            if raid_bucket["description"] is None:
                idet = blizz_get(
                    f"/data/wow/journal-instance/{inst_id}", GLOBAL_NS, GLOBAL_LO
                )
                raid_bucket["description"] = idet.get("description")
                media = fetch_media(
                    f"/data/wow/media/journal-instance/{inst_id}", GLOBAL_NS, GLOBAL_LO
                )
                raid_bucket["img"] = next(
                    (a["value"] for a in media.get("assets", []) if a["key"] == "tile"),
                    None,
                )

            # build encounter record
            creatures = detail.get("creatures", [])
            disp = creatures[0]["creature_display"]["id"] if creatures else None
            cimg = None
            if disp:
                cm = fetch_media(
                    f"/data/wow/media/creature-display/{disp}", GLOBAL_NS, GLOBAL_LO
                )
                cimg = next(
                    (a["value"] for a in cm.get("assets", []) if a["key"] == "zoom"),
                    None,
                )

            enc_rec = {
                "blizzard-id": eid,
                "name": enc_name,
                "description": detail.get("description"),
                "creature_display_id": disp,
                "img": cimg,
            }
            raid_bucket["encounters"].append(enc_rec)

            # 3.5) Also duplicate into Current Season if in that set
            if inst_id in season_inst_ids:
                expansions["Current Season"]["raids"][inst_id] = raid_bucket

    # 4) Fetch all dungeon instances and assign to expansions + Current Season
    inst_idx = blizz_get("/data/wow/journal-instance/index", GLOBAL_NS, GLOBAL_LO)
    for entry in inst_idx.get("instances", []):
        iid, iname = entry.get("id"), entry.get("name")
        det = blizz_get(f"/data/wow/journal-instance/{iid}", GLOBAL_NS, GLOBAL_LO)
        if det.get("category", {}).get("type") != "DUNGEON":
            continue

        exp_name = det.get("expansion", {}).get("name")
        if not exp_name:
            logger.error(f"Missing expansion for dungeon instance {iid}")
            continue

        media = fetch_media(
            f"/data/wow/media/journal-instance/{iid}", GLOBAL_NS, GLOBAL_LO
        )
        rec = {
            "blizzard-id": iid,
            "name": iname,
            "description": det.get("description"),
            "img": next(
                (a["value"] for a in media.get("assets", []) if a["key"] == "tile"),
                None,
            ),
        }

        # assign to its real expansion
        exp = expansions.setdefault(exp_name, {"raids": {}, "dungeons": {}})
        exp["dungeons"][iid] = rec

        # duplicate into Current Season if listed
        if iid in season_inst_ids:
            expansions["Current Season"]["dungeons"][iid] = rec

    # 5) Write YAML per expansion, assigning sequential IDs
    for exp_name, data in expansions.items():
        out_dir = BASE_OUTPUT / exp_name
        out_dir.mkdir(parents=True, exist_ok=True)

        # dungeons.yml
        seq = 1
        for inst in data["dungeons"].values():
            inst["id"] = seq
            seq += 1
        with (out_dir / "dungeons.yml").open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                list(data["dungeons"].values()), f, sort_keys=False, allow_unicode=True
            )

        # raids.yml
        seq = 1
        for inst in data["raids"].values():
            inst["id"] = seq
            ec_seq = 1
            for ec in inst["encounters"]:
                ec["id"] = ec_seq
                ec_seq += 1
            seq += 1
        with (out_dir / "raids.yml").open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                list(data["raids"].values()), f, sort_keys=False, allow_unicode=True
            )

        logger.info(f"Total Blizzard API calls made: {API_CALL_COUNT}")
        logger.info(
            f"[{exp_name}] wrote {len(data['dungeons'])} dungeons and {len(data['raids'])} raids"
        )


if __name__ == "__main__":
    main()
