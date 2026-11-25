"""Free permanent cloud persistence for SmartStudy AI via Private GitHub Repo Sync (REST API).

When deployed on an ephemeral host (such as Streamlit Community Cloud), setting
`GITHUB_TOKEN` and `GITHUB_DATA_REPO` (e.g. `username/smartstudy-data`) in Secrets
causes `smartstudy.db` (including `file_blobs` for uploaded PDFs/certificates) to be
pulled automatically on startup and pushed automatically after any database write.
"""

from __future__ import annotations

import base64
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

_PULLED_THIS_PROCESS = False
_LAST_SYNC_STATUS: dict[str, Any] = {
    "mode": "Local Disk",
    "last_sync": None,
    "last_error": None,
}


def _get_secret(key: str, default: str = "") -> str:
    val = os.getenv(key, "").strip()
    if val:
        return val
    try:
        import streamlit as st

        sval = st.secrets.get(key, "")
        return str(sval).strip() if sval else default
    except Exception:
        return default


def is_configured() -> bool:
    return bool(_get_secret("GITHUB_TOKEN") and _get_secret("GITHUB_DATA_REPO"))


def _config() -> tuple[str, str, str, str]:
    token = _get_secret("GITHUB_TOKEN")
    repo = _get_secret("GITHUB_DATA_REPO")
    branch = _get_secret("GITHUB_DATA_BRANCH", "main") or "main"
    remote_path = _get_secret("GITHUB_DATA_PATH", "smartstudy.db") or "smartstudy.db"
    return token, repo, branch, remote_path


def get_sync_status() -> dict[str, Any]:
    status = dict(_LAST_SYNC_STATUS)
    if is_configured():
        _, repo, branch, remote_path = _config()
        status["mode"] = f"☁️ GitHub Cloud Sync ({repo}@{branch}:{remote_path})"
    elif _get_secret("SMARTSTUDY_DB_PATH"):
        status["mode"] = f"💾 Persistent Volume ({_get_secret('SMARTSTUDY_DB_PATH')})"
    else:
        status["mode"] = "💻 Local SQLite Disk"
    return status


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def pull_db_on_startup(db_path: Path, force: bool = False) -> bool:
    """Pull `smartstudy.db` from the configured GitHub repo once on cold start (or when forced)."""
    global _PULLED_THIS_PROCESS
    if not is_configured():
        return False
    if _PULLED_THIS_PROCESS and not force:
        return False
    _PULLED_THIS_PROCESS = True

    # If local DB already exists and this is an automatic cold-start check, do not overwrite local edits
    if db_path.exists() and not force:
        return False

    token, repo, branch, remote_path = _config()
    url = f"https://api.github.com/repos/{repo}/contents/{remote_path}"
    try:
        resp = requests.get(url, headers=_headers(token), params={"ref": branch}, timeout=15)
        if resp.status_code == 404:
            _LAST_SYNC_STATUS["last_error"] = None
            return False
        resp.raise_for_status()
        payload = resp.json()
        raw_bytes: bytes | None = None
        if payload.get("content"):
            raw_bytes = base64.b64decode(payload["content"])
        elif payload.get("download_url"):
            dl = requests.get(payload["download_url"], headers=_headers(token), timeout=20)
            dl.raise_for_status()
            raw_bytes = dl.content
        if raw_bytes and raw_bytes.startswith(b"SQLite format 3"):
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_path.write_bytes(raw_bytes)
            _LAST_SYNC_STATUS["last_sync"] = f"Pulled {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            _LAST_SYNC_STATUS["last_error"] = None
            return True
        return False
    except Exception as exc:
        _LAST_SYNC_STATUS["last_error"] = str(exc)
        return False


def push_db(db_path: Path) -> bool:
    """Push `smartstudy.db` snapshot to the configured private GitHub repo."""
    if not is_configured() or not db_path.exists():
        return False

    token, repo, branch, remote_path = _config()
    url = f"https://api.github.com/repos/{repo}/contents/{remote_path}"
    try:
        sha = None
        get_resp = requests.get(url, headers=_headers(token), params={"ref": branch}, timeout=12)
        if get_resp.status_code == 200:
            sha = get_resp.json().get("sha")

        b64 = base64.b64encode(db_path.read_bytes()).decode("ascii")
        body: dict[str, Any] = {
            "message": f"SmartStudy AI auto-sync ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})",
            "content": b64,
            "branch": branch,
        }
        if sha:
            body["sha"] = sha

        put_resp = requests.put(url, headers=_headers(token), json=body, timeout=25)
        put_resp.raise_for_status()
        _LAST_SYNC_STATUS["last_sync"] = f"Pushed {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        _LAST_SYNC_STATUS["last_error"] = None
        return True
    except Exception as exc:
        _LAST_SYNC_STATUS["last_error"] = str(exc)
        return False
