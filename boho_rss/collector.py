from __future__ import annotations

import json
import logging
from typing import Any

from boho_rss.article import parse_article
from boho_rss.http_client import HttpClient
from boho_rss.rss import parse_rss
from boho_rss.settings import Settings

LOGGER = logging.getLogger(__name__)


class Collector:
    def __init__(self, settings: Settings, client: HttpClient) -> None:
        self.settings = settings
        self.client = client

    def collect(self, limit: int | None = None) -> list[dict[str, Any]]:
        feed = self.client.get(self.settings.rss_url)
        items = parse_rss(feed.content)
        if limit is not None:
            items = items[:limit]

        articles: list[dict[str, Any]] = []
        for item in items:
            response = self.client.get(item.url)
            response.encoding = response.encoding or response.apparent_encoding or "utf-8"
            article = parse_article(response.text, item, response.url)
            self._save_article(article)
            articles.append(article)
            LOGGER.info("Saved advisory %s: %s", item.post_id, article["title"])
        return articles

    def _save_article(self, article: dict[str, Any]) -> None:
        articles_dir = self.settings.output_dir / "articles"
        articles_dir.mkdir(parents=True, exist_ok=True)
        path = articles_dir / f"{article['post_id']}.json"
        path.write_text(
            json.dumps(article, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
