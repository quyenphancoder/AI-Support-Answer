"""Fetch public English articles without navigation from Zendesk's article API."""

import hashlib
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ARTICLES_URL = "https://support.optisigns.com/api/v2/help_center/en-us/articles.json?per_page=100"


def to_markdown(article: dict) -> str:
    soup = BeautifulSoup(article["body"], "html.parser")
    for tag in soup.select("script, style, nav, noscript"):
        tag.decompose()
    body = markdownify(str(soup), heading_style="ATX").strip()
    # Retain the original href values, including relative links.
    return f'# {article["title"]}\n\nArticle URL: {article["html_url"]}\n\n{body}\n'


def scrape(data_dir: Path, limit: int = 30) -> list[dict]:
    output = data_dir / "articles"
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    seen = set()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=retry))
        session.headers["User-Agent"] = "AmberAtlasTakeHome/0.1"
        url = ARTICLES_URL
        while url:
            response = session.get(url, timeout=30)
            response.raise_for_status()
            payload = response.json()
            for article in payload["articles"]:
                article_id = str(article["id"])
                if article_id in seen or article.get("draft") or not article.get("body"):
                    continue
                seen.add(article_id)
                content = to_markdown(article)
                filename = f"{article_id}.md"
                (output / filename).write_text(content, encoding="utf-8")
                rows.append({
                    "id": article_id,
                    "filename": filename,
                    "title": article["title"],
                    "url": article["html_url"],
                    "updated_at": article.get("updated_at"),
                    "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                })
                if limit and len(rows) >= limit:
                    break
            if limit and len(rows) >= limit:
                break
            url = payload.get("next_page")
    if not rows:
        raise RuntimeError("No articles returned; inspect source before continuing.")
    return rows
