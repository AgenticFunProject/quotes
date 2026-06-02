from __future__ import annotations

import os
import urllib.request
import urllib.error
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


SCHEDULES_API_URL = os.environ.get("SCHEDULES_API_URL", "")
SCHEDULES_API_TOKEN = os.environ.get("SCHEDULES_API_TOKEN", "")


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
    def __init__(self, base_url: str, token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token

    def get_schedule(self, schedule_id: str) -> Schedule | None:
        url = f"{self._base_url}/schedules/{schedule_id}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self._token}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise
        except Exception:
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
    if SCHEDULES_API_URL and SCHEDULES_API_TOKEN:
        return ApiScheduleProvider(SCHEDULES_API_URL, SCHEDULES_API_TOKEN)
    return InMemoryScheduleProvider(SCHEDULES_API_STUB)
