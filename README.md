# iRacing cars and tracks, with an AI filter

The full iRacing car and track catalog, flagged by whether iRacing lists each item as **AI-enabled**
(asphalt and dirt). A small script keeps it current, and a searchable web page lets you filter it
from any device.

- **Web page:** `index.html` (free on GitHub Pages: `https://loupus00.github.io/<repo-name>/`, or open the file locally)
- **Data:** `data/cars.csv`, `data/tracks.csv` (same content as `.json`); column `ai_enabled` is `yes`/`no`
- **What changed and when:** `CHANGES.md`

## Where each field comes from

| Field | Source | Trust |
|---|---|---|
| `ai_enabled`, `rain`, `legacy`, track `configs`, `surface` for AI rows | iRacing support pages "AI Content Available" (asphalt, dirt) | As good as iRacing's pages |
| the catalog itself, car `category` (NASCAR, Sports Car, Prototypes, Formula Car, Dirt Oval, Rallycross, Off-Road), `detail_url`, `image_url`, `site_label` (New, Tech Track) | iracing.com/cars and /tracks | iRacing's own data |
| `car_class`, `track_type` | Rules in `scripts/ailists.py` (`meta_source = estimate`) | **Best guess, not from iRacing**; many non-AI items are left "Unclassified" rather than guessed |
| the same fields, typed by you in `data/overrides/` | You (`meta_source = override`) | Wins over estimates |
| images | Downloaded from the iracing.com thumbnails by the update script | See "Images" |

Not-AI rows have `surface = unknown` unless iRacing's category says Dirt Oval (cars) or the name says "Dirt"
(tracks); the sources do not state a surface for them, so none is guessed. `rain` is `unknown` for them.

### "Added" dates and the highlight

Each AI row can carry `ai_added` (the date it joined iRacing's AI list) and `ai_added_src`:
- `release notes`: dates typed into `data/overrides/added.csv` (`id,ai_added,source`). The 9/9/2026 Season 4
  items came from iRacing's "2026 Season 4 Initial Release Notes".
- `detected`: set by the update script to the day it first noticed a new AI item. iRacing's pages carry no dates,
  so this is the day *this script saw it*, which can lag the real date by up to a week.
- Items that were already AI-enabled when tracking began (2026-10-29) have no date and show none.

The viewer highlights every row whose `ai_added` equals the newest date found across cars and tracks. When a
newer batch appears, the older batch loses its highlight and keeps its "Added M/D/YYYY" line. Track dates apply
to the whole track row, even when iRacing only added some configs (for example Auto Club, Kansas).

### Name matching (AI list <-> iracing.com)

The two sources spell names differently ("Next Gen NASCAR Cup Series Chevrolet Camaro ZL1" vs
"NASCAR Cup Series Next Gen Chevrolet Camaro ZL1"). Names are normalised (case, accents, punctuation) and then
looked up in `data/overrides/aliases.csv` (`kind,ai_name,site_name`). The aliases shipped were chosen by
comparing names, not verified against iRacing; a few are less certain than the rest (the "NASCAR Truck ..."
rows to the "NASCAR Truck Series ..." cars, `Audi R8 LMS` to `Audi R8 LMS GT3`, `Porsche 911 GT3 Cup (991)`).
**Unmatched AI items** are printed by the update script and show up in the viewer without a link or thumbnail.
At the time of writing: cars `Ford GT GT2`, `Ford GT GT3`, `Formula Vee - Cutlass`, `Street Stock`,
`Street Stock - Casino, Eagle`, `ARCA Menards Chevrolet Impala`; tracks `Nürburgring Combined`,
`Bristol Motor Speedway - 2021` (dirt). Add a line to `aliases.csv` once you know the right counterpart.
An unmatched item on iracing.com also appears as a separate "No AI" row, so a wrong or missing alias can create a duplicate.

## Publish it on GitHub (free)

1. Signed in as `loupus00`, create a **public** repository (for example `iracing-ai-lists`).
2. Upload everything in this folder. The web uploader takes up to 100 files per batch, so for the `images/`
   folder it is easier to use git from the NAS (below) once the first run has downloaded the images.
3. *Settings > Pages > Build and deployment*: Source = *Deploy from a branch*, branch `main`, folder `/ (root)`.
4. After a minute the page is at `https://loupus00.github.io/<repo-name>/`.

## Weekly update on the Synology NAS

`scripts/update.py` reads the two support pages and the two iracing.com pages, compares them with the stored
lists, records changes in `data/` and `CHANGES.md`, and downloads thumbnails that are missing.
It uses only the Python standard library and needs to run somewhere that can reach `support.iracing.com`,
`www.iracing.com` and `s100.iracing.com`; the Claude sandbox it was built in could not reach any of them.

1. Install the **Python 3** package in DSM Package Center. You also need `git` (DSM's *Git Server*
   package provides it; I have not checked this against your DSM version).
2. Clone your repo onto the NAS and make sure `git push` works non-interactively
   (a GitHub deploy key with write access is the usual way).
3. Try it by hand first: `python3 scripts/update.py --dry-run`
   then `python3 scripts/update.py`. The first real run downloads about 340 thumbnails at
   0.4 s apiece plus transfer time: I expect roughly 3-6 minutes (an estimate; I could not time it against the real site).
4. *Control Panel > Task Scheduler > Create > Scheduled Task > User-defined script*, weekly, running
   `sh /path/to/iracing-ai-lists/scripts/run_update.sh`.
   The script pulls, updates, and commits and pushes only when something changed.

**Safety nets.** If a support page changes layout, the script stops with an error and writes nothing.
If the iracing.com pages cannot be read, it prints a warning and keeps using the stored snapshot
(`data/source/catalog_*.txt`), so the AI list still updates. A bad image download is reported and skipped.

**Confidence note.** The support-page reader was tested on a reconstruction of the page's table and the
iracing.com reader on synthetic HTML built from the page's rendered text. Neither has run against the live HTML,
so expect that the first run on the NAS may need a fix. `--dry-run` writes nothing, so it is safe to try.

## Images

- The viewer shows the local file when there is one and otherwise falls back to iRacing's own thumbnail URL
  (so you see pictures before the first download; hotlinking depends on iRacing's server allowing it).
- Local files are named by row `id`: `images/cars/<id>__1.jpg`, `images/tracks/<id>.jpg`. Extra car images
  can be added as `<id>__2.jpg` etc. by hand; the script only fetches the one listing thumbnail per car.
  Several images per car would need the individual car pages, which I have not written a reader for.
- iRacing owns these images. You asked to use them; keeping them in a public repo is your call.
- Options: `--no-images`, `--image-limit N`.

## Fixing a wrong class or track type

Add a line to `data/overrides/cars.csv` (`id,category,car_class`) or `data/overrides/tracks.csv`
(`id,track_type`), then run `python3 scripts/build_data.py`. Overrides survive every update.

## Files

- `scripts/update.py` fetch pages, update data, download images (the weekly job)
- `scripts/site_scrape.py` iracing.com catalog reader and image downloader
- `scripts/build_data.py` rebuild from saved snapshots in `data/source/` without the network
- `scripts/ailists.py` parsing, estimate rules, matching, merge logic
- `scripts/run_update.sh` update, then commit and push if changed
- `data/source/*.txt` the last captured pages. `catalog_cars.txt` and `catalog_tracks.txt` were seeded from a
  text rendering of the iracing.com pages (2026-10-29) and are replaced by the first successful live run.
