#!/usr/bin/env python3
"""Parse a Fandom Special:Export XML of the iRacing wiki car pages -> list of dicts."""
import re, xml.etree.ElementTree as ET

def clean(s): return re.sub(r"\s+", " ", re.sub(r"\[\[File:[^\]]*\]\]", "", s or "")).strip()

def parse(path):
    root = ET.parse(path).getroot()
    ns = {"m": root.tag.split("}")[0][1:]}
    out = []
    for pg in root.findall("m:page", ns):
        title = pg.find("m:title", ns).text
        rev = pg.find("m:revision", ns)
        txt = rev.find("m:text", ns).text or ""
        d = {"wiki_title": title, "wiki_edited": rev.find("m:timestamp", ns).text[:10]}
        body = re.sub(r"\[\[Category:[^\]]*\]\]", "", txt)
        def f(label, stop=r"\n"):
            m = re.search(label + r":\s*(.*?)(?=" + stop + r"|$)", body, re.S)
            return clean(m.group(1)) if m else ""
        pw = f("Power"); m = re.match(r"([\d.,]+)\s*hp", pw)
        d["hp"] = str(round(float(m.group(1).replace(",", "")))) if m else ""
        wt = f("Weight"); m = re.match(r"([\d.,]+)\s*kg", wt)
        d["kg"] = str(round(float(m.group(1).replace(",", "")))) if m else ""
        m = re.search(r"\(([\d.,]+)\s*lbs", wt); d["lbs"] = str(round(float(m.group(1).replace(",", "")))) if m else ""
        d["engine"] = f("Engine")
        d["configuration"] = f("Configuration")
        d["year"] = f("Year")
        d["wiki_type"] = f("Type")
        d["difficulty"] = f("Difficulty")
        m = re.search(r"Price:\s*\$([\d.]+)", body); d["price_usd"] = m.group(1) if m else ""
        m = re.search(r"Bio:\s*(.*)", body, re.S); d["bio"] = clean(m.group(1)) if m else ""
        cats = re.findall(r"\[\[Category:([^\]]*)\]\]", txt)
        d["cats"] = cats
        d["transmission"] = next((c for c in cats if re.search(r"Shift|Manual|H-Pattern|Automatic|Dog|Sequential|Paddle|CVT|DM", c) and "Single-DM" not in c), "")
        d["rain_enabled"] = "yes" if "Rain Enabled" in cats else ""
        out.append(d)
    return out

if __name__ == "__main__":
    import sys
    rows = parse(sys.argv[1])
    for k in ("hp", "kg", "lbs", "engine", "configuration", "year", "wiki_type", "difficulty", "price_usd", "bio", "transmission"):
        print(k, sum(1 for r in rows if r[k]))
    print(len(rows))
