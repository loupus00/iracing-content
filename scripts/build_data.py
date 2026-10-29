#!/usr/bin/env python3
"""Rebuild data/ from the saved snapshots in data/source/ (no network needed).

Use this for the first import, or to re-run the rules after editing them.
Normal weekly updates use update.py, which fetches the live support pages.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ailists  # noqa: E402

SRC = ailists.DATA / "source"


def read_snapshot(name: str, width: int):
    rows, modified = [], ""
    for line in (SRC / name).read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            m = re.search(r"Page modified: (.*?)\. Captured", line)
            modified = m.group(1) if m else modified
            continue
        if not line.strip():
            continue
        cells = line.split("|")
        rows.append(cells + [""] * (width - len(cells)))
    return rows, modified


def main():
    dry = "--dry-run" in sys.argv
    asphalt, a_mod = read_snapshot("asphalt_snapshot.txt", 4)
    dirt, d_mod = read_snapshot("dirt_snapshot.txt", 2)
    site_cars = ailists.read_site_snapshot(SRC / "catalog_cars.txt", "cars")
    site_tracks = ailists.read_site_snapshot(SRC / "catalog_tracks.txt", "tracks")
    s = ailists.run_update(asphalt, dirt, {"asphalt": a_mod, "dirt": d_mod}, dry_run=dry,
                           site_cars=site_cars or None, site_tracks=site_tracks or None)
    print("changed:", s["changed"], "| counts:", s["counts"])
    for k, names in s["unmatched_ai"].items():
        if names:
            print(f"AI {k} with NO iracing.com match ({len(names)}):", names)
    for k, log in s["logs"].items():
        for kind, items in log.items():
            if items:
                print(f"  {k} {kind}: {len(items)}")
    if s["unclassified"]:
        print("UNCLASSIFIED cars:", s["unclassified"])


if __name__ == "__main__":
    main()
