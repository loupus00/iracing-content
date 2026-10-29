"""Parse the iracing.com /cars/ and /tracks/ catalog pages and download thumbnails.

Standard library only. UNTESTED AGAINST THE LIVE HTML: it was written from the page's rendered
text (the sandbox it was built in could not fetch raw HTML), so it is deliberately generic and
validates its own result. If it cannot find enough items it raises SanityError and the updater
keeps using data/source/catalog_*.txt.
"""
from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

import ailists

BASE = "https://www.iracing.com"
CAR_CATEGORIES = {"NASCAR", "Sports Car", "Prototypes", "Formula Car", "Dirt Oval", "Rallycross", "Off-Road"}
LABELS = {"new", "new!", "tech track", "legacy"}


class CatalogParser(HTMLParser):
    def __init__(self, kind: str):
        super().__init__(convert_charrefs=True)
        self.kind = kind
        self.href_re = re.compile(rf"^(?:https?://www\.iracing\.com)?/{kind}/([^/?#]+)/?$")
        self.items: dict[str, dict] = {}
        self.order: list[str] = []
        self.category = ""
        self._head = None      # heading text being collected (outside anchors only)
        self._a = None         # current anchor href
        self._pieces: list[str] = []

    def _item(self, href):
        url = urllib.parse.urljoin(BASE + "/", href)
        if url not in self.items:
            self.items[url] = {"category": self.category, "name": "", "detail_url": url,
                               "image_url": "", "label": "", "alt": ""}
            self.order.append(url)
        return self.items[url]

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("h1", "h2", "h3", "h4") and self._a is None:
            self._head = []
        elif tag == "a" and a.get("href") and self.href_re.match(a["href"].split("#")[0]):
            self._a, self._pieces = a["href"], []
            self._item(self._a)
        elif tag == "img" and self._a is not None:
            src = a.get("data-src") or a.get("data-lazy-src") or a.get("src") or ""
            if not src and a.get("srcset"):
                src = a["srcset"].split()[0]
            if src and not src.startswith("data:"):
                it = self._item(self._a)
                if not it["image_url"]:
                    it["image_url"] = safe_url(urllib.parse.urljoin(BASE + "/", src))
                it["alt"] = it["alt"] or ailists.clean(a.get("alt", ""))

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4") and self._head is not None:
            text = ailists.clean("".join(self._head))
            self._head = None
            if text and text.lower() not in ("cars", "tracks"):
                self.category = text
        elif tag == "a" and self._a is not None:
            it = self._item(self._a)
            for piece in self._pieces:
                piece = ailists.clean(piece)
                if not piece:
                    continue
                if piece.lower() in LABELS:
                    it["label"] = it["label"] or piece
                elif not it["name"]:
                    it["name"] = piece
            self._a = None

    def handle_data(self, data):
        if self._a is not None:
            self._pieces.append(data)
        elif self._head is not None:
            self._head.append(data)


def parse_catalog(html: str, kind: str, min_items: int) -> list[dict]:
    p = CatalogParser(kind)
    p.feed(html)
    items = []
    for url in p.order:
        it = p.items[url]
        it["name"] = it["name"] or it["alt"]
        it.pop("alt", None)
        if it["name"]:
            items.append(it)
    if len(items) < min_items:
        raise ailists.SanityError(f"{kind}: only {len(items)} items found on iracing.com (need {min_items})")
    if kind == "cars":
        known = sum(1 for it in items if it["category"] in CAR_CATEGORIES)
        if known < 0.5 * len(items):
            raise ailists.SanityError("cars: most items have no recognised iRacing category heading")
    else:
        for it in items:
            it.pop("category", None)
    return items


# ------------------------------------------------------------------ images

def safe_url(url: str) -> str:
    """Percent-encode non-ASCII characters (iRacing file names can contain e.g. U+200F)."""
    return urllib.parse.quote(url, safe="%/:=&?~#+!$,;'@()*[]")


def image_ext(url: str) -> str:
    ext = Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)).suffix.lower()
    return ext if ext in (".jpg", ".jpeg", ".png", ".webp") else ".jpg"


def download_images(rows: list[dict], kind: str, delay: float = 0.4, limit: int | None = None):
    """Download image_url for rows that have no local image yet. Returns (ok, failed list)."""
    folder = ailists.IMAGES / kind
    folder.mkdir(parents=True, exist_ok=True)
    ok, failed = 0, []
    for r in rows:
        if r["status"] != "active" or not r["image_url"]:
            continue
        have = r["images"] if kind == "cars" else r["image"]
        if have:
            continue
        if limit is not None and ok >= limit:
            break
        name = f"{r['id']}__1" if kind == "cars" else r["id"]
        dest = folder / (name + image_ext(r["image_url"]))
        try:
            req = urllib.request.Request(safe_url(r["image_url"]), headers={
                "User-Agent": "Mozilla/5.0 (compatible; iracing-ai-lists/1.0)", "Referer": BASE + "/"})
            with urllib.request.urlopen(req, timeout=40) as resp:
                ctype = resp.headers.get("Content-Type", "")
                data = resp.read(4_000_001)
            if not ctype.startswith("image/") or len(data) < 500 or len(data) > 4_000_000:
                raise ValueError(f"unexpected content ({ctype}, {len(data)} bytes)")
            dest.write_bytes(data)
            ok += 1
        except Exception as e:  # noqa: BLE001 - one bad image must not stop the run
            failed.append(f"{r['name']}: {e}")
        time.sleep(delay)
    return ok, failed
