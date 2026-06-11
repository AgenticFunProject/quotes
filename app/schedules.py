from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import math
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


_logger = logging.getLogger(__name__)




def _generate_schedules_token() -> str:
    """Generate a fresh short-lived HS256 JWT for the schedules service."""
    secret = os.environ.get("SCHEDULES_JWT_SECRET", "")
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    now = math.floor(time.time())
    payload = base64.urlsafe_b64encode(
        json.dumps({
            "sub": "quotes-service",
            "iss": "schedules-service",
            "aud": "schedules-api",
            "exp": now + 300,
            "scope": "schedules:read",
        }).encode()
    ).rstrip(b"=").decode()
    signing_input = f"{header}.{payload}"
    sig = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return f"{signing_input}.{sig}"


def _get_schedules_token() -> str:
    if os.environ.get("SCHEDULES_JWT_SECRET", ""):
        return _generate_schedules_token()
    return os.environ.get("SCHEDULES_API_TOKEN", "")


@dataclass(frozen=True)
class Schedule:
    schedule_id: str
    origin_port: str
    destination_port: str
    departure_date: date


class ScheduleProvider(Protocol):
    def get_schedule(self, schedule_id: str) -> Schedule | None:
        ...


@dataclass(frozen=True)
class InMemoryScheduleProvider:
    schedules: dict[str, Schedule]

    def get_schedule(self, schedule_id: str) -> Schedule | None:
        return self.schedules.get(schedule_id)


class ApiScheduleProvider:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def get_schedule(self, schedule_id: str) -> Schedule | None:
        url = f"{self._base_url}/schedules/{schedule_id}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {_get_schedules_token()}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            _logger.error("Schedules API HTTP error %s for schedule %s: %s", e.code, schedule_id, e.read())
            raise
        except Exception as e:
            _logger.error("Schedules API call failed for schedule %s: %s: %s", schedule_id, type(e).__name__, e)
            return None

        return Schedule(
            schedule_id=data["id"],
            origin_port=data["originPort"],
            destination_port=data["destinationPort"],
            departure_date=datetime.fromisoformat(data["etd"].replace("Z", "+00:00")).date(),
        )


SCHEDULES_API_STUB: dict[str, Schedule] = {
    "df62a7d2-a45e-4d4d-b3cb-b4af65435274": Schedule(
        schedule_id="df62a7d2-a45e-4d4d-b3cb-b4af65435274",
        origin_port="NLRTM",
        destination_port="USNYC",
        departure_date=date(2026, 8, 18),
    ),
    "7a59721c-cd5d-4d9f-86a0-9aa9f7f6c47b": Schedule(
        schedule_id="7a59721c-cd5d-4d9f-86a0-9aa9f7f6c47b",
        origin_port="CNSHA",
        destination_port="DEHAM",
        departure_date=date(2026, 6, 5),
    ),
    "1ce1ab21-9d58-4a6d-b867-afc93098352f": Schedule(
        schedule_id="1ce1ab21-9d58-4a6d-b867-afc93098352f",
        origin_port="BRSSZ",
        destination_port="USLAX",
        departure_date=date(2026, 7, 12),
    ),
}


def get_schedule_provider() -> ScheduleProvider:
    api_url = os.environ.get("SCHEDULES_API_URL", "")
    has_auth = bool(os.environ.get("SCHEDULES_JWT_SECRET", "") or os.environ.get("SCHEDULES_API_TOKEN", ""))
    if api_url and has_auth:
        return ApiScheduleProvider(api_url)
    return InMemoryScheduleProvider(SCHEDULES_API_STUB)
