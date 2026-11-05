#!/usr/bin/env python3
"""
Scraper MagisTV24 - Extrae streams reales HLS (Castellano)
Versión mejorada con más debug
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import re
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://magistv24.com"
CARTELERA_URL = f"{BASE_URL}/cartelera-peliculas/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Referer": "https://magistv24.com/",
    "Connection": "keep-alive",
}

MAX_PAGES = 2
MAX_MOVIES = 30
TREMBED = 1          # 1 = Castellano
WORKERS = 4


def get_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def scrape_list(session, max_pages=2) -> list[dict]:
    movies = []
    seen = set()

    for page in range(1, max_pages + 1):
        url = CARTELERA_URL if page == 1 else f"{CARTELERA_URL}page/{page}/"
        print(f"[*] Listando: {url}")
        try:
            r = session.get(url, timeout=25)
            r.raise_for_status()
            soup = BeautifulSoup(r.content, "lxml")

            for li in soup.select("li[id^='post-']"):
                post_id = li.get("id", "").replace("post-", "")
                if not post_id.isdigit() or post_id in seen:
                    continue

                title_tag = li.select_one("h2.entry-title")
                title = title_tag.get_text(strip=True) if title_tag else "Sin título"

                year_tag = li.select_one("span.year")
                year = year_tag.get_text(strip=True) if year_tag else ""

                rating_tag = li.select_one("span.vote")
                rating = ""
                if rating_tag:
                    rating = rating_tag.get_text(strip=True).replace("TMDB", "").strip()

                img = li.select_one("img")
                poster = ""
                if img:
                    poster = img.get("src") or img.get("data-src") or ""
                    if poster.startswith("//"):
                        poster = "https:" + poster

                movies.append({
                    "id": post_id,
                    "title": title,
                    "year": year,
                    "rating": rating,
                    "poster": poster,
                })
                seen.add(post_id)

                if len(movies) >= MAX_MOVIES:
                    return movies

            time.sleep(1.0)
        except Exception as e:
            print(f"[!] Error página {page}: {e}")
            break

    return movies


def extract_stream(session, post_id: str, title: str = "") -> str | None:
    """Extrae el master.m3u8 de la opción Castellano"""
    try:
        # 1. Embed de MagisTV
        embed_url = f"{BASE_URL}/?trembed={TREMBED}&trid={post_id}&trtype=1"
        r = session.get(embed_url, timeout=20)
        if r.status_code != 200:
            print(f"    → Embed status {r.status_code}")
            return None

        # Buscar iframe de fastream
        match = re.search(r'(https?://(?:www\.)?fastream\.to/embed-[a-zA-Z0-9]+\.html)', r.text)
        if not match:
            # A veces viene escapado
            match = re.search(r'(https?:\\/\\/fastream\.to\\/embed-[a-zA-Z0-9]+\.html)', r.text)
            if match:
                fastream_url = match.group(1).replace("\\/", "/")
            else:
                print(f"    → No se encontró iframe fastream")
                return None
        else:
            fastream_url = match.group(1)

        # 2. Página de fastream
        r2 = session.get(fastream_url, timeout=20, headers={
            **HEADERS,
            "Referer": embed_url
        })
        if r2.status_code != 200:
            print(f"    → Fastream status {r2.status_code}")
            return None

        text = r2.text

        # 3. Buscar el m3u8 (varios patrones)
        patterns = [
            r'(https?://[^"\'\\s]+?master\.m3u8[^"\'\\s]*)',
            r'(https?://s\d+\.fastream\.to/[^"\'\\s]+?\.m3u8[^"\'\\s]*)',
            r'(https?://[^"\'\\s]+?\.m3u8\?t=[^"\'\\s]+)',
            r'sources?\s*[:=]\s*\[\s*\{\s*file\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
        ]

        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                url = m.group(1) if m.lastindex else m.group(0)
                url = url.replace("\\/", "/").replace("\\u0026", "&").strip("'\"")
                if ".m3u8" in url:
                    return url

        print(f"    → No se encontró m3u8 en la página de fastream")
        return None

    except Exception as e:
        print(f"    → Excepción: {e}")
        return None


def process_movie(session, movie: dict) -> dict | None:
    stream = extract_stream(session, movie["id"], movie["title"])
    if not stream:
        return None
    movie["stream"] = stream
    return movie


def generate_m3u(movies: list[dict], filename="playlist.m3u"):
    lines = [
        "#EXTM3U",
        f"# Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"# Opción: Castellano",
        f"# Fuente: {CARTELERA_URL}",
        "",
    ]

    for m in movies:
        title = m["title"]
        if m.get("year"):
            title += f" ({m['year']})"
        if m.get("rating"):
            title += f" ★{m['rating']}"

        logo = f' tvg-logo="{m["poster"]}"' if m.get("poster") else ""
        group = ' group-title="Películas Castellano"'

        lines.append(f'#EXTINF:-1{logo}{group},{title}')
        lines.append(m["stream"])
        lines.append("")

    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n[✓] Generado {filename} con {len(movies)} streams")


def main():
    session = get_session()

    print("[*] Scrapeando listado de películas...")
    movies = scrape_list(session, max_pages=MAX_PAGES)
    print(f"[*] Encontradas {len(movies)} películas. Extrayendo streams Castellano...\n")

    valid = []
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(process_movie, session, m): m for m in movies}
        for future in as_completed(futures):
            result = future.result()
            if result:
                valid.append(result)
                print(f"  [+] {result['title']}")
            else:
                m = futures[future]
                print(f"  [-] Falló: {m['title']}")

    if not valid:
        print("\n[!] No se pudo extraer ningún stream")
        sys.exit(1)

    id_order = {m["id"]: i for i, m in enumerate(movies)}
    valid.sort(key=lambda x: id_order.get(x["id"], 999))

    generate_m3u(valid)


if __name__ == "__main__":
    main()
