"""
File splitting utilities for handling large files.
Uses native Linux 'split' command for performance.
"""

import os
import asyncio
import subprocess
from config import settings


async def split_large_file(filepath: str, max_size_bytes: int = None) -> list[str]:
    """
    Split a large file using the Linux 'split' command.
    
    Args:
        filepath: Path to file to split
        max_size_bytes: Maximum size per part (default: settings.SPLIT_SIZE)
        
    Returns:
        List of file paths. If file is small enough, returns [filepath].
    """
    if max_size_bytes is None:
        max_size_bytes = settings.SPLIT_SIZE
    
    if not os.path.exists(filepath):
        print(f"[split] File not found: {filepath}")
        return []

    try:
        file_size = os.path.getsize(filepath)
    except OSError as e:
        print(f"[split] Cannot get file size: {e}")
        return [filepath]

    # No splitting needed
    if file_size <= max_size_bytes:
        return [filepath]

    base, ext = os.path.splitext(filepath)
    prefix = f"{base}.part"

    print(f"[split] Splitting {filepath} ({file_size} bytes) into {max_size_bytes}-byte parts")

    try:
        proc = await asyncio.create_subprocess_exec(
            "split",
            "-b", str(max_size_bytes),
            "-d",  # Numeric suffixes
            "-a", "3",  # 3-digit suffixes
            "--additional-suffix", ext,
            filepath,
            prefix,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err_text = stderr.decode(errors="replace").strip()
            print(f"[split] Command failed (code {proc.returncode}): {err_text}")
            return [filepath]

        # Find created parts
        dir_name = os.path.dirname(filepath) or "."
        base_prefix = os.path.basename(prefix)
        
        try:
            parts = sorted([
                os.path.join(dir_name, f)
                for f in os.listdir(dir_name)
                if f.startswith(base_prefix) and f.endswith(ext)
            ])
        except OSError as e:
            print(f"[split] Failed to list parts: {e}")
            return [filepath]
        
        if parts:
            print(f"[split] Created {len(parts)} parts")
            return parts
        else:
            print("[split] No parts found after split")
            return [filepath]

    except FileNotFoundError:
        print("[split] 'split' binary not found - using original file")
        return [filepath]
    except Exception as exc:
        print(f"[split] Unexpected error: {exc}")
        return [filepath]


def get_part_info(filepath: str, max_size_bytes: int = None) -> tuple[int, int]:
    """
    Calculate how many parts a file would be split into.
    
    Args:
        filepath: Path to file
        max_size_bytes: Maximum size per part
        
    Returns:
        Tuple of (total_parts, total_size)
    """
    if max_size_bytes is None:
        max_size_bytes = settings.SPLIT_SIZE
        
    if not os.path.exists(filepath):
        return 0, 0
        
    try:
        size = os.path.getsize(filepath)
        parts = (size + max_size_bytes - 1) // max_size_bytes
        return parts, size
    except OSError:
        return 0, 0
