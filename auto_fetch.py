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
MAX_ITEMS = 36  # أقصى عدد أفلام/مسلسلات هيفضل ظاهر في السايت (الأقدم بيتشال تلقائيًا)

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
    """يجيب مجموعة (id, kind) من Trending/Upcoming/Popular عالميًا + محتوى مصري/عربي مخصص"""
    movie_paths = ["trending/movie/week", "movie/upcoming", "movie/popular"]
    tv_paths = ["trending/tv/week", "tv/popular", "tv/on_the_air"]

    movie_pairs, tv_pairs = [], []
    seen = set()

    # محتوى مصري بالتحديد (منشأ مصر) - أولوية عشان محتوى مصري ما يتزحلقش برة السقف
    _pull("discover/movie", {"with_origin_country": "EG", "sort_by": "popularity.desc"},
          kind="فيلم", seen=seen, bucket=movie_pairs)
    _pull("discover/tv", {"with_origin_country": "EG", "sort_by": "popularity.desc"},
          kind="مسلسل", seen=seen, bucket=tv_pairs)

    # محتوى عربي بشكل عام (لغة أصلية عربي) كتغطية إضافية
    _pull("discover/movie", {"with_original_language": "ar", "sort_by": "popularity.desc"},
          kind="فيلم", seen=seen, bucket=movie_pairs)
    _pull("discover/tv", {"with_original_language": "ar", "sort_by": "popularity.desc"},
          kind="مسلسل", seen=seen, bucket=tv_pairs)

    # بعدين نكمل بالأجانب الرائجة عالميًا
    for path in movie_paths:
        _pull(path, kind="فيلم", seen=seen, bucket=movie_pairs)
    for path in tv_paths:
        _pull(path, kind="مسلسل", seen=seen, bucket=tv_pairs)

    # نتبادل فيلم/مسلسل عشان النوعين يفضلوا موجودين حتى لو في سقف للعدد
    pairs = []
    for a, b in zip(movie_pairs, tv_pairs):
        pairs.append(a)
        pairs.append(b)
    pairs += movie_pairs[len(tv_pairs):] + tv_pairs[len(movie_pairs):]

    return pairs[:MAX_ITEMS]


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

    print(f"\nتم تحديث movies-data.json تلقائيًا - {len(results)} عنصر")


if __name__ == "__main__":
    main()
