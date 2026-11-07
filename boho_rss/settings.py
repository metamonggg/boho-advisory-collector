from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Settings:
    rss_url: str
    output_dir: Path
    request_timeout_seconds: float
    request_retries: int
    request_interval_seconds: float
    user_agent: str
    log_level: str


def load_settings(config_path: Path) -> Settings:
    config_path = config_path.expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as file:
        values: dict[str, Any] = json.load(file)

    def resolve_path(value: str) -> Path:
        path = Path(value).expanduser()
        return path.resolve() if path.is_absolute() else (config_path.parent / path).resolve()

    settings = Settings(
        rss_url=str(values["rss_url"]),
        output_dir=resolve_path(str(values["output_dir"])),
        request_timeout_seconds=float(values.get("request_timeout_seconds", 20)),
        request_retries=int(values.get("request_retries", 3)),
        request_interval_seconds=float(values.get("request_interval_seconds", 0.7)),
        user_agent=str(values.get("user_agent", "boho-rss-collector/1.0")),
        log_level=str(values.get("log_level", "INFO")).upper(),
    )
    if settings.request_timeout_seconds <= 0:
        raise ValueError("request_timeout_seconds must be greater than zero")
    if settings.request_retries < 0:
        raise ValueError("request_retries must not be negative")
    if settings.request_interval_seconds < 0:
        raise ValueError("request_interval_seconds must not be negative")
    return settings
