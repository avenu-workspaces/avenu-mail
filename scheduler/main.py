from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone

from client import BackendClient, BackendClientError
from config import load_config


logger = logging.getLogger("scheduler")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = load_config()
    client = BackendClient(config.backend_api_url)
    last_fired: dict[str, str] = {}

    logger.info(
        (
            "scheduler_started backend=%s weekly_cron=%s image_prune_cron=%s "
            "optix_member_sync_cron=%s timezone=%s tick_seconds=%d"
        ),
        config.backend_api_url,
        config.cron_expression,
        config.image_prune_cron_expression,
        config.optix_member_sync_cron_expression,
        config.timezone.key,
        config.tick_seconds,
    )

    while True:
        now_utc = datetime.now(tz=timezone.utc)
        local_now = now_utc.astimezone(config.timezone).replace(second=0, microsecond=0)
        minute_key = local_now.strftime("%Y-%m-%dT%H:%M")

        if last_fired.get("weekly") != minute_key and config.schedule.matches(local_now):
            _run_weekly_summary(client, config.scheduler_token, now_utc)
            last_fired["weekly"] = minute_key

        if last_fired.get("image_prune") != minute_key and config.image_prune_schedule.matches(local_now):
            _run_image_prune(client, config.scheduler_token, local_now)
            last_fired["image_prune"] = minute_key

        if last_fired.get("optix_member_sync") != minute_key and config.optix_member_sync_schedule.matches(local_now):
            _run_optix_member_sync(client, config.scheduler_token, local_now)
            last_fired["optix_member_sync"] = minute_key

        time.sleep(config.tick_seconds)


def _run_weekly_summary(client: BackendClient, token: str, now_utc: datetime) -> None:
    week_start, week_end = compute_previous_week_range(now_utc)
    idempotency_key = f"weekly-summary:{week_start.isoformat()}"
    try:
        result = client.trigger_weekly_summary(
            scheduler_token=token,
            week_start=week_start,
            week_end=week_end,
            idempotency_key=idempotency_key,
        )
        logger.info(
            (
                "weekly_summary_trigger_success weekStart=%s weekEnd=%s processed=%s sent=%s "
                "skipped=%s failed=%s errors=%s"
            ),
            week_start.isoformat(),
            week_end.isoformat(),
            result.get("processed"),
            result.get("sent"),
            result.get("skipped"),
            result.get("failed"),
            result.get("errors"),
        )
    except BackendClientError as exc:
        logger.exception(
            "weekly_summary_trigger_failed weekStart=%s weekEnd=%s detail=%s",
            week_start.isoformat(),
            week_end.isoformat(),
            str(exc),
        )


def _run_image_prune(client: BackendClient, token: str, local_now: datetime) -> None:
    # Keying on local date (not minute) keeps a single retry on backend failure
    # from triggering duplicate prunes on the same day.
    idempotency_key = f"image-prune:{local_now.date().isoformat()}"
    try:
        result = client.trigger_image_prune(
            scheduler_token=token,
            idempotency_key=idempotency_key,
        )
        logger.info(
            (
                "image_prune_trigger_success rowsScanned=%s filesDeleted=%s "
                "rowsMarkedDeleted=%s orphanFilesDeleted=%s"
            ),
            result.get("rowsScanned"),
            result.get("filesDeleted"),
            result.get("rowsMarkedDeleted"),
            result.get("orphanFilesDeleted"),
        )
    except BackendClientError as exc:
        logger.exception("image_prune_trigger_failed detail=%s", str(exc))

def _run_optix_member_sync(client: BackendClient, token: str, local_now: datetime) -> None:
    idempotency_key = f"optix-member-sync:{local_now.strftime('%Y-%m-%dT%H')}"
    try:
        result = client.trigger_optix_member_sync(
            scheduler_token=token,
            idempotency_key=idempotency_key,
        )
        logger.info(
            "optix_member_sync_success created=%s updated=%s failed=%s pages=%s",
            result.get("created"),
            result.get("updated"),
            result.get("failed"),
            result.get("pages"),
        )
    except BackendClientError as exc:
        logger.exception("optix_member_sync_failed detail=%s", str(exc))

def compute_previous_week_range(now: datetime) -> tuple[date, date]:
    if now.tzinfo is None:
        utc_now = now.replace(tzinfo=timezone.utc)
    else:
        utc_now = now.astimezone(timezone.utc)

    today = utc_now.date()
    days_since_monday = today.weekday()
    current_week_start = today - timedelta(days=days_since_monday)
    previous_week_start = current_week_start - timedelta(days=7)
    previous_week_end = current_week_start - timedelta(days=1)
    return previous_week_start, previous_week_end


if __name__ == "__main__":
    raise SystemExit(main())
