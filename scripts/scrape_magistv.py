#!/usr/bin/env python3
"""
Scraper MagisTV24 - Versión de diagnóstico
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import re
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

BASE_URL = "https://magistv24.com"
CARTELERA_URL = f"{BASE_URL}/cartelera-peliculas/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Referer": "https://magistv24.com/",
}

MAX_PAGES = 1
MAX_MOVIES = 8          # Solo pocas para diagnosticar
TREMBED = 1
WORKERS = 2


def get_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def scrape_list(session) -> list[dict]:
    movies = []
    seen = set()
    url = CARTELERA_URL
    print(f"[*] Listando: {url}")
    r = session.get(url, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "lxml")

    for li in soup.select("li[id^='post-']"):
        post_id = li.get("id", "").replace("post-", "")
        if not post_id.isdigit() or post_id in seen:
            continue

        title_tag = li.select_one("h2.entry-title")
        title = title_tag.get_text(strip=True) if title_tag else "Sin título"

        movies.append({"id": post_id, "title": title})
        seen.add(post_id)
        if len(movies) >= MAX_MOVIES:
            break
    return movies


def extract_stream(session, post_id: str, title: str) -> str | None:
    try:
        embed_url = f"{BASE_URL}/?trembed={TREMBED}&trid={post_id}&trtype=1"
        print(f"  → Probando embed: {embed_url}")
        r = session.get(embed_url, timeout=20)

        # Guardar el HTML del embed para diagnóstico
        with open(f"debug_embed_{post_id}.html", "w", encoding="utf-8") as f:
            f.write(r.text)

        if r.status_code != 200:
            print(f"    Status embed: {r.status_code}")
            return None

        # Buscar cualquier iframe
        iframes = re.findall(r'src=["\']([^"\']+)["\']', r.text)
        print(f"    Iframes encontrados: {iframes[:3]}")

        match = re.search(r'(https?://(?:www\.)?fastream\.to/embed-[a-zA-Z0-9]+\.html)', r.text)
        if not match:
            print(f"    → No se encontró iframe fastream")
            # Mostrar un poco del HTML
            print(f"    Primeros 300 chars: {r.text[:300].replace(chr(10), ' ')}")
            return None

        fastream_url = match.group(1)
        print(f"    Fastream URL: {fastream_url}")

        r2 = session.get(fastream_url, timeout=20, headers={**HEADERS, "Referer": embed_url})

        with open(f"debug_fastream_{post_id}.html", "w", encoding="utf-8") as f:
            f.write(r2.text)

        if r2.status_code != 200:
            print(f"    Status fastream: {r2.status_code}")
            return None

        # Buscar m3u8
        m3u8s = re.findall(r'(https?://[^"\'\s\\]+?\.m3u8[^"\'\s\\]*)', r2.text)
        print(f"    m3u8 encontrados: {m3u8s[:2]}")

        if m3u8s:
            url = m3u8s[0].replace("\\/", "/")
            return url

        print(f"    → No se encontró m3u8")
        print(f"    Primeros 400 chars de fastream: {r2.text[:400].replace(chr(10), ' ')}")
        return None

    except Exception as e:
        print(f"    → Excepción: {e}")
        return None


def main():
    session = get_session()
    movies = scrape_list(session)
    print(f"[*] Probando {len(movies)} películas...\n")

    valid = []
    for m in movies:
        print(f"[*] {m['title']} (id={m['id']})")
        stream = extract_stream(session, m["id"], m["title"])
        if stream:
            print(f"  [+] ÉXITO: {stream[:80]}...")
            m["stream"] = stream
            valid.append(m)
        else:
            print(f"  [-] Falló\n")
        time.sleep(1.5)

    if not valid:
        print("\n[!] Ningún stream extraído")
        # Listar archivos de debug generados
        print("Archivos de debug creados:")
        for f in os.listdir("."):
            if f.startswith("debug_"):
                print(f"  - {f}")
        sys.exit(1)

    print(f"\n[✓] Se extrajeron {len(valid)} streams")


if __name__ == "__main__":
    main()
