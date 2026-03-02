"""
aria2_client.py — Aria2c JSON-RPC client
-----------------------------------------
State machine:
  HTTP:    waiting → active → complete
  Torrent: waiting → active → complete (metadata) → followedBy → waiting → active → complete (data)

Features:
  • Robust file path resolution with multiple fallback strategies
  • Stall detection and auto-recovery
  • Support for both single files and torrent directories
  • Proper error handling and cleanup
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
    """
    Send a JSON-RPC request to the aria2c daemon.
    
    Args:
        method: RPC method name
        params: Method parameters
        
    Returns:
        Result field of response or None on failure
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
                RPC_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                result = await resp.json()
                
                if "error" in result:
                    error_msg = result["error"].get("message", "Unknown error")
                    raise Exception(f"RPC Error: {error_msg}")
                    
                return result.get("result")
                
    except asyncio.TimeoutError:
        print(f"[aria2 RPC] {method} timed out")
        return None
    except Exception as exc:
        print(f"[aria2 RPC] {method} failed: {exc}")
        return None


async def add_download(uri: str, download_dir: str) -> Optional[str]:
    """
    Add a URI or magnet to aria2c and return its GID.
    
    Args:
        uri: Download URL or magnet link
        download_dir: Directory for downloads
        
    Returns:
        GID string or None on failure
    """
    options = {
        "dir": download_dir,
        "seed-time": "0",
        "continue": "true",
        "allow-overwrite": "true",
        "max-file-not-found": "5",
        "max-tries": "10",
        "retry-wait": "5",
    }
    
    if uri.startswith(("http://", "https://", "ftp://", "magnet:")):
        gid = await aria2_rpc("aria2.addUri", [[uri], options])
        if gid:
            print(f"[aria2] Added download with GID: {gid}")
        return gid
    
    print(f"[aria2] Unsupported URI scheme: {uri[:50]}...")
    return None


async def _tell_status(gid: str) -> Optional[Dict[str, Any]]:
    """Get status for a GID."""
    keys = [
        "status", "totalLength", "completedLength",
        "downloadSpeed", "errorMessage", "followedBy", "files",
        "dir", "connections", "numSeeders"
    ]
    return await aria2_rpc("aria2.tellStatus", [gid, keys])


async def get_download_status(gid: str) -> Optional[Dict[str, Any]]:
    """Public wrapper for getting download status."""
    return await _tell_status(gid)


async def _force_remove(gid: str) -> None:
    """Force remove a download from aria2."""
    try:
        await aria2_rpc("aria2.forceRemove", [gid])
    except Exception:
        pass


def _resolve_path(raw_path: str) -> Optional[str]:
    """
    Resolve a file path reported by aria2 with multiple strategies.
    
    Args:
        raw_path: Path from aria2
        
    Returns:
        Absolute path if file exists, None otherwise
    """
    if not raw_path:
        return None
    
    # Strategy 1: Try as-is (absolute or relative to CWD)
    abs_p = os.path.abspath(raw_path)
    if os.path.exists(abs_p):
        return abs_p
    
    # Strategy 2: Clean path and try relative to DOWNLOAD_DIR
    clean = raw_path.replace("\\", "/").lstrip("./")
    
    # Remove common prefixes
    prefixes = [
        "downloads/",
        "DOWNLOADS/",
        settings.DOWNLOAD_DIR.lstrip("./").rstrip("/") + "/"
    ]
    for p in prefixes:
        if clean.startswith(p):
            clean = clean[len(p):]
            break
    
    candidate = os.path.abspath(os.path.join(settings.DOWNLOAD_DIR, clean))
    if os.path.exists(candidate):
        return candidate
    
    # Strategy 3: Check if basename exists in DOWNLOAD_DIR
    base_candidate = os.path.abspath(os.path.join(settings.DOWNLOAD_DIR, os.path.basename(raw_path)))
    if os.path.exists(base_candidate):
        return base_candidate
    
    return None


def _find_largest_file(files: List[Dict[str, Any]]) -> Optional[str]:
    """
    Find the largest file from aria2's file list.
    
    Args:
        files: List of file objects from aria2
        
    Returns:
        Path to largest file or None
    """
    largest_path = None
    max_size = 0

    for f in files:
        base = _resolve_path(f.get("path", ""))
        if not base:
            continue

        if os.path.isdir(base):
            # Walk directory for torrents
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
    """
    Monitor an aria2 download until completion or error.
    
    Args:
        gid: The aria2 GID
        progress_callback: Async callback for progress updates
        start_time: Download start timestamp
        action: Action name for progress messages
        
    Returns:
        Tuple of (success: bool, result: filepath_or_error)
    """
    current_gid = gid
    last_ui_update = 0.0
    UI_INTERVAL = 2.0

    # Stall detection
    last_progress_bytes = -1
    last_progress_time = time.time()
    STALL_TIMEOUT = 60  # seconds
    stall_retries = 0
    MAX_STALL_RETRIES = 3

    print(f"[aria2] Monitoring GID: {gid}")

    while True:
        info = await _tell_status(current_gid)

        if info is None:
            await asyncio.sleep(2)
            continue

        status = info.get("status", "")
        total_len = int(info.get("totalLength", 0) or 0)
        completed = int(info.get("completedLength", 0) or 0)
        speed = int(info.get("downloadSpeed", 0) or 0)

        # Handle errors
        if status == "error":
            error_msg = info.get("errorMessage") or "Unknown aria2 error"
            print(f"[aria2] Download error: {error_msg}")
            return False, error_msg

        if status == "removed":
            print("[aria2] Download was removed")
            return False, "Download was cancelled"

        # Handle completion
        if status == "complete":
            followed_by = info.get("followedBy") or []
            if followed_by:
                # Torrent: metadata complete, switch to data GID
                print(f"[aria2] Metadata complete, switching to: {followed_by[0]}")
                current_gid = followed_by[0]
                last_progress_bytes = -1
                last_progress_time = time.time()
                await asyncio.sleep(1)
                continue

            # Real completion - find the file
            files = info.get("files") or []
            filepath = _find_largest_file(files)

            if not filepath and files:
                # Last resort: try raw paths
                for f in files:
                    raw = f.get("path", "")
                    res = _resolve_path(raw)
                    if res:
                        filepath = res
                        break

            if not filepath or not os.path.exists(filepath):
                msg = f"Download complete but file not found. Files: {files}"
                print(f"[aria2] {msg}")
                return False, msg

            print(f"[aria2] Download complete: {filepath}")
            return True, filepath

        # Handle active/waiting states
        if status in ("active", "waiting"):
            # Case 1: 100% complete but still active (seeding/assembly)
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
                    print(f"[aria2] 100% active, file confirmed: {filepath}")
                    await _force_remove(current_gid)
                    return True, filepath

                # Still assembling - show 100% and wait
                await _update_ui(
                    progress_callback, action,
                    completed, total_len, start_time, 0, 0,
                    last_ui_update, UI_INTERVAL
                )
                await asyncio.sleep(2)
                continue

            # Case 2: Stall detection
            if completed != last_progress_bytes:
                last_progress_bytes = completed
                last_progress_time = time.time()
                stall_retries = 0
            elif time.time() - last_progress_time > STALL_TIMEOUT:
                pct = (completed / total_len * 100) if total_len > 0 else 0
                if pct > 85 and stall_retries < MAX_STALL_RETRIES:
                    stall_retries += 1
                    print(f"[aria2] Stall at {pct:.1f}%, retry {stall_retries}/{MAX_STALL_RETRIES}")
                    await aria2_rpc("aria2.unpause", [current_gid])
                    last_progress_time = time.time()

            # Normal progress update
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

        await asyncio.sleep(1)


async def _update_ui(cb, action, completed, total, t0, speed, eta, last_t, interval):
    """Update UI with throttling."""
    now = time.time()
    if cb and now - last_t >= interval:
        await cb(action, completed, total, t0, speed=speed, eta_seconds=eta)
        return now
    return last_t
