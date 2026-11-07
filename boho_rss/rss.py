from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

from boho_rss.models import FeedItem

POST_ID_PATTERN = re.compile(r"[?&]nttId=(\d+)(?:&|$)", re.IGNORECASE)


class FeedParseError(ValueError):
    """Raised when an RSS document cannot be safely interpreted."""


def parse_rss(xml_bytes: bytes) -> list[FeedItem]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise FeedParseError(f"Invalid RSS XML: {exc}") from exc

    if root.tag.rsplit("}", 1)[-1].lower() != "rss" or root.attrib.get("version") != "2.0":
        raise FeedParseError(f"Expected an RSS 2.0 document, received root element {root.tag!r}")

    channel = next((child for child in root if child.tag.rsplit("}", 1)[-1] == "channel"), None)
    if channel is None:
        raise FeedParseError("RSS document has no channel element")

    items: list[FeedItem] = []
    seen_ids: set[str] = set()
    for element in channel:
        if element.tag.rsplit("}", 1)[-1] != "item":
            continue
        fields = {child.tag.rsplit("}", 1)[-1]: (child.text or "").strip() for child in element}
        link = fields.get("link", "")
        match = POST_ID_PATTERN.search(link)
        if not match:
            raise FeedParseError(f"RSS item has no nttId in link: {link!r}")
        post_id = match.group(1)
        if post_id in seen_ids:
            continue
        seen_ids.add(post_id)
        items.append(
            FeedItem(
                post_id=post_id,
                title=fields.get("title", ""),
                url=link,
                published_at=_parse_pub_date(fields.get("pubDate", "")),
            )
        )
    return items


def _parse_pub_date(value: str) -> str | None:
    if not value:
        return None
    try:
        parsed: datetime = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed.isoformat()
