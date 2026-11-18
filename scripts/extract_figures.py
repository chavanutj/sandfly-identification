"""Extract figures from the open-access (CC BY) source PDFs into site/img/figures/.

Only sources whose licence allows reuse with attribution are processed. For each figure
caption ("Fig. 3", "Figure 3.", "Fig 3.") the page region covered by images and drawings is
rendered to a JPEG, and the caption is saved to data/figures.csv.

Which PDFs to process is set in data/figure_sources.csv (one row per CC BY paper:
figure_prefix, source_id, pdf_file, caption_regex, licence). Add a row there for a new paper.
Rows of data/figures.csv belonging to sources whose PDF is not present are kept unchanged,
so the script is safe to run on a machine (or in CI) that lacks some PDFs.

Usage:  python scripts/extract_figures.py              all sources in figure_sources.csv
        python scripts/extract_figures.py ding2025     only one figure_prefix
Needs:  pip install pymupdf
"""
import csv
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "img" / "figures"
PDF_DIRS = [ROOT, ROOT / "inbox", ROOT / "sources"]  # PDFs are git-ignored; keep them in any of these

with open(ROOT / "data" / "figure_sources.csv", encoding="utf-8") as _f:
    SOURCES = {r["figure_prefix"]: (r["pdf_file"], r["caption_regex"], r["licence"]) for r in csv.DictReader(_f)}


def find_pdf(name):
    for d in PDF_DIRS:
        p = d / name
        if p.exists():
            return p
        hits = list(d.rglob(name)) if d != ROOT else []
        if hits:
            return hits[0]
    # tolerate small differences in punctuation of file names
    key = re.sub(r"[^a-z0-9]", "", name.lower())[:40]
    for d in PDF_DIRS:
        for q in (d.glob("*.pdf") if d == ROOT else d.rglob("*.pdf")):
            if re.sub(r"[^a-z0-9]", "", q.name.lower())[:40] == key:
                return q
    return None


def figure_rects(page):
    """Image and drawing boxes on the page, ignoring tiny items and full-page frames."""
    rects = [pymupdf.Rect(i["bbox"]) for i in page.get_image_info()]
    rects += [d["rect"] for d in page.get_drawings() if d["rect"].width > 30 and d["rect"].height > 30]
    pr = page.rect
    return [r for r in rects if r.width * r.height > 2000 and r.width < pr.width * 0.98]


def figure_clip(rects, caption_rect, upper_limit):
    """Union of the boxes lying between the previous caption (upper_limit) and this caption."""
    sel = [r for r in rects if r.y1 <= caption_rect.y0 + 8 and r.y0 >= upper_limit - 2]
    if not sel:
        return None
    clip = pymupdf.Rect(caption_rect)
    for r in sel:
        clip |= r
    return clip + (-6, -6, 6, 6)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])
    fig_csv = ROOT / "data" / "figures.csv"
    old = []
    if fig_csv.exists():
        with open(fig_csv, encoding="utf-8") as f:
            old = list(csv.DictReader(f))
    rows, done = [], set()
    for sid, (fname, rx, lic) in SOURCES.items():
        if only and sid not in only:
            continue
        pdf = find_pdf(fname)
        if not pdf:
            print(f"[skip] {sid}: PDF not found ({fname}); existing figure rows kept")
            continue
        done.add(sid)
        doc = pymupdf.open(pdf)
        seen = set()
        for pno, page in enumerate(doc):
            rects = figure_rects(page)
            caps = []
            for block in page.get_text("blocks"):
                text = " ".join(block[4].split())
                m = re.match(rx, text)
                if m:
                    caps.append((pymupdf.Rect(block[:4]), m))
            caps.sort(key=lambda c: c[0].y0)
            upper = 0
            for crect, m in caps:
                n = int(m.group(1))
                clip = figure_clip(rects, crect, upper)
                upper = crect.y1
                if clip is None or n in seen:
                    continue
                seen.add(n)
                fig_id = f"{sid}:Fig{n}"
                out = OUT / f"{sid}_fig{n}.jpg"
                page.get_pixmap(dpi=160, clip=clip).save(out, jpg_quality=82)
                caption = re.sub(r"\s*https?://doi\S+", "", m.group(2)).strip()
                rows.append({"figure_id": fig_id, "source_id": sid, "figure": f"Fig. {n}",
                             "file": f"img/figures/{out.name}", "page": pno + 1,
                             "caption": caption, "licence": lic})
                print(f"[ok] {fig_id} page {pno + 1}")
    rows += [r for r in old if r["source_id"] not in done]   # keep figures of sources not processed now
    with open(fig_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["figure_id", "source_id", "figure", "file", "page", "caption", "licence"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["source_id"], int(r["figure"].split()[1]))))
    print(f"{len(rows)} figures written to data/figures.csv")


if __name__ == "__main__":
    main()
