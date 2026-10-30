#!/usr/bin/env python3
"""Parse a Fandom Special:Export XML of iRacing wiki track pages."""
import re, xml.etree.ElementTree as ET
from wiki_cars import clean

LABELS = ["Location", "Length", "Turns", "Configurations", "Pit Road Speed", "Price", "Owner", "Opened", "Status",
          "Difficulty", "Types", "Seating Capacity", "Track Changes", "Nicknames", "Banking", "Fantasy Names", "Bio"]

def parse(path):
    root = ET.parse(path).getroot(); ns = {"m": root.tag.split("}")[0][1:]}
    out = []
    for pg in root.findall("m:page", ns):
        rev = pg.find("m:revision", ns); txt = rev.find("m:text", ns).text or ""
        body = re.sub(r"\[\[Category:[^\]]*\]\]", "", txt)
        body = re.sub(r"\[\[File:[^\]]*\]\]", "", body)
        d = {"wiki_title": pg.find("m:title", ns).text, "wiki_edited": rev.find("m:timestamp", ns).text[:10]}
        def f(label):
            m = re.search(r"(?m)^" + label + r":[ \t]*(.*?)(?=\n(?:" + "|".join(re.escape(l) for l in LABELS) + r")\b[^\n]*:|\n== |\Z)", body, re.S)
            return clean(m.group(1)) if m else ""
        for lab, key in [("Location", "location"), ("Length", "length_raw"), ("Turns", "turns"), ("Configurations", "configs_n"),
                         ("Pit Road Speed", "pit_speed"), ("Owner", "owner"), ("Opened", "opened"), ("Status", "status"),
                         ("Difficulty", "difficulty"), ("Types", "types"), ("Seating Capacity", "seating"), ("Bio", "bio")]:
            d[key] = f(lab)
        d["bio"] = d["bio"].split("Previous Track Logos")[0].strip()
        m = re.search(r"Price:\s*\$([\d.]+)", body); d["price_usd"] = m.group(1) if m else ""
        m = re.search(r"([\d.,]+)(?:\s*to\s*([\d.,]+))?\s*Miles\s*\(([\d.,]+)(?:\s*to\s*([\d.,]+))?\s*km\)", d["length_raw"], re.I)
        d["length_mi"] = (m.group(1) if not m.group(2) else m.group(1) + "-" + m.group(2)) if m else ""
        d["length_km"] = (m.group(3) if not m.group(4) else m.group(3) + "-" + m.group(4)) if m else ""
        d["cats"] = re.findall(r"\[\[Category:([^\]]*)\]\]", txt)
        out.append(d)
    return out

if __name__ == "__main__":
    import sys; R = parse(sys.argv[1])
    for k in ("location","length_mi","turns","configs_n","pit_speed","price_usd","opened","status","difficulty","types","bio"):
        print(k, sum(1 for r in R if r[k]))
    print(len(R)); print({k: R[3][k] for k in R[3] if k != "cats"})
