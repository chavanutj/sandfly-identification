"""Crop the glossary diagrams listed in data/diagrams.csv out of the figures in site/img/figures/.

    python scripts/make_diagrams.py

Run it again after changing a crop. Output goes to scripts/assets/img/diagrams/ (copied into site/ by build_site.py).
Hotspot coordinates in data/hotspots.csv are in pixels of the ORIGINAL figure, so changing a crop does not move them.
Needs Pillow (pip install pillow).
"""
import csv
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
figs = {r["figure_id"]: r for r in csv.DictReader(open(ROOT / "data" / "figures.csv", encoding="utf-8"))}
for d in csv.DictReader(open(ROOT / "data" / "diagrams.csv", encoding="utf-8")):
    src = ROOT / "site" / figs[d["figure_id"]]["file"]
    x0, y0, x1, y1 = map(int, d["crop"].split())
    out = ROOT / "scripts" / d["file"]  # file is assets/img/diagrams/<id>.jpg
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.open(src).convert("RGB").crop((x0, y0, x1, y1)).save(out, quality=88, optimize=True)
    print(f"{d['diagram_id']}: {x1 - x0}x{y1 - y0} -> {out.relative_to(ROOT)}")
