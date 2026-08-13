"""
ARBFLIX — الاستيراد التلقائي (يشتغل من GitHub Actions بدون تدخل يدوي)
======================================================================
السكريبت ده بيجيب أحدث وأشهر الأفلام تلقائيًا من TMDb (Trending + Upcoming)
من غير ما تحتاج تحط أرقام أفلام يدويًا زي fetch_movies.py.
بيشتغل تلقائيًا كل يوم عن طريق GitHub Actions (شوف .github/workflows/update-movies.yml)

المتغيرات دي بييجوا من GitHub Secrets:
- TMDB_API_KEY: مفتاح TMDb بتاعك
- AFFILIATE_URL: (اختياري) لينك الأفيليت الافتراضي اللي هيتحط تلقائيًا لكل فيلم جديد
- PLATFORM_NAME: (اختياري) اسم المنصة الافتراضية (Shahid افتراضيًا)
"""

import datetime
import json
import os
import re
import requests
from urllib.parse import urljoin, urlencode
from bs4 import BeautifulSoup

API_KEY = os.environ.get("TMDB_API_KEY", "")
AFFILIATE_URL = os.environ.get("AFFILIATE_URL", "REPLACE_WITH_YOUR_AFFILIATE_LINK")
PLATFORM_NAME = os.environ.get("PLATFORM_NAME", "Shahid")
LANGUAGE = "ar-EG"
MAX_ITEMS = 200  # أقصى عدد أفلام/مسلسلات هيفضل ظاهر في السايت (الأقدم بيتشال تلقائيًا)

BASE = "https://api.themoviedb.org/3"
QFILM_BASE_URL = os.environ.get("QFILM_BASE_URL", "https://a.qfilm.tv").rstrip("/")
QFILM_TIMEOUT = int(os.environ.get("QFILM_TIMEOUT", "20"))
QFILM_ENABLED = os.environ.get("QFILM_ENABLED", "true").lower() in {"1", "true", "yes", "on"}

QFILM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
DEFAULT_PLATFORM = {"name": PLATFORM_NAME, "affiliate_url": AFFILIATE_URL}


def fetch_details(tmdb_id, kind):
    endpoint = "movie" if kind == "فيلم" else "tv"
    r = requests.get(f"{BASE}/{endpoint}/{tmdb_id}",
                      params={"api_key": API_KEY, "language": LANGUAGE, "append_to_response": "videos"})
    r.raise_for_status()
    d = r.json()

    title_original = d.get("original_title") or d.get("original_name") or ""
    title_ar = d.get("title") or d.get("name") or title_original
    year_raw = d.get("release_date") or d.get("first_air_date") or ""
    year = int(year_raw[:4]) if year_raw else None
    genre = d["genres"][0]["name"] if d.get("genres") else "عام"
    rating = round(d.get("vote_average", 0), 1)
    poster_path = d.get("poster_path")
    overview = d.get("overview") or "لا يوجد وصف متاح حاليًا."
    slug = title_original.lower().replace(" ", "-").replace(":", "")

    trailer_key = None
    for v in (d.get("videos", {}) or {}).get("results", []):
        if v.get("site") == "YouTube" and v.get("type") == "Trailer":
            trailer_key = v.get("key")
            break
    if not trailer_key:
        for v in (d.get("videos", {}) or {}).get("results", []):
            if v.get("site") == "YouTube":
                trailer_key = v.get("key")
                break

    return {
        "id": f"{slug}-{tmdb_id}",
        "title": title_original,
        "title_ar": title_ar,
        "type": kind,
        "year": year,
        "rating": rating,
        "genre": genre,
        "poster_path": poster_path,
        "overview": overview,
        "trailer_key": trailer_key,
        "platforms": [DEFAULT_PLATFORM],
    }


def _pull(path, extra_params=None, kind="فيلم", seen=None, bucket=None):
    params = {"api_key": API_KEY, "language": LANGUAGE, "page": 1}
    if extra_params:
        params.update(extra_params)
    r = requests.get(f"{BASE}/{path}", params=params)
    if r.ok:
        for item in r.json().get("results", []):
            key = (kind, item["id"])
            if key not in seen:
                seen.add(key)
                bucket.append(key)


def discover_ids():
    """يجيب توليفة متوازنة: أجنبي (أفلام+مسلسلات) + مصري + عربي، كل فئة بحصة ثابتة
    عشان محتوى مصري ما ياكلش مكان الأجنبي ولا العكس"""
    CATEGORIES = [
        ("فيلم", "trending/movie/week", {}),
        ("مسلسل", "trending/tv/week", {}),
        ("فيلم", "movie/popular", {}),
        ("مسلسل", "tv/popular", {}),
        ("فيلم", "movie/upcoming", {}),
        ("مسلسل", "tv/on_the_air", {}),
        ("فيلم", "discover/movie", {"with_origin_country": "EG", "sort_by": "popularity.desc"}),
        ("مسلسل", "discover/tv", {"with_origin_country": "EG", "sort_by": "popularity.desc"}),
        ("فيلم", "discover/movie", {"with_original_language": "ar", "sort_by": "popularity.desc"}),
        ("مسلسل", "discover/tv", {"with_original_language": "ar", "sort_by": "popularity.desc"}),
    ]
    PER_CATEGORY_CAP = 20  # كل فئة بتاخد حصة متساوية بحد أقصى ٢٠ عنصر

    seen = set()
    category_lists = []
    for kind, path, extra in CATEGORIES:
        bucket = []
        _pull(path, extra, kind=kind, seen=seen, bucket=bucket)
        category_lists.append(bucket[:PER_CATEGORY_CAP])

    # نلف على الفئات بالتبادل (فيلم أجنبي، مسلسل أجنبي، فيلم مصري، مسلسل مصري...)
    # عشان النتيجة النهائية تبقى متنوعة بدل ما فئة توحدة توكل الباقي
    merged = []
    i = 0
    while len(merged) < MAX_ITEMS and any(category_lists):
        for lst in category_lists:
            if i < len(lst):
                merged.append(lst[i])
        i += 1

    return merged[:MAX_ITEMS]


def _qfilm_get(url):
    """Fetch a QFilm HTML page. Errors are isolated so TMDb updates still succeed."""
    r = requests.get(url, headers=QFILM_HEADERS, timeout=QFILM_TIMEOUT)
    r.raise_for_status()
    return r.text


def qfilm_find_player(title, year=None):
    """Find the best matching QFilm watch page and extract its iframe URL.

    Returns a small JSON-safe dict or None. This only follows normal
    search/watch/iframe links; it does not attempt to bypass access controls.
    """
    if not QFILM_ENABLED or not title:
        return None

    try:
        search_url = f"{QFILM_BASE_URL}/search.php?{urlencode({'keywords': title})}"
        html = _qfilm_get(search_url)
        soup = BeautifulSoup(html, "html.parser")

        candidates = []
        for a in soup.select("a[href]"):
            text = a.get_text(" ", strip=True)
            href = a.get("href")
            if not text or not href:
                continue
            url = urljoin(search_url, href)
            if "/watch.php" not in url:
                continue
            candidates.append({"title": text, "url": url})

        if not candidates:
            return None

        wanted = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
        year_text = str(year) if year else ""

        def score(candidate):
            text = candidate["title"].lower()
            normalized = re.sub(r"[^a-z0-9]+", " ", text).strip()
            s = 0
            if year_text and year_text in text:
                s += 30
            if wanted and wanted in normalized:
                s += 60
            wanted_words = set(wanted.split())
            s += sum(1 for w in wanted_words if len(w) >= 3 and w in normalized)
            return s

        match = max(candidates, key=score)
        if score(match) < 2:
            return None

        watch_html = _qfilm_get(match["url"])
        watch_soup = BeautifulSoup(watch_html, "html.parser")

        embed_urls = []
        for iframe in watch_soup.select("iframe[src], iframe[data-src]"):
            raw = iframe.get("src") or iframe.get("data-src")
            if not raw:
                continue
            url = urljoin(match["url"], raw.strip())
            if url.startswith(("http://", "https://")):
                embed_urls.append(url)

        if not embed_urls:
            return None

        # Follow one normal iframe level, matching the successful Termux test.
        for embed_url in embed_urls:
            try:
                embed_html = _qfilm_get(embed_url)
                embed_soup = BeautifulSoup(embed_html, "html.parser")
                nested = []
                for iframe in embed_soup.select("iframe[src], iframe[data-src]"):
                    raw = iframe.get("src") or iframe.get("data-src")
                    if not raw:
                        continue
                    player_url = urljoin(embed_url, raw.strip())
                    if player_url.startswith(("http://", "https://")):
                        nested.append(player_url)
                if nested:
                    return {
                        "type": "iframe",
                        "url": nested[0],
                        "label": "QFilm",
                        "source_url": match["url"],
                    }
            except requests.RequestException:
                pass

        return {
            "type": "iframe",
            "url": embed_urls[0],
            "label": "QFilm",
            "source_url": match["url"],
        }

    except (requests.RequestException, ValueError, UnicodeError) as exc:
        print(f"⚠️ QFilm فشل لـ {title!r}: {exc}")
        return None
    except Exception as exc:
        print(f"⚠️ QFilm parsing فشل لـ {title!r}: {exc}")
        return None


def enrich_with_qfilm(items):
    """Attach a pre-resolved QFilm iframe to each generated item."""
    if not QFILM_ENABLED:
        return items

    found = 0
    for item in items:
        player = qfilm_find_player(item.get("title"), item.get("year"))
        if player:
            item["qfilm_player"] = player
            item["qfilm_source"] = player.get("source_url")
            found += 1
            print("  ✓ QFilm -", item.get("title"), "->", player.get("url"))
        else:
            item.pop("qfilm_player", None)
            item.pop("qfilm_source", None)

    print(f"QFilm: تم العثور على Player لـ {found}/{len(items)} عنصر")
    return items


def write_sitemap(items):
    today = datetime.date.today().isoformat()
    urls = [("https://arbflix.site/", "1.0")]
    for item in items:
        loc = f"https://arbflix.site/movie.html?id={item['id']}"
        urls.append((loc, "0.7"))

    body = "\n".join(
        f"  <url><loc>{loc}</loc><lastmod>{today}</lastmod><priority>{priority}</priority></url>"
        for loc, priority in urls
    )
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}\n</urlset>\n'
    with open("sitemap.xml", "w", encoding="utf-8") as f:
        f.write(xml)


def main():
    if not API_KEY:
        print("⚠️  TMDB_API_KEY مش موجود كـ Secret.")
        return

    results = []
    for kind, tmdb_id in discover_ids():
        try:
            results.append(fetch_details(tmdb_id, kind))
            print("✓", results[-1]["type"], "-", results[-1]["title"])
        except Exception as e:
            print("✗ فشل استيراد", tmdb_id, "-", e)

    # Resolve QFilm players during the GitHub Actions build. The frontend is
    # static, so it cannot execute Python at click-time; storing the iframe
    # here makes the movie page work without a separate backend.
    results = enrich_with_qfilm(results)

    with open("movies-data.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    write_sitemap(results)

    print(f"\nتم تحديث movies-data.json و sitemap.xml تلقائيًا - {len(results)} عنصر")


if __name__ == "__main__":
    main()
