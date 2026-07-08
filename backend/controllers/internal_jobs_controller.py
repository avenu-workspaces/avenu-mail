from __future__ import annotations

import hmac

from flask import Blueprint, current_app, jsonify, request

from config import SCHEDULER_INTERNAL_TOKEN
from controllers.common import parse_iso_date
from errors import APIError
from services.idempotency_service import begin_request, commit_response, rollback_reservation
from services.image_pruner import prune_expired_images
from services.notifications.channels.factory import build_notification_channels
from services.notifications.weekly_summary_cron_job import run_weekly_summary_cron_job
from services.notifications.weekly_summary_notifier import WeeklySummaryNotifier
from validators import require_dict
from config import OPTIX_ORG_TOKEN
from services.identity_sync_service import sync_all_optix_members

internal_jobs_bp = Blueprint("internal_jobs", __name__)


def _require_scheduler_token() -> None:
    provided = (request.headers.get("X-Scheduler-Token") or "").strip()
    if not SCHEDULER_INTERNAL_TOKEN:
        raise APIError(503, "scheduler token is not configured")
    if not provided or not hmac.compare_digest(provided, SCHEDULER_INTERNAL_TOKEN):
        raise APIError(401, "unauthorized")


def _weekly_job_response_body(result: dict) -> dict:
    return {
        "weekStart": result["weekStart"].isoformat(),
        "weekEnd": result["weekEnd"].isoformat(),
        "processed": result["processed"],
        "sent": result["sent"],
        "skipped": result["skipped"],
        "failed": result["failed"],
        "errors": result["errors"],
    }


@internal_jobs_bp.route("/api/internal/jobs/weekly-summary", methods=["POST"])
def internal_weekly_summary_job_route():
    _require_scheduler_token()

    body_raw = request.get_json(silent=True)
    payload = {} if body_raw is None else require_dict(body_raw)
    week_start_value = payload.get("weekStart")
    week_end_value = payload.get("weekEnd")
    week_start = None
    week_end = None

    if (week_start_value is None) != (week_end_value is None):
        raise APIError(422, "weekStart and weekEnd must be provided together")
    if week_start_value is not None:
        if not isinstance(week_start_value, str):
            raise APIError(422, "weekStart must be YYYY-MM-DD")
        if not isinstance(week_end_value, str):
            raise APIError(422, "weekEnd must be YYYY-MM-DD")
        week_start = parse_iso_date(week_start_value, field_name="weekStart")
        week_end = parse_iso_date(week_end_value, field_name="weekEnd")
        if week_end < week_start:
            raise APIError(422, "weekEnd must be on or after weekStart")

    route = "/api/internal/jobs/weekly-summary"
    idempotency_key, replay = begin_request(
        headers=request.headers,
        payload=payload,
        route=route,
        method="POST",
    )
    if replay is not None:
        return jsonify(replay["body"]), replay["status"]

    try:
        notifier = WeeklySummaryNotifier(
            channels=build_notification_channels(testing=current_app.config["TESTING"])
        )
        result = run_weekly_summary_cron_job(
            notifier=notifier,
            week_start=week_start,
            week_end=week_end,
        )
        body = _weekly_job_response_body(result)
        commit_response(key=idempotency_key, route=route, method="POST", status=200, body=body)
        return jsonify(body), 200
    except Exception:
        rollback_reservation(key=idempotency_key, route=route, method="POST")
        raise


@internal_jobs_bp.route("/api/internal/jobs/image-prune", methods=["POST"])
def internal_image_prune_job_route():
    _require_scheduler_token()

    body_raw = request.get_json(silent=True)
    payload = {} if body_raw is None else require_dict(body_raw)
    retention_override = payload.get("retentionHours")
    retention_hours: int | None = None
    if retention_override is not None:
        if not isinstance(retention_override, int) or isinstance(retention_override, bool) or retention_override <= 0:
            raise APIError(422, "retentionHours must be a positive integer")
        retention_hours = retention_override

    route = "/api/internal/jobs/image-prune"
    idempotency_key, replay = begin_request(
        headers=request.headers,
        payload=payload,
        route=route,
        method="POST",
    )
    if replay is not None:
        return jsonify(replay["body"]), replay["status"]

    try:
        result = prune_expired_images(retention_hours=retention_hours)
        body = result.to_dict()
        commit_response(key=idempotency_key, route=route, method="POST", status=200, body=body)
        return jsonify(body), 200
    except Exception:
        rollback_reservation(key=idempotency_key, route=route, method="POST")
        raise

@internal_jobs_bp.route("/api/internal/jobs/optix-member-sync", methods=["POST"])
def internal_optix_member_sync_route():
    _require_scheduler_token()

    if not OPTIX_ORG_TOKEN:
        raise APIError(503, "OPTIX_ORG_TOKEN is not configured")

    body_raw = request.get_json(silent=True)
    payload = {} if body_raw is None else require_dict(body_raw)

    route = "/api/internal/jobs/optix-member-sync"
    idempotency_key, replay = begin_request(
        headers=request.headers,
        payload=payload,
        route=route,
        method="POST",
    )
    if replay is not None:
        return jsonify(replay["body"]), replay["status"]

    try:
        counts = sync_all_optix_members(org_token=OPTIX_ORG_TOKEN)
        commit_response(
            key=idempotency_key, route=route, method="POST", status=200, body=counts
        )
        return jsonify(counts), 200
    except Exception:
        rollback_reservation(key=idempotency_key, route=route, method="POST")
        raise
