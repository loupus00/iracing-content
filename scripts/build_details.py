#!/usr/bin/env python3
"""Merge spec sources into data/details.js (window.DETAILS) for the viewer's Details table.
Priority per field: iRacing wiki export (car_specs_wiki.csv / track_specs_wiki.csv), then the user's spreadsheet
(car_specs.csv, cars only; marked with *_src = "sheet"). Blank stays blank: nothing is guessed."""
import csv, json, sys
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

def main():
    wiki, sheet, twiki = rd("car_specs_wiki.csv"), rd("car_specs.csv"), rd("track_specs_wiki.csv")
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
        for f in ("engine", "year", "wiki_type", "difficulty", "price_usd", "bio", "wiki_title"):
            if w.get(f): d[f] = w[f]
        hp, kg = num(d.get("hp")), num(d.get("kg"))
        if hp and kg: d["kg_per_hp"] = "%.2f" % (kg / hp)
        if d: out["cars"][c["id"]] = d
    for t in csv.DictReader(open(D / "tracks.csv", encoding="utf-8-sig")):
        w = twiki.get(t["id"], {})
        d = {f: w[f] for f in ("location", "length_mi", "length_km", "turns", "configs_n", "pit_speed", "price_usd", "owner",
                               "opened", "status", "difficulty", "types", "bio", "wiki_title") if w.get(f)}
        if "status" in d: d["wiki_status"] = d.pop("status")
        if d: out["tracks"][t["id"]] = d
    out["credit"] = "Specs and descriptions: iRacing Wiki (iracing.fandom.com), community-written."
    (D / "details.js").write_text("window.DETAILS = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print("details.js:", len(out["cars"]), "cars,", len(out["tracks"]), "tracks")

if __name__ == "__main__":
    main()
