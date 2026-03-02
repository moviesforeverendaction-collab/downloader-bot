import os
import asyncio
import subprocess
from config import settings


async def split_large_file(filepath: str, max_size_bytes: int = settings.SPLIT_SIZE) -> list[str]:
    """
    Splits a large file using the Linux `split` command (non-blocking).
    Returns a list of resulting file paths.
    If the file is within the size limit, returns [filepath] unchanged.
    """
    if not os.path.exists(filepath):
        return []

    file_size = os.path.getsize(filepath)
    if file_size <= max_size_bytes:
        return [filepath]

    base, ext = os.path.splitext(filepath)
    prefix = f"{base}.part"

    try:
        proc = await asyncio.create_subprocess_exec(
            "split",
            "-b", str(max_size_bytes),
            "-d",
            "-a", "3",
            "--additional-suffix", ext,
            filepath,
            prefix,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err_text = stderr.decode(errors="replace").strip()
            print(f"[split_utils] split command failed (code {proc.returncode}): {err_text}")
            return [filepath]  # Fall back to single original file

        dir_name = os.path.dirname(filepath) or "."
        base_prefix = os.path.basename(prefix)
        parts = sorted(
            os.path.join(dir_name, f)
            for f in os.listdir(dir_name)
            if f.startswith(base_prefix) and f.endswith(ext)
        )
        return parts if parts else [filepath]

    except FileNotFoundError:
        print("[split_utils] 'split' binary not found (non-Linux?). Uploading original file.")
        return [filepath]
    except Exception as exc:
        print(f"[split_utils] Unexpected error: {exc}")
        return [filepath]
