from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeedItem:
    post_id: str
    title: str
    url: str
    published_at: str | None
