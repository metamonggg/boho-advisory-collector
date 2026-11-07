from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import requests

from boho_rss.article import ArticleParseError
from boho_rss.collector import Collector
from boho_rss.http_client import BohoHttpClient
from boho_rss.rss import FeedParseError
from boho_rss.settings import load_settings

LOGGER = logging.getLogger("boho_rss")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="보호나라 보안공지 JSON 수집기")
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--limit", type=int, help="최대 수집 건수")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be greater than zero")

    settings = load_settings(args.config)
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(levelname)s: %(message)s",
    )
    client = BohoHttpClient(settings)
    try:
        articles = Collector(settings, client).collect(args.limit)
    except (
        requests.RequestException,
        ArticleParseError,
        FeedParseError,
        OSError,
        UnicodeError,
    ) as error:
        LOGGER.error("공지 수집에 실패했습니다: %s", error)
        return 1
    finally:
        client.session.close()

    print(json.dumps(articles, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
