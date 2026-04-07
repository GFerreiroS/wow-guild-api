from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml
from sqlalchemy import delete
from sqlmodel import Session, select

from lib.db import Encounter, Expansion, Instance

logger = logging.getLogger(__name__)

DATA_DIR = Path("data/instances")
CURRENT_SEASON_DIR = DATA_DIR / "Current Season"


# ---------------------------------------------------------------------------
# Internal helpers
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


def get_instance(session: Session, blizzard_id: int) -> Optional[dict]:
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


def is_db_empty(session: Session) -> bool:
    return session.exec(select(Instance)).first() is None


def seed_from_data(
    session: Session,
    raids: dict,  # exp_name -> {inst_id -> raid_rec}
    current_season_raid_ids: set[int],
) -> dict:
    """Wipe instance tables and reload from in-memory raid data."""
    session.execute(delete(Encounter))
    session.execute(delete(Instance))
    session.execute(delete(Expansion))
    session.commit()

    total_instances = 0
    total_encounters = 0

    for exp_name, instances_map in raids.items():
        if exp_name == "Current Season" or not instances_map:
            continue
        expansion = Expansion(name=exp_name)
        session.add(expansion)
        session.commit()
        session.refresh(expansion)

        for sort_idx, raid_rec in enumerate(instances_map.values()):
            inst = Instance(
                blizzard_id=raid_rec["blizzard-id"],
                expansion_id=expansion.id,
                name=raid_rec.get("name", ""),
                description=raid_rec.get("description"),
                img=raid_rec.get("img"),
                instance_type="raid",
                is_current_season=raid_rec["blizzard-id"] in current_season_raid_ids,
                sort_order=sort_idx,
            )
            session.add(inst)
            session.commit()
            session.refresh(inst)
            total_instances += 1

            for enc_idx, enc in enumerate(raid_rec.get("encounters", [])):
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


def seed_from_yaml(session: Session) -> dict:
    """Wipe instance tables and reload from YAML archive files.

    Returns empty result silently if the data directory doesn't exist yet
    (fresh install before POST /admin/instances/seed has run).
    """
    if not DATA_DIR.exists():
        return {"instances": 0, "encounters": 0}

    current_ids = _current_season_ids()

    raids: dict = {}
    for exp_dir in sorted(DATA_DIR.iterdir()):
        if not exp_dir.is_dir() or exp_dir.name == "Current Season":
            continue
        instances_map = {}
        for entry in _load_yaml(exp_dir / "raids.yml"):
            bid = entry.get("blizzard-id")
            if bid:
                instances_map[bid] = entry
        if instances_map:
            raids[exp_dir.name] = instances_map

    return seed_from_data(session, raids, current_ids)
