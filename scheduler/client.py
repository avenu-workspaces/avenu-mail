from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import date


class BackendClientError(RuntimeError):
    pass


class BackendClient:
    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    def trigger_weekly_summary(
        self,
        *,
        scheduler_token: str,
        week_start: date,
        week_end: date,
        idempotency_key: str,
    ) -> dict:
        payload = json.dumps(
            {
                "weekStart": week_start.isoformat(),
                "weekEnd": week_end.isoformat(),
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url=f"{self._base_url}/api/internal/jobs/weekly-summary",
            method="POST",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Scheduler-Token": scheduler_token,
                "Idempotency-Key": idempotency_key,
            },
        )
        return _send(request)

    def trigger_image_prune(
        self,
        *,
        scheduler_token: str,
        idempotency_key: str,
    ) -> dict:
        payload = json.dumps({}).encode("utf-8")
        request = urllib.request.Request(
            url=f"{self._base_url}/api/internal/jobs/image-prune",
            method="POST",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Scheduler-Token": scheduler_token,
                "Idempotency-Key": idempotency_key,
            },
        )
        return _send(request)


def _send(request: urllib.request.Request) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise BackendClientError(f"backend returned status={exc.code} body={detail}") from exc
    except urllib.error.URLError as exc:
        raise BackendClientError(str(exc)) from exc

def trigger_optix_member_sync(
        self,
        *,
        scheduler_token: str,
        idempotency_key: str,
    ) -> dict:
        payload = json.dumps({}).encode("utf-8")
        request = urllib.request.Request(
            url=f"{self._base_url}/api/internal/jobs/optix-member-sync",
            method="POST",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Scheduler-Token": scheduler_token,
                "Idempotency-Key": idempotency_key,
            },
        )
        return _send(request)
