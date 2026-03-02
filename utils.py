import re
import time

from config import settings


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_bytes(size: float) -> str:
    """Return human-readable byte size string."""
    size = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def format_speed(bps: float) -> str:
    return format_bytes(bps) + "/s"


def format_eta(seconds: float) -> str:
    if seconds <= 0 or seconds > 86400:
        return "∞"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def format_progress(
    current: int,
    total: int,
    start_time: float,
    action: str,
    speed: float = 0,
    eta_seconds: float = 0,
) -> str:
    """
    Render a rich progress bar for Telegram.
    Uses aria2-reported speed & ETA when provided;
    falls back to elapsed-time calculation if speed == 0.
    """
    elapsed = time.time() - start_time

    if speed == 0 and elapsed > 0:
        speed = current / elapsed

    if eta_seconds == 0 and speed > 0 and total > current:
        eta_seconds = (total - current) / speed

    pct = (current / total * 100.0) if total > 0 else 0.0
    filled = min(int(pct / 5), 20)
    bar = "█" * filled + "░" * (20 - filled)
    icon = "⬇️" if "Download" in action else "⬆️"

    return (
        f"{icon} **{action}**\n"
        f"`{bar}` {pct:.1f}%\n"
        f"📦 {format_bytes(current)} / {format_bytes(total)}\n"
        f"⚡ {format_speed(speed)}  |  ⏱ ETA: {format_eta(eta_seconds)}"
    )
