import asyncio
import json
import urllib.request
from urllib.error import URLError

RPC_URL = "http://localhost:6800/jsonrpc"

def test_rpc():
    options = {
        "dir": "/tmp",
        "max-connection-per-server": "32",
        "split": "32",
        "min-split-size": "1M",
        "piece-length": "1M",
        "seed-time": "0",
        "max-overall-download-limit": "0",
        "max-overall-upload-limit": "0",
        "continue": "true",
        "allow-overwrite": "true",
        "disable-ipv6": "true",
        "disk-cache": "64M",
        "enable-mmap": "true"
    }

    payload = {
        "jsonrpc": "2.0",
        "id": "q",
        "method": "aria2.addUri",
        "params": [["http://ipv4.download.thinkbroadband.com/5MB.zip"], options]
    }
    
    req = urllib.request.Request(RPC_URL, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read())
            print("Response:", result)
    except Exception as e:
        print("Error connecting or parsing:", e)
        if hasattr(e, 'read'):
            print("Body:", e.read().decode('utf-8'))

test_rpc()
