"""
Utility functions for formatting progress and byte sizes.
"""

import time


def format_bytes(size: float) -> str:
    """Convert bytes to human-readable format."""
    if size < 0:
        return "0 B"
    
    size = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def format_speed(bps: float) -> str:
    """Format speed in bytes per second."""
    if bps <= 0:
        return "0 B/s"
    return format_bytes(bps) + "/s"


def format_eta(seconds: float) -> str:
    """Format ETA in human-readable time."""
    if seconds <= 0 or seconds > 86400 * 7:  # Max 1 week
        return "∞"
    
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    
    if d > 0:
        return f"{d}d {h}h"
    if h > 0:
        return f"{h}h {m}m"
    if m > 0:
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
    Render a rich progress bar for Telegram messages.
    
    Args:
        current: Current bytes downloaded
        total: Total bytes to download
        start_time: Unix timestamp when download started
        action: Current action text (e.g., "Downloading")
        speed: Current speed in bytes/second (0 = auto-calculate)
        eta_seconds: ETA in seconds (0 = auto-calculate)
    
    Returns:
        Formatted markdown string for Telegram
    """
    elapsed = time.time() - start_time

    # Auto-calculate speed if not provided
    if speed == 0 and elapsed > 0 and current > 0:
        speed = current / elapsed

    # Auto-calculate ETA if not provided
    if eta_seconds == 0 and speed > 0 and total > current > 0:
        eta_seconds = (total - current) / speed

    # Calculate percentage and bar
    pct = (current / total * 100.0) if total > 0 else 0.0
    pct = min(100.0, max(0.0, pct))  # Clamp between 0-100
    
    # Progress bar (20 chars wide)
    filled = min(int(pct / 5), 20)
    bar = "█" * filled + "░" * (20 - filled)
    
    # Icon based on action
    icon = "⬇️" if "download" in action.lower() else "⬆️" if "upload" in action.lower() else "⚙️"

    lines = [
        f"{icon} **{action}**",
        f"`{bar}` **{pct:.1f}%**",
        f"📦 {format_bytes(current)} / {format_bytes(total)}",
    ]
    
    # Only show speed/ETA if we have meaningful values
    if speed > 0 or elapsed > 5:
        lines.append(f"⚡ {format_speed(speed)}  |  ⏱ ETA: {format_eta(eta_seconds)}")

    return "\n".join(lines)
