#!/usr/bin/env python3
"""Check the iRacing support pages for AI-enabled content and update data/.

Standard library only, so it runs on a Synology NAS with the stock Python 3 package.

  python3 scripts/update.py                  # fetch both pages, update data/
  python3 scripts/update.py --dry-run        # show what would change, write nothing
  python3 scripts/update.py --asphalt-html a.html --dirt-html d.html   # use saved pages

Exit codes: 0 = ran fine (changed or not), 2 = fetch/parse problem (nothing written).
"""
import argparse
import re
import sys
import urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ailists  # noqa: E402
import site_scrape  # noqa: E402

URLS = {
    "asphalt": "https://support.iracing.com/support/solutions/articles/31000159313-ai-content-available-asphalt",
    "dirt": "https://support.iracing.com/support/solutions/articles/31000179017-ai-content-available-dirt",
}
TITLES = {"asphalt": "AI Content Available - Asphalt", "dirt": "AI Content Available - Dirt"}
COLUMNS = {"asphalt": "car | car_rain | track | track_rain  (blank = empty cell on the page)",
           "dirt": "car | track  (this page has no rain column)"}
WIDTH = {"asphalt": 4, "dirt": 2}
SRC = ailists.DATA / "source"
SITE_URLS = {"cars": "https://www.iracing.com/cars/", "tracks": "https://www.iracing.com/tracks/"}
SITE_MIN = {"cars": 100, "tracks": 80}
SITE_HEADER = "# Snapshot of {url} (full catalog, AI and non-AI). Captured: {today}."


class TableParser(HTMLParser):
    """Collects the text of every outermost <table> as a list of rows of cell strings."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self._t, self._row, self._cell, self._depth = [], None, None, None, 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self._t = []
        elif tag == "tr" and self._t is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(ailists.clean("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._t is not None:
                self._t.append(self._row)
            self._row = None
        elif tag == "table":
            self._depth -= 1
            if self._depth == 0 and self._t is not None:
                self.tables.append(self._t)
                self._t = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; iracing-ai-lists/1.0)"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", errors="replace")


def page_modified(html: str) -> str:
    m = re.search(r"Modified on:\s*(?:<[^>]*>\s*)*([^<\n]+)", html)
    return ailists.clean(m.group(1)) if m else "unknown"


def extract(html: str, kind: str):
    p = TableParser()
    p.feed(html)
    table = next((t for t in p.tables if t and any("cars available" in c.lower() for c in t[0])), None)
    if table is None:
        raise ailists.SanityError(f"{kind}: no table with a 'Cars Available' header found; page layout changed?")
    header, body = table[0], table[1:]
    width = WIDTH[kind]
    ok = len(header) >= width and "car" in header[0].lower() and \
        "track" in header[2 if kind == "asphalt" else 1].lower()
    if not ok:
        raise ailists.SanityError(f"{kind}: unexpected table header {header!r}; page layout changed?")
    rows = [(r + [""] * width)[:width] for r in body if any(r)]
    if len(rows) < 10:
        raise ailists.SanityError(f"{kind}: only {len(rows)} rows parsed; refusing to continue")
    return rows


def snapshot_text(kind: str, modified: str, today: str, rows) -> str:
    head = [f'# Snapshot of iRacing support page "{TITLES[kind]}"',
            f"# Page modified: {modified}. Captured: {today}.",
            f"# Columns: {COLUMNS[kind]}"]
    return "\n".join(head + ["|".join(r) for r in rows]) + "\n"


def body_lines(text: str):
    return [l for l in text.splitlines() if not l.startswith("#")]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report changes but write nothing")
    ap.add_argument("--asphalt-html", help="use this saved page instead of fetching")
    ap.add_argument("--dirt-html", help="use this saved page instead of fetching")
    ap.add_argument("--cars-html", help="use this saved iracing.com/cars page instead of fetching")
    ap.add_argument("--tracks-html", help="use this saved iracing.com/tracks page instead of fetching")
    ap.add_argument("--no-images", action="store_true", help="do not download thumbnails")
    ap.add_argument("--image-limit", type=int, help="download at most N images per run (per list)")
    args = ap.parse_args()
    today = date.today().isoformat()

    try:
        pages = {}
        for kind, local in (("asphalt", args.asphalt_html), ("dirt", args.dirt_html)):
            html = Path(local).read_text(encoding="utf-8") if local else fetch(URLS[kind])
            pages[kind] = (page_modified(html), extract(html, kind))
    except (OSError, ailists.SanityError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    # Full catalog from iracing.com. If it cannot be read, fall back to the stored snapshot and say so.
    site, site_fresh = {}, {}
    for kind, local in (("cars", args.cars_html), ("tracks", args.tracks_html)):
        try:
            html = Path(local).read_text(encoding="utf-8") if local else fetch(SITE_URLS[kind])
            site[kind] = site_scrape.parse_catalog(html, kind, SITE_MIN[kind])
            site_fresh[kind] = True
        except (OSError, ailists.SanityError) as e:
            print(f"WARNING: could not read iracing.com {kind} ({e}); using stored snapshot", file=sys.stderr)
            site[kind] = ailists.read_site_snapshot(SRC / f"catalog_{kind}.txt", kind)

    try:
        summary = ailists.run_update(pages["asphalt"][1], pages["dirt"][1],
                                     {k: v[0] for k, v in pages.items()}, today=today, dry_run=args.dry_run,
                                     site_cars=site["cars"] or None, site_tracks=site["tracks"] or None)
    except (OSError, ailists.SanityError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if not args.dry_run:
        SRC.mkdir(parents=True, exist_ok=True)
        for kind, (modified, rows) in pages.items():
            path = SRC / f"{kind}_snapshot.txt"
            new = snapshot_text(kind, modified, today, rows)
            if not path.exists() or body_lines(path.read_text(encoding="utf-8")) != body_lines(new):
                path.write_text(new, encoding="utf-8")

        for kind, items in site.items():
            if site_fresh.get(kind):
                path = SRC / f"catalog_{kind}.txt"
                head = SITE_HEADER.format(url=SITE_URLS[kind], today=today)
                new = ailists.snapshot_site_text(items, kind, head)
                if not path.exists() or body_lines(path.read_text(encoding="utf-8")) != body_lines(new):
                    path.write_text(new, encoding="utf-8")

        if not args.no_images:
            for kind in ("cars", "tracks"):
                rows = ailists.load_csv(ailists.DATA / f"{kind}.csv", kind)
                ailists.attach_images(rows if kind == "cars" else [], rows if kind == "tracks" else [])
                n, failed = site_scrape.download_images(rows, kind, limit=args.image_limit)
                print(f"  images ({kind}): {n} downloaded, {len(failed)} failed")
                for f in failed[:10]:
                    print(f"    FAILED {f}")
            # re-run so new image files are attached to the rows
            summary2 = ailists.run_update(pages["asphalt"][1], pages["dirt"][1],
                                          {k: v[0] for k, v in pages.items()}, today=today,
                                          site_cars=site["cars"] or None, site_tracks=site["tracks"] or None)
            summary["changed"] = summary["changed"] or summary2["changed"]

    print(f"active: {summary['counts']['cars']} cars, {summary['counts']['tracks']} tracks "
          f"| page modified: asphalt={pages['asphalt'][0]}, dirt={pages['dirt'][0]}")
    any_change = False
    for k in ("cars", "tracks"):
        for what, items in summary["logs"][k].items():
            for it in items:
                any_change = True
                print(f"  {k[:-1]} {what}: {it}")
    if not any_change:
        print("  no changes to the support-page lists")
    if summary["unclassified"]:
        print("  NOTE: cars with no class rule yet (add a rule or an override):", ", ".join(summary["unclassified"]))
    if args.dry_run:
        print("(dry run: nothing written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
