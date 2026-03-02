"""
aria2_client.py — Aria2c JSON-RPC client
-----------------------------------------
State machine:
  HTTP:    waiting → active → complete
  Torrent: waiting → active → complete (metadata) → followedBy → waiting → active → complete (data)

Key fixes:
  • active+100%: immediately return the file — no .aria2 check needed after aria2 confirms 100%
  • Stall detector: if speed==0 for 45s and >85% done, push aria2 to force-complete
  • Directory fallback: if aria2 reports a directory, walk it to find the largest file
"""

import aiohttp
import asyncio
import os
import time
from typing import Optional, Dict, List, Tuple, Any
from config import settings
RPC_URL = "http://localhost:6800/jsonrpc"
_RPC_ID = 0


async def aria2_rpc(method: str, params: list) -> Optional[Any]:
    """Send a JSON-RPC request to the aria2c RPC daemon.

    Returns the result field of the JSON-RPC response or ``None`` on failure.
    """
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


async def add_download(uri: str, download_dir: str) -> Optional[str]:
    """Add a URI / magnet to aria2c and return its GID, or ``None`` on failure.

    Args:
        uri: The download URL or magnet link.
        download_dir: Directory where aria2 should store the file.
    """
    options = {
        "dir": download_dir,
        "seed-time": "0",
        "continue": "true",
        "allow-overwrite": "true",
    }
    if uri.startswith(("http://", "https://", "ftp://", "magnet:")):
        return await aria2_rpc("aria2.addUri", [[uri], options])
    return None


async def _tell_status(gid: str) -> Optional[Dict[str, Any]]:
    """Retrieve status information for a given GID from aria2.

    Returns a dictionary with selected keys or ``None`` on RPC failure.
    """
    keys = [
        "status", "totalLength", "completedLength",
        "downloadSpeed", "errorMessage", "followedBy", "files",
    ]
    return await aria2_rpc("aria2.tellStatus", [gid, keys])


async def get_download_status(gid: str) -> Optional[Dict[str, Any]]:
    """Public wrapper to retrieve download status.

    Returns the same dictionary as ``_tell_status`` for external callers.
    """
    return await _tell_status(gid)



async def _force_remove(gid: str) -> None:
    """Force‑remove a download from aria2 (used after file confirmed on disk)."""
    try:
        await aria2_rpc("aria2.forceRemove", [gid])
    except Exception:
        pass


def _resolve_path(raw_path: str) -> Optional[str]:
    """Robustly resolve a file path reported by aria2.

    Checks absolute paths, paths relative to CWD, and paths relative to
    the configured DOWNLOAD_DIR.
    """
    if not raw_path:
        return None
        
    # 1. Try as-is (absolute or relative to current CWD)
    abs_p = os.path.abspath(raw_path)
    if os.path.exists(abs_p):
        return abs_p
    
    # 2. Try relative to DOWNLOAD_DIR
    # Strip common prefixes aria2 might have added if it's confused about CWD
    clean: str = raw_path.replace("\\", "/").lstrip("./")
    prefixes = ["downloads/", "DOWNLOADS/", settings.DOWNLOAD_DIR.lstrip("./").rstrip("/") + "/"]
    for p in prefixes:
        if clean.startswith(p):
            clean = clean[len(p):]
            break
    
    candidate = os.path.abspath(os.path.join(settings.DOWNLOAD_DIR, clean))
    if os.path.exists(candidate):
        return candidate
        
    # 3. Last ditch: check if just the basename exists in DOWNLOAD_DIR
    base_candidate = os.path.abspath(os.path.join(settings.DOWNLOAD_DIR, os.path.basename(raw_path)))
    if os.path.exists(base_candidate):
        return base_candidate
        
    return None


def _find_largest_file(files: List[Dict[str, Any]]) -> Optional[str]:
    """
    Given a list of aria2 file objects, return the path to the largest
    actual file on disk. Walks directories recursively.
    Returns None if nothing found.
    """
    largest_path = None
    max_size = 0

    for f in files:
        base = _resolve_path(f.get("path", ""))
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
) -> Tuple[bool, str]:
    """Monitor an aria2 download until it finishes or errors.

    Args:
        gid: The aria2 GID for the download.
        progress_callback: Callable to report progress updates.
        start_time: Timestamp when the download started.
        action: Description used in progress messages.

    Returns:
        Tuple[bool, str]: ``(True, filepath)`` on success or ``(False, error_message)`` on failure.
    """
    current_gid = gid
    last_ui_update = 0.0
    UI_INTERVAL = 3.0

    # Stall detection: track when speed last was non-zero
    last_progress_bytes = -1
    last_progress_time = time.time()
    STALL_TIMEOUT = 60  # seconds of zero-progress before we force-complete

    while True:
        info = await _tell_status(current_gid)

        if info is None:
            await asyncio.sleep(2)
            continue

        status    = info.get("status", "")
        total_len = int(info.get("totalLength",    0) or 0)
        completed = int(info.get("completedLength", 0) or 0)
        speed     = int(info.get("downloadSpeed",  0) or 0)

        # ── ERRORS ───────────────────────────────────────────────────────
        if status == "error":
            return False, info.get("errorMessage") or "Unknown aria2 error"

        if status == "removed":
            return False, "Download was cancelled."

        # ── COMPLETE STATUS ───────────────────────────────────────────────
        if status == "complete":
            followed_by = info.get("followedBy") or []
            if followed_by:
                # Torrent: metadata GID finished → switch to actual data GID
                print(f"[aria2] Metadata done. Switching to data GID: {followed_by[0]}")
                current_gid = followed_by[0]
                last_progress_bytes = -1
                last_progress_time = time.time()
                await asyncio.sleep(1)
                continue

            # Real download is 'complete' — find the file
            files = info.get("files") or []
            filepath = _find_largest_file(files)

            if not filepath and files:
                # Last resort: use the raw path aria2 gave us with robust resolution
                for f in files:
                    raw = f.get("path", "")
                    res = _resolve_path(raw)
                    if res:
                        filepath = res
                        break

            if not filepath or not os.path.exists(filepath):
                msg = f"Download completed but file not found on disk. (aria2 files: {files})"
                print(f"[aria2] {msg}")
                return False, msg

            return True, filepath

        # ── ACTIVE / WAITING ─────────────────────────────────────────────
        if status in ("active", "waiting"):

            # ── Case 1: aria2 says 100% received but still "active" ────────
            # This happens when: torrent seed-time not expired, or CDN final-byte stall
            # Fix: just grab the file if it physically exists — it IS done.
            if status == "active" and total_len > 0 and completed >= total_len:
                files = info.get("files") or []
                filepath = _find_largest_file(files)
                
                if not filepath and files:
                    for f in files:
                        res = _resolve_path(f.get("path", ""))
                        if res:
                            filepath = res
                            break

                if filepath and os.path.exists(filepath):
                    print(f"[aria2] 100% active → file confirmed on disk: {filepath}")
                    await _force_remove(current_gid)
                    return True, filepath

                # File not on disk yet → aria2 is still assembling pieces
                # Show 100% progress and wait
                await _update_ui(progress_callback, action,
                                 completed, total_len, start_time, 0, 0,
                                 last_ui_update, UI_INTERVAL)
                await asyncio.sleep(2)
                continue

            # ── Case 2: Stall detector (e.g. CDN throttles final 5%) ──────
            # If completed bytes haven't changed in STALL_TIMEOUT seconds,
            # force aria2 to re-try connections.
            if completed != last_progress_bytes:
                last_progress_bytes = completed
                last_progress_time = time.time()
            elif time.time() - last_progress_time > STALL_TIMEOUT:
                pct = (completed / total_len * 100) if total_len > 0 else 0
                if pct > 85:
                    print(f"[aria2] Stall detected at {pct:.1f}%. Forcing aria2 connection re-try.")
                    # Unpause to reset connections (works even if already active)
                    await aria2_rpc("aria2.unpause", [current_gid])
                    last_progress_time = time.time()  # reset stall timer

            # Normal in-progress UI update
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

    # Fallback: should never reach here, but ensure a return
    return False, "Download monitoring exited unexpectedly"


async def _update_ui(cb, action, completed, total, t0, speed, eta, last_t, interval):
    now = time.time()
    if cb and now - last_t >= interval:
        await cb(action, completed, total, t0, speed=speed, eta_seconds=eta)
        return now
    return last_t
