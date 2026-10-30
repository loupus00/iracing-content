#!/usr/bin/env python3
"""One-off import of the user's spreadsheet specs into data/overrides/car_specs.csv.
usage: sheet_import.py path/to/iRacing_Car__Track_List.xlsx
Matching = exact normalised name, else the hand-checked map in data/overrides/sheet_map.csv.
Never fuzzy-matches by itself: unmatched cars are left blank."""
import csv, re, sys
from pathlib import Path
import openpyxl
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ailists
D = ailists.DATA
FIELDS = ["id", "hp", "kg", "lbs", "w_hp", "drivetrain", "engine_loc", "gears", "transmission", "car_type", "spec_source"]

def k(s):
    s = ailists.norm(str(s)); s = re.sub(r"\s+", " ", s); return s.strip()

def main(xlsx):
    ws = openpyxl.load_workbook(xlsx, data_only=True)["Cars"]
    hdr = [c.value for c in ws[1]]
    sheet = {}
    for r in ws.iter_rows(min_row=2):
        d = dict(zip(hdr, [c.value for c in r]))
        if d.get("Car"): sheet[k(d["Car"])] = d
    smap = {}
    for r in csv.DictReader(open(D / "overrides/sheet_map.csv", encoding="utf-8-sig")):
        smap[k(r["car_name"])] = r["sheet_name"]
    out, un = [], []
    for c in csv.DictReader(open(D / "cars.csv", encoding="utf-8-sig")):
        row = sheet.get(k(c["name"])) or sheet.get(k(c["site_name"] or c["name"]))
        how = "spreadsheet (exact name)"
        if not row and k(c["name"]) in smap:
            row = sheet.get(k(smap[k(c["name"])]))
            how = "spreadsheet (hand-matched)"
            if not row: print("BAD MAP", c["name"])
        if not row:
            un.append(c); continue
        g = lambda key: "" if row.get(key) in (None, "") else str(row[key]).strip()
        out.append({"id": c["id"], "hp": g("HP"), "kg": g("Kg"), "lbs": g("Lbs"), "w_hp": g("W:HP"),
                    "drivetrain": g("Drivetrain"), "engine_loc": g("Engine Loc"), "gears": g("Gears"),
                    "transmission": g("Transmission"), "car_type": g("Type"), "spec_source": how})
    with open(D / "overrides/car_specs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(out)
    full = sum(1 for r in out if r["hp"] and r["kg"])
    print(f"{len(out)} cars with a sheet row, {full} with HP+kg; {len(un)} cars with none")
    for c in un: print("  none:", c["ai_enabled"], c["id"], "|", c["name"])

if __name__ == "__main__":
    main(sys.argv[1])
