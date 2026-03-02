import aiohttp
import asyncio
import json
import time

RPC_URL = "http://localhost:6800/jsonrpc"

async def aria2_rpc(method: str, params: list):
    """Send a JSON-RPC request to the aria2c daemon."""
    payload = {
        "jsonrpc": "2.0",
        "id": "q",
        "method": method,
        "params": params
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(RPC_URL, json=payload, timeout=5) as response:
                result = await response.json()
                if "error" in result:
                    raise Exception(result["error"]["message"])
                return result.get("result")
    except Exception as e:
        print(f"Aria2 RPC Error ({method}): {e}")
        return None

async def add_download(uri: str, download_dir: str):
    """Add a URI (HTTP/HTTPS/FTP/Magnet) or Torrent to aria2c."""
    options = {
        "dir": download_dir,
        "seed-time": "0",
        "continue": "true",
        "allow-overwrite": "true"
    }
    
    # If it's a direct magnet or web link
    if uri.startswith(("http", "https", "ftp", "magnet:")):
        gid = await aria2_rpc("aria2.addUri", [[uri], options])
        return gid
    
    return None

async def get_download_status(gid: str):
    """Get the current status of a download by GID."""
    # We want status, totalLength, completedLength, downloadSpeed, connections, errorMessage, followedBy, files
    keys = ["status", "totalLength", "completedLength", "downloadSpeed", "connections", "errorMessage", "followedBy", "files"]
    result = await aria2_rpc("aria2.tellStatus", [gid, keys])
    return result

async def remove_download(gid: str):
    """Remove a download by GID."""
    await aria2_rpc("aria2.remove", [gid])
    
async def monitor_download(gid: str, progress_callback, start_time: float, action="Downloading"):
    """
    Monitor an aria2 download until it completes or errors out.
    Updates the Pyrogram progress bar via callback.
    """
    current_gid = gid
    last_update_time = time.time()
    
    while True:
        status_info = await get_download_status(current_gid)
        if not status_info:
            await asyncio.sleep(2)
            continue
            
        status = status_info.get("status")
        total_len = int(status_info.get("totalLength", 0))
        completed_len = int(status_info.get("completedLength", 0))
        speed = int(status_info.get("downloadSpeed", 0))
        
        # We strictly wait for "complete" to avoid racing aria2's internal parsing/assembly
        is_finished = (status == "complete")

        if is_finished:
            followed_by = status_info.get("followedBy")
            if followed_by and isinstance(followed_by, list) and len(followed_by) > 0:
                current_gid = followed_by[0]
                continue
            
            # Find the actual downloaded file path (accounting for torrent directories)
            files = status_info.get("files", [])
            downloaded_file = None
            
            if files and len(files) > 0:
                import os
                
                # We need to find the absolute largest file among all paths and directories
                largest_file = None
                max_size = 0
                
                for f in files:
                    base_path = f.get("path")
                    if not base_path or not os.path.exists(base_path):
                        continue
                        
                    # If aria2 handed us a Directory (very common for Torrents)
                    if os.path.isdir(base_path):
                        for root, _, filenames in os.walk(base_path):
                            for fname in filenames:
                                full_path = os.path.join(root, fname)
                                try:
                                    sz = os.path.getsize(full_path)
                                    if sz > max_size:
                                        max_size = sz
                                        largest_file = full_path
                                except OSError:
                                    pass
                    else:
                        # It's a direct file
                        try:
                            sz = os.path.getsize(base_path)
                            if sz > max_size:
                                max_size = sz
                                largest_file = base_path
                        except OSError:
                            pass
                
                downloaded_file = largest_file
                if not downloaded_file:
                    downloaded_file = files[0].get("path")

            # Aria2 allocating/verifying pieces can take time.
            # We must wait until the .aria2 tracking file is gone before it is truly "done"
            if downloaded_file and os.path.exists(downloaded_file + ".aria2"):
                await progress_callback(action, completed_len, total_len, start_time, speed, eta_seconds=0)
                await asyncio.sleep(2)
                continue
            
            # Since we manually force finish if active & 100%, we should remove the task
            if status == "active":
                await remove_download(current_gid)
                
            return True, downloaded_file
            
        elif status == "error":
            err_msg = status_info.get("errorMessage", "Unknown Error")
            return False, err_msg
            
        elif status == "removed":
            return False, "Download cancelled."
            
        elif status == "active" or status == "waiting":
            now = time.time()
            if progress_callback and (now - last_update_time >= 3.0 or speed == 0):
                # Calculate simple ETA
                if speed > 0 and total_len > completed_len:
                    remaining_bytes = total_len - completed_len
                    eta_seconds = remaining_bytes / speed
                else:
                    eta_seconds = 0
                
                await progress_callback(
                    action, 
                    completed_len, 
                    total_len, 
                    start_time, 
                    speed=speed, 
                    eta_seconds=eta_seconds
                )
                last_update_time = now
                
        await asyncio.sleep(2)

