"""Merge staged additions (written by parallel key-transcriber agents) into data/.

Each agent writes only inside data/staging/<batch>/ (plus its own new data/transcriptions/<source_id>.txt):
    sources.csv  keys_index.csv  taxa.csv  conflicts.csv  glossary.csv  figure_sources.csv
    literature_log.csv  update_notes.txt
using the same column headers as the files in data/ (missing columns are allowed).

Merge rules
- sources, keys_index, glossary, figure_sources: append rows whose id (first column) is new; an existing id is
  reported and skipped.
- taxa: a new taxon is appended. For an existing taxon, empty fields are filled; text fields that already have
  content get the new text appended after " | " (if not already present); list fields (key_names, sources,
  figure_ids) are merged as ;-separated sets. 'genus', 'subgenus', 'author', 'status' are never overwritten -
  a differing value is reported so a human can decide (and log it in conflicts.csv).
- conflicts: appended with the next free C-number (the staged conflict_id is ignored).
- literature_log: rows matched by DOI (else citation) update status/source_id/notes; unmatched rows are appended.
- update_notes.txt: lines appended (exact duplicates skipped).

    python scripts/merge_staging.py --check <batch>   merge into a temporary copy and run build_data.py there
    python scripts/merge_staging.py <batch> [<batch> ...]   merge for real (then run update_site.py)
    python scripts/merge_staging.py --all             merge every folder in data/staging/
Merged batches are moved to data/staging/_merged/.
"""
import csv
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIST_FIELDS = {"key_names", "sources", "figure_ids"}
KEEP_FIELDS = {"taxon", "genus", "subgenus", "author", "status"}


def read(p):
    if not p.exists():
        return [], []
    with open(p, encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        return list(r), r.fieldnames or []


def write(p, rows, fields):
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def merge_batch(data, stage, log):
    # simple id-keyed tables
    for name in ["sources.csv", "keys_index.csv", "glossary.csv", "figure_sources.csv"]:
        new, _ = read(stage / name)
        if not new:
            continue
        rows, fields = read(data / name)
        idf = fields[0]
        have = {r[idf] for r in rows}
        for r in new:
            if r.get(idf) in have:
                log.append(f"{stage.name}/{name}: '{r.get(idf)}' already exists - skipped")
            else:
                rows.append({k: r.get(k, "") for k in fields})
                have.add(r.get(idf))
        write(data / name, rows, fields)

    # taxa
    new, _ = read(stage / "taxa.csv")
    if new:
        rows, fields = read(data / "taxa.csv")
        idx = {r["taxon"]: r for r in rows}
        for r in new:
            t = (r.get("taxon") or "").strip()
            if not t:
                continue
            if t not in idx:
                row = {k: (r.get(k) or "") for k in fields}
                rows.append(row)
                idx[t] = row
                continue
            cur = idx[t]
            for k in fields:
                v = (r.get(k) or "").strip()
                if not v or k == "taxon":
                    continue
                if k in LIST_FIELDS:
                    items = [x for x in cur[k].split(";") if x.strip()]
                    for x in v.split(";"):
                        if x.strip() and x.strip() not in [i.strip() for i in items]:
                            items.append(x.strip())
                    cur[k] = ";".join(i.strip() for i in items)
                elif not cur[k].strip():
                    cur[k] = v
                elif k in KEEP_FIELDS:
                    if v != cur[k]:
                        log.append(f"{stage.name}/taxa.csv: {t}: {k} differs (kept '{cur[k]}', staged '{v}') - check, log in conflicts.csv")
                elif v not in cur[k]:
                    cur[k] = f"{cur[k]} | {v}"
        write(data / "taxa.csv", sorted(rows, key=lambda x: x["taxon"]), fields)

    # conflicts
    new, _ = read(stage / "conflicts.csv")
    if new:
        rows, fields = read(data / "conflicts.csv")
        n = max([int(r["conflict_id"][1:]) for r in rows if r["conflict_id"][1:].isdigit()] or [0])
        for r in new:
            n += 1
            row = {k: (r.get(k) or "") for k in fields}
            row["conflict_id"] = f"C{n:02d}"
            rows.append(row)
        write(data / "conflicts.csv", rows, fields)

    # literature log
    new, _ = read(stage / "literature_log.csv")
    if new:
        rows, fields = read(data / "literature_log.csv")
        for r in new:
            m = next((x for x in rows if r.get("doi") and x["doi"].lower() == r["doi"].lower()), None) or \
                next((x for x in rows if not r.get("doi") and x["citation"] == r.get("citation")), None)
            if m:
                for k in ("status", "source_id", "notes"):
                    if r.get(k):
                        m[k] = r[k]
            else:
                rows.append({k: (r.get(k) or "") for k in fields})
        write(data / "literature_log.csv", rows, fields)

    # update notes
    un = stage / "update_notes.txt"
    if un.exists():
        target = data / "transcriptions" / "_update_notes.txt"
        old = target.read_text(encoding="utf-8")
        have = set(old.splitlines())
        add = [l for l in un.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#") and l not in have]
        if add:
            target.write_text(old.rstrip("\n") + "\n" + "\n".join(add) + "\n", encoding="utf-8")


def main():
    args = sys.argv[1:]
    if not args or any(a in ("-h", "--help", "help") for a in args):
        sys.exit(__doc__)
    check = "--check" in args
    args = [a for a in args if a != "--check"]
    stroot = ROOT / "data" / "staging"
    if args == ["--all"]:
        batches = [p.name for p in stroot.iterdir() if p.is_dir() and not p.name.startswith("_")] if stroot.exists() else []
    else:
        unknown = [a for a in args if a.startswith("-") or not (stroot / a).is_dir()]
        if unknown:
            sys.exit(f"Unknown option or no such batch folder in data/staging/: {', '.join(unknown)}\n\n{__doc__}")
        batches = args
    if not batches:
        sys.exit("Nothing to merge: data/staging/ has no batch folders.")
    log = []
    if check:
        tmp = Path(tempfile.mkdtemp())
        shutil.copytree(ROOT / "data", tmp / "data")
        shutil.copytree(ROOT / "scripts", tmp / "scripts")
        shutil.copy(ROOT / "project.json", tmp / "project.json")
        for b in batches:
            merge_batch(tmp / "data", stroot / b, log)
        print("\n".join(log) or "merge: no warnings")
        r = subprocess.run([sys.executable, str(tmp / "scripts" / "build_data.py")], cwd=tmp)
        shutil.rmtree(tmp, ignore_errors=True)
        sys.exit(r.returncode)
    for b in batches:
        merge_batch(ROOT / "data", stroot / b, log)
        dest = stroot / "_merged" / b
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(stroot / b), str(dest))
        print(f"merged {b}")
    print("\n".join(log) or "no warnings")


if __name__ == "__main__":
    main()
