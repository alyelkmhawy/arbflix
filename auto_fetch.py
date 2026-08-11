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

import json
import os
import requests

API_KEY = os.environ.get("TMDB_API_KEY", "")
AFFILIATE_URL = os.environ.get("AFFILIATE_URL", "REPLACE_WITH_YOUR_AFFILIATE_LINK")
PLATFORM_NAME = os.environ.get("PLATFORM_NAME", "Shahid")
LANGUAGE = "ar-EG"
MAX_ITEMS = 24  # أقصى عدد أفلام هيفضل ظاهر في السايت (الأقدم بيتشال تلقائيًا)

BASE = "https://api.themoviedb.org/3"
DEFAULT_PLATFORM = {"name": PLATFORM_NAME, "affiliate_url": AFFILIATE_URL}


def fetch_details(tmdb_id, kind):
    endpoint = "movie" if kind == "فيلم" else "tv"
    r = requests.get(f"{BASE}/{endpoint}/{tmdb_id}", params={"api_key": API_KEY, "language": LANGUAGE})
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
        "platforms": [DEFAULT_PLATFORM],
    }


def discover_ids():
    """يجيب مجموعة أرقام أفلام من Trending + Upcoming بدون تكرار"""
    ids = []
    for path in ["trending/movie/week", "movie/upcoming", "movie/popular"]:
        r = requests.get(f"{BASE}/{path}", params={"api_key": API_KEY, "language": LANGUAGE, "page": 1})
        if r.ok:
            for item in r.json().get("results", []):
                if item["id"] not in ids:
                    ids.append(item["id"])
    return ids[:MAX_ITEMS]


def main():
    if not API_KEY:
        print("⚠️  TMDB_API_KEY مش موجود كـ Secret.")
        return

    results = []
    for tmdb_id in discover_ids():
        try:
            results.append(fetch_details(tmdb_id, "فيلم"))
            print("✓", results[-1]["title"])
        except Exception as e:
            print("✗ فشل استيراد", tmdb_id, "-", e)

    with open("movies-data.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nتم تحديث movies-data.json تلقائيًا - {len(results)} عنصر")


if __name__ == "__main__":
    main()
