from __future__ import annotations

from collections.abc import Iterable
import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from boho_rss.models import FeedItem

CVE_PATTERN = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
VULNERABILITY_PATTERN = re.compile(r"발생하는\s+(.+?)\s+취약점", re.IGNORECASE)
SECTION_LABELS = {
    "overview": ("개요",),
    "vulnerability_description": ("설명", "취약점 설명"),
    "response": ("대응 방안", "해결 방안", "조치 방안"),
}
PRODUCT_COLUMNS = {
    "cve": ("취약점", "cve", "cve번호", "취약점번호"),
    "manufacturer": ("제조사", "업체", "벤더"),
    "product": ("제품명", "제품"),
    "affected_version": ("영향받는버전", "취약버전", "영향버전"),
    "fixed_version": ("해결버전", "해결방안", "패치버전", "업데이트버전"),
}


class ArticleParseError(ValueError):
    """Raised when an HTTP response is not a recognizable KISA article."""


def parse_article(html: str, item: FeedItem, detail_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    article = soup.select_one("section#View.bbs")
    if article is None:
        raise ArticleParseError("KISA article section was not found")

    title_element = article.select_one(".b_title h2")
    content = article.select_one(".content")
    if title_element is None or content is None:
        raise ArticleParseError("KISA article is missing its title or body")

    title = _clean(title_element.get_text(" ", strip=True))
    if not title:
        raise ArticleParseError("KISA article title is empty")

    body_text = content.get_text("\n", strip=True)
    sections = _read_sections(content)
    products, warnings = _read_products(content)
    cve_ids = _unique(CVE_PATTERN.findall(body_text))

    product_cves = {cve for product in products for cve in product["cve_ids"]}
    unmapped_cves = [cve for cve in cve_ids if cve not in product_cves]
    if unmapped_cves:
        warnings.append("제품 행에 연결되지 않은 CVE가 있습니다: " + ", ".join(unmapped_cves))
    if not cve_ids:
        warnings.append("본문에서 CVE 번호를 찾지 못했습니다.")
    if not products:
        warnings.append("제품 표에서 영향을 받는 제품 정보를 찾지 못했습니다.")

    description = sections.get("vulnerability_description", "")
    vulnerability_types = _unique(
        _clean(value).rstrip(".,;")
        for value in VULNERABILITY_PATTERN.findall(description)
    )
    manufacturers = _unique(
        product["manufacturer"] for product in products if product["manufacturer"]
    )
    date_element = article.select_one(".b_title span")
    date_text = _clean(date_element.get_text(" ", strip=True)) if date_element else ""
    references = _read_references(content, detail_url)
    response = sections.get("response") or _read_response_after_table(content)

    return {
        "schema_version": "1.3",
        "post_id": item.post_id,
        "title": title,
        "published_at": _read_date(date_text) or item.published_at,
        "url": detail_url,
        "overview": sections.get("overview", ""),
        "vulnerability_description": description,
        "cve_ids": cve_ids,
        "vulnerability_types": vulnerability_types,
        "manufacturers": manufacturers,
        "affected_products": products,
        "response": response,
        "references": references,
        "body_text": body_text,
        "review_required": bool(warnings),
        "warnings": _unique(warnings),
    }


def _read_sections(content: Tag) -> dict[str, str]:
    sections: dict[str, list[str]] = {name: [] for name in SECTION_LABELS}
    for paragraph in content.find_all("p"):
        text = _clean(paragraph.get_text(" ", strip=True))
        normalized = re.sub(r"^[□■▣]\s*", "", text)
        for name, labels in SECTION_LABELS.items():
            for label in labels:
                match = re.match(re.escape(label) + r"\s*", normalized)
                if match:
                    value = re.sub(
                        r"^[o○●ㆍ·]\s*", "", normalized[match.end() :]
                    ).strip()
                    if value:
                        sections[name].append(value)
                    break
    return {name: "\n".join(values) for name, values in sections.items()}


def _read_products(content: Tag) -> tuple[list[dict[str, Any]], list[str]]:
    products: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[tuple[str, ...]] = set()

    for table in content.find_all("table"):
        rows = [
            [
                _clean(cell.get_text(" ", strip=True))
                for cell in row.find_all(["th", "td"], recursive=False)
            ]
            for row in table.find_all("tr")
        ]
        rows = [row for row in rows if row]
        if len(rows) < 2:
            continue

        headers = [_normalize(header) for header in rows[0]]
        columns = {
            name: _find_column(headers, aliases)
            for name, aliases in PRODUCT_COLUMNS.items()
        }
        if columns["product"] is None:
            continue

        missing_cve_count = 0
        for row in rows[1:]:
            cve_ids = _unique(CVE_PATTERN.findall(_cell(row, columns["cve"])))
            if columns["cve"] is not None and not cve_ids:
                missing_cve_count += 1

            manufacturer = _cell(row, columns["manufacturer"])
            product_name = _cell(row, columns["product"])
            affected_version = _cell(row, columns["affected_version"])
            fixed_version = _cell(row, columns["fixed_version"])
            if not any((manufacturer, product_name, affected_version, fixed_version)):
                continue

            product_key = (
                manufacturer,
                product_name,
                affected_version,
                fixed_version,
                *cve_ids,
            )
            if product_key in seen:
                continue
            seen.add(product_key)
            affected_version_range = _parse_version_range(affected_version or None)
            fixed_version_range = _parse_fixed_version_range(
                fixed_version or None,
                affected_version_range,
            )
            products.append(
                {
                    "manufacturer": manufacturer or None,
                    "product_name": product_name or None,
                    "affected_version": affected_version or None,
                    "affected_version_range": affected_version_range,
                    "fixed_version_or_action": fixed_version or None,
                    "fixed_version_range": fixed_version_range,
                    "cve_ids": cve_ids,
                    "evidence": row,
                }
            )

        if missing_cve_count:
            warnings.append(
                f"제품 표에 CVE가 적히지 않은 행이 {missing_cve_count}개 있습니다."
            )

    return products, warnings


def _parse_version_range(
    value: str | None, *, allow_description: bool = False
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "needs_review",
        "minimum": None,
        "maximum": None,
    }
    if not value:
        result["status"] = "not_provided"
        return result

    value = value.strip()
    if allow_description:
        value = re.sub(r"\s*\([^()]*\)\s*$", "", value).strip()
        if ":" in value:
            value = value.rsplit(":", 1)[-1].strip()

    range_match = re.fullmatch(
        r"(.+?)\s+(이상|초과)\s+(.+?)\s+(미만|이하)", value
    )
    if range_match:
        minimum, minimum_operator, maximum, maximum_operator = (
            part.strip() for part in range_match.groups()
        )
        result.update(
            status="parsed",
            minimum={
                "version": minimum,
                "inclusive": minimum_operator == "이상",
            },
            maximum={
                "version": maximum,
                "inclusive": maximum_operator == "이하",
            },
        )
        return result

    bound_match = re.fullmatch(r"(.+?)\s+(이상|초과|이하|미만)", value)
    if bound_match:
        version, operator = (part.strip() for part in bound_match.groups())
        result["status"] = "parsed"
        if operator in ("이상", "초과"):
            result["minimum"] = {
                "version": version,
                "inclusive": operator == "이상",
            }
        else:
            result["maximum"] = {
                "version": version,
                "inclusive": operator == "이하",
            }
    return result


def _parse_fixed_version_range(
    fixed_version: str | None,
    affected_version_range: dict[str, Any],
) -> dict[str, Any]:
    result = _parse_version_range(fixed_version, allow_description=True)
    maximum = affected_version_range["maximum"]
    if (
        fixed_version
        and result["status"] == "needs_review"
        and affected_version_range["status"] == "parsed"
        and maximum is not None
        and not maximum["inclusive"]
        and fixed_version.strip() == maximum["version"]
    ):
        result.update(
            status="parsed",
            minimum={"version": fixed_version.strip(), "inclusive": True},
            maximum=None,
        )
    return result


def _read_references(content: Tag, detail_url: str) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    seen: set[str] = set()
    for link in content.find_all(["p", "li"]):
        for anchor in link.find_all("a", href=True):
            url = urljoin(detail_url, str(anchor["href"]).strip())
            if not url.startswith(("https://", "http://")) or url in seen:
                continue
            seen.add(url)
            references.append({"url": url, "text": _clean(anchor.get_text(" ", strip=True))})
    return references


def _read_response_after_table(content: Tag) -> str:
    table = content.find("table")
    if table is None:
        return ""

    responses: list[str] = []
    for paragraph in table.find_all_next("p"):
        text = _clean(paragraph.get_text(" ", strip=True))
        if re.match(r"^(?:참고\s*사이트|참고사이트|문의사항|작성)", text):
            break
        if any(word in text for word in ("업데이트", "패치", "차단", "마이그레이션", "적용 권고")):
            responses.append(text)
    return "\n".join(_unique(responses))


def _find_column(headers: list[str], aliases: tuple[str, ...]) -> int | None:
    for index, header in enumerate(headers):
        if header in aliases:
            return index
    return None


def _cell(row: list[str], index: int | None) -> str:
    return row[index] if index is not None and index < len(row) else ""


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _read_date(value: str) -> str | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return value


def _unique(values: Iterable[str]) -> list[str]:
    unique_values = (value.upper() if value.upper().startswith("CVE-") else value for value in values)
    return list(dict.fromkeys(unique_values))


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
