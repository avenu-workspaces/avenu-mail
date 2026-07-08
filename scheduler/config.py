from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

@dataclass(frozen=True)
class CronField:
    values: frozenset[int] | None

    def matches(self, value: int) -> bool:
        return self.values is None or value in self.values


@dataclass(frozen=True)
class CronSchedule:
    minute: CronField
    hour: CronField
    day_of_month: CronField
    month: CronField
    day_of_week: CronField

    def matches(self, dt: datetime) -> bool:
        minute_match = self.minute.matches(dt.minute)
        hour_match = self.hour.matches(dt.hour)
        month_match = self.month.matches(dt.month)
        dom_match = self.day_of_month.matches(dt.day)
        cron_weekday = (dt.weekday() + 1) % 7
        dow_match = self.day_of_week.matches(cron_weekday)

        dom_any = self.day_of_month.values is None
        dow_any = self.day_of_week.values is None
        if dom_any and dow_any:
            day_match = True
        elif dom_any:
            day_match = dow_match
        elif dow_any:
            day_match = dom_match
        else:
            day_match = dom_match or dow_match

        return minute_match and hour_match and month_match and day_match


@dataclass(frozen=True)
class SchedulerConfig:
    backend_api_url: str
    scheduler_token: str
    cron_expression: str
    schedule: CronSchedule
    image_prune_cron_expression: str
    image_prune_schedule: CronSchedule
    optix_member_sync_cron_expression: str
    optix_member_sync_schedule: CronSchedule
    timezone: ZoneInfo
    tick_seconds: int


def load_config() -> SchedulerConfig:
    backend_api_url = os.getenv("BACKEND_API_URL", "http://backend:8000").rstrip("/")
    scheduler_token = os.getenv("SCHEDULER_INTERNAL_TOKEN", "").strip()
    if not scheduler_token:
        raise RuntimeError("SCHEDULER_INTERNAL_TOKEN is required")

    cron_expression = os.getenv("SCHEDULER_CRON", "0 8 * * 1").strip()
    if not cron_expression:
        raise RuntimeError("SCHEDULER_CRON is required")
    schedule = parse_cron_expression(cron_expression)

    image_prune_cron_expression = os.getenv("IMAGE_PRUNE_CRON", "0 3 * * *").strip()
    if not image_prune_cron_expression:
        raise RuntimeError("IMAGE_PRUNE_CRON is required")
    image_prune_schedule = parse_cron_expression(image_prune_cron_expression)
    
    optix_member_sync_cron_expression = os.getenv("OPTIX_MEMBER_SYNC_CRON", "0 * * * *").strip()
    if not optix_member_sync_cron_expression:
        raise RuntimeError("OPTIX_MEMBER_SYNC_CRON is required")
    optix_member_sync_schedule = parse_cron_expression(optix_member_sync_cron_expression)

    timezone_name = os.getenv("SCHEDULER_TIMEZONE", "UTC").strip() or "UTC"
    timezone = ZoneInfo(timezone_name)

    tick_seconds = int(os.getenv("SCHEDULER_TICK_SECONDS", "20"))
    if tick_seconds < 5:
        tick_seconds = 5

    return SchedulerConfig(
        backend_api_url=backend_api_url,
        scheduler_token=scheduler_token,
        cron_expression=cron_expression,
        schedule=schedule,
        image_prune_cron_expression=image_prune_cron_expression,
        image_prune_schedule=image_prune_schedule,
        optix_member_sync_cron_expression=optix_member_sync_cron_expression,
        optix_member_sync_schedule=optix_member_sync_schedule,
        timezone=timezone,
        tick_seconds=tick_seconds,
    )


def parse_cron_expression(expression: str) -> CronSchedule:
    parts = expression.split()
    if len(parts) != 5:
        raise ValueError("cron expression must have 5 fields")
    return CronSchedule(
        minute=_parse_field(parts[0], 0, 59),
        hour=_parse_field(parts[1], 0, 23),
        day_of_month=_parse_field(parts[2], 1, 31),
        month=_parse_field(parts[3], 1, 12),
        day_of_week=_parse_field(parts[4], 0, 7, normalize_weekday=True),
    )


def _parse_field(field: str, minimum: int, maximum: int, *, normalize_weekday: bool = False) -> CronField:
    field = field.strip()
    if field == "*":
        return CronField(values=None)

    values: set[int] = set()
    for token in field.split(","):
        token = token.strip()
        if not token:
            raise ValueError("invalid cron field")
        values.update(_expand_token(token, minimum, maximum))

    if normalize_weekday:
        normalized = {0 if value == 7 else value for value in values}
        values = normalized
    return CronField(values=frozenset(values))


def _expand_token(token: str, minimum: int, maximum: int) -> set[int]:
    if token.startswith("*/"):
        step = int(token[2:])
        if step <= 0:
            raise ValueError("invalid cron step")
        return set(range(minimum, maximum + 1, step))

    if "/" in token:
        range_part, step_part = token.split("/", 1)
        step = int(step_part)
        if step <= 0:
            raise ValueError("invalid cron step")
        if "-" not in range_part:
            raise ValueError("invalid cron range step syntax")
        start, end = _parse_range(range_part, minimum, maximum)
        return set(range(start, end + 1, step))

    if "-" in token:
        start, end = _parse_range(token, minimum, maximum)
        return set(range(start, end + 1))

    value = int(token)
    if value < minimum or value > maximum:
        raise ValueError("cron value out of range")
    return {value}


def _parse_range(token: str, minimum: int, maximum: int) -> tuple[int, int]:
    start_text, end_text = token.split("-", 1)
    start = int(start_text)
    end = int(end_text)
    if start > end:
        raise ValueError("invalid cron range")
    if start < minimum or end > maximum:
        raise ValueError("cron value out of range")
    return start, end
