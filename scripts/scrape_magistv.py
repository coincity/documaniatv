#!/usr/bin/env python3
"""
Scraper MagisTV24 - Extrae streams reales HLS (Castellano)
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": BASE_URL,
}

# Configuración
MAX_PAGES = 2          # Páginas de cartelera a scrapear
MAX_MOVIES = 40        # Límite de películas (para no saturar)
TREMBED = 1            # 0=Latino, 1=Castellano, 2=VOSE
WORKERS = 6            # Hilos paralelos


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

            time.sleep(1.2)
        except Exception as e:
            print(f"[!] Error página {page}: {e}")
            break

    return movies


def extract_stream(session, post_id: str) -> str | None:
    """Extrae el master.m3u8 de la opción Castellano (trembed=1)"""
    try:
        # 1. Pedir el embed interno de MagisTV
        embed_url = f"{BASE_URL}/?trembed={TREMBED}&trid={post_id}&trtype=1"
        r = session.get(embed_url, timeout=20)
        r.raise_for_status()

        # Buscar el iframe de fastream
        match = re.search(r'src=["\'](https?://fastream\.to/embed-[^"\']+)["\']', r.text)
        if not match:
            # A veces viene sin comillas o con data-src
            match = re.search(r'(https?://fastream\.to/embed-[a-z0-9]+\.html)', r.text)
        if not match:
            return None

        fastream_url = match.group(1)

        # 2. Pedir la página de fastream
        r2 = session.get(fastream_url, timeout=20, headers={**HEADERS, "Referer": embed_url})
        r2.raise_for_status()

        # 3. Extraer el master.m3u8 (está dentro del JS ofuscado)
        # Buscamos patrones típicos de fastream
        patterns = [
            r'(https?://[^"\'\s]+?\.m3u8[^"\'\s]*)',
            r'(https?://s\d+\.fastream\.to/hls2/[^"\'\s]+master\.m3u8[^"\'\s]*)',
        ]

        for pat in patterns:
            m = re.search(pat, r2.text)
            if m:
                url = m.group(1)
                # Limpiar posibles escapes
                url = url.replace("\\/", "/").replace("\\u0026", "&")
                if "master.m3u8" in url or ".m3u8" in url:
                    return url

        return None
    except Exception as e:
        print(f"  [!] Error extrayendo {post_id}: {e}")
        return None


def process_movie(session, movie: dict) -> dict | None:
    stream = extract_stream(session, movie["id"])
    if not stream:
        return None

    movie["stream"] = stream
    return movie


def generate_m3u(movies: list[dict], filename="playlist.m3u"):
    lines = [
        "#EXTM3U",
        f"# Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"# Opción: Castellano (trembed={TREMBED})",
        f"# Fuente: {CARTELERA_URL}",
        "# Los enlaces caducan aprox. cada 12 horas → actualizar playlist frecuentemente",
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

    print(f"\n[✓] Generado {filename} con {len(movies)} streams válidos")


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
        print("[!] No se pudo extraer ningún stream")
        sys.exit(1)

    # Ordenar por el orden original
    id_order = {m["id"]: i for i, m in enumerate(movies)}
    valid.sort(key=lambda x: id_order.get(x["id"], 999))

    generate_m3u(valid)


if __name__ == "__main__":
    main()
