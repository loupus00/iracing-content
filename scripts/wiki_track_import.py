#!/usr/bin/env python3
"""data/source/wiki_tracks.xml + data/overrides/wiki_track_map.csv -> data/overrides/track_specs_wiki.csv"""
import csv, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ailists, wiki_tracks
D = ailists.DATA
FIELDS = ["id","wiki_title","wiki_match","location","length_mi","length_km","turns","configs_n","pit_speed","price_usd","owner","opened","status","difficulty","types","seating","wiki_edited","bio"]

def k(s):
    s = re.sub(r"^\((legacy|retired)\)\s*", "", s, flags=re.I); s = ailists.norm(s); return re.sub(r"\s+", " ", s).strip()

def main():
    W = [w for w in wiki_tracks.parse(str(D / "source/wiki_tracks.xml")) if not w["wiki_title"].startswith(("Category:", "Tracks"))]
    bk = {}
    for w in W: bk.setdefault(k(w["wiki_title"]), []).append(w)
    mp = {k(r["track_name"]): r["wiki_title"] for r in csv.DictReader(open(D / "overrides/wiki_track_map.csv", encoding="utf-8"))}
    out = []
    for t in csv.DictReader(open(D / "tracks.csv", encoding="utf-8-sig")):
        n = k(t["name"]); how = "wiki (exact name)"
        cands = bk.get(n)
        if not cands and n in mp:
            cands = bk.get(k(mp[n])); how = "wiki (hand-matched)"
            if t["surface"] == "dirt" and bk.get(k(mp[n] + " dirt")): cands = bk[k(mp[n] + " dirt")]
        if cands and t["id"].endswith("-legacy"):
            leg = [w for ks, ws in bk.items() if ks.startswith(n + " ") for w in ws if w["wiki_title"].startswith("(Legacy)")]
            if leg: cands = leg
        if not cands: continue
        leg = t["id"].endswith("-legacy"); dirt = t["surface"] == "dirt" or "dirt" in t["name"].lower()
        pick = [w for w in cands if w["wiki_title"].startswith("(Legacy)") == leg] or cands
        pick = [w for w in pick if ("dirt" in w["wiki_title"].lower()) == dirt] or pick
        w = pick[0]
        out.append({"id": t["id"], "wiki_match": how, **{f: w.get(f, "") for f in FIELDS if f not in ("id", "wiki_match")}})
    with open(D / "overrides/track_specs_wiki.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=FIELDS); wr.writeheader(); wr.writerows(out)
    tracks = list(csv.DictReader(open(D / "tracks.csv", encoding="utf-8-sig")))
    got = {r["id"] for r in out}
    print(len(out), "of", len(tracks), "track rows matched; AI rows matched", sum(1 for t in tracks if t["ai_enabled"] == "yes" and t["id"] in got), "of", sum(1 for t in tracks if t["ai_enabled"] == "yes"))
    print("none:", [t["name"] + (" [AI]" if t["ai_enabled"] == "yes" else "") for t in tracks if t["id"] not in got])

if __name__ == "__main__":
    main()
