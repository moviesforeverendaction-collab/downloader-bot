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
  • Absolute path handling for container environments (Render, Heroku)
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
        uri: Download URL, magnet link, or file:// path for local torrent files
        download_dir: Directory for downloads (will be converted to absolute path)
        
    Returns:
        GID string or None on failure
    """
    # Always use absolute path for aria2
    abs_download_dir = os.path.abspath(download_dir)
    os.makedirs(abs_download_dir, exist_ok=True)
    
    options = {
        "dir": abs_download_dir,
        "seed-time": "0",
        "continue": "true",
        "allow-overwrite": "true",
        "max-file-not-found": "5",
        "max-tries": "10",
        "retry-wait": "5",
    }
    
    print(f"[aria2] Adding download to dir: {abs_download_dir}")
    
    if uri.startswith(("http://", "https://", "ftp://", "magnet:")):
        gid = await aria2_rpc("aria2.addUri", [[uri], options])
        if gid:
            print(f"[aria2] Added download with GID: {gid}")
        return gid
    
    # Handle local torrent files via file:// URL
    if uri.startswith("file://"):
        torrent_path = uri[7:]  # Remove 'file://' prefix
        if os.path.exists(torrent_path):
            # For torrent files, we need to read and add via aria2.addTorrent
            try:
                with open(torrent_path, 'rb') as f:
                    torrent_data = f.read()
                
                # Convert to base64 for JSON-RPC
                import base64
                torrent_base64 = base64.b64encode(torrent_data).decode('utf-8')
                
                gid = await aria2_rpc("aria2.addTorrent", [torrent_base64, [], options])
                if gid:
                    print(f"[aria2] Added torrent with GID: {gid}")
                return gid
            except Exception as e:
                print(f"[aria2] Failed to add torrent file: {e}")
                return None
        else:
            print(f"[aria2] Torrent file not found: {torrent_path}")
            return None
    
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


def _resolve_path(raw_path: str, aria2_dir: Optional[str] = None) -> Optional[str]:
    """
    Resolve a file path reported by aria2 with multiple strategies.

    Args:
        raw_path: Path from aria2
        aria2_dir: The download directory aria2 actually used (from status['dir'])

    Returns:
        Absolute path if file exists, None otherwise
    """
    if not raw_path:
        return None
    
    print(f"[aria2] Resolving path: {raw_path[:100]}...")

    # Strategy 0: If raw_path is absolute and exists, use it directly
    if os.path.isabs(raw_path) and os.path.exists(raw_path):
        print(f"[aria2] Found via absolute path: {raw_path}")
        return raw_path

    # Strategy 1: Try as-is with abspath (handles relative to CWD)
    abs_p = os.path.abspath(raw_path)
    if os.path.exists(abs_p):
        print(f"[aria2] Found via abspath: {abs_p}")
        return abs_p

    # Strategy 2: Use aria2's reported directory
    if aria2_dir:
        aria2_dir_abs = os.path.abspath(aria2_dir)
        
        # Try the basename in aria2_dir
        basename = os.path.basename(raw_path)
        candidate = os.path.join(aria2_dir_abs, basename)
        if os.path.exists(candidate):
            print(f"[aria2] Found via basename in aria2_dir: {candidate}")
            return candidate
        
        # Try raw_path relative to aria2_dir (handles ./ prefix)
        if raw_path.startswith("./") or raw_path.startswith("../") or not raw_path.startswith("/"):
            candidate = os.path.abspath(os.path.join(aria2_dir_abs, raw_path))
            if os.path.exists(candidate):
                print(f"[aria2] Found via relative to aria2_dir: {candidate}")
                return candidate

    # Strategy 3: Use settings.DOWNLOAD_DIR (already absolute)
    download_dir = os.path.abspath(settings.DOWNLOAD_DIR)
    
    # Clean path - remove ./ and ../ prefixes
    clean = raw_path.replace("\\", "/").lstrip("./")
    
    # Remove common prefixes
    prefixes = [
        "downloads/",
        "DOWNLOADS/",
    ]
    for p in prefixes:
        if clean.lower().startswith(p.lower()):
            clean = clean[len(p):]
            break
    
    candidate = os.path.join(download_dir, clean)
    if os.path.exists(candidate):
        print(f"[aria2] Found via clean path in download_dir: {candidate}")
        return candidate

    # Strategy 4: Check basename in download_dir
    basename = os.path.basename(raw_path)
    base_candidate = os.path.join(download_dir, basename)
    if os.path.exists(base_candidate):
        print(f"[aria2] Found via basename in download_dir: {base_candidate}")
        return base_candidate

    # Strategy 5: Search for file by basename in download_dir (handles encoding issues)
    try:
        for entry in os.listdir(download_dir):
            if entry == basename:
                full_path = os.path.join(download_dir, entry)
                if os.path.exists(full_path):
                    print(f"[aria2] Found via search in download_dir: {full_path}")
                    return full_path
    except (OSError, IOError) as e:
        print(f"[aria2] Error listing download_dir: {e}")

    print(f"[aria2] Path not found: {raw_path}")
    return None


def _find_largest_file(files: List[Dict[str, Any]], aria2_dir: Optional[str] = None) -> Optional[str]:
    """
    Find the largest file from aria2's file list.

    Args:
        files: List of file objects from aria2
        aria2_dir: The download directory aria2 actually used (from status['dir'])

    Returns:
        Path to largest file or None
    """
    largest_path = None
    max_size = 0

    for f in files:
        base = _resolve_path(f.get("path", ""), aria2_dir)
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


def _search_largest_file_in_dir(directory: str, min_size: int = 0) -> Optional[str]:
    """
    Search for the largest file in a directory recursively.
    
    Args:
        directory: Directory to search in
        min_size: Minimum file size to consider
        
    Returns:
        Path to largest file or None
    """
    largest_path = None
    max_size = min_size
    
    try:
        for root, _dirs, filenames in os.walk(directory):
            for fname in filenames:
                full = os.path.join(root, fname)
                try:
                    sz = os.path.getsize(full)
                    if sz > max_size:
                        max_size = sz
                        largest_path = full
                except OSError:
                    pass
    except OSError as e:
        print(f"[aria2] Error searching directory: {e}")
    
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
    
    # Track expected file size for fallback search
    expected_size = 0

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
        
        # Track expected size for fallback
        if total_len > 0:
            expected_size = total_len

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
            aria2_dir = info.get("dir")
            filepath = _find_largest_file(files, aria2_dir)

            if not filepath and files:
                # Last resort: try raw paths
                for f in files:
                    raw = f.get("path", "")
                    res = _resolve_path(raw, aria2_dir)
                    if res:
                        filepath = res
                        break

            # Fallback: search for largest file in download directory
            if not filepath or not os.path.exists(filepath):
                print(f"[aria2] File not found via aria2 paths, searching download directory...")
                download_dir = os.path.abspath(settings.DOWNLOAD_DIR)
                filepath = _search_largest_file_in_dir(download_dir, min_size=expected_size * 0.9 if expected_size > 0 else 0)
                
                if filepath:
                    print(f"[aria2] Found file via directory search: {filepath}")

            if not filepath or not os.path.exists(filepath):
                # List files in download directory for debugging
                download_dir = os.path.abspath(settings.DOWNLOAD_DIR)
                try:
                    files_in_dir = os.listdir(download_dir)
                    print(f"[aria2] Files in download dir: {files_in_dir[:10]}")
                except Exception as e:
                    print(f"[aria2] Could not list download dir: {e}")
                
                msg = f"Download complete but file not found. Expected size: {expected_size}, aria2_dir: {aria2_dir}"
                print(f"[aria2] {msg}")
                return False, msg

            print(f"[aria2] Download complete: {filepath}")
            return True, filepath

        # Handle active/waiting states
        if status in ("active", "waiting"):
            # Case 1: 100% complete but still active (seeding/assembly)
            if status == "active" and total_len > 0 and completed >= total_len:
                files = info.get("files") or []
                aria2_dir = info.get("dir")
                filepath = _find_largest_file(files, aria2_dir)

                if not filepath and files:
                    for f in files:
                        res = _resolve_path(f.get("path", ""), aria2_dir)
                        if res:
                            filepath = res
                            break

                # Fallback: search in download directory
                if not filepath or not os.path.exists(filepath):
                    download_dir = os.path.abspath(settings.DOWNLOAD_DIR)
                    filepath = _search_largest_file_in_dir(download_dir, min_size=total_len * 0.9)

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
