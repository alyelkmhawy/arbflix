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
import requests

API_KEY = os.environ.get("TMDB_API_KEY", "")
AFFILIATE_URL = os.environ.get("AFFILIATE_URL", "REPLACE_WITH_YOUR_AFFILIATE_LINK")
PLATFORM_NAME = os.environ.get("PLATFORM_NAME", "Shahid")
LANGUAGE = "ar-EG"
MAX_ITEMS = 200  # أقصى عدد أفلام/مسلسلات هيفضل ظاهر في السايت (الأقدم بيتشال تلقائيًا)

BASE = "https://api.themoviedb.org/3"
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

    with open("movies-data.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    write_sitemap(results)

    print(f"\nتم تحديث movies-data.json و sitemap.xml تلقائيًا - {len(results)} عنصر")


if __name__ == "__main__":
    main()
