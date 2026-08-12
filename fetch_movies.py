"""
ARBFLIX — سكريبت الاستيراد التلقائي من TMDb
=================================================
بدل ما تدخل بيانات كل فيلم يدويًا (الاسم، البوستر، القصة، التقييم)،
السكريبت ده بيجيبهم تلقائيًا من TMDb (قاعدة بيانات أفلام مجانية ومرخصة)
ويبنيلك ملف movies-data.json جاهز.

خطوات الاستخدام:
------------------
1. اعمل حساب مجاني على https://www.themoviedb.org
2. من إعدادات حسابك، روح لـ API واطلب "API Key (v3 auth)" — مجاني وفوري
3. حط الـ API Key بتاعك مكان "YOUR_TMDB_API_KEY" تحت
4. في قايمة MOVIE_IDS / SERIES_IDS تحت، حط أرقام TMDb بتاعة الأفلام
   اللي عايز تضيفها (تلاقي رقم أي فيلم في آخر اللينك بتاعه على tmdb.org
   مثال: themoviedb.org/movie/1092073 → الرقم هو 1092073)
5. شغّل: pip install requests
6. شغّل: python fetch_movies.py
7. هيتبني ملف movies-data.json جديد فيه كل البيانات + روابط بوسترات حقيقية

بعد كده لازم بس تروح تحط لينكات الأفيليت بتاعتك يدويًا في كل عنصر
(الحاجة الوحيدة اللي مينفعش تتشاف تلقائي، لأنها خاصة بحسابك إنت).
"""

import json
import requests

API_KEY = "78c8955796d2c9973becd049be61f255"  # حط الـ API Key بتاعك هنا
LANGUAGE = "ar-EG"              # عشان يجيب الاسم والقصة بالعربي لو متاح

# حط أرقام TMDb بتاعة الأفلام والمسلسلات اللي عايزها هنا
# دول ٤ أفلام حقيقية من أفلام ٢٠٢٦ جاهزين كبداية — ضيف عليهم أي أرقام تانية عايزها
MOVIE_IDS = [
    1003596,  # Avengers: Doomsday (2026)
    969681,   # Spider-Man: Brand New Day (2026)
    1084242,  # Zootopia 2 (2025/2026)
    967941,   # Wicked: For Good (2025/2026)
    1170608,  # Dune: Part Three (2026)
    1084244,  # Toy Story 5 (2026)
]
SERIES_IDS = []  # مثال: [125988, 94997]

# منصات المشاهدة الافتراضية — عدّل الأفيليت لينك بعد التشغيل
DEFAULT_PLATFORM = {"name": "Shahid", "affiliate_url": "REPLACE_WITH_YOUR_AFFILIATE_LINK"}

BASE = "https://api.themoviedb.org/3"


def fetch_item(tmdb_id, kind):
    endpoint = "movie" if kind == "فيلم" else "tv"
    url = f"{BASE}/{endpoint}/{tmdb_id}"
    r = requests.get(url, params={"api_key": API_KEY, "language": LANGUAGE, "append_to_response": "videos"})
    r.raise_for_status()
    d = r.json()

    title_original = d.get("original_title") or d.get("original_name") or ""
    title_ar = d.get("title") or d.get("name") or title_original
    year_raw = d.get("release_date") or d.get("first_air_date") or ""
    year = int(year_raw[:4]) if year_raw else None
    genre = d["genres"][0]["name"] if d.get("genres") else "عام"
    rating = round(d.get("vote_average", 0), 1)
    poster_path = d.get("poster_path")  # ده اللي بيخليك تشوف بوستر حقيقي بدل التدرج اللوني
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
        "title": title_original,   # العنوان الرئيسي بلغته الأصلية (إنجليزي للأفلام الأجنبية)
        "title_ar": title_ar,      # الاسم بالعربي محفوظ لو احتجناه لاحقًا
        "type": kind,
        "year": year,
        "rating": rating,
        "genre": genre,
        "poster_path": poster_path,
        "overview": overview,
        "trailer_key": trailer_key,
        "platforms": [DEFAULT_PLATFORM],
    }


def main():
    if API_KEY == "YOUR_TMDB_API_KEY":
        print("⚠️  لازم تحط الـ API Key بتاعك الأول في أول السكريبت.")
        return

    results = []
    for mid in MOVIE_IDS:
        results.append(fetch_item(mid, "فيلم"))
        print("✓ استوردت فيلم:", results[-1]["title"])
    for sid in SERIES_IDS:
        results.append(fetch_item(sid, "مسلسل"))
        print("✓ استوردت مسلسل:", results[-1]["title"])

    with open("movies-data.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nتم! {len(results)} عنصر اتكتب في movies-data.json")
    print("متبقى بس تحط لينكات الأفيليت الحقيقية بدل REPLACE_WITH_YOUR_AFFILIATE_LINK")


if __name__ == "__main__":
    main()
