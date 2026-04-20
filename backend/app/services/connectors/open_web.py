from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
import re
from urllib.parse import parse_qs, urlparse
from xml.etree import ElementTree as ET

import httpx

from app.services.connectors.base import BaseConnector, ConnectorItem, ConnectorResult


class OpenWebConnector(BaseConnector):
    provider = "open_web"

    async def search(self, query: str, lookback_days: int, limit: int) -> ConnectorResult:
        del lookback_days
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/135.0.0.0 Safari/537.36"
            )
        }

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            rss_rows = await _fetch_google_news_rss(client, query, headers, limit=min(limit, 24))
            ddg_rows, ddg_status, ddg_message = await _fetch_duckduckgo_rows(
                client,
                query,
                headers,
                limit=min(limit, 32),
            )

        rows = _dedupe_rows(rss_rows + ddg_rows)[: min(limit, 50)]
        if not rows and ddg_status in {"rate_limited", "error"}:
            return ConnectorResult(
                provider=self.provider,
                status=ddg_status,
                message=ddg_message,
                items=[],
            )

        items: list[ConnectorItem] = []
        for row in rows:
            url = row["url"]
            domain = _extract_domain(url)
            items.append(
                ConnectorItem(
                    provider=self.provider,
                    source_type="news",
                    source_name=domain or row["source"] or "open web",
                    source_country=None,
                    language=None,
                    title=row["title"] or url,
                    url=url,
                    summary=row["snippet"][:900],
                    published_at=row.get("published_at") or datetime.now(timezone.utc),
                    ranking_score=0,
                    raw_payload=row,
                )
            )

        return ConnectorResult(
            provider=self.provider,
            status="ok",
            message="Материалы загружены через открытый веб-поиск и новостной RSS-поиск.",
            items=items,
        )


async def _fetch_google_news_rss(
    client: httpx.AsyncClient,
    query: str,
    headers: dict[str, str],
    *,
    limit: int,
) -> list[dict]:
    params = {
        "q": query,
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    }
    try:
        response = await client.get("https://news.google.com/rss/search", params=params, headers=headers)
        if response.status_code >= 400:
            return []
        return _parse_google_news_rss(response.text, limit=limit)
    except Exception:
        return []


async def _fetch_duckduckgo_rows(
    client: httpx.AsyncClient,
    query: str,
    headers: dict[str, str],
    *,
    limit: int,
) -> tuple[list[dict], str, str]:
    params = {"q": query, "kl": "wt-wt"}
    try:
        response = await client.get("https://html.duckduckgo.com/html/", params=params, headers=headers)
        if response.status_code == 429:
            return [], "rate_limited", "Открытый веб-поиск временно ограничил запросы. Повторите чуть позже."
        if response.status_code >= 400:
            return [], "error", f"Открытый веб-поиск вернул HTTP {response.status_code}."
        return _parse_duckduckgo_results(response.text, limit=limit), "ok", "Материалы загружены через DuckDuckGo."
    except Exception as exc:
        return [], "error", f"Открытый веб-поиск завершился с ошибкой: {exc}"


def _parse_google_news_rss(xml_text: str, limit: int) -> list[dict]:
    rows: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return rows

    channel = root.find("channel")
    if channel is None:
        return rows

    for item in channel.findall("item"):
        title_text = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = _strip_tags(item.findtext("description") or "")
        pub_date_raw = (item.findtext("pubDate") or "").strip()
        source_name = ""
        source_node = item.find("source")
        if source_node is not None:
            source_name = (source_node.text or "").strip()

        if not title_text or not link:
            continue

        if " - " in title_text and not source_name:
            headline, possible_source = title_text.rsplit(" - ", 1)
            if possible_source and len(possible_source) < 80:
                title_text = headline.strip()
                source_name = possible_source.strip()

        published_at = None
        if pub_date_raw:
            try:
                published_at = parsedate_to_datetime(pub_date_raw)
                if published_at.tzinfo is None:
                    published_at = published_at.replace(tzinfo=timezone.utc)
            except Exception:
                published_at = None

        rows.append(
            {
                "title": title_text,
                "url": link,
                "snippet": description,
                "source": source_name or _extract_domain(link),
                "published_at": published_at,
                "origin": "google_news_rss",
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _parse_duckduckgo_results(html: str, limit: int) -> list[dict]:
    rows: list[dict] = []
    title_pattern = re.compile(r'class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
    snippet_pattern = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>|class="result__snippet"[^>]*>(.*?)</div>', re.S)
    for match in title_pattern.finditer(html):
        raw_href = unescape(match.group(1))
        url = _normalize_result_url(raw_href)
        if not url or not url.startswith(("http://", "https://")):
            continue
        title = _strip_tags(unescape(match.group(2)))
        local_html = html[match.end() : match.end() + 2200]
        snippet_match = snippet_pattern.search(local_html)
        snippet_raw = snippet_match.group(1) or snippet_match.group(2) if snippet_match else ""
        snippet = _strip_tags(unescape(snippet_raw))
        source = _extract_domain(url)
        rows.append(
            {
                "title": title.strip(),
                "url": url,
                "snippet": snippet.strip(),
                "source": source,
                "published_at": None,
                "origin": "duckduckgo",
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _dedupe_rows(rows: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        fingerprint = f"{(row.get('url') or '').split('?')[0].rstrip('/').lower()}|{' '.join((row.get('title') or '').lower().split())[:180]}"
        if not row.get("url") or fingerprint in seen:
            continue
        seen.add(fingerprint)
        deduped.append(row)
    return deduped


def _normalize_result_url(raw_href: str) -> str:
    if raw_href.startswith("//"):
        raw_href = "https:" + raw_href
    parsed = urlparse(raw_href)
    if raw_href.startswith("/l/?kh=") or (
        "duckduckgo.com" in (parsed.hostname or "")
        and parsed.path == "/l/"
        and "uddg=" in parsed.query
    ):
        uddg = parse_qs(parsed.query).get("uddg", [None])[0]
        return unescape(uddg) if uddg else raw_href
    return raw_href


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value).replace("&nbsp;", " ").replace("\n", " ").strip()


def _extract_domain(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host.lower().removeprefix("www.")
