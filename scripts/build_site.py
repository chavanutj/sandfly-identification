"""Build the static website in site/ from the CSV files in data/.

    python scripts/build_data.py      # 1. parse transcriptions -> data/keys.csv (and check them)
    python scripts/build_site.py      # 2. write site/*.html

The site is plain HTML + one CSS file + one small JS file. Open site/index.html in a browser,
or publish the site/ folder (GitHub Pages, university web space, any static host).
"""
import csv
import html
import json
import re
import shutil
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SITE = ROOT / "site"
ASSETS = ROOT / "scripts" / "assets"

# Everything group-specific comes from project.json (see the key-builder toolkit)
CFG = json.loads((ROOT / "project.json").read_text(encoding="utf-8"))
SITE_TITLE = CFG["title"]
SITE_SUB = CFG.get("subtitle", "Identification keys, species pages and terminology")
SHORT = CFG.get("short_name", "Key")
FOCUS = CFG.get("focus_country", "")
BADGE = CFG.get("focus_badge", FOCUS[:2].upper())


def read(name):
    with open(DATA / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def esc(s):
    return html.escape(s or "")


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


GENERA = list(dict.fromkeys(CFG.get("genera", []) + CFG.get("other_italic_names", [])))
# epithets that are italicised after a genus or its abbreviation; taxa.csv names are added below
EPITHETS = set(CFG.get("extra_epithets", []))
GEN_RX = "|".join([re.escape(g) for g in GENERA] + [re.escape(a) for a in CFG.get("genus_abbreviations", [])]) or "(?!)"


def italic_names(text):
    """Italicise genus names and binomials ('P. argentipes', 'S. babu insularis', 'Phlebotomus stantoni').
    A word after a genus is only treated as an epithet if it is a known epithet (taxa.csv or EPITHETS)."""
    t = esc(text)

    def rep(m):
        words, keep = m.group(2).split(" "), []
        for w in words:
            if w in EPITHETS:
                keep.append(w)
            else:
                break
        if not keep:
            return m.group(0)
        rest = m.group(2)[len(" ".join(keep)):]
        return f"<i>{m.group(1)} {' '.join(keep)}</i>{rest}"
    t = re.sub(rf"\b({GEN_RX}) ([a-z]+(?: [a-z]+)?)", rep, t)
    if GENERA:
        t = re.sub(rf"(?<![>\w])({'|'.join(map(re.escape, GENERA))})(?![\w<])", r"<i>\1</i>", t)
    return t


# --------------------------------------------------------------------------- data
sources = {s["source_id"]: s for s in read("sources.csv")}
keys_index = sorted(read("keys_index.csv"), key=lambda k: int(k["order"]))
leads = read("keys.csv")
taxa = read("taxa.csv")
glossary = read("glossary.csv")
conflicts = read("conflicts.csv")
figures = {f["figure_id"]: f for f in read("figures.csv")} if (DATA / "figures.csv").exists() else {}

name_to_taxon = {}
for t in taxa:
    EPITHETS.update(t["taxon"].split(" ")[1:])
    for k in t["key_names"].split(";"):
        EPITHETS.update(k.split(" ")[1:])
    name_to_taxon[t["taxon"]] = t
    for k in filter(None, (x.strip() for x in t["key_names"].split(";"))):
        name_to_taxon[k] = t

key_figure_source = CFG.get("key_figure_source", {})  # key_id -> figure prefix, to turn "Fig. 3" in a lead into a thumbnail
for t in taxa:  # older data used the column name thailand_record
    t.setdefault("focus_record", t.get("thailand_record", ""))
FOCUS_PAGE = (slug(FOCUS) or "focus") + ".html"

by_key = defaultdict(list)
for l in leads:
    by_key[l["key_id"]].append(l)

# paths from start couplet to every lead (for "how this taxon keys out")
paths = defaultdict(list)  # taxon name -> list of (key_id, [leads...])
for k in keys_index:
    kid = k["key_id"]
    cmap = defaultdict(list)
    for l in by_key[kid]:
        cmap[l["couplet"]].append(l)

    def walk(c, trail, kid=kid, cmap=cmap):
        for l in sorted(cmap[c], key=lambda x: x["lead"]):
            t2 = trail + [l]
            if l["goto"]:
                walk(l["goto"], t2)
            for name in filter(None, (x.strip() for x in l["taxon"].split(";"))):
                paths[name].append((kid, t2))
    walk(k["start"], [])


def taxon_link(name, prefix):
    t = name_to_taxon.get(name)
    label = f"<i>{esc(name)}</i>" if not name.startswith("Subgenus") else f"Subgenus <i>{esc(name.split(' ', 1)[1])}</i>"
    if t:
        alt = f' <span class="muted">(= <i>{esc(t["taxon"])}</i>)</span>' if t["taxon"] != name else ""
        s = slug(t["taxon"])
        return (f'<a class="taxon" href="{prefix}taxa/{s}.html" title="Open species page">{label}</a>{alt}'
                f'<a class="tolist" href="{prefix}taxa/index.html#{s}" title="Show in species list">☰</a>')
    return label


def fig_links(lead, prefix):
    src = key_figure_source.get(lead["key_id"])
    out = []
    for m in re.finditer(r"Figs?\.?\s*(\d+)", lead["text"]):
        fid = f"{src}:Fig{m.group(1)}" if src else None
        if fid and fid in figures and fid not in [o[0] for o in out]:
            out.append((fid, figures[fid]))
    return "".join(
        f'<a class="thumb" href="{prefix}{f["file"]}" title="{esc(f["figure"])}: {esc(f["caption"][:200])}">'
        f'<img loading="lazy" src="{prefix}{f["file"]}" alt="{esc(f["figure"])}"></a>' for fid, f in out)


# --------------------------------------------------------------------------- page shell
NAV = [("index.html", "Home"), ("keys.html", "Identification keys"), ("taxa/index.html", "Species list"),
       *([(FOCUS_PAGE, f"{FOCUS} records")] if FOCUS else []), ("glossary.html", "Glossary"), ("figures.html", "Figures"),
       ("conflicts.html", "Conflicts & updates"), ("sources.html", "Sources"), ("about.html", "About / how to edit")]


def page(title, body, prefix="", active=""):
    nav = "".join(f'<li><a href="{prefix}{h}"{" class=on" if h == active else ""}>{esc(t)}</a></li>' for h, t in NAV)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} | {esc(SHORT)}</title>
<link rel="stylesheet" href="{prefix}assets/style.css">
<script>(function(){{var d=document.documentElement,q=new URLSearchParams(location.search),s=null,v=null;
try{{s=localStorage.getItem("sf-size");v=localStorage.getItem("sf-view");}}catch(e){{}}
if(q.get("size")){{s=q.get("size");try{{localStorage.setItem("sf-size",s);}}catch(e){{}}}}
if(q.get("view")){{v=q.get("view");try{{localStorage.setItem("sf-view",v);}}catch(e){{}}}}
d.dataset.size=s||"m";d.dataset.view=v||"normal";}})();</script></head>
<body>
<header class="banner"><a class="brand" href="{prefix}index.html"><span class="t1">{esc(SITE_TITLE)}</span>
<span class="t2">{esc(SITE_SUB)}</span></a>
<div class="viewctl" role="group" aria-label="Display settings">
<span class="lbl">Text</span><button type="button" data-size="s" title="Smaller text">A−</button><button type="button" data-size="m" title="Normal text">A</button><button type="button" data-size="l" title="Large text">A+</button><button type="button" data-size="xl" title="Extra large text">A++</button>
<button type="button" class="scope" data-view="scope" title="Large high-contrast view for use beside the microscope">🔬 Microscope mode</button></div></header>
<div class="wrap">
<nav class="side"><ul>{nav}</ul>
<form class="search" action="{prefix}taxa/index.html"><input name="q" placeholder="Find a species…" aria-label="Find a species"></form>
</nav>
<main>{body}</main></div>
<footer>Built {date.today().isoformat()} from <code>data/*.csv</code>. Key texts are transcribed from the cited
publications; check the original before formal identification. Figures © their authors (CC BY 4.0 where stated).</footer>
<script src="{prefix}assets/site.js"></script>
</body></html>"""


def write(rel, content):
    p = SITE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def cite(sid, prefix=""):
    s = sources.get(sid)
    return f'<a href="{prefix}sources.html#{sid}">{esc(s["short"] if s else sid)}</a>'


# --------------------------------------------------------------------------- key pages
def lead_html(l, prefix, kid, idp=""):
    """One lead. idp prefixes the anchors so several keys can share one page (keys.html)."""
    res = (f'<a class="goto" href="#{idp}c{esc(l["goto"])}" data-goto="{esc(l["goto"])}">→ {esc(l["goto"])}</a>' if l["goto"]
           else " ; ".join(taxon_link(n.strip(), prefix) for n in l["taxon"].split(";") if n.strip()))
    group = f'<span class="group">{italic_names(l["group"])}</span>' if l["group"] else ""
    warn = ""
    notes = []
    if l["note"]:
        is_problem = any(w in l["note"].upper() for w in ("CORRECTION", "AS PRINTED", "OVERLAP", "NOT SEPARATED", "PRINTED AS"))
        notes.append(("note" + (" problem" if is_problem else ""), "Note", l["note"]))
    if l["update_note"]:
        notes.append(("update", "Update from later literature", l["update_note"]))
    pref = f' <span class="pref">{esc(l["page_ref"])}</span>' if l.get("page_ref") else ""
    if notes:
        warn = '<span class="warn" title="This lead has a note">⚠</span>'
    det = "".join(f'<div class="{c}"><b>{t}:</b> {italic_names(n)}</div>' for c, t, n in notes)
    return (f'<div class="lead" id="{idp}l{esc(l["lead_id"])}"><div class="lt"><span class="lid">{esc(l["couplet"])}{"" if l["lead"] == "a" else "′"}</span>'
            f'{"" if l["lead"] == "a" else "<span class=dash>–</span>"} {italic_names(l["text"])} {warn}{fig_links(l, prefix)}{pref}</div>'
            f'<div class="res">{group}{res}</div>{det}</div>')


def build_keys():
    rows = []
    embedded = []
    for k in keys_index:
        kid = k["key_id"]
        ls = by_key[kid]
        couplets = []
        seen = []
        for l in ls:
            if l["couplet"] not in seen:
                seen.append(l["couplet"])
        for c in seen:
            pair = [l for l in ls if l["couplet"] == c]
            couplets.append(f'<section class="couplet" id="c{esc(c)}" data-c="{esc(c)}">'
                            + "".join(lead_html(l, "../", kid) for l in sorted(pair, key=lambda x: x["lead"])) + "</section>")
        n_taxa = len({n.strip() for l in ls for n in l["taxon"].split(";") if n.strip()})
        n_notes = sum(1 for l in ls if l["note"] or l["update_note"])
        s = sources[k["source_id"]]
        body = f"""<p class="crumb"><a href="../keys.html">Keys</a> › {esc(k['title'])}</p>
<h1>{esc(k['title'])}</h1>
<p>{italic_names(k['description'])}</p>
<table class="meta"><tr><th>Source</th><td>{esc(s['citation'])} {f'<a href="{esc(s["doi_or_url"])}">{esc(s["doi_or_url"])}</a>' if s['doi_or_url'] else ''}</td></tr>
<tr><th>Region</th><td>{esc(k['region'])}</td></tr><tr><th>Sexes</th><td>{esc(k['sexes'])}</td></tr>
<tr><th>Size</th><td>{len(seen)} couplets, {n_taxa} terminal taxa, {n_notes} leads with notes (⚠)</td></tr></table>
<div class="modes"><button data-mode="step" class="on">Step through</button><button data-mode="full">Full key (printable)</button></div>
<div id="stepper" data-start="{esc(k['start'])}"><div class="trail"></div><div class="current"></div>
<p class="stepnav"><button class="back">◀ Back</button> <button class="restart">Restart</button></p></div>
<div id="fullkey" class="key">{''.join(couplets)}</div>"""
        write(f"keys/{kid}.html", page(k["title"], body, "../", "keys.html"))
        rows.append(f'<tr><td><a href="#key-{kid}" data-show="{kid}">{esc(k["title"])}</a></td><td>{cite(k["source_id"])}</td>'
                    f'<td>{esc(k["region"])}</td><td>{esc(k["sexes"])}</td><td class="num">{len(seen)}</td><td class="num">{n_taxa}</td>'
                    f'<td><a href="keys/{kid}.html">step through ›</a></td></tr>')
        # the same key, embedded on keys.html (anchors prefixed with the key id)
        emb = "".join(
            f'<section class="couplet" id="{kid}-c{esc(c)}" data-c="{esc(c)}">'
            + "".join(lead_html(l, "", kid, f"{kid}-") for l in sorted([x for x in ls if x["couplet"] == c], key=lambda x: x["lead"]))
            + "</section>" for c in seen)
        embedded.append(f'<div class="dkey" id="key-{kid}" data-key="{kid}"><h2>{esc(k["title"])}</h2>'
                        f'<p class="muted">{esc(s["short"])} · {esc(k["region"])} · {len(seen)} couplets · start at couplet '
                        f'<a href="#{kid}-c{esc(k["start"])}">{esc(k["start"])}</a> · '
                        f'<a href="keys/{kid}.html">step-through version ›</a></p><div class="key">{emb}</div></div>')
    options = "".join(f'<option value="{k["key_id"]}">{esc(k["title"])} ({esc(sources[k["source_id"]]["short"])})</option>' for k in keys_index)
    body = f"""<h1>Identification keys</h1>
<p>Each key is transcribed word for word from its source. Choose a key below and follow the couplets: click
<b>→ number</b> to jump to the next couplet. Every result links to its <b>species page</b>; the <span class="tolist">☰</span>
next to it shows the species in the <a href="taxa/index.html">species list</a>. Leads marked <span class="warn">⚠</span>
carry a note (printing error, ambiguous character, or an <b>update</b> from later literature): read it before accepting a result.</p>
{CFG.get("keys_advice_html", "")}
<details class="keytable"><summary>All keys ({len(keys_index)}): sources, regions and sizes</summary>
<table class="list"><tr><th>Key</th><th>Source</th><th>Region</th><th>Sexes</th><th>Couplets</th><th>Taxa</th><th></th></tr>{''.join(rows)}</table></details>
<div class="keybar"><label for="keyselect">Key:</label> <select id="keyselect">{options}</select>
<button type="button" id="keytop">↑ Couplet 1</button></div>
<div id="dkeys">{''.join(embedded)}</div>"""
    write("keys.html", page("Identification keys", body, "", "keys.html"))


# --------------------------------------------------------------------------- taxa
def conflicts_for(t):
    names = {t["taxon"], *[x.strip() for x in t["key_names"].split(";") if x.strip()]}
    ep = t["taxon"].split(" ", 1)[1] if " " in t["taxon"] else t["taxon"]
    out = []
    for c in conflicts:
        cn = [x.strip() for x in c["taxon"].split(";")]
        if any(n in cn for n in names) or any(x.split(" ", 1)[-1] == ep for x in cn):
            out.append(c)
    return out


def build_taxa():
    groups = defaultdict(list)
    for t in taxa:
        groups[(t["genus"], t["subgenus"])].append(t)
    for t in taxa:
        tid = slug(t["taxon"])
        key_paths = []
        names = [t["taxon"], *[x.strip() for x in t["key_names"].split(";") if x.strip()]]
        for n in names:
            for kid, trail in paths.get(n, []):
                k = next(x for x in keys_index if x["key_id"] == kid)
                steps = "".join(f'<li><a href="../keys/{kid}.html#l{esc(l["lead_id"])}">{esc(l["lead_id"])}</a> '
                                f'{italic_names(l["text"])}{" <span class=warn>⚠</span>" if (l["note"] or l["update_note"]) else ""}</li>'
                                for l in trail)
                key_paths.append(f'<details><summary>{esc(k["title"])} ({cite(k["source_id"], "../")}) – couplet '
                                 f'{esc(trail[-1]["lead_id"])}</summary><ol class="path">{steps}</ol></details>')
        figs = [figures[f] for f in t["figure_ids"].split(";") if f in figures]
        fig_html = "".join(f'<figure><a href="../{esc(f["file"])}"><img loading="lazy" src="../{esc(f["file"])}" alt=""></a>'
                           f'<figcaption>{italic_names(f["caption"])} <span class="muted">({esc(f["licence"])})</span></figcaption></figure>'
                           for f in figs)
        cf = conflicts_for(t)
        cf_html = ""
        if cf:
            cf_html = '<div class="conflict-box"><h2>⚠ Conflicting characters</h2><table class="list"><tr><th>Character</th><th>Source A</th><th>Source B</th><th>Type</th><th>Comment</th></tr>' + "".join(
                f'<tr><td>{italic_names(c["character"])}</td><td>{cite(c["source_a"], "../")}: {italic_names(c["value_a"])}</td>'
                f'<td>{cite(c["source_b"], "../")}: {italic_names(c["value_b"])}</td><td>{esc(c["type"])}</td><td>{italic_names(c["comment"])}</td></tr>'
                for c in cf) + "</table></div>"
        rowsx = [("Classification", f'Genus <i>{esc(t["genus"])}</i>' + (f', subgenus <i>{esc(t["subgenus"])}</i>' if t["subgenus"] and t["subgenus"] != "ungrouped" else (", ungrouped" if t["subgenus"] == "ungrouped" else ""))),
                 ("Status", italic_names(t["status"])), ("Other names in keys", italic_names(t["key_names"])),
                 ("Distribution", italic_names(t["distribution"])), (FOCUS, italic_names(t["focus_record"])),
                 (CFG.get("importance_label", "Importance"), italic_names(t["medical_note"])), ("Diagnostic notes", italic_names(t["diagnostic_note"])),
                 ("Sources", ", ".join(cite(s, "../") for s in t["sources"].split(";") if s))]
        table = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rowsx if v)
        no_key = "" if key_paths else '<p class="note problem">This taxon is not reached by any key in this collection (described or recognised later). Use the diagnostic notes and the original description.</p>'
        body = f"""<p class="crumb"><a href="index.html">Species</a> › <i>{esc(t['genus'])}</i>{(' › <i>' + esc(t['subgenus']) + '</i>') if t['subgenus'] else ''}</p>
<h1><i>{esc(t['taxon'])}</i> <span class="author">{esc(t['author'])}</span></h1>
<table class="meta">{table}</table>
{cf_html}
<h2>How it keys out</h2>{no_key}<p class="muted">The chain of characters leading to this taxon in each key (a ready-made diagnosis).</p>{''.join(key_paths)}
{('<h2>Figures</h2><div class="gallery">' + fig_html + '</div>') if fig_html else ''}"""
        write(f"taxa/{tid}.html", page(t["taxon"], body, "../", "taxa/index.html"))

    order = CFG.get("genera", [])
    blocks = []
    for (g, sg), ts in sorted(groups.items(), key=lambda x: (order.index(x[0][0]) if x[0][0] in order else 9, x[0][1] == "ungrouped", x[0][1])):
        def keyed_at(t):
            names = [t["taxon"], *[x.strip() for x in t["key_names"].split(";") if x.strip()]]
            links = []
            for n in names:
                for kid, trail in paths.get(n, []):
                    short = sources[next(k for k in keys_index if k["key_id"] == kid)["source_id"]]["short"]
                    lab = f'{short.replace(" & Gunathilaka", "").replace(" et al.", "")} {trail[-1]["lead_id"]}'
                    sx = next(k for k in keys_index if k["key_id"] == kid)["sexes"]
                    lab += {"female": " ♀", "male": " ♂"}.get(sx, "")
                    links.append(f'<a href="../keys.html#{kid}-l{esc(trail[-1]["lead_id"])}" title="{esc(kid)}">{esc(lab)}</a>')
            if not links:
                return ' <span class=new title="Not in any key here">not keyed</span>'
            return '<span class="keyedat">keyed at: ' + ", ".join(links) + "</span>"
        items = "".join(f'<li id="{slug(t["taxon"])}" data-name="{esc(t["taxon"].lower())} {esc(t["key_names"].lower())}"><a href="{slug(t["taxon"])}.html"><i>{esc(t["taxon"])}</i></a> '
                        f'<span class="author">{esc(t["author"])}</span>{f" <span class=th title=\"Recorded from {esc(FOCUS)}\">{esc(BADGE)}</span>" if t["focus_record"] else ""}'
                        f'{keyed_at(t)}</li>'
                        for t in sorted(ts, key=lambda x: x["taxon"]))
        head = f"<i>{esc(g)}</i>" + (f" (<i>{esc(sg)}</i>)" if sg and sg != "ungrouped" else (" – ungrouped" if sg == "ungrouped" else ""))
        blocks.append(f"<h3>{head}</h3><ul class='taxlist'>{items}</ul>")
    body = f"""<h1>Species list</h1>
<p>{len(taxa)} taxa: every taxon reached by a key, plus species described later.
{f'<span class="th">{esc(BADGE)}</span> = recorded from {esc(FOCUS)} in the sources used here;' if FOCUS else ''}
<span class="new">not keyed</span> = not reached by any key in this collection.</p>
<p><input id="taxfilter" placeholder="Filter by name…" aria-label="Filter species"> <label{'' if FOCUS else ' class="hidden"'}><input type="checkbox" id="thonly"> {esc(FOCUS)} only</label></p>
{''.join(blocks)}"""
    write("taxa/index.html", page("Species list", body, "../", "taxa/index.html"))

    if not FOCUS:
        return
    th = [t for t in taxa if t["focus_record"]]
    rows = "".join(f'<tr><td><a href="taxa/{slug(t["taxon"])}.html"><i>{esc(t["taxon"])}</i></a></td><td>{italic_names(t["focus_record"])}</td>'
                   f'<td>{italic_names(t["medical_note"])}</td></tr>' for t in sorted(th, key=lambda x: x["taxon"]))
    body = f"""<h1>Species recorded from {esc(FOCUS)}</h1>
<p>Only records stated in the sources of this project are listed ({len(th)} taxa). This is <b>not</b> a complete national
checklist. Add further records to the <code>focus_record</code> column of <code>data/taxa.csv</code>.</p>
<table class="list"><tr><th>Taxon</th><th>Record (source)</th><th>{esc(CFG.get("importance_label", "Importance"))}</th></tr>{rows}</table>"""
    write(FOCUS_PAGE, page(f"{FOCUS} records", body, "", FOCUS_PAGE))


# --------------------------------------------------------------------------- other pages
def build_misc():
    rows = []
    for g in glossary:
        figs = [figures[f] for f in g["figure_ids"].split(";") if f in figures]
        th = "".join(f'<a class="thumb" href="{esc(f["file"])}" title="{esc(f["caption"][:200])}"><img loading="lazy" src="{esc(f["file"])}" alt=""></a>' for f in figs)
        rows.append(f'<tr id="{slug(g["term"])}"><td><b>{esc(g["term"])}</b></td><td>{esc(g["preferred_term"])}</td>'
                    f'<td>{esc(g["synonyms"])}</td><td>{esc(g["sex"])}</td><td>{italic_names(g["definition"])}</td><td class="thumbs">{th}</td></tr>')
    body = f"""<h1>Glossary of characters</h1>
{CFG.get("glossary_intro_html", "<p>Terms used in the keys, with preferred terms and synonyms. Thumbnails open the illustrating figure.</p>")}
<table class="list gloss"><tr><th>Term in keys</th><th>Preferred term</th><th>Synonyms</th><th>Sex</th><th>Meaning</th><th>Figures</th></tr>{''.join(rows)}</table>"""
    write("glossary.html", page("Glossary", body, "", "glossary.html"))

    bysrc = defaultdict(list)
    for f in figures.values():
        bysrc[f["source_id"]].append(f)
    srcname = {}
    if (DATA / "figure_sources.csv").exists():
        srcname = {r["figure_prefix"]: r["source_id"] for r in read("figure_sources.csv")}
    blocks = []
    for sid, fs in bysrc.items():
        items = "".join(f'<figure id="{esc(f["figure_id"])}"><a href="{esc(f["file"])}"><img loading="lazy" src="{esc(f["file"])}" alt=""></a>'
                        f'<figcaption><b>{esc(f["figure"])}</b> {italic_names(f["caption"])}</figcaption></figure>'
                        for f in sorted(fs, key=lambda x: int(x["figure"].split()[1])))
        blocks.append(f'<h2>{cite(srcname.get(sid, sid))} <span class="muted">({esc(fs[0]["licence"].split(" - ")[0])})</span></h2><div class="gallery">{items}</div>')
    body = f"""<h1>Figures</h1><p>Figures reproduced from open-access (CC BY) publications, with attribution. Figures in
copyrighted sources are cited by number in the keys but not reproduced.</p>{''.join(blocks)}"""
    write("figures.html", page("Figures", body, "", "figures.html"))

    rows = "".join(f'<tr id="{esc(c["conflict_id"])}"><td>{esc(c["conflict_id"])}</td><td>{italic_names(c["taxon"])}</td><td>{italic_names(c["character"])}</td>'
                   f'<td>{cite(c["source_a"])}: {italic_names(c["value_a"])}</td><td>{cite(c["source_b"])}: {italic_names(c["value_b"])}</td>'
                   f'<td>{esc(c["type"])}</td><td>{italic_names(c["comment"])}</td><td>{esc(c["status"])}</td></tr>' for c in conflicts)
    upd = [l for l in leads if l["update_note"]]
    urows = "".join(f'<tr><td><a href="keys/{l["key_id"]}.html#l{esc(l["lead_id"])}">{esc(l["key_id"])} {esc(l["lead_id"])}</a></td>'
                    f'<td>{italic_names(l["update_note"])}</td></tr>' for l in upd)
    body = f"""<h1>Conflicts and updates</h1>
<p>Nothing is changed silently. Where sources disagree, or a printed key contains an error or an outdated name, the
disagreement is listed here with both citations. The keys themselves stay as printed.</p>
<h2>Conflicts between sources ({len(conflicts)})</h2>
<table class="list small"><tr><th>ID</th><th>Taxon</th><th>Character</th><th>Source A</th><th>Source B</th><th>Type</th><th>Comment</th><th>Status</th></tr>{rows}</table>
<h2>Update notes attached to key leads ({len(upd)})</h2>
<table class="list small"><tr><th>Lead</th><th>Update</th></tr>{urows}</table>"""
    write("conflicts.html", page("Conflicts & updates", body, "", "conflicts.html"))

    rows = "".join(f'<tr id="{esc(s["source_id"])}"><td><b>{esc(s["short"])}</b></td><td>{esc(s["citation"])}'
                   f'{(" <a href=" + chr(34) + esc(s["doi_or_url"]) + chr(34) + ">" + esc(s["doi_or_url"]) + "</a>") if s["doi_or_url"] else ""}</td>'
                   f'<td>{esc(s["license"])}</td><td>{esc(s["use_in_project"])}</td></tr>' for s in sources.values())
    body = f"""<h1>Sources</h1><table class="list small"><tr><th>Short</th><th>Reference</th><th>Licence</th><th>Use in this project</th></tr>{rows}</table>"""
    write("sources.html", page("Sources", body, "", "sources.html"))

    body = (ROOT / "scripts" / "assets" / "about.html").read_text(encoding="utf-8")
    write("about.html", page("About", body, "", "about.html"))

    n_th = sum(1 for t in taxa if t["focus_record"])
    img = (f'<img src="{esc(CFG["home_image"])}" alt="{esc(CFG.get("home_image_alt", ""))}">' if CFG.get("home_image") else "")
    focus_tile = (f'<a href="{FOCUS_PAGE}"><b>{n_th}</b> recorded from {esc(FOCUS)}<br><span>in the sources used</span></a>' if FOCUS else "")
    start = CFG.get("start_key") or (keys_index[0]["key_id"] if keys_index else "")
    start_link = f' (start with <a href="keys/{esc(start)}.html">the main key</a>)' if start else ""
    quick = CFG.get("quick_start_html") or (
        f'<li>Open <a href="keys.html">the keys</a>{start_link} '
        'and use <b>Step through</b>.</li><li>Read any <span class="warn">⚠</span> note on the leads you passed.</li>'
        '<li>Open the species page and compare diagnostic notes, conflicts and figures.</li>')
    body = f"""<h1>{esc(SITE_TITLE)}</h1>
<div class="intro">{img}<div>{CFG.get("home_intro_html", "")}</div></div>
<div class="tiles">
<a href="keys.html"><b>{len(keys_index)}</b> identification keys<br><span>{len(leads)} leads, {len({l['key_id'] + l['couplet'] for l in leads})} couplets</span></a>
<a href="taxa/index.html"><b>{len(taxa)}</b> taxa<br><span>with key paths and notes</span></a>
{focus_tile}
<a href="conflicts.html"><b>{len(conflicts)}</b> documented conflicts<br><span>plus {sum(1 for l in leads if l['update_note'])} update notes</span></a>
</div>
<h2>Quick start</h2>
<ol>{quick}</ol>
<h2>Keys</h2><ul>{''.join(f'<li><a href="keys/{k["key_id"]}.html">{esc(k["title"])}</a> <span class="muted">({esc(sources[k["source_id"]]["short"])})</span></li>' for k in keys_index)}</ul>"""
    write("index.html", page("Home", body, "", "index.html"))


def main():
    if (SITE / "assets").exists():
        shutil.rmtree(SITE / "assets")
    for d in ("keys", "taxa"):
        if (SITE / d).exists():
            shutil.rmtree(SITE / d)
    shutil.copytree(ASSETS, SITE / "assets", ignore=shutil.ignore_patterns("about.html"))
    build_keys()
    build_taxa()
    build_misc()
    n = len(list(SITE.rglob("*.html")))
    print(f"site/: {n} HTML pages written. Open site/index.html")


if __name__ == "__main__":
    main()
