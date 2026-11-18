"""Turn the transcriptions in data/transcriptions/*.txt into data/keys.csv and check them.

Transcription format (one lead per line):
    <couplet><lead> | text | goto | taxon | group | note
    e.g.  27a | Pharyngeal armature ... | | Phlebotomus stantoni | | Lewis 1978 p. 248
A line "# key_id: xxx" starts a new key. Other lines starting with "#" are comments.
Several taxa in one result are separated by ";".

data/transcriptions/_update_notes.txt adds notes from later literature ("UPDATE: ...").

Checks: every couplet has exactly an a- and b-lead, every goto exists, every lead ends in either a
goto or a taxon, every couplet is reachable from the start couplet, and every taxon is in taxa.csv.

Usage:  python scripts/build_data.py
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TR = DATA / "transcriptions"

CFG = json.loads((ROOT / "project.json").read_text(encoding="utf-8")) if (ROOT / "project.json").exists() else {}
RANKS = set(CFG.get("rank_results", ["Genus", "Subgenus", "Tribe", "Subfamily", "Family", "Section", "Series", "Group"]))

LEAD_RE = re.compile(r"^([A-Za-z]*\d+)([ab])$")


def read_csv(name):
    with open(DATA / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_transcriptions():
    leads = []
    for path in sorted(TR.glob("*.txt")):
        if path.name.startswith("_"):
            continue
        key_id = None
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            m = re.match(r"#\s*key_id:\s*(\S+)", line)
            if m:
                key_id = m.group(1)
                continue
            if line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            parts += [""] * (6 - len(parts))
            lid, text, goto, taxon, group, note = parts[:6]
            # page references such as "Lewis 1978 p. 233" go to their own column; the rest stays as a note
            page_ref = ""
            pm = re.match(r"^((?:[A-Z][\w\-]+(?: (?:&|and) [A-Z][\w\-]+| et al\.)?) \d{4}[a-z]? pp?\. [\d, \-]+)\.?\s*(.*)$", note)
            if pm:
                page_ref, note = pm.group(1).strip(" ,"), pm.group(2).strip()
            lm = LEAD_RE.match(lid)
            if not lm or not key_id:
                sys.exit(f"{path.name}:{n}: cannot parse lead id '{lid}'")
            leads.append({
                "key_id": key_id, "couplet": lm.group(1), "lead": lm.group(2), "lead_id": lid,
                "text": text, "goto": goto, "taxon": taxon, "group": group,
                "figures": "; ".join(re.findall(r"Figs?\.?\s*[\d][\w,\s\-–]*?(?=\)|;|$)", text)),
                "note": note, "page_ref": page_ref, "update_note": "", "source_file": path.name,
            })
    return leads


def apply_updates(leads):
    idx = {(l["key_id"], l["lead_id"]): l for l in leads}
    problems = []
    path = TR / "_update_notes.txt"
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        head, note = [p.strip() for p in line.split("|", 1)]
        key_id, lead_id = head.split()
        lead = idx.get((key_id, lead_id))
        if not lead:
            problems.append(f"_update_notes.txt:{n}: unknown lead {key_id} {lead_id}")
            continue
        lead["update_note"] = (lead["update_note"] + " " + note).strip()
    return problems


def validate(leads, keys_index, taxa_names):
    problems = []
    by_key = defaultdict(list)
    for l in leads:
        by_key[l["key_id"]].append(l)
    starts = {k["key_id"]: k["start"] for k in keys_index}
    for key_id, ls in by_key.items():
        if key_id not in starts:
            problems.append(f"{key_id}: not listed in keys_index.csv")
            continue
        couplets = defaultdict(list)
        for l in ls:
            couplets[l["couplet"]].append(l["lead"])
        for c, sides in couplets.items():
            if sorted(sides) != ["a", "b"]:
                problems.append(f"{key_id} couplet {c}: leads {sides} (need exactly a and b)")
        for l in ls:
            if l["goto"] and l["goto"] not in couplets:
                problems.append(f"{key_id} {l['lead_id']}: goto {l['goto']} does not exist")
            if bool(l["goto"]) == bool(l["taxon"]):
                problems.append(f"{key_id} {l['lead_id']}: needs either goto or taxon (not both/neither)")
            for t in filter(None, (x.strip() for x in l["taxon"].split(";"))):
                # results that are a higher rank ("Subgenus Euphlebotomus") need no row in taxa.csv
                if t.split(" ")[0] in RANKS:
                    continue
                if t not in taxa_names:
                    problems.append(f"{key_id} {l['lead_id']}: taxon '{t}' missing from taxa.csv")
        # reachability
        seen, todo = set(), [starts[key_id]]
        while todo:
            c = todo.pop()
            if c in seen or c not in couplets:
                continue
            seen.add(c)
            todo += [l["goto"] for l in ls if l["couplet"] == c and l["goto"]]
        for c in couplets:
            if c not in seen:
                problems.append(f"{key_id}: couplet {c} is unreachable from start {starts[key_id]}")
    return problems


def main():
    leads = parse_transcriptions()
    problems = apply_updates(leads)
    keys_index = read_csv("keys_index.csv")
    taxa_names = set()
    if (DATA / "taxa.csv").exists():
        for t in read_csv("taxa.csv"):
            taxa_names.add(t["taxon"])
            taxa_names.update(x.strip() for x in t["key_names"].split(";") if x.strip())

    problems += validate(leads, keys_index, taxa_names)
    fields = ["key_id", "couplet", "lead", "lead_id", "text", "goto", "taxon", "group",
              "figures", "note", "page_ref", "update_note", "source_file"]
    with open(DATA / "keys.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(leads)
    n_keys = len({l["key_id"] for l in leads})
    print(f"keys.csv: {len(leads)} leads in {n_keys} keys")
    if problems:
        print(f"{len(problems)} problem(s):")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
