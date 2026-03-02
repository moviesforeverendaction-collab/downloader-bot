import asyncio
from lastperson07.aria2_client import add_download, get_download_status, monitor_download
import time
import os
import json

async def main():
    download_dir = os.path.abspath("downloads")
    os.makedirs(download_dir, exist_ok=True)
    
    # Torrent Test
    url1 = "https://nyaa.si/download/2081686.torrent"
    print(f"Adding torrent: {url1}")
    gid1 = await add_download(url1, download_dir)
    print(f"Torrent GID: {gid1}")
    
    for _ in range(5):
        status = await get_download_status(gid1)
        print(f"Status 1: {json.dumps(status, indent=2)}")
        await asyncio.sleep(2)

    # What if we see followedBy? Let's check that gid.
    status = await get_download_status(gid1)
    if status and "followedBy" in status and status["followedBy"]:
        gid2 = status["followedBy"][0]
        print(f"Followed by: {gid2}")
        status2 = await get_download_status(gid2)
        print(f"Status 2: {json.dumps(status2, indent=2)}")

if __name__ == "__main__":
    asyncio.run(main())
