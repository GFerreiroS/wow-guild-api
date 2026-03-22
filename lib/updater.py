import logging
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

GITHUB_REPO = os.getenv("GITHUB_REPO", "GFerreiroS/wow-guild-api")
VERSION_FILE = Path(__file__).parent.parent / "VERSION"


def _parse_version(v: str) -> tuple:
    return tuple(int(x) for x in v.strip().lstrip("v").split("."))


def get_local_version() -> str:
    return VERSION_FILE.read_text().strip()


def get_latest_release() -> dict:
    resp = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
        headers={"Accept": "application/vnd.github+json"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def check_for_updates() -> dict:
    local = get_local_version()
    release = get_latest_release()
    latest_tag = release["tag_name"].lstrip("v")
    update_available = _parse_version(latest_tag) > _parse_version(local)
    return {
        "current_version": local,
        "latest_version": latest_tag,
        "update_available": update_available,
        "release_url": release.get("html_url"),
        "release_notes": release.get("body"),
    }


def apply_update(game_mode: str) -> dict:
    repo_root = Path(__file__).parent.parent

    result = subprocess.run(
        ["git", "pull"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git pull failed: {result.stderr}")

    new_version = get_local_version()

    if game_mode.lower() == "retail":
        regen = subprocess.run(
            [sys.executable, "scripts/generate_instances_yaml.py"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if regen.returncode != 0:
            logger.warning("Instance regeneration failed: %s", regen.stderr)
        else:
            logger.info("Instances regenerated successfully.")

    logger.info("Update applied to %s. Restarting in 1 second...", new_version)
    threading.Timer(1.0, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()

    return {"updated_to": new_version, "restarting": True}
