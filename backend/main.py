from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote
import re

app = FastAPI(title="ARBFLIX QFilm API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_URL = "https://a.qfilm.tv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

class SearchRequest(BaseModel):
    query: str
    year: int | None = None
    kind: str | None = None


def normalize(text):
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def get_page(url):
    r = requests.get(
        url,
        headers=HEADERS,
        timeout=20,
    )
    r.raise_for_status()
    return r.text


def find_qfilm(query, year=None):
    search_url = f"{BASE_URL}/search.php?keywords={quote(query)}"
    html = get_page(search_url)
    soup = BeautifulSoup(html, "html.parser")

    candidates = []

    for a in soup.select("a[href]"):
        href = a.get("href")
        text = a.get_text(" ", strip=True)

        if not href or not text:
            continue

        url = urljoin(search_url, href)

        if "/watch.php" not in url:
            continue

        candidates.append({
            "title": text,
            "url": url,
        })

    if not candidates:
        return None

    wanted = normalize(query)
    wanted_words = set(wanted.split())
    year_text = str(year) if year else ""

    def score(item):
        text = normalize(item["title"])
        score_value = 0

        if wanted and wanted in text:
            score_value += 60

        score_value += sum(
            1 for word in wanted_words
            if len(word) >= 3 and word in text
        )

        if year_text and year_text in item["title"]:
            score_value += 30

        return score_value

    best = max(candidates, key=score)

    if score(best) < 2:
        return None

    watch_html = get_page(best["url"])
    watch_soup = BeautifulSoup(watch_html, "html.parser")

    for iframe in watch_soup.select("iframe[src], iframe[data-src]"):
        raw = iframe.get("src") or iframe.get("data-src")

        if not raw:
            continue

        iframe_url = urljoin(best["url"], raw.strip())

        if iframe_url.startswith(("http://", "https://")):
            return {
                "source": "QFilm",
                "status": "found",
                "matched_title": best["title"],
                "page_url": best["url"],
                "confidence": round(min(score(best) / 100, 0.99), 4),
                "players": [
                    {
                        "type": "iframe",
                        "url": iframe_url,
                        "label": "QFilm",
                    }
                ],
                "error": None,
            }

    return None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/search")
def search(request: SearchRequest):
    if not request.query.strip():
        return {
            "success": False,
            "error": "query is required",
            "results": [],
        }

    try:
        result = find_qfilm(
            request.query.strip(),
            request.year,
        )

        return {
            "success": True,
            "query": request.query,
            "results": [
                result
            ] if result else [],
        }

    except Exception as exc:
        return {
            "success": False,
            "query": request.query,
            "results": [],
            "error": str(exc),
        }
