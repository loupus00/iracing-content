#!/usr/bin/env python3
"""Merge spec sources into data/details.js (window.DETAILS) for the viewer's Details table.
Priority per field: iRacing wiki export (car_specs_wiki.csv / track_specs_wiki.csv), then the user's spreadsheet
(car_specs.csv, cars only; marked with *_src = "sheet"). Blank stays blank: nothing is guessed."""
import csv, json, re, sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ailists
D = ailists.DATA

def rd(name):
    p = D / "overrides" / name
    if not p.exists(): return {}
    return {r["id"]: r for r in csv.DictReader(open(p, encoding="utf-8-sig"))}

def num(s):
    try: return float(s)
    except (TypeError, ValueError): return None

def one_dec(v):
    """'1.261-1.864' -> '1.3\u20131.9' (round half up, one decimal)."""
    def r(x): return str(Decimal(x).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    return "\u2013".join(r(x) for x in re.findall(r"\d+(?:\.\d+)?", v))


LEVELS = ["World Champion", "Novice", "Rookie", "Clubman", "Advanced", "Pro", "Expert"]


def clean_track(d):
    """The wiki infobox sometimes runs fields together; keep only each field's own value."""
    loc = d.get("location", "")
    m = re.search(r"\s*(?:\u2022|Length:)", loc)
    if m:   # location swallowed the neighbouring infobox rows; recover what they held
        tail, d["location"] = loc[m.start():], loc[:m.start()].strip()
        g = re.search(r"Length:\s*([\d.]+)(?:\s*to\s*([\d.]+))?\s*Miles\s*\(([\d.]+)(?:\s*to\s*([\d.]+))?\s*km\)", tail)
        if g and "length_mi" not in d:
            d["length_mi"] = "%s-%s" % (g.group(1), g.group(2)) if g.group(2) else g.group(1)
            d["length_km"] = "%s-%s" % (g.group(3), g.group(4)) if g.group(4) else g.group(3)
        g = re.search(r"Turns:\s*([\d]+(?:\s*[-\u2013]\s*\d+)?)", tail)
        if g and "turns" not in d: d["turns"] = g.group(1)
        g = re.search(r"Configurations:\s*(\d+)", tail)
        if g and "configs_n" not in d: d["configs_n"] = g.group(1)
        g = re.search(r"Pit Road Speed:\s*(.+?)\s*(?:\u2022|Price:|$)", tail)
        if g and "pit_speed" not in d: d["pit_speed"] = g.group(1)
    if "location" in d:   # "Benalla, Victoria, AustraliaLength: ..." (no bullet)
        d["location"] = re.sub(r"(?<=[a-z])(?:Length|Turns|Nickname|Nationality|Type):.*$", "", d["location"]).strip()
    if "pit_speed" in d:   # "20 mph (32 kmh) to 35 mph (56 kmh) Price: ..." -> "20-35"
        n = re.findall(r"(\d+)\s*mph", d["pit_speed"])
        if n: d["pit_speed"] = (n[0] if len(set(n)) == 1 else "%s\u2013%s" % (n[0], n[-1])) + " mph"
        else: del d["pit_speed"]
    if "difficulty" in d:
        lv = [l for l in LEVELS if d["difficulty"].startswith(l)]
        if lv: d["difficulty"] = lv[0]
    if "opened" in d:      # keep the first year; closures and re-openings stay on the wiki
        y = re.search(r"\d{4}", d["opened"])
        if y: d["opened"] = y.group(0)
        else: del d["opened"]


def main():
    wiki, sheet, twiki = rd("car_specs_wiki.csv"), rd("car_specs.csv"), rd("track_specs_wiki.csv")
    rel, upd = rd("released.csv"), rd("updated.csv")
    out = {"cars": {}, "tracks": {}}
    for c in csv.DictReader(open(D / "cars.csv", encoding="utf-8-sig")):
        w, s = wiki.get(c["id"], {}), sheet.get(c["id"], {})
        d = {}
        for f in ("hp", "kg", "lbs", "drivetrain", "engine_loc", "transmission", "gears"):
            if w.get(f): d[f] = w[f]
            elif s.get(f):
                v = s[f]; n = num(v)
                d[f] = str(round(n)) if n is not None and f in ("hp", "kg", "lbs") else v
                d[f + "_src"] = "sheet"
        for f in ("engine", "year", "wiki_type", "difficulty", "bio", "wiki_title"):
            if w.get(f): d[f] = re.sub(r"\s+Racer$", "", w[f].rstrip(": ").strip()) if f == "wiki_type" else w[f].rstrip(": ").strip()
        hp, kg = num(d.get("hp")), num(d.get("kg"))
        if hp and kg: d["kg_per_hp"] = "%.2f" % (kg / hp)
        if c["id"] in rel: d["released"] = rel[c["id"]]["released"]
        if c["id"] in upd: d["updated"] = upd[c["id"]]["updated"]
        if d: out["cars"][c["id"]] = d
    for t in csv.DictReader(open(D / "tracks.csv", encoding="utf-8-sig")):
        w = twiki.get(t["id"], {})
        d = {f: w[f] for f in ("location", "length_mi", "length_km", "turns", "configs_n", "pit_speed", "owner",
                               "opened", "status", "difficulty", "track_type", "bio", "wiki_title") if w.get(f)}
        if "status" in d: d["wiki_status"] = d.pop("status")
        clean_track(d)
        for k in ("length_mi", "length_km"):
            if k in d: d[k] = one_dec(d[k])
        if "location" in d:   # "City, Region, Country" -> location + country
            parts = [x.strip() for x in d["location"].split(",")]
            if len(parts) > 1: d["country"] = parts[-1]; d["location"] = ", ".join(parts[:-1])
            else: d["country"] = parts[0]; d["location"] = ""
            d["country"] = re.sub(r"\s*(?:Nationality|Nickname|Type):.*$", "", d["country"]).strip()
            if not d["location"]: del d["location"]
        if t["id"] in rel: d["released"] = rel[t["id"]]["released"]
        if t["id"] in upd: d["updated"] = upd[t["id"]]["updated"]
        if d: out["tracks"][t["id"]] = d
    out["credit"] = "Specs and descriptions: iRacing Wiki (iracing.fandom.com), community-written."
    (D / "details.js").write_text("window.DETAILS = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print("details.js:", len(out["cars"]), "cars,", len(out["tracks"]), "tracks")

if __name__ == "__main__":
    main()
