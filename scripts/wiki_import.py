#!/usr/bin/env python3
"""data/source/wiki_cars.xml + data/overrides/wiki_map.csv -> data/overrides/car_specs_wiki.csv
Exact normalised name first, then the hand-checked map. Unmatched cars stay blank."""
import csv, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ailists, wiki_cars
D = ailists.DATA

def k(s):
    s = re.sub(r"^\((legacy|retired)\)\s*", "", s, flags=re.I); s = ailists.norm(s); return re.sub(r"\s+", " ", s).strip()

def main():
    W = wiki_cars.parse(str(D / "source/wiki_cars.xml")); byt = {w["wiki_title"]: w for w in W}
    bk = {}
    for w in W: bk.setdefault(k(w["wiki_title"]), w)
    mp = {k(r["car_name"]): r["wiki_title"] for r in csv.DictReader(open(D / "overrides/wiki_map.csv", encoding="utf-8"))}
    out = []
    for c in csv.DictReader(open(D / "cars.csv", encoding="utf-8-sig")):
        w, how = None, ""
        for n in (k(c["name"]), k(c["site_name"] or c["name"])):
            if n in bk: w, how = bk[n], "wiki (exact name)"; break
        if not w and byt.get(mp.get(k(c["name"]), "")): w, how = byt[mp[k(c["name"])]], "wiki (hand-matched)"
        if not w: continue
        cfg = w["configuration"]
        loc = (re.search(r"(Mid|Rear|Front)-Engine", cfg) or [None])[0] or ""
        dt = (re.search(r"\b(AWD|RWD|FWD|4WD)\b", cfg) or [None])[0] or ""
        out.append(dict(id=c["id"], wiki_title=w["wiki_title"], wiki_match=how, hp=w["hp"], kg=w["kg"], lbs=w["lbs"],
                        engine=w["engine"], engine_loc=loc, drivetrain=dt, transmission=w["transmission"], year=w["year"],
                        wiki_type=w["wiki_type"], difficulty=w["difficulty"], price_usd=w["price_usd"],
                        wiki_edited=w["wiki_edited"], bio=w["bio"]))
    with open(D / "overrides/car_specs_wiki.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(out[0])); wr.writeheader(); wr.writerows(out)
    print(len(out), "cars matched to the wiki")

if __name__ == "__main__":
    main()
