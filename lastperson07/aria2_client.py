"""
aria2_client.py — Aria2c JSON-RPC client
-----------------------------------------
Correct state machine:
  1. addUri → get GID
  2. If the GID reaches `complete` and has `followedBy`, switch to followedBy GID
     (this is the torrent case: first GID = metadata download, followedBy = actual data)
  3. Poll the real data GID until status == 'complete'
     OR status == 'active' AND completed == total (CDN stall fallback)
  4. Walk files list recursively to find the largest actual file on disk
"""

import aiohttp
import asyncio
import os
import time

RPC_URL = "http://localhost:6800/jsonrpc"
_RPC_ID = 0

async def aria2_rpc(method: str, params: list):
    """Send a JSON-RPC request to the aria2c RPC daemon."""
    global _RPC_ID
    _RPC_ID += 1
    payload = {
        "jsonrpc": "2.0",
        "id": str(_RPC_ID),
        "method": method,
        "params": params,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                RPC_URL, json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                result = await resp.json()
                if "error" in result:
                    raise Exception(result["error"]["message"])
                return result.get("result")
    except Exception as exc:
        print(f"[aria2 RPC] {method} failed: {exc}")
        return None


async def add_download(uri: str, download_dir: str) -> str | None:
    """Add a URI / magnet to aria2c and return its GID, or None on failure."""
    options = {
        "dir": download_dir,
        "seed-time": "0",
        "continue": "true",
        "allow-overwrite": "true",
    }
    if uri.startswith(("http://", "https://", "ftp://", "magnet:")):
        return await aria2_rpc("aria2.addUri", [[uri], options])
    return None


async def _tell_status(gid: str) -> dict | None:
    keys = [
        "status", "totalLength", "completedLength",
        "downloadSpeed", "errorMessage", "followedBy", "files",
    ]
    return await aria2_rpc("aria2.tellStatus", [gid, keys])


def _find_largest_file(files: list) -> str | None:
    """
    Given a list of aria2 file objects, return the path to the largest
    actual file on disk.  Walks directories recursively.
    """
    largest_path = None
    max_size = 0

    for f in files:
        base = f.get("path", "")
        if not base:
            continue

        if os.path.isdir(base):
            # Torrent folder — walk every file inside
            for root, _dirs, filenames in os.walk(base):
                for fname in filenames:
                    full = os.path.join(root, fname)
                    try:
                        sz = os.path.getsize(full)
                        if sz > max_size:
                            max_size = sz
                            largest_path = full
                    except OSError:
                        pass
        elif os.path.isfile(base):
            try:
                sz = os.path.getsize(base)
                if sz > max_size:
                    max_size = sz
                    largest_path = base
            except OSError:
                pass

    return largest_path


async def monitor_download(
    gid: str,
    progress_callback,
    start_time: float,
    action: str = "Downloading",
):
    """
    Monitor an aria2 download until it finishes or errors.
    Returns (True, filepath) on success, (False, error_msg) on failure.

    State machine:
      waiting → active → complete  (HTTP / direct link)
      waiting → active → complete → [followedBy] waiting → active → complete  (Torrent)
    """
    current_gid = gid
    last_ui_update = 0.0
    UI_INTERVAL = 3.0          # min seconds between Telegram edits

    while True:
        info = await _tell_status(current_gid)

        if info is None:
            # daemon not reachable yet, wait a moment
            await asyncio.sleep(2)
            continue

        status       = info.get("status", "")
        total_len    = int(info.get("totalLength", 0) or 0)
        completed    = int(info.get("completedLength", 0) or 0)
        speed        = int(info.get("downloadSpeed", 0) or 0)

        # ── ERROR / CANCELLED ────────────────────────────────────────────
        if status == "error":
            return False, info.get("errorMessage") or "Unknown aria2 error"

        if status == "removed":
            return False, "Download was cancelled."

        # ── COMPLETE ─────────────────────────────────────────────────────
        if status == "complete":
            followed_by = info.get("followedBy") or []
            if followed_by:
                # This was a torrent metadata download.
                # Switch to the actual data GID and keep looping.
                print(f"[aria2] Torrent metadata done. Switching to data GID: {followed_by[0]}")
                current_gid = followed_by[0]
                await asyncio.sleep(1)
                continue

            # Real download finished — find the largest file
            files = info.get("files") or []
            filepath = _find_largest_file(files)

            if not filepath:
                # Fallback: use first path as-is (may be a directory name)
                if files:
                    fallback = files[0].get("path", "")
                    if fallback and os.path.exists(fallback):
                        filepath = fallback

            if not filepath or not os.path.exists(filepath):
                return False, f"Download completed but file not found on disk. (aria2 files: {files})"

            return True, filepath

        # ── ACTIVE ───────────────────────────────────────────────────────
        if status in ("active", "waiting"):
            # CDN stall fallback: if 100 % bytes received but still active,
            # wait until the .aria2 temp file disappears (piece assembly done)
            if status == "active" and total_len > 0 and completed >= total_len:
                files = info.get("files") or []
                filepath = _find_largest_file(files)

                aria2_tmp = (filepath + ".aria2") if filepath else None
                if aria2_tmp and os.path.exists(aria2_tmp):
                    # Still being assembled, push a 100 % UI tick and wait
                    await _maybe_update_ui(
                        progress_callback, action,
                        completed, total_len, start_time, speed, 0,
                        last_ui_update, UI_INTERVAL,
                    )
                    await asyncio.sleep(2)
                    continue
                else:
                    # Assembly done or no .aria2 file; treat as finished
                    if filepath and os.path.exists(filepath):
                        print(f"[aria2] CDN stall resolved. File ready: {filepath}")
                        return True, filepath

            # Normal in-progress update
            now = time.time()
            if now - last_ui_update >= UI_INTERVAL:
                eta = (
                    int((total_len - completed) / speed)
                    if speed > 0 and total_len > completed
                    else 0
                )
                await progress_callback(
                    action, completed, total_len, start_time,
                    speed=speed, eta_seconds=eta,
                )
                last_ui_update = now

        await asyncio.sleep(2)


async def _maybe_update_ui(cb, action, completed, total, t0, speed, eta, last_t, interval):
    now = time.time()
    if now - last_t >= interval and cb:
        await cb(action, completed, total, t0, speed=speed, eta_seconds=eta)
        return now
    return last_t
