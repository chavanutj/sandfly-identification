"""PDF helpers for transcribing identification keys.

    python scripts/pdf_tools.py info      <pdf>                     pages, text per page, scanned or not, DOIs
    python scripts/pdf_tools.py text      <pdf> <out.txt>           text with "=== PAGE n ===" markers
    python scripts/pdf_tools.py find-keys <pdf>                     pages that probably contain a dichotomous key
    python scripts/pdf_tools.py render    <pdf> <pages> <outdir> [dpi]   e.g. pages "7-17,20"; default dpi 130
    python scripts/pdf_tools.py figures   <pdf>                     figure captions with page numbers

Why render? Keys printed with dot leaders or in two columns are scrambled by text extraction
(one word per line, columns interleaved). Transcribe keys from the rendered page images, and
use the extracted text only to locate pages and to copy long passages.
Needs: pip install pymupdf
"""
import re
import sys
from pathlib import Path

import pymupdf

KEY_HEAD = re.compile(r"(key\s+to\b|identification\s+key|dichotomous|cl[ée]\s+(de|d'identification)|chave\s+de|"
                      r"clave\s+(de|para)|table\s+\d+\s+key)", re.I)
# a couplet-like line: "12 Cibarium with ... 13" / "12a ..." / "– Style with five spines ...... 14"
COUPLET = re.compile(r"^\s*(\d{1,3}[ab]?\.?|[-–—])\s*\(?\d*\)?\s+[A-Z♀♂].{8,}", re.M)
DOI = re.compile(r"10\.\d{4,9}/[^\s\"<>,;)]+", re.I)


def parse_pages(spec, n):
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        a = int(a)
        b = int(b) if b else a
        out += [p for p in range(a, b + 1) if 1 <= p <= n]
    return out


def cmd_info(pdf):
    d = pymupdf.open(pdf)
    chars = [len(p.get_text()) for p in d]
    scanned = sum(1 for c in chars if c < 150)
    text = "".join(p.get_text() for p in d[:3])
    print(f"file:     {Path(pdf).name}")
    print(f"pages:    {d.page_count}")
    print(f"text:     {sum(chars)} characters; {scanned} page(s) with almost no text")
    if scanned > d.page_count * 0.6:
        print("WARNING:  looks like a scanned/image-only PDF. Read it from rendered page images.")
    dois = sorted(set(m.rstrip(".") for m in DOI.findall(text)))
    print(f"DOIs (first pages): {', '.join(dois[:5]) or '-'}")
    meta = d.metadata or {}
    if meta.get("title"):
        print(f"title:    {meta['title']}")


def cmd_text(pdf, out):
    d = pymupdf.open(pdf)
    Path(out).write_text("".join(f"\n\n=== PAGE {i + 1} ===\n" + p.get_text() for i, p in enumerate(d)), encoding="utf-8")
    print(f"wrote {out}")


def cmd_find_keys(pdf):
    d = pymupdf.open(pdf)
    for i, p in enumerate(d):
        t = p.get_text()
        heads = [" ".join(m.group(0).split()) for m in KEY_HEAD.finditer(t)]
        couplets = len(COUPLET.findall(t))
        leaders = t.count(" . . ") + t.count("....") + t.count(" .\n")
        score = len(heads) * 5 + couplets + leaders // 5
        if score >= 6:
            line = next((" ".join(l.split()) for l in t.splitlines() if KEY_HEAD.search(l)), "")
            print(f"page {i + 1:4d}  score {score:3d}  couplet-like lines {couplets:3d}  {line[:90]}")


def cmd_render(pdf, spec, outdir, dpi=130):
    d = pymupdf.open(pdf)
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9]+", "_", Path(pdf).stem)[:30]
    for p in parse_pages(spec, d.page_count):
        f = out / f"{stem}_p{p:03d}.png"
        d[p - 1].get_pixmap(dpi=int(dpi)).save(f)
        print(f)


def cmd_figures(pdf):
    d = pymupdf.open(pdf)
    rx = re.compile(r"^(Fig\.?|Figure|Figs?\s)\s*(\d+)[.:]?\s*(.{0,90})")
    for i, p in enumerate(d):
        for b in p.get_text("blocks"):
            t = " ".join(b[4].split())
            m = rx.match(t)
            if m:
                print(f"page {i + 1:4d}  {m.group(1)} {m.group(2)}  {m.group(3)}")


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    {"info": cmd_info, "text": cmd_text, "find-keys": cmd_find_keys,
     "render": cmd_render, "figures": cmd_figures}[cmd](*args)


if __name__ == "__main__":
    main()
