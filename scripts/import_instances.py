#!/usr/bin/env python3
"""
Import raid instance data from YAML files into the PostgreSQL database.

Run after generate_instances_yaml.py has produced the data/instances/ files.

Usage:
    python scripts/import_instances.py           # full wipe + reload
    python scripts/import_instances.py --dry-run # show what would be imported
"""
import argparse
import logging
import sys
from pathlib import Path

# Make sure lib/ is importable when running from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from lib.db import Session, engine
from lib.instances import seed_from_yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
logger = logging.getLogger("import_instances")

DATA_DIR = Path("data/instances")


def count_yaml_entries() -> dict:
    counts = {"expansions": 0, "raids": 0, "encounters": 0}
    for exp_dir in sorted(DATA_DIR.iterdir()):
        if not exp_dir.is_dir() or exp_dir.name == "Current Season":
            continue
        raids_file = exp_dir / "raids.yml"
        if not raids_file.exists():
            continue
        import yaml
        raids = yaml.safe_load(raids_file.read_text(encoding="utf-8")) or []
        if raids:
            counts["expansions"] += 1
            counts["raids"] += len(raids)
            counts["encounters"] += sum(len(r.get("encounters", [])) for r in raids)
    return counts


def main():
    parser = argparse.ArgumentParser(
        description="Import WoW raid instance YAML data into the database."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be imported without writing to the database.",
    )
    args = parser.parse_args()

    if not DATA_DIR.exists():
        logger.error("data/instances/ directory not found. Run generate_instances_yaml.py first.")
        sys.exit(1)

    counts = count_yaml_entries()
    logger.info(
        "Found %d expansions, %d raids, %d encounters in YAML files.",
        counts["expansions"],
        counts["raids"],
        counts["encounters"],
    )

    if args.dry_run:
        logger.info("Dry run — no changes written.")
        return

    logger.info("Wiping existing instance data and reloading from YAML...")
    with Session(engine) as session:
        result = seed_from_yaml(session)

    logger.info(
        "Done. Imported %d instances and %d encounters.",
        result["instances"],
        result["encounters"],
    )


if __name__ == "__main__":
    main()
