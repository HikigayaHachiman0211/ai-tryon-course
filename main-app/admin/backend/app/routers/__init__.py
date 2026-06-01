from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")


def to_beijing_str(dt: datetime | None) -> str | None:
    """Convert a naive-UTC or aware datetime to a Beijing-time formatted string."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")
