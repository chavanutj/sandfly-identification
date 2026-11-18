"""One command to rebuild and check everything after editing data or adding a paper.

    python scripts/update_site.py            rebuild data + site, check links, print what changed
    python scripts/update_site.py --figures  also re-extract figures from CC BY PDFs (needs pymupdf + PDFs)
    python scripts/update_site.py --serve    afterwards open a local preview at http://127.0.0.1:8000

Steps: [figures] -> build_data.py (validates every key) -> build_site.py -> link check -> summary.
Stops at the first failing step and shows why. Windows users can double-click update.bat.
"""
import json
import re
import subprocess
import sys
import urllib.parse
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
STATE = ROOT / "data" / ".last_build.json"


def run(script, *args):
    print(f"\n== {script} {' '.join(args)}", flush=True)
    r = subprocess.run([PY, str(ROOT / "scripts" / script), *args], cwd=ROOT)
    if r.returncode:
        sys.exit(f"\nSTOPPED: {script} reported problems (see above). Fix them and run again.")


def link_check():
    site = ROOT / "site"
    ids, bad, n = {}, [], 0
    pages = list(site.rglob("*.html"))
    for p in pages:
        ids[p.resolve()] = set(re.findall(r'id="([^"]+)"', p.read_text(encoding="utf-8")))
    for p in pages:
        for u in re.findall(r'(?:href|src)="([^"]+)"', p.read_text(encoding="utf-8")):
            if u.startswith(("http", "mailto", "#key-")):
                continue
            n += 1
            path, _, frag = u.partition("#")
            path = path.split("?")[0]
            tgt = (p.parent / urllib.parse.unquote(path)).resolve() if path else p.resolve()
            if path and not tgt.exists():
                bad.append(f"{p.relative_to(site)} -> {u}")
            elif frag and tgt.suffix == ".html" and frag not in ids.get(tgt, set()):
                bad.append(f"{p.relative_to(site)} -> {u}")
    print(f"\n== link check: {n} internal links in {len(pages)} pages, {len(bad)} broken")
    for b in bad[:25]:
        print("   ", b)
    if bad:
        sys.exit("STOPPED: broken links.")


def count(name):
    p = ROOT / "data" / name
    return sum(1 for _ in open(p, encoding="utf-8")) - 1 if p.exists() else 0


def summary():
    import csv
    leads = list(csv.DictReader(open(ROOT / "data" / "keys.csv", encoding="utf-8")))
    now = {
        "keys": len({l["key_id"] for l in leads}), "leads": len(leads),
        "taxa": count("taxa.csv"), "conflicts": count("conflicts.csv"),
        "update_notes": sum(1 for l in leads if l["update_note"]), "sources": count("sources.csv"),
        "figures": count("figures.csv"), "glossary": count("glossary.csv"),
        "pages": len(list((ROOT / "site").rglob("*.html"))),
    }
    before = json.loads(STATE.read_text()) if STATE.exists() else {}
    print("\n== summary")
    for k, v in now.items():
        d = v - before.get(k, v)
        print(f"   {k:13s} {v:6d}" + (f"   ({'+' if d > 0 else ''}{d} since last build)" if d else ""))
    STATE.write_text(json.dumps(now, indent=1))


def main():
    args = set(sys.argv[1:])
    if "--figures" in args:
        run("extract_figures.py")
    run("build_data.py")
    run("build_site.py")
    link_check()
    summary()
    print("\nDone. Open site/index.html, or run with --serve for a local preview.")
    if "--serve" in args:
        webbrowser.open("http://127.0.0.1:8000/")
        subprocess.run([PY, "-m", "http.server", "8000", "--bind", "127.0.0.1", "-d", str(ROOT / "site")])


if __name__ == "__main__":
    main()
