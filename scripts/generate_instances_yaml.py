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
LOG_PATH = Path("generate_instances.log")
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
            "Zul'Farrak",
        ],
        "raids": {
            "Molten Core": [
                "Lucifron",
                "Magmadar",
                "Gehennas",
                "Garr",
                "Shazzrah",
                "Baron Geddon",
                "Sulfuron Harbinger",
                "Golemagg the Incinerator",
                "Majordomo Executus",
                "Ragnaros",
            ],
            "Blackwing Lair": [
                "Razorgore the Untamed",
                "Vaelastrasz the Corrupt",
                "Broodlord Lashlayer",
                "Firemaw",
                "Ebonroc",
                "Flamegor",
                "Chromaggus",
                "Nefarian",
            ],
            "Ruins of Ahn'Qiraj": [
                "Kurinnaxx",
                "General Rajaxx",
                "Moam",
                "Buru the Gorger",
                "Ayamiss the Hunter",
                "Ossirian the Unscarred",
            ],
            "Temple of Ahn'Qiraj": [
                "The Prophet Skeram",
                "Silithid Royalty",
                "Battleguard Sartura",
                "Fankriss the Unyielding",
                "Thruk",
                "Viscidus",
                "Princess Huhuran",
                "Executioner Gore",
                "The Twin Emperors",
                "Ouro",
                "C'Thun",
            ],
            "Blackrock Depths": [
                "High Interrogator Gerstahn",
                "Lord Roccor",
                "Houndmaster Grebmar",
                "Ring of Law",
                "Pyromancer Loregrain",
                "Lord Incendius",
                "Warden Stilgiss",
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
            ],
        },
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
            "The Underbog",
        ],
        "raids": {
            "Karazhan": [
                "Servant's Quarters",
                "Attumen the Huntsman",
                "Moroes",
                "Maiden of Virtue",
                "Opera Hall",
                "The Curator",
                "Terestian Illhoof",
                "Netherspite",
                "Princess Malchezaar",
            ],
            "Gruul's Lair": [
                "High King Maulgar",
                "Gruul the Dragonkiller",
            ],
            "Magtheridon's Lair": [
                "Magtheridon",
            ],
            "Serpentshrine Cavern": [
                "Hydross the Unstable",
                "The Lurker Below",
                "Leotheras the Blind",
                "Fathom-Lord Karathress",
                "Morogrim Tidewalker",
                "Lady Vashj",
            ],
            "The Eye": [
                "Al'ar",
                "Void Reaver",
                "High Astromancer Solarian",
                "Kael'thas Sunstrider",
            ],
            "The Battle For Mount Hyjal": [
                "Rage Winterchill",
                "Anetheron",
                "Kaz'rogal",
                "Azgalor",
                "Archimonde",
            ],
            "Black Temple": [
                "High Warlord Naj'entus",
                "Supremus",
                "Shade of Akama",
                "Teron Gorefiend",
                "Gurtogg Bloodboil",
                "Reliquary of Souls",
                "Mother Shahraz",
                "The Illidari Council",
                "Illidan Stormrage",
            ],
            "Sunwell Plateau": [
                "Kalecgos",
                "Brutallus",
                "Felmyst",
                "Eredar Twins",
                "M'uru",
                "Kil'jaeden",
            ],
        },
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
            "Utgarde Pinnacle",
        ],
        "raids": {
            "Vault of Archavon": [
                "Archavon the Stone Watcher",
                "Emalon the Storm Watcher",
                "Koralon the Flame Watcher",
                "Toravon the Ice Watcher",
            ],
            "Naxxramas": [
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
            ],
            "The Obsidian Sanctum": [
                "Sartharion",
            ],
            "The Eye of Eternity": [
                "Malygos",
            ],
            "Ulduar": [
                "Flame Leviathan",
                "Ignis the Furnace Master",
                "Razorscale",
                "XT-002 Deconstructor",
                "Assembly of Iron",
                "Kologarn",
                "Auriaya",
                "Hodir",
                "Thorim",
                "Freya",
                "Mimiron",
                "General Vezax",
                "Yogg-Saron",
                "Algalon the Observer",
            ],
            "Trial of the Crusader": [
                "The Northrend Beasts",
                "Lord Jaraxxus",
                "Faction Champions",
                "Twin Val'kyr",
                "Anub'arak",
            ],
            "Onyxia's Lair": [
                "Onyxia",
            ],
            "Icecrown Citadel": [
                "Lord Marrowgar",
                "Lady Deathwhisper",
                "Gunship Battle",
                "Deathbringer Saurfang",
                "Festergut",
                "Rotface",
                "Professor Putricide",
                "Blood Prince Council",
                "Blood-Queen Lana'thel",
                "Valithria Dreamwalker",
                "Sindragosa",
                "The Lich King",
            ],
            "The Ruby Sanctum": [
                "Halion",
            ],
        },
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
            "Zul'Gurub",
        ],
        "raids": {
            "Baradin Hold": [
                "Argaloth",
                "Occu'thar",
                "Alizabal, Mistress of Hate",
            ],
            "Blackwing Descent": [
                "Omnotron Defense System",
                "Magmaw",
                "Atramedes",
                "Chimaeron",
                "Maloriak",
                "Nefarian's End",
            ],
            "The Bastion of Twilight": [
                "Halfus Wyrmbreaker",
                "Theralion and Valiona",
                "Ascendant Council",
                "Cho'gall",
                "Sinestra",
            ],
            "Throne of the Four Winds": [
                "The Conclave of Wind",
                "Al'Akir",
            ],
            "Firelands": [
                "Beth'tilac",
                "Lord Rhyolith",
                "Alysrazor",
                "Shannox",
                "Baleroc, the GateKeeper",
                "Majordomo Staghelm",
                "Ragnaros",
            ],
            "Dragon Soul": [
                "Morchok",
                "Warlord Zon'ozz",
                "Yor'sahj the Unsleeping",
                "Hagara the Stormbinder",
                "Ultraxion",
                "Warmaster Blackhorn",
                "Spine of Deathwing",
                "Madness of Deathwing",
            ],
        },
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
            "Temple of the Jade Serpent",
        ],
        "raids": {
            "Mogu'shan Vaults": [
                "The Stone Guard",
                "Feng the Accursed",
                "Gara'jal the Spiritbinder",
                "The Spirit Kings",
                "Elegon",
                "Will of the Emperor",
            ],
            "Heart of Fear": [
                "Imperial Vizier Zor'lok",
                "Blade Lord Ta'yak",
                "Garalon",
                "Wind Lord Mel'jarak",
                "Amber-Shaper Un'sok",
                "Grand Empress Shek'zeer",
            ],
            "Terrace of Endless Spring": [
                "Protectors of the Endless",
                "Tsulong",
                "Lei Shi",
                "Sha of Fear",
            ],
            "Throne of Thunder": [
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
            ],
            "Siege of Orgrimmar": [
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
            ],
        },
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
            "Upper Blackrock Spire",
        ],
        "raids": {
            "Highmaul": [
                "Kargath Bladefist",
                "The Butcher",
                "Tectus",
                "Brackenspore",
                "Twin Ogron",
                "Ko'ragh",
                "Imperator Mar'gok",
            ],
            "Blackrock Foundry": [
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
            ],
            "Hellfire Citadel": [
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
            ],
        },
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
            "Vault of the Wardens",
        ],
        "raids": {
            "The Emerald Nightmare": [
                "Nythendra",
                "Il'gynoth, Heart of Corruption",
                "Elerethe Renferal",
                "Ursoc",
                "Dragons of Nightmare",
                "Cenarius",
                "Xavius",
            ],
            "Trial of Valor": [
                "Odyn",
                "Guarm",
                "Helya",
            ],
            "The Nighthold": [
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
            ],
            "Tomb of Sargeras": [
                "Goroth",
                "Demonic Inquisition",
                "Harjatan",
                "Sisters of the Moon",
                "Mistress Sassz'ine",
                "The Desolate Host",
                "Maiden of Vigilance",
                "Fallen Avatar",
                "Kil'jaeden",
            ],
            "Antorus, the Burnin Throne": [
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
            ],
        },
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
            "Waycrest Manor",
        ],
        "raids": {
            "Uldir": [
                "Taloc",
                "MOTHER",
                "Fetid Devourer",
                "Zek'voz, Herald of N'zoth",
                "Vectis",
                "Zul, Reborn",
                "Mythrax the Unraveler",
                "G'huun",
            ],
            "Battle of Dazar'alor": [
                "Frida Ironbellows",
                "Ra'wani Kanae",
                "Grong the Revenant",
                "Grong, the Jungle Lord",
                "Ma'ra Grimfang",
                "Anathos Firecaller",
                "Manceroy Flamefist",
                "Mestrah",
                "Opulence",
                "Conclave of the Chosen",
                "King Rastakhan",
                "High Tinker Mekkatorque",
                "Stormwall Blockade",
                "Lady Jaina Proudmoore",
                # "horde": [
                #         "Frida Ironbellows",
                #         "Grong, the Jungle Lord",
                #         "Jadefire Masters",
                #         "High Tinker Mekkatorque",
                #         "Stormwall Blockade",
                #         "Lady Jaina Proudmoore",
                #     ],
                # "alliance": [
                #         "Ra'wani Kanae",
                #         "Grong the Revenant",
                #         "Jadefire Masters",
                #         "Opulence",
                #         "Stormwall Blockade",
                #         "Lady Jaina Proudmoore",
                #     ],
                # TODO: add logic to differentiate between horde and alliance
            ],
            "Crucible of Storms": [
                "The Restless Cabal",
                "Uu'nat, Harbinger of the void",
            ],
            "The Eternal Palace": [
                "Abyssal Commander Sivara",
                "Blackwater Behemoth",
                "Radiance of Azshara",
                "Lady Ashvane",
                "Orgozoa",
                "The Queen's Court",
                "Za'qul, Harbinger of Ny'alotha",
                "Queen Azshara",
            ],
            "Ny'alotha the Waking City": [
                "Wrathion, the Black Emperor",
                "Maut",
                "The Prophet Skitra",
                "Dark Inquisitor Xanesh",
                "The Hivemind",
                "Shad'har the insatiable",
                "Drest'agath",
                "Il'gunoth, Corruption Reborn",
                "Vexiona",
                "Ra-den the Despoiled",
                "Carapace of N'Zoth",
                "N'Zoth the Corruptor",
            ],
        },
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
            "Theater of Pain",
        ],
        "raids": {
            "Castle Nathria": [
                "Shriekwing",
                "Huntsman Altimor",
                "Sun King's Salvation",
                "Artificier Xy'mox",
                "Hungering Destroyer",
                "Lady Inerva Darkvein",
                "The Council of Blood",
                "Sludgefist",
                "Stone Legion Generals",
                "Sire Denathrius",
            ],
            "Sanctum of Domination": [
                "The Tarragrue",
                "The Eye of the Jailer",
                "The Nine",
                # TODO: list all NPCs
                "Remnant of Ner'zhul",
                "Soulrender Dormazain",
                "Painsmith Raznal",
                "Guardian of the First Ones",
                "Fatescribe",
                "Kel'Thuzad",
                "Sylvanas Windrunner",
            ],
            "Sepulcher of the First Ones": [
                "Vigilant Guardian",
                "Skolex, the Insatiable Ravener",
                "Artificer Xy'mox",
                "Dausegne, the Fallen Oracle",
                "Prototype Pantheon",
                "Lihuvim, Principal Architect",
                "Halondrus the Reclaimer",
                "Anduin Wrynn",
                "Lords of Dread",
                # TODO: list npcs
                "Rygelon",
                "The Jailer",
            ],
        },
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
            "Dawn of the Infinite",
        ],
        "raids": {
            "Vault of the Incarnates": [
                "Eranog",
                "Terros",
                "The Primal Council",
                "Sennarth, the Cold Breath",
                "Dathea, Ascended",
                "Kurog Grimtotem",
                "Bloodkeeper Diurna",
                "Raszageth the Storm-Eater",
            ],
            "Aberrus, the Shadowed Crucible": [
                "Kazzara, the Hellforged",
                "The Amalgamation Chamber",
                "The Forgotten Experiments",
                "Assault of Zaqali",
                "Rashok, the Elder",
                "The Vigilant Steward, Zskarn",
                "Magmorax",
                "Echo of Neltharion",
                "Scalecommander Sarkareth",
            ],
            "Amirdrassil, the Dream's Hope": [
                "Gnarlroot",
                "Igira the Cruel",
                "Volcoross",
                "Council of Dreams",
                "Larodar, Keeper of the Flame",
                "Nymue, Weaver of the Cycle",
                "Smolderon",
                "Tindral Sageswift, Seer of the Flame",
                "Fyrakk the Blazing",
            ],
        },
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
            "OPERATION: FLOODGATE",
        ],
        "raids": {
            "Nerub-ar Palace": [
                "Ulgrax the Devourer",
                "The Bloodbound Horror",
                "Sikran, Captain of the Sureki",
                "Rasha'nan",
                "Broodtwister Ovi'nax",
                "Nexus-Princess Ky'veza",
                "The Silken Court",
                "Queen Ansurek",
            ],
            "Liberation of Undermine": [
                "Vexie and the Geargrinders",
                "Cauldron of Carnage",
                "Rik Reverb",
                "Stix Bunkjunker",
                "Sprocketmonger Lockenstock",
                "The One-Armed Bandit",
                "Mug'Zee, Heads of Security",
                "Chrome King Gallywix",
            ],
        },
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
            "The MOTHERLODE!!",
        ],
        "raids": {
            "Liberation of Undermine": [
                "Vexie and the Geargrinders",
                "Cauldron of Carnage",
                "Rik Reverb",
                "Stix Bunkjunker",
                "Sprocketmonger Lockenstock",
                "The One-Armed Bandit",
                "Mug'Zee, Heads of Security",
                "Chrome King Gallywix",
            ],
        },
    },
}

# ——————————————————————————————————————————————
# LOGGER SETUP
# ——————————————————————————————————————————————

logger = logging.getLogger("by_expansion")
logger.setLevel(logging.INFO)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

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
        desc = detail.get("description")

        media = fetch_media(
            f"/data/wow/media/journal-instance/{bid}", namespace, locale
        )
        img = next(
            (a["value"] for a in media.get("assets", []) if a["key"] == "tile"), None
        )

        encounters = []
        ec_id = 1
        for enc in detail.get("encounters", []):
            ebid = enc.get("id")
            enc_name = enc.get("name")
            if not ebid:
                continue
            edetail = blizz_get(
                f"/data/wow/journal-encounter/{ebid}", namespace, locale
            )
            enc_desc = edetail.get("description")

            creatures = []
            c_id = 1
            for c in edetail.get("creatures", []):
                cid = c.get("id")
                cname = c.get("name")
                if not cid:
                    continue
                disp = c["creature_display"]["id"]
                cmedia = fetch_media(
                    f"/data/wow/media/creature-display/{disp}", namespace, locale
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

        return {
            "kind": kind,
            "record": {
                "blizzard_id": bid,
                "name": name,
                "description": desc,
                "img": img,
                "encounters": encounters,
            },
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
            bid = entry.get("id")
            name = entry.get("name")
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
                pool.submit(process_instance, name, bid, kind, namespace, locale): (
                    name,
                    bid,
                )
                for name, bid, kind in to_process
            }
            for fut in as_completed(futures):
                res = fut.result()
                if not res:
                    continue
                kind = res["kind"]
                rec = res["record"]
                if kind == "dungeon":
                    rec["id"] = d_id
                    d_list.append(rec)
                    d_id += 1
                else:
                    rec["id"] = r_id
                    r_list.append(rec)
                    r_id += 1

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
