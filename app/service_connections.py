from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


_DEFAULT_HEALTH_PATH = "/health"
_DEFAULT_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True)
class ServiceConnectionConfig:
    service: str
    base_url: str
    health_path: str
    timeout_seconds: float


def check_configured_service_health(
    *,
    service: str,
    base_url_env: str,
    health_path_env: str,
    timeout_env: str,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    env = os.environ if environ is None else environ
    config = _load_service_connection_config(
        service=service,
        base_url_env=base_url_env,
        health_path_env=health_path_env,
        timeout_env=timeout_env,
        environ=env,
    )
    if config is None:
        return {
            "service": service,
            "configured": False,
            "ok": False,
            "status": "not_configured",
            "detail": f"{base_url_env} is not configured",
        }

    base_url = _redacted_base_url(config.base_url)
    health_path = _normalized_health_path(config.health_path)
    health_url = _join_url(config.base_url, health_path)
    if health_url is None:
        return {
            "service": service,
            "configured": True,
            "ok": False,
            "status": "unhealthy",
            "baseUrl": base_url,
            "healthPath": health_path,
            "errorType": "InvalidConfiguration",
            "detail": f"{base_url_env} must be an http(s) URL",
        }

    try:
        request = Request(
            health_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "quotes-service-connection-check/0.1",
            },
        )
        with urlopen(request, timeout=config.timeout_seconds) as response:
            http_status = response.getcode()
            response.read()
    except HTTPError as error:
        return _unhealthy_response(config, http_status=error.code, error_type=type(error).__name__)
    except (TimeoutError, URLError, OSError) as error:
        return _unhealthy_response(config, error_type=type(error).__name__)

    return {
        "service": config.service,
        "configured": True,
        "ok": 200 <= http_status < 300,
        "status": "ok" if 200 <= http_status < 300 else "unhealthy",
        "baseUrl": base_url,
        "healthPath": health_path,
        "httpStatus": http_status,
    }


def _load_service_connection_config(
    *,
    service: str,
    base_url_env: str,
    health_path_env: str,
    timeout_env: str,
    environ: Mapping[str, str],
) -> ServiceConnectionConfig | None:
    base_url = environ.get(base_url_env, "").strip()
    if not base_url:
        return None

    return ServiceConnectionConfig(
        service=service,
        base_url=base_url.rstrip("/"),
        health_path=environ.get(health_path_env, _DEFAULT_HEALTH_PATH).strip() or _DEFAULT_HEALTH_PATH,
        timeout_seconds=_timeout_seconds(environ.get(timeout_env)),
    )


def _timeout_seconds(raw_value: str | None) -> float:
    if raw_value is None or not raw_value.strip():
        return _DEFAULT_TIMEOUT_SECONDS
    try:
        timeout = float(raw_value)
    except ValueError:
        return _DEFAULT_TIMEOUT_SECONDS
    if timeout <= 0:
        return _DEFAULT_TIMEOUT_SECONDS
    return min(timeout, 30.0)


def _normalized_health_path(path: str) -> str:
    normalized = path.strip() or _DEFAULT_HEALTH_PATH
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized


def _join_url(base_url: str, health_path: str) -> str | None:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{base_url.rstrip('/')}{health_path}"


def _redacted_base_url(base_url: str) -> str:
    parsed = urlsplit(base_url.rstrip("/"))
    if not parsed.username and not parsed.password:
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))

    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port is not None else ""
    return urlunsplit((parsed.scheme, f"<redacted>@{host}{port}", parsed.path, "", ""))


def _unhealthy_response(
    config: ServiceConnectionConfig,
    *,
    error_type: str,
    http_status: int | None = None,
) -> dict[str, object]:
    response: dict[str, object] = {
        "service": config.service,
        "configured": True,
        "ok": False,
        "status": "unhealthy",
        "baseUrl": _redacted_base_url(config.base_url),
        "healthPath": _normalized_health_path(config.health_path),
        "errorType": error_type,
    }
    if http_status is not None:
        response["httpStatus"] = http_status
    return response
