import logging
import os
from pathlib import Path
from typing import Optional

import yaml
from sqlalchemy import delete
from sqlmodel import Session, select

from lib.db import Encounter, Expansion, Instance

logger = logging.getLogger(__name__)

DATA_DIR = Path("data/instances")
CURRENT_SEASON_DIR = DATA_DIR / "Current Season"


def _backend() -> str:
    return os.getenv("INSTANCE_BACKEND", "yaml").lower()


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> list:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def _current_season_ids() -> set[int]:
    return {
        entry["blizzard-id"]
        for entry in _load_yaml(CURRENT_SEASON_DIR / "raids.yml")
        if entry.get("blizzard-id")
    }


def _parse_yaml_entry(entry: dict, exp_name: str, itype: str, current_ids: set[int]) -> dict:
    return {
        "blizzard_id": entry.get("blizzard-id"),
        "expansion": exp_name,
        "name": entry.get("name"),
        "description": entry.get("description"),
        "img": entry.get("img"),
        "instance_type": itype,
        "is_current_season": entry.get("blizzard-id") in current_ids,
        "encounters": [
            {
                "blizzard_id": e.get("blizzard-id"),
                "name": e.get("name"),
                "description": e.get("description"),
                "creature_display_id": e.get("creature_display_id"),
                "img": e.get("img"),
                "sort_order": e.get("id", idx),
            }
            for idx, e in enumerate(entry.get("encounters", []))
        ],
    }


def _iter_yaml(
    expansion: Optional[str],
    instance_type: Optional[str],
    current_season: bool,
) -> list[dict]:
    current_ids = _current_season_ids()
    exp_names = (
        [expansion]
        if expansion
        else sorted(
            d.name for d in DATA_DIR.iterdir()
            if d.is_dir() and d.name != "Current Season"
        )
    )
    results = []
    for exp_name in exp_names:
        exp_dir = DATA_DIR / exp_name
        if not exp_dir.exists():
            continue
        type_files = []
        if not instance_type or instance_type == "raid":
            type_files.append(("raid", exp_dir / "raids.yml"))
        for itype, path in type_files:
            for entry in _load_yaml(path):
                parsed = _parse_yaml_entry(entry, exp_name, itype, current_ids)
                if current_season and not parsed["is_current_season"]:
                    continue
                results.append(parsed)
    return results


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _row_to_dict(inst: Instance, exp_name: str, encounters: list[Encounter]) -> dict:
    return {
        "blizzard_id": inst.blizzard_id,
        "expansion": exp_name,
        "name": inst.name,
        "description": inst.description,
        "img": inst.img,
        "instance_type": inst.instance_type,
        "is_current_season": inst.is_current_season,
        "encounters": [
            {
                "blizzard_id": e.blizzard_id,
                "name": e.name,
                "description": e.description,
                "creature_display_id": e.creature_display_id,
                "img": e.img,
                "sort_order": e.sort_order,
            }
            for e in sorted(encounters, key=lambda x: x.sort_order)
        ],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_instances(
    session: Session,
    expansion: Optional[str] = None,
    instance_type: Optional[str] = None,
    current_season: bool = False,
    include_encounters: bool = False,
) -> list[dict]:
    if _backend() == "db":
        query = select(Instance, Expansion).join(Expansion)
        if expansion:
            query = query.where(Expansion.name == expansion)
        if instance_type:
            query = query.where(Instance.instance_type == instance_type)
        if current_season:
            query = query.where(Instance.is_current_season == True)  # noqa: E712
        query = query.order_by(Expansion.name, Instance.sort_order)
        results = []
        for inst, exp in session.exec(query):
            encs = []
            if include_encounters:
                encs = list(session.exec(
                    select(Encounter)
                    .where(Encounter.instance_id == inst.id)
                    .order_by(Encounter.sort_order)
                ).all())
            d = _row_to_dict(inst, exp.name, encs)
            if not include_encounters:
                d.pop("encounters")
            results.append(d)
        return results

    results = _iter_yaml(expansion, instance_type, current_season)
    if not include_encounters:
        for r in results:
            r.pop("encounters", None)
    return results


def get_instance(session: Session, blizzard_id: int) -> Optional[dict]:
    if _backend() == "db":
        row = session.exec(
            select(Instance, Expansion)
            .join(Expansion)
            .where(Instance.blizzard_id == blizzard_id)
        ).first()
        if not row:
            return None
        inst, exp = row
        encs = list(session.exec(
            select(Encounter)
            .where(Encounter.instance_id == inst.id)
            .order_by(Encounter.sort_order)
        ).all())
        return _row_to_dict(inst, exp.name, encs)

    for inst in _iter_yaml(None, None, False):
        if inst["blizzard_id"] == blizzard_id:
            return inst
    return None


def is_db_empty(session: Session) -> bool:
    return session.exec(select(Instance)).first() is None


def seed_from_yaml(session: Session) -> dict:
    """Wipe instance tables and reload from YAML files."""
    session.execute(delete(Encounter))
    session.execute(delete(Instance))
    session.execute(delete(Expansion))
    session.commit()

    current_ids = _current_season_ids()
    total_instances = 0
    total_encounters = 0

    for exp_dir in sorted(DATA_DIR.iterdir()):
        if not exp_dir.is_dir() or exp_dir.name == "Current Season":
            continue
        expansion = Expansion(name=exp_dir.name)
        session.add(expansion)
        session.commit()
        session.refresh(expansion)

        for sort_idx, entry in enumerate(_load_yaml(exp_dir / "raids.yml")):
                inst = Instance(
                    blizzard_id=entry.get("blizzard-id"),
                    expansion_id=expansion.id,
                    name=entry.get("name", ""),
                    description=entry.get("description"),
                    img=entry.get("img"),
                    instance_type="raid",
                    is_current_season=entry.get("blizzard-id") in current_ids,
                    sort_order=sort_idx,
                )
                session.add(inst)
                session.commit()
                session.refresh(inst)
                total_instances += 1

                for enc_idx, enc in enumerate(entry.get("encounters", [])):
                    session.add(Encounter(
                        blizzard_id=enc.get("blizzard-id"),
                        instance_id=inst.id,
                        name=enc.get("name", ""),
                        description=enc.get("description"),
                        creature_display_id=enc.get("creature_display_id"),
                        img=enc.get("img"),
                        sort_order=enc_idx,
                    ))
                    total_encounters += 1
                session.commit()

    logger.info("Seeded %d instances and %d encounters.", total_instances, total_encounters)
    return {"instances": total_instances, "encounters": total_encounters}
