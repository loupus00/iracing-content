"""Shared logic for the iRacing AI content lists.

Pipeline: support-page table rows -> parse -> merge into data/*.csv -> write CSV/JSON/JS.
Anything not on the support pages (class, track type, images) is either an
"estimate" made by the rules below, an "override" typed into data/overrides/,
or (later) filled by the iRacing data API.
"""
from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
IMAGES = ROOT / "images"

CAR_FIELDS = ["id", "name", "surface", "legacy", "rain", "ai_enabled", "category", "category_source",
              "car_class", "meta_source", "images", "image_url", "detail_url", "site_name", "site_label",
              "status", "first_seen", "removed_on"]
TRACK_FIELDS = ["id", "name", "surface", "legacy", "configs", "rain", "ai_enabled", "track_type",
                "meta_source", "image", "image_url", "detail_url", "site_name", "site_label",
                "status", "first_seen", "removed_on"]
FIELDS = {"cars": CAR_FIELDS, "tracks": TRACK_FIELDS}
# Fields that come straight from the iRacing support pages.
SOURCE_FIELDS = {"cars": ["name", "surface", "legacy", "rain"],
                 "tracks": ["name", "surface", "legacy", "configs", "rain"]}

# Listed in the *cars* column of the asphalt page but is a track (confirmed typo by the owner).
MISPLACED_TRACKS = {"Qualcomm Circuit (Naval Base Coronado)"}


class SanityError(RuntimeError):
    pass


# ---------------------------------------------------------------- parsing

def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def split_legacy(name: str):
    m = re.match(r"^\[Legacy\]\s*(.*)$", name)
    return (m.group(1), True) if m else (name, False)


def rain_car(v: str) -> str:
    v = clean(v).upper()
    return "yes" if v == "YES" else ("no" if v == "" else f"other:{v}")


def rain_track(v: str) -> str:
    v = clean(v).upper().replace(" ", "")
    if v == "":
        return "none"
    if v == "YES":
        return "all"
    if v == "ROAD-YES":
        return "road_only"
    return f"other:{v}"


def split_track(raw: str):
    """'Spa - ALL 7 Configs' -> ('Spa', 'ALL 7 Configs'). Heuristic; check new entries."""
    raw = clean(raw)
    m = re.match(r"^(.*?)\s*-\s*((?:ALL|All)\b.*)$", raw)
    if m:
        return clean(m.group(1)), clean(m.group(2))
    m = re.match(r"^(.*?)\s+((?:ALL|All) Configs.*)$", raw)
    if m:
        return clean(m.group(1)), clean(m.group(2))
    parts = re.split(r"\s+-\s*|(?<=[A-Za-z])-\s+(?=[A-Za-z0-9])", raw, maxsplit=1)
    if len(parts) == 2:
        return clean(parts[0]), clean(parts[1])
    return raw, ""


def make_id(row: dict) -> str:
    return f"{row['surface']}-{slug(row['name'])}" + ("-legacy" if row["legacy"] == "yes" else "")


def parse_asphalt(rows):
    """rows: (car, car_rain, track, track_rain) strings, one per table row."""
    cars, tracks = [], []
    for car, car_rain, track, track_rain in rows:
        car, track = clean(car), clean(track)
        if car in MISPLACED_TRACKS:
            tracks.append({"name": car, "surface": "asphalt", "legacy": "no", "configs": "",
                           "rain": rain_track(car_rain)})
        elif car:
            name, legacy = split_legacy(car)
            cars.append({"name": name, "surface": "asphalt", "legacy": "yes" if legacy else "no",
                         "rain": rain_car(car_rain)})
        if track:
            name, legacy = split_legacy(track)
            name, configs = split_track(name)
            tracks.append({"name": name, "surface": "asphalt", "legacy": "yes" if legacy else "no",
                           "configs": configs, "rain": rain_track(track_rain)})
    return cars, tracks


def parse_dirt(rows):
    """rows: (car, track) strings. The dirt page has no rain column."""
    cars, tracks = [], []
    for car, track in rows:
        car, track = clean(car), clean(track)
        if car:
            name, legacy = split_legacy(car)
            cars.append({"name": name, "surface": "dirt", "legacy": "yes" if legacy else "no", "rain": "n/a"})
        if track:
            # Dirt names are kept whole: "Bristol Motor Speedway - 2021" is its own track.
            name, legacy = split_legacy(track)
            tracks.append({"name": name, "surface": "dirt", "legacy": "yes" if legacy else "no",
                           "configs": "", "rain": "n/a"})
    return cars, tracks


# ---------------------------------------------------------------- estimates
# NOT from iRacing: rule-of-thumb labels so the list is useful before real data
# (iRacing data API) is available. Rows keep meta_source="estimate" until replaced.

CAR_RULES = [
    (r"^Dirt ", "Dirt Oval", "Dirt"),
    (r"GTP|M Hybrid V8|499P|Valkyrie", "Prototypes", "GTP / Hypercar"),
    (r"Porsche 919|Audi R18", "Prototypes", "LMP1 (older prototype)"),
    (r"HPD ARX-01c|Dallara P217", "Prototypes", "LMP2"),
    (r"Ligier JS P320", "Prototypes", "LMP3"),
    (r"Daytona Prototype", "Prototypes", "Daytona Prototype"),
    (r"90 GTO", "Sports Car", "IMSA GTO (historic)"),
    (r"GT3 Cup|911 Cup|296 Challenge|MX-5 Cup|Jetta TDI|Solstice|Spec Racer|Radical|Caterham|Clio|GR86|FR500S|BMW M2|Kia Optima|CTS-V",
     "Sports Car", "Production / One-make"),
    (r"GT3|^Audi R8 LMS$", "Sports Car", "GT3"),
    (r"GT4", "Sports Car", "GT4"),
    (r"GTE|RSR", "Sports Car", "GTE"),
    (r"GT2", "Sports Car", "GT2"),
    (r"GT1", "Sports Car", "GT1"),
    (r"TCR|Elantra|Veloster|Civic Type R", "Sports Car", "Touring Car (TCR)"),
    (r"Supercars", "Sports Car", "Australian Supercars"),
    (r"IR18", "Formula Car", "IndyCar"),
    (r"IL-15", "Formula Car", "Indy Lights"),
    (r"Formula Vee", "Formula Car", "Formula Vee"),
    (r"Super Formula", "Formula Car", "Super Formula"),
    (r"Lotus 49|Lotus 79|AMG (?:F1 )?W1[23]|FW31|MP4-30", "Formula Car", "Formula 1"),
    (r"Dallara F3|iR-01|FIA F4|Formula Renault|Indy Pro 2000|FF1600|Skip Barber|USF 2000",
     "Formula Car", "Junior / Ladder"),
    (r"Next Gen", "NASCAR", "NASCAR Cup - Next Gen"),
    (r"NASCAR Cup Series", "NASCAR", "NASCAR Cup - Gen 6"),
    (r"Gen 4", "NASCAR", "NASCAR Gen 4"),
    (r"Legends", "NASCAR", "Legends"),
    (r"NASCAR Truck", "NASCAR", "NASCAR Truck"),
    (r"O.Reilly", "NASCAR", "NASCAR O'Reilly (Xfinity)"),
    (r"Whelen|Modified - SK", "NASCAR", "Modifieds"),
    (r"ARCA", "NASCAR", "ARCA"),
    (r"EURO NASCAR", "NASCAR", "Euro NASCAR"),
    (r"Stock Car Pro", "NASCAR", "Stock Car Brasil"),
    (r"SRX", "NASCAR", "SRX"),
    (r"Silver Crown", "NASCAR", "Silver Crown"),
    (r"Late Model", "NASCAR", "Late Models"),
    (r"Street Stock|Mini Stock", "NASCAR", "Street / Mini Stock"),
]

OVAL_TRACKS = {
    "Chicagoland Speedway", "Concord Speedway", "Darlington Raceway", "Dover International Speedway",
    "EchoPark Speedway (ATL)", "Federated Auto Parts Raceway at I-55", "Five Flags Speedway",
    "Hickory Motor Speedway", "Iowa Speedway", "iRacing Superspeedway", "Irwindale Speedway",
    "Kentucky Speedway", "Kern County Raceway Park", "LA Coliseum Raceway", "Langley Speedway",
    "Lanier National Speedway", "Las Vegas Motor Speedway", "Lucas Oil Indianapolis Raceway Park",
    "Martinsville Speedway", "Michigan International Speedway", "Myrtle Beach Speedway",
    "Nashville Fairgrounds Speedway", "Nashville Superspeedway", "New Smyrna Speedway",
    "North Wilkesboro Speedway", "Oswego Speedway", "Oxford Plains Speedway", "Phoenix Raceway",
    "Pocono Raceway", "Richmond Raceway", "Rockingham Speedway", "Slinger Speedway",
    "South Boston Speedway", "Southern National Motorsports Park", "Stafford Motor Speedway",
    "Talladega Superspeedway", "Texas Motor Speedway", "The Bullring",
    "Thompson Speedway Motorsports Park", "USA International Speedway",
    "World Wide Technology Raceway (Gateway)", "Bristol Motor Speedway",
}
ROAD_AND_OVAL_TRACKS = {
    "Auto Club Speedway", "Charlotte Motor Speedway", "Daytona International Speedway",
    "Homestead Miami Speedway", "Indianapolis Motor Speedway", "Kansas Speedway",
    "Mobility Resort Motegi", "New Hampshire Motor Speedway", "The Milwaukee Mile",
    "Autódromo Hermanos Rodríguez (Mexico City)",
}
STREET_TRACKS = {
    "Adelaide Street Circuit", "Chicago Street Course", "Detroit Grand Prix at Belle Isle",
    "Long Beach Street Circuit", "St. Petersburg Grand Prix", "Qualcomm Circuit (Naval Base Coronado)",
}


def estimate(row: dict, kind: str) -> None:
    if kind == "cars":
        for pattern, category, klass in CAR_RULES:
            if re.search(pattern, row["name"]):
                row["category"], row["car_class"], row["meta_source"] = category, klass, "estimate"
                return
        row["category"], row["car_class"], row["meta_source"] = "", "Unclassified", ""
    else:
        if row["surface"] == "dirt":
            row["track_type"] = "Dirt Oval"
        elif row["name"] in OVAL_TRACKS:
            row["track_type"] = "Oval"
        elif row["name"] in ROAD_AND_OVAL_TRACKS:
            row["track_type"] = "Road & Oval"
        elif row["name"] in STREET_TRACKS:
            row["track_type"] = "Street"
        else:
            row["track_type"] = "Road"
        row["meta_source"] = "estimate"


# ---------------------------------------------------------------- storage

def load_csv(path: Path, kind: str) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    out = [{k: r.get(k, "") or "" for k in FIELDS[kind]} | {"id": r["id"]} for r in rows]
    for r in out:  # files written before the full-catalog change had only AI rows
        if not r["ai_enabled"]:
            r["ai_enabled"] = "yes" if r["status"] == "active" else "no"
    return out


def csv_text(rows: list[dict], kind: str) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS[kind], lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in FIELDS[kind]})
    return buf.getvalue()


def apply_overrides(rows: list[dict], path: Path, fields: list[str]) -> None:
    """data/overrides/*.csv: id + any of the enrichment columns; non-empty values win."""
    if not path.exists():
        return
    with open(path, newline="", encoding="utf-8-sig") as f:
        ov = {r["id"]: r for r in csv.DictReader(f) if r.get("id")}
    for r in rows:
        o = ov.get(r["id"])
        if not o:
            continue
        hit = False
        for f_ in fields:
            if clean(o.get(f_, "")):
                r[f_] = clean(o[f_])
                hit = True
        if hit:
            r["meta_source"] = "override"
            if "category" in fields and clean(o.get("category", "")):
                r["category_source"] = "override"


def attach_images(cars: list[dict], tracks: list[dict]) -> None:
    """Images are found by file name: cars/<id>__1.jpg, __2.jpg ...; tracks/<id>.jpg."""
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    for r in cars:
        found = sorted(p for p in (IMAGES / "cars").glob(f"{r['id']}__*") if p.suffix.lower() in exts)
        r["images"] = "|".join(p.relative_to(ROOT).as_posix() for p in found)
    for r in tracks:
        found = sorted(p for p in (IMAGES / "tracks").glob(f"{r['id']}.*") if p.suffix.lower() in exts)
        r["image"] = found[0].relative_to(ROOT).as_posix() if found else ""


# ---------------------------------------------------------------- merge

def label(r: dict) -> str:
    return f"{r['name']}{' [legacy]' if r['legacy'] == 'yes' else ''} ({r['surface']})"


def merge(existing: list[dict], parsed: list[dict], kind: str, today: str):
    """Merge the AI-enabled rows from the support pages into the stored rows.

    ai_enabled="yes" means "on the support page right now". Rows that fell off the page
    become ai_enabled="no" (apply_catalog later decides whether they are still in the
    full iRacing catalog). Site-only rows (ids starting "site-") are regenerated each run.
    """
    fields, src = FIELDS[kind], SOURCE_FIELDS[kind]
    old = {r["id"]: r for r in existing}
    seen: set[str] = set()
    out: list[dict] = []
    log = {"added to AI list": [], "removed from AI list": [], "back on AI list": [], "changed": []}
    for p in parsed:
        pid = p["id"]
        if pid in seen:
            raise ValueError(f"Duplicate id in source pages: {pid} ({p['name']})")
        seen.add(pid)
        r = old.get(pid)
        if r is None:
            r = {f: "" for f in fields}
            r.update({k: p[k] for k in src})
            r["id"], r["ai_enabled"], r["status"], r["first_seen"] = pid, "yes", "active", today
            estimate(r, kind)
            log["added to AI list"].append(label(r))
        else:
            if r["ai_enabled"] != "yes":
                r["ai_enabled"], r["status"], r["removed_on"] = "yes", "active", ""
                log["back on AI list"].append(label(r))
            for f in src:
                if r[f] != p[f]:
                    log["changed"].append(f"{label(r)}: {f} '{r[f]}' -> '{p[f]}'")
                    r[f] = p[f]
            if r["meta_source"] in ("", "estimate"):
                estimate(r, kind)
        out.append(r)
    for pid, r in old.items():
        if pid in seen or pid.startswith("site-"):
            continue
        if r["ai_enabled"] == "yes":
            r["ai_enabled"], r["status"], r["removed_on"] = "no", "removed", today
            log["removed from AI list"].append(label(r))
        out.append(r)
    return out, log


# ---------------------------------------------------------------- full catalog (iracing.com)

def norm(s: str) -> str:
    """Name key for matching support-page names to iracing.com names."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\[legacy\]", " ", s).replace("&", " and ")
    s = re.sub(r"[\u2019\u2018'`.]", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def load_aliases(path: Path) -> dict:
    """data/overrides/aliases.csv: kind (car|track), ai_name, site_name -> {(kind, norm(ai)): norm(site)}"""
    out = {}
    if path.exists():
        with open(path, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r.get("kind") and r.get("ai_name") and r.get("site_name"):
                    out[(r["kind"].strip(), norm(r["ai_name"]))] = norm(r["site_name"])
    return out


def apply_catalog(rows: list[dict], site: list[dict], kind: str, aliases: dict, old_rows: list[dict],
                  today: str):
    """Attach iracing.com data to AI rows and add site-only rows (ai_enabled="no").

    site: dicts with name, detail_url, image_url, label (+ category for cars).
    Returns (rows, log, unmatched_ai_names).
    """
    one = kind[:-1]
    index: dict[str, list[dict]] = {}
    for it in site:
        index.setdefault(norm(it["name"]), []).append(it)
    claimed: set[int] = set()
    unmatched = []
    for r in rows:
        key = norm(r["name"])
        key = aliases.get((one, key), key)
        hits = index.get(key)
        if not hits:
            if r["ai_enabled"] == "yes":
                unmatched.append(r["name"])
            if r["ai_enabled"] != "yes":
                r["status"] = "removed"
            if kind == "cars" and r["ai_enabled"] == "yes" and r["category"]:
                r["category_source"] = r["category_source"] or "estimate"
            continue
        it = hits[0]
        claimed.update(id(h) for h in hits)
        r["site_name"], r["detail_url"], r["image_url"], r["site_label"] = (
            it["name"], it["detail_url"], it["image_url"], it["label"])
        if r["ai_enabled"] != "yes":
            r["status"] = "active"  # dropped from the AI list but still sold
        if kind == "cars" and r["category_source"] != "override":
            r["category"], r["category_source"] = it["category"], "iracing.com"
    old = {r["id"]: r for r in old_rows}
    added, new_ids = [], set()
    for it in site:
        if id(it) in claimed:
            continue
        r = {f: "" for f in FIELDS[kind]}
        dirt = (it.get("category") == "Dirt Oval") if kind == "cars" else bool(re.search(r"\bdirt\b", it["name"], re.I))
        r.update({"name": it["name"], "surface": "dirt" if dirt else "unknown", "legacy": "no",
                  "rain": "unknown", "ai_enabled": "no", "status": "active",
                  "site_name": it["name"], "detail_url": it["detail_url"], "image_url": it["image_url"],
                  "site_label": it["label"]})
        r["id"] = f"site-{slug(it['name'])}"
        if r["id"] in new_ids:
            r["id"] += "-2"
        new_ids.add(r["id"])
        prev = old.get(r["id"])
        r["first_seen"] = prev["first_seen"] if prev else today
        if not prev:
            added.append(f"{it['name']} (not AI-enabled)")
        if kind == "cars":
            estimate(r, kind)
            r["category"], r["category_source"] = it["category"], "iracing.com"
        else:
            estimate_site_track(r)
        rows.append(r)
    gone = [r["name"] for r in old_rows if r["id"].startswith("site-") and r["id"] not in new_ids]
    rows.sort(key=lambda r: (r["ai_enabled"] != "yes", r["name"].lower(), r["legacy"]))
    return rows, {"added to catalog (not AI)": added, "left catalog": gone}, unmatched


def estimate_site_track(r: dict) -> None:
    """Site-only tracks: only label what we can justify; otherwise Unclassified."""
    key = norm(r["name"])
    if r["surface"] == "dirt":
        r["track_type"], r["meta_source"] = "Dirt Oval", "estimate"
    elif key in {norm(n) for n in OVAL_TRACKS}:
        r["track_type"], r["meta_source"] = "Oval", "estimate"
    elif key in {norm(n) for n in ROAD_AND_OVAL_TRACKS}:
        r["track_type"], r["meta_source"] = "Road & Oval", "estimate"
    elif key in {norm(n) for n in STREET_TRACKS}:
        r["track_type"], r["meta_source"] = "Street", "estimate"
    else:
        r["track_type"], r["meta_source"] = "Unclassified", ""


def run_update(asphalt_rows, dirt_rows, page_modified: dict, today: str | None = None,
               dry_run: bool = False, site_cars=None, site_tracks=None) -> dict:
    """site_cars / site_tracks: parsed iracing.com catalog. If None, only the AI lists are updated
    and the site-only rows already stored are carried forward unchanged."""
    today = today or date.today().isoformat()
    a_cars, a_tracks = parse_asphalt(asphalt_rows)
    d_cars, d_tracks = parse_dirt(dirt_rows)
    parsed = {"cars": a_cars + d_cars, "tracks": a_tracks + d_tracks}
    for rows in parsed.values():
        for r in rows:
            r["id"] = make_id(r)

    old = {k: load_csv(DATA / f"{k}.csv", k) for k in parsed}
    for k in parsed:  # guard against a changed page layout wiping the lists
        active = sum(1 for r in old[k] if r["ai_enabled"] == "yes")
        if active and len(parsed[k]) < 0.5 * active:
            raise SanityError(f"Parsed only {len(parsed[k])} {k} vs {active} stored AI rows; "
                              "page layout may have changed. Nothing written.")
    site = {"cars": site_cars, "tracks": site_tracks}
    for k in parsed:
        stored_site = sum(1 for r in old[k] if r["site_name"])
        if site[k] is not None and stored_site and len(site[k]) < 0.5 * stored_site:
            raise SanityError(f"Parsed only {len(site[k])} {k} from iracing.com vs {stored_site} stored; "
                              "page layout may have changed. Nothing written.")

    aliases = load_aliases(DATA / "overrides" / "aliases.csv")
    new, logs, unmatched = {}, {}, {}
    for k in parsed:
        new[k], logs[k] = merge(old[k], parsed[k], k, today)
        if site[k] is not None:
            new[k], extra, unmatched[k] = apply_catalog(new[k], site[k], k, aliases, old[k], today)
            logs[k].update(extra)
        else:  # no site data this run: carry the stored site-only rows forward unchanged
            keep = [r for r in old[k] if r["id"].startswith("site-")]
            new[k] = new[k] + keep
            unmatched[k] = []
    apply_overrides(new["cars"], DATA / "overrides" / "cars.csv", ["category", "car_class"])
    apply_overrides(new["tracks"], DATA / "overrides" / "tracks.csv", ["track_type"])
    attach_images(new["cars"], new["tracks"])

    texts = {k: csv_text(new[k], k) for k in new}
    changed = any(not (DATA / f"{k}.csv").exists() or (DATA / f"{k}.csv").read_text(encoding="utf-8-sig") != texts[k]
                  for k in new)
    counts = {k: {"ai": sum(1 for r in new[k] if r["ai_enabled"] == "yes"),
                  "total": sum(1 for r in new[k] if r["status"] == "active")} for k in new}
    summary = {"changed": changed, "logs": logs, "counts": counts, "unmatched_ai": unmatched,
               "unclassified": [r["name"] for r in new["cars"] if r["car_class"] == "Unclassified"]}
    if not changed or dry_run:
        return summary

    DATA.mkdir(exist_ok=True)
    meta = {"updated": today, "page_modified": page_modified, "counts": counts,
            "meta_note": "car_class/track_type are estimates unless meta_source says otherwise; "
                         "car category is iRacing's own when category_source is iracing.com"}
    payload = {"meta": meta}
    for k in new:
        (DATA / f"{k}.csv").write_text(texts[k], encoding="utf-8-sig")
        rows_json = []
        for r in new[k]:
            j = dict(r)
            if k == "cars":
                j["images"] = [x for x in r["images"].split("|") if x]
            rows_json.append(j)
        (DATA / f"{k}.json").write_text(json.dumps(rows_json, ensure_ascii=False, indent=1), encoding="utf-8")
        payload[k] = rows_json
    (DATA / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    (DATA / "data.js").write_text("window.AI_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n",
                                  encoding="utf-8")

    lines = [f"## {today}"]
    for k in ("cars", "tracks"):
        for kind_, items in logs[k].items():
            for it in items:
                lines.append(f"- {k[:-1]} {kind_}: {it}")
    if len(lines) == 1:  # only images/metadata changed: no log entry
        return summary
    chg = ROOT / "CHANGES.md"
    prev = chg.read_text(encoding="utf-8") if chg.exists() else "# Change log\n"
    head, _, rest = prev.partition("\n")
    chg.write_text(head + "\n\n" + "\n".join(lines) + "\n" + rest, encoding="utf-8")
    return summary


# ---------------------------------------------------------------- site snapshot files

def read_site_snapshot(path: Path, kind: str) -> list[dict]:
    """catalog_cars.txt: category | name | detail_url | image_url | labels ; tracks: no category."""
    items = []
    if not path.exists():
        return items
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        c = [x.strip() for x in line.split("|")]
        if kind == "cars":
            c += [""] * (5 - len(c))
            items.append({"category": c[0], "name": c[1], "detail_url": c[2], "image_url": c[3], "label": c[4]})
        else:
            c += [""] * (4 - len(c))
            items.append({"name": c[0], "detail_url": c[1], "image_url": c[2], "label": c[3]})
    return items


def snapshot_site_text(items: list[dict], kind: str, header: str) -> str:
    cols = "category | name | detail_url | image_url | labels" if kind == "cars" else \
        "name | detail_url | image_url | labels"
    out = [header, f"# Columns: {cols}"]
    for it in items:
        vals = ([it["category"]] if kind == "cars" else []) + [it["name"], it["detail_url"], it["image_url"], it["label"]]
        out.append(" | ".join(vals).rstrip())
    return "\n".join(out) + "\n"
