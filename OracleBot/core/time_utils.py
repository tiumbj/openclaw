from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Union, overload

from zoneinfo import ZoneInfo


UTC_TZ: Final[ZoneInfo] = ZoneInfo("UTC")
THAILAND_TZ: Final[ZoneInfo] = ZoneInfo("Asia/Bangkok")
DEFAULT_MT5_SERVER_TZ_KEY: Final[str] = "Europe/Athens"


@dataclass(frozen=True)
class MT5TimeConversionConfig:
    """
    MT5 time conversion configuration.

    Many MT5 brokers operate their server clocks in Eastern European time with DST
    (EET/EEST). An IANA zone like Europe/Athens models EET/EEST transitions and is
    suitable as a default when the broker server timezone is not explicitly known.
    """

    server_timezone: str = DEFAULT_MT5_SERVER_TZ_KEY


MT5TimeInput = Union[datetime, str]

_DEFAULT_CFG: Final[MT5TimeConversionConfig] = MT5TimeConversionConfig()


def mt5_server_time_to_thailand(
    value: MT5TimeInput,
    *,
    config: MT5TimeConversionConfig = _DEFAULT_CFG,
) -> datetime:
    """
    Convert MT5 server time (EET/EEST) to Thailand local time (Asia/Bangkok).

    Required routing (strict):
        MT5 Server Time (EET/EEST) -> UTC -> Asia/Bangkok

    Input:
        - datetime: naive (interpreted as MT5 server local time) or tz-aware
        - str: ISO-8601 datetime (naive or tz-aware; trailing 'Z' supported)

    Output:
        - timezone-aware datetime in Asia/Bangkok

    Errors:
        - TypeError for unsupported input types
        - ValueError for invalid datetime strings or invalid timezone keys
    """
    try:
        server_tz = ZoneInfo(config.server_timezone)
    except Exception as exc:
        raise ValueError(f"Invalid MT5 server timezone: {config.server_timezone!r}") from exc

    dt = _coerce_to_datetime(value)
    server_dt = _as_server_time(dt, server_tz)
    utc_dt = server_dt.astimezone(UTC_TZ)
    return utc_dt.astimezone(THAILAND_TZ)


@overload
def mt5_timestamp_to_thailand(
    timestamp_seconds: int,
    *,
    config: MT5TimeConversionConfig = _DEFAULT_CFG,
) -> datetime: ...


@overload
def mt5_timestamp_to_thailand(
    timestamp_seconds: float,
    *,
    config: MT5TimeConversionConfig = _DEFAULT_CFG,
) -> datetime: ...


def mt5_timestamp_to_thailand(
    timestamp_seconds: Union[int, float],
    *,
    config: MT5TimeConversionConfig = _DEFAULT_CFG,
) -> datetime:
    """
    Convert an MT5 epoch timestamp (seconds) to Thailand local time.

    This produces a server-time aware datetime first (EET/EEST), then routes via UTC
    to Asia/Bangkok to keep the conversion architecture consistent.
    """
    try:
        server_tz = ZoneInfo(config.server_timezone)
    except Exception as exc:
        raise ValueError(f"Invalid MT5 server timezone: {config.server_timezone!r}") from exc

    try:
        ts = float(timestamp_seconds)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"Expected epoch seconds convertible to float, got {type(timestamp_seconds).__name__}") from exc

    server_dt = datetime.fromtimestamp(ts, tz=server_tz)
    utc_dt = server_dt.astimezone(UTC_TZ)
    return utc_dt.astimezone(THAILAND_TZ)


def _coerce_to_datetime(value: MT5TimeInput) -> datetime:
    if isinstance(value, datetime):
        return value

    if not isinstance(value, str):
        raise TypeError(f"Expected datetime or ISO string, got {type(value).__name__}")

    s = value.strip()
    if not s:
        raise ValueError("Empty datetime string")

    try:
        return datetime.fromisoformat(_normalize_iso_string(s))
    except Exception as exc:
        raise ValueError(f"Invalid datetime format: {value!r}") from exc


def _normalize_iso_string(s: str) -> str:
    if s.endswith("Z") or s.endswith("z"):
        return s[:-1] + "+00:00"
    return s


def _as_server_time(dt: datetime, server_tz: ZoneInfo) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=server_tz)
    return dt.astimezone(server_tz)


if __name__ == "__main__":
    cfg = MT5TimeConversionConfig(server_timezone="Europe/Athens")

    winter_server_naive = datetime(2026, 1, 15, 12, 0, 0)
    winter_bkk = mt5_server_time_to_thailand(winter_server_naive, config=cfg)
    assert winter_bkk.tzinfo is not None and getattr(winter_bkk.tzinfo, "key", "") == "Asia/Bangkok"
    winter_delta_hours = (winter_bkk.replace(tzinfo=None) - winter_server_naive).total_seconds() / 3600.0
    assert winter_delta_hours == 5.0, f"Winter delta hours mismatch: {winter_delta_hours}"

    summer_server_naive = datetime(2026, 7, 15, 12, 0, 0)
    summer_bkk = mt5_server_time_to_thailand(summer_server_naive, config=cfg)
    assert summer_bkk.tzinfo is not None and getattr(summer_bkk.tzinfo, "key", "") == "Asia/Bangkok"
    summer_delta_hours = (summer_bkk.replace(tzinfo=None) - summer_server_naive).total_seconds() / 3600.0
    assert summer_delta_hours == 4.0, f"Summer delta hours mismatch: {summer_delta_hours}"

    assert mt5_server_time_to_thailand("2026-01-15T12:00:00", config=cfg) == winter_bkk
    assert mt5_server_time_to_thailand("2026-07-15T12:00:00", config=cfg) == summer_bkk

    assert mt5_server_time_to_thailand("2026-01-15T10:00:00Z", config=cfg).hour == 17

    try:
        mt5_server_time_to_thailand("not-a-date", config=cfg)
        raise AssertionError("Expected ValueError for invalid datetime string")
    except ValueError:
        pass
