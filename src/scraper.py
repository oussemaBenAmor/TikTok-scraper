#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import asyncio
import contextlib
import csv
import json
import os
import re
from typing import Dict, List, Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

PROFILE_BASE = "https://www.tiktok.com"




'''
On va nettoiyer le nom d’utilisateur TikTok en retirant les espaces et le symbole @, afin d’obtenir un format uniforme utilisable pour les URL ou fichiers
'''
def normalize_username(username: str) -> str:
    username = username.strip()
    return username[1:] if username.startswith("@") else username


'''
Maintenant, on va génèrer l’URL complète du profil TikTok à partir d’un nom d’utilisateur normalisé,
en forçant la langue anglaise pour garantir la stabilité du scraping
'''
def build_profile_url(username: str) -> str:
    username = normalize_username(username)
    return f"{PROFILE_BASE}/@{username}?lang=en"


'''
Maintenant, on va récupèrer l’ID numérique d’une vidéo TikTok à partir de son URL, 
ce qui permet d’identifier et de manipuler la vidéo de manière unique.
'''
def extract_video_id_from_url(url: str) -> str:
    try:
        path = urlparse(url).path
        m = re.search(r"/video/(\d+)", path)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""


'''
Maintenant, on va transformer les nombres abrégés TikTok (comme 12.3K, 4M ou 789) en entiers,
en interprétant correctement les suffixes K, M et B.
'''
def _parse_abbrev_num(txt: Optional[str]) -> Optional[int]:
    if txt is None:
        return None
    txt = txt.strip().upper().replace(",", "")
    if not txt:
        return None
    m = re.match(r"^([0-9]*\.?[0-9]+)\s*([KMB])?$", txt)
    if not m:
        if re.fullmatch(r"\d+", txt):
            return int(txt)
        return None
    num = float(m.group(1))
    suf = m.group(2)
    if suf == "K":
        num *= 1_000
    elif suf == "M":
        num *= 1_000_000
    elif suf == "B":
        num *= 1_000_000_000
    return int(num)


'''
Maintenant, on va automatiser la fermeture ou l’acceptation des bannières de cookies sur une page TikTok en détectant et cliquant sur les boutons
de consentement disponibles parce qu'il y a souvent des bannières de cookies ou de consentement qui bloquent l’interaction avec la page tant qu'on
n’as pas cliqué sur “Accepter” et c'est pour récupérer les données des vidéos.
'''
async def click_cookies_or_consent(page) -> None:
    candidates = [
        'button[data-e2e="cookie-banner-accept-button"]',
        'button:has-text("Accept all")',
        'button:has-text("Accept All")',
        'button:has-text("Allow all")',
        'button:has-text("Tout accepter")',
        'text=Accept',
        'text=I agree',
    ]
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible():
                await loc.click(timeout=1000)
                return
        except Exception:
            continue


'''
Maintenant, in va récupèrer et analyser le JSON SIGI_STATE embarqué dans la page TikTok, qui contient les informations des vidéos.
Si un video_id_hint est fourni et correspond à une vidéo, elle renvoie les données de cette vidéo.
Sinon, elle renvoie la première vidéo disponible, ou un dictionnaire vide si aucune donnée n’est trouvée.
'''
async def parse_sigi_state(page, video_id_hint: str = "") -> Dict:
    try:
        script = page.locator('script#SIGI_STATE')
        await script.wait_for(state="attached", timeout=10000)
        raw = await script.inner_text()
        data = json.loads(raw)
        item_module = data.get("ItemModule", {})
        if not item_module:
            return {}
        if video_id_hint and video_id_hint in item_module:
            return item_module[video_id_hint]
        for _, item in item_module.items():
            return item
    except Exception:
        pass
    return {}


'''
Maintenant, on va récupèrer le contenu d’une balise meta OpenGraph sur la page, comme l’image, la description ou le nombre de vues d’une vidéo 
TikTok.
La fonction prend le nom de l’info qu'on veut et te renvoie sa valeur.
Si l’info n’existe pas ou qu’il y a un problème, elle renvoie juste une chaîne vide.
'''
async def get_meta_content(page, prop: str) -> str:
    try:
        return await page.eval_on_selector(
            f'meta[property="{prop}"]',
            "el => el ? el.content : ''"
        ) or ""
    except Exception:
        return ""


'''
Petit utilitaire: normaliser les URL d'images éventuellement "protocol-relative" (//... -> https://...)
'''
def _normalize_url(u: Optional[str]) -> str:
    if not u:
        return ""
    u = u.strip()
    if u.startswith("//"):
        return "https:" + u
    return u


'''
Maintenant on va trouver rapidement le premier texte utile sur une page, même si la structure HTML change un peu comme la description d’une vidéo,
le nombre de vues affiché sous la vidéo, un nom d’utilisateur ou un hashtag.
'''
async def _first_text(page, selectors, timeout=2500) -> str:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            await loc.wait_for(state="visible", timeout=timeout)
            txt = await loc.text_content()
            if txt and txt.strip():
                return txt.strip()
        except Exception:
            pass
    return ""


'''
Cette fonction cherche un élément sur la page en essayant plusieurs endroits possibles et récupère la première valeur d’un attribut précis comme
l’URL d’une image,l’image de couverture.
'''
async def _first_attr(page, selectors, attr: str, timeout=2000) -> Optional[str]:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            await loc.wait_for(state="attached", timeout=timeout)
            val = await loc.get_attribute(attr)
            if val:
                return val
        except Exception:
            pass
    return None


'''
Elle permet de récupérer le nombre de vues directement depuis le texte de la page quand les autres méthodes échouent.
C'est le dernier recours pour obtenir les vues
'''
async def _views_from_page_text(page) -> Optional[int]:
    try:
        txt = await page.evaluate("() => document.body.innerText")
        if not txt:
            return None
        
        m = re.search(r"([0-9][0-9,.\s]*[KMB]?)\s+(views|vues)\b", txt, flags=re.I)
        if m:
            return _parse_abbrev_num(m.group(1))
    except Exception:
        pass
    return None


'''
Petit utilitaire: récupérer un thumbnail via l'endpoint oEmbed de TikTok quand les autres sources sont vides.
On ajoute Referer et User-Agent pour fiabiliser la réponse.
'''
async def fetch_oembed_thumbnail(context, video_url: str, ua: str = "") -> str:
    try:
        headers = {"Referer": video_url, "Accept": "application/json"}
        if ua:
            headers["User-Agent"] = ua
            headers["Accept-Language"] = "en-US,en;q=0.9"
        resp = await context.request.get(
            "https://www.tiktok.com/oembed",
            params={"url": video_url},
            headers=headers,
            timeout=10000
        )
        if resp.ok:
            data = await resp.json()
            thumb = (data.get("thumbnail_url") or "").strip()
            return _normalize_url(thumb)
    except Exception:
        pass
    return ""


'''
Autre fallback: certaines pages exposent un JSON-LD avec "thumbnailUrl".
'''
async def fetch_jsonld_thumbnail(page) -> str:
    try:
        scripts = await page.locator('script[type="application/ld+json"]').all()
        for s in scripts:
            try:
                raw = await s.text_content()
                if not raw:
                    continue
                data = json.loads(raw)
                candidates = data if isinstance(data, list) else [data]
                for obj in candidates:
                    thumb = obj.get("thumbnailUrl")
                    if isinstance(thumb, list) and thumb:
                        return _normalize_url(str(thumb[0]))
                    if isinstance(thumb, str) and thumb.strip():
                        return _normalize_url(thumb)
            except Exception:
                continue
    except Exception:
        pass
    return ""


'''
Cette fonction fait défiler la page d’un profil TikTok et récupère les vidéos visibles dans la grille, en enregistrant pour chacune son URL, 
le nombre de vues affiché et un éventuel thumbnail de la vignette (grid_thumb) en dernier recours.
'''
async def gather_profile_items(page, username: str, limit: int = 50, wait_ms: int = 600) -> List[Dict]:
    items: Dict[str, Dict] = {}
    last_count = -1
    retries_same_count = 0
    username = normalize_username(username)
    target_pattern = f"/@{username}/video/"

    async def scrape_grid_batch() -> Dict[str, Dict]:
        data = await page.evaluate("""
        () => {
          const containers = Array.from(document.querySelectorAll(
            '[data-e2e="user-post-item"], [data-e2e="tiktok-post"], li:has(a[href*="/video/"])'
          ));
          return containers.map(el => {
            const a = el.querySelector('a[href*="/video/"]');
            const href = a ? (a.href || '').split('?')[0] : '';

            // Plusieurs chemins possibles pour le texte des vues
            const picks = [
              '[data-e2e="video-views"] strong',
              'strong[data-e2e="video-views"]',
              '[data-e2e="view-count"]',
              'span[data-e2e="video-views"]',
              'span:has(svg[aria-label*="views" i])',
              'span:has(svg[aria-label*="vues" i])',
              'strong'
            ];

            let txt = '';
            for (const sel of picks) {
              const n = el.querySelector(sel);
              if (n && n.textContent && n.textContent.trim()) {
                txt = n.textContent.trim();
                break;
              }
            }
            // Fallback aria-label sur le conteneur
            if (!txt && el.getAttribute('aria-label')) {
              txt = el.getAttribute('aria-label');
            }
            // Fallback aria-label sur l'ancre
            if (!txt && a && a.getAttribute('aria-label')) {
              txt = a.getAttribute('aria-label');
            }

            // Essayer de récupérer un thumbnail depuis la grille
            const imgEl = el.querySelector('img') || (a ? a.querySelector('img') : null);
            let gridThumb = '';
            if (imgEl) {
              gridThumb = imgEl.currentSrc || imgEl.src || '';
              if (!gridThumb && imgEl.srcset) {
                gridThumb = imgEl.srcset.split(',')[0].trim().split(' ')[0];
              }
            }

            return { href, txt, gridThumb };
          });
        }
        """)
        out: Dict[str, Dict] = {}
        for row in data:
            href = (row.get("href") or "").strip()
            if not href or target_pattern not in href:
                continue
            url = href if href.startswith("http") else PROFILE_BASE + href
            raw = (row.get("txt") or "").strip()
            m = re.search(r"([0-9][0-9,.\s]*[KMBkmb]?)", raw) if raw else None
            val = _parse_abbrev_num(m.group(1)) if m else (_parse_abbrev_num(raw) if raw else 0)
            grid_thumb = (row.get("gridThumb") or "").strip()
            out[url] = {
                "grid_views": int(val or 0),
                "grid_thumb": grid_thumb,
            }
        return out

    while True:
        batch = await scrape_grid_batch()
        items.update(batch)
        if limit and len(items) >= limit:
            break
        await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
        await page.wait_for_timeout(wait_ms)
        if len(items) == last_count:
            retries_same_count += 1
        else:
            retries_same_count = 0
            last_count = len(items)
        if retries_same_count >= 5:
            break

    urls = list(items.keys())
    if limit:
        urls = urls[:limit]
    return [{"url": u, "grid_views": items[u]["grid_views"], "grid_thumb": items[u]["grid_thumb"]} for u in urls]


'''
Cette fonction ouvre une page vidéo TikTok et en extrait toutes les informations principales comme:
-Description de la vidéo
-thumbnail
-Nombre de vues
-Nombre de likes
-Nombre de commentaires

On ajoute un paramètre grid_thumb_hint utilisé en dernier recours si toutes les autres sources échouent.
'''
async def scrape_video_details(page, url: str, grid_views_hint: int = 0, grid_thumb_hint: str = "", timeout_ms: int = 30000) -> Optional[Dict]:
    try:
        await page.goto(url, timeout=timeout_ms, wait_until="load")
        
        await page.wait_for_timeout(900)  
    except PlaywrightTimeoutError:
        return None
    except Exception:
        return None

    await click_cookies_or_consent(page)

    vid = extract_video_id_from_url(url)
    item = await parse_sigi_state(page, video_id_hint=vid) or {}

    desc = item.get("desc") or ""
    stats = item.get("stats") or {}
    play_count = stats.get("playCount")
    like_count = stats.get("diggCount")
    comment_count = stats.get("commentCount")

    
    thumb = ""
    video_obj = item.get("video") or {}
    for k in ["cover", "originCover", "dynamicCover", "downloadAddr", "poster"]:
        v = video_obj.get(k)
        if isinstance(v, str) and v.strip():
            v = _normalize_url(v)
            if v.startswith("http"):
                thumb = v
                break

    
    if not thumb:
        for prop in ("og:image", "og:image:secure_url", "twitter:image", "twitter:image:src"):
            t = _normalize_url(await get_meta_content(page, prop))
            if t and t.startswith("http"):
                thumb = t
                break

    
    if not thumb:
        poster = await _first_attr(page, ["video", "video[data-e2e='video-player']"], "poster", timeout=1500)
        poster = _normalize_url(poster)
        if poster and poster.startswith("http"):
            thumb = poster

    
    if not thumb:
        t = await fetch_jsonld_thumbnail(page)
        if t and t.startswith("http"):
            thumb = t

    
    if not thumb:
        ua = await page.evaluate("() => navigator.userAgent")
        t = await fetch_oembed_thumbnail(page.context, url, ua=ua)
        if t and t.startswith("http"):
            thumb = t

    
    if not thumb and grid_thumb_hint:
        t = _normalize_url(grid_thumb_hint)
        if t and t.startswith("http"):
            thumb = t

    if like_count is None:
        like_txt = await _first_text(page, [
            '[data-e2e="like-count"]',
            'button[data-e2e="like-count"]',
            'button:has(svg[aria-label*="Like"])',
        ], timeout=2000)
        like_count = _parse_abbrev_num(like_txt) or 0

    if comment_count is None:
        comment_txt = await _first_text(page, [
            '[data-e2e="comment-count"]',
            'button[data-e2e="comment-count"]',
            'button:has(svg[aria-label*="Comment"])',
        ], timeout=2000)
        comment_count = _parse_abbrev_num(comment_txt) or 0

    if play_count is None or int(play_count or 0) == 0:
        if grid_views_hint and grid_views_hint > 0:
            play_count = int(grid_views_hint)
        else:
            view_txt = await _first_text(page, [
                'strong[data-e2e="browse-video-views"]',
                '[data-e2e="browse-video-views"] strong',
                '[data-e2e="video-views"] strong',
                'span[data-e2e="video-views"]',
            ], timeout=2000)
            views = _parse_abbrev_num(view_txt) if view_txt else None
            if views is None:
                meta = await get_meta_content(page, "og:video:views")
                views = _parse_abbrev_num(meta) if meta else None
            if views is None:
                views = await _views_from_page_text(page)
            play_count = int(views or 0)

    if not desc:
        desc = await _first_text(page, [
            '[data-e2e="browse-video-desc"]',
            'h1[data-e2e="browse-video-desc"]',
            'div[data-e2e="video-desc"]',
        ], timeout=2000) or (await get_meta_content(page, "og:description")) or ""

    return {
        "url": url,
        "description": desc.strip(),
        "thumbnail": thumb or "",
        "views": int(play_count or 0),
        "likes": int(like_count or 0),
        "comments": int(comment_count or 0),
    }


'''
Cette fonction orchestrate tout le scraping d’un profil TikTok de A à Z :

1-Lancement du navigateur avec Playwright, en mode headless ou visible.

2-Blocage des ressources lourdes pour aller plus vite.

3-Ouverture de la page profil et collecte des vidéos visibles dans la grille.

4-Scraping parallèle des vidéos (2 à 4 pages à la fois) pour récupérer :

URL, description, thumbnail, vues, likes, commentaires.

5-Fermeture propre du navigateur et du contexte.

6-Retourne une liste de dictionnaires, une par vidéo, avec toutes les infos.
'''
async def scrape_tiktok_profile_async(
    username: str,
    limit: int = 20,
    headless: bool = True,
    timeout_ms: int = 30000,
    parallel_pages: int = 3
) -> List[Dict]:
    username = normalize_username(username)
    profile_url = build_profile_url(username)

    proxy_server = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    proxy = {"server": proxy_server} if proxy_server else None

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless, proxy=proxy)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
            viewport={"width": 1366, "height": 900},
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        
        async def _route(route):
            req = route.request
            url = req.url
            rtype = req.resource_type
            if rtype in {"media"} or url.endswith((".m3u8", ".mpd", ".mp4")):
                return await route.abort()
            return await route.continue_()
        await context.route("**/*", _route)

        page = await context.new_page()
        try:
            await page.goto(profile_url, timeout=timeout_ms, wait_until="domcontentloaded")
            await page.wait_for_timeout(800)
        except Exception as e:
            await context.close()
            await browser.close()
            raise RuntimeError(f"Échec d’ouverture du profil: {e}")

        await click_cookies_or_consent(page)
        items = await gather_profile_items(page, username=username, limit=limit, wait_ms=600)
        if not items:
            await context.close()
            await browser.close()
            raise RuntimeError("Aucune vidéo trouvée (profil vide/privé/bloqué).")

        sem = asyncio.Semaphore(max(1, int(parallel_pages)))

        async def scrape_one(it):
            async with sem:
                p = await context.new_page()
                try:
                    return await scrape_video_details(
                        p,
                        it["url"],
                        grid_views_hint=it.get("grid_views", 0),
                        grid_thumb_hint=it.get("grid_thumb", ""),
                        timeout_ms=timeout_ms
                    )
                finally:
                    with contextlib.suppress(Exception):
                        await p.close()

        tasks = [scrape_one(it) for it in items]
        results = await asyncio.gather(*tasks)
        rows = [r for r in results if r]

        await context.close()
        await browser.close()

    return rows


'''
Cette fonction vérifie que le dossier où tu veux enregistrer un fichier existe.
Si le dossier n’existe pas, elle le crée automatiquement.
'''
def ensure_output_dir(path: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


'''
Maintenant, on va voir un échantillon rapide et lisible des résultats directement dans la console.
'''
def print_sample(rows: List[Dict], n: int = 10) -> None:
    print("\nExtrait des premières lignes:")
    for i, r in enumerate(rows[:n], 1):
        print(
            f"{i:02d}. url={r['url']}\n"
            f"    vues={r['views']} likes={r['likes']} commentaires={r['comments']}\n"
            f"    desc={r['description'][:100]!r}\n"
            f"    thumbnail={r['thumbnail'][:120] if r['thumbnail'] else ''}\n"
        )


'''
Cette fonction sert à exécuter le scraper depuis la console, gérer les options, lancer le scraping, enregistrer les données et 
afficher un aperçu.
'''
async def run_cli_async():
    parser = argparse.ArgumentParser(description="Scraper les vidéos d’un profil TikTok public et exporter en CSV.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--username", type=str, help="Nom d’utilisateur TikTok (avec ou sans @), ex: hugodecrypte")
    group.add_argument("--profile-url", type=str, help="URL complète du profil, ex: https://www.tiktok.com/@hugodecrypte")

    
    try:
        BooleanFlag = argparse.BooleanOptionalAction  
    except AttributeError:
        BooleanFlag = None

    parser.add_argument("--limit", type=int, default=50, help="Nombre max de vidéos à scraper (défaut: 50)")
    parser.add_argument("--output", type=str, default="", help="Chemin CSV de sortie (défaut: /data/tiktok_<username>.csv)")
    if BooleanFlag:
        parser.add_argument("--headless", default=True, action=BooleanFlag, help="Mode headless (défaut: True). Utilisez --no-headless pour afficher le navigateur.")
    else:
        parser.add_argument("--headless", action="store_true", help="Mode headless (active si présent).")
    parser.add_argument("--parallel-pages", type=int, default=3, help="Nombre de pages parallèles (2–4 recommandé)")
    parser.add_argument("--timeout-ms", type=int, default=30000, help="Timeout de navigation par page (ms)")
    parser.add_argument("--print-rows", type=int, default=10, help="Afficher les N premières lignes (défaut: 10)")

    args = parser.parse_args()

    if args.profile_url:
        m = re.search(r"/@([^/?#]+)", urlparse(args.profile_url).path)
        username = m.group(1) if m else "tiktok_user"
    else:
        username = normalize_username(args.username)

    
    output_path = args.output or f"/data/tiktok_{username}.csv"
    ensure_output_dir(output_path)

    
    headless = getattr(args, "headless", True)

    print(f"Profil ciblé: @{username}")
    print(f"Limit: {args.limit} | Headless: {headless} | Pages parallèles: {args.parallel_pages}")
    proxy_env = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if proxy_env:
        print("Proxy détecté via HTTPS_PROXY/HTTP_PROXY.")

    rows = await scrape_tiktok_profile_async(
        username=username,
        limit=args.limit,
        headless=headless,
        timeout_ms=args.timeout_ms,
        parallel_pages=args.parallel_pages,
    )

    
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["url", "description", "thumbnail", "views", "likes", "comments"])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"\nCSV écrit: {output_path} ({len(rows)} lignes)")
    if rows:
        print_sample(rows, n=args.print_rows)



def main():
    asyncio.run(run_cli_async())


if __name__ == "__main__":
    main()