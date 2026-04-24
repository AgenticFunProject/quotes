from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


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


_schedule_provider = InMemoryScheduleProvider(SCHEDULES_API_STUB)


def get_schedule_provider() -> ScheduleProvider:
    return _schedule_provider
