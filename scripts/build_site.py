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
for _s in sources.values():  # a bare DOI ("10.1186/...") becomes a full link
    _u = (_s.get("doi_or_url") or "").strip()
    if _u.lower().startswith("doi:"):
        _u = _u[4:].strip()
    if _u.startswith("10."):
        _s["doi_or_url"] = "https://doi.org/" + _u
keys_index = sorted(read("keys_index.csv"), key=lambda k: int(k["order"]))
leads = read("keys.csv")
taxa = read("taxa.csv")
glossary = read("glossary.csv")
conflicts = read("conflicts.csv")
figures = {f["figure_id"]: f for f in read("figures.csv")} if (DATA / "figures.csv").exists() else {}

abbrevs = read("abbreviations.csv") if (DATA / "abbreviations.csv").exists() else []
diagrams = read("diagrams.csv") if (DATA / "diagrams.csv").exists() else []
hotspots = read("hotspots.csv") if (DATA / "hotspots.csv").exists() else []
BODY_PARTS = ["Head & antenna", "Mouthparts, cibarium & pharynx", "Thorax & wing", "Abdomen", "Female genitalia", "Male genitalia"]


# --------------------------------------------------------------------------- term popups (glossary + abbreviations)
# Every glossary term and abbreviation gets a popup entry (written to assets/terms.js). Words in key texts, notes and
# species pages that match glossary.csv `match_words` or abbreviations.csv `match_in_keys` are wrapped in
# <span class="gt" data-t="KEY">, and site.js shows the popup when the cursor is on them.
def term_key(entry):
    """'g:Antenna 3' -> 'antenna-3' (glossary card id); 'a:fI' -> 'a-fi' (abbreviation row id)."""
    kind, _, name = entry.partition(":")
    return slug(name) if kind == "g" else "a-" + slug(name)


gl_by_term = {g["term"]: g for g in glossary}


def make_terms():
    """Popup data, keyed like the data-t attributes. Paths are relative to the site root."""
    terms = {}
    for g in glossary:
        terms[slug(g["term"])] = {"t": esc(g["term"]), "f": esc(g["preferred_term"]) if g["preferred_term"] != g["term"] else "",
                                  "s": esc(g["synonyms"]), "x": g["sex"], "d": italic_names(g["definition"]),
                                  "g": f"glossary.html#{slug(g['term'])}"}
    for a in abbrevs:
        link = a["glossary_term"] if a["glossary_term"] in gl_by_term else ""
        terms["a-" + slug(a["id"])] = {"t": esc(a["abbr"]), "f": esc(a["full_name"]) if a["full_name"] != a["abbr"] else "",
                                       "d": italic_names(a["description"]),
                                       "g": f"glossary.html#{slug(link) if link else 'a-' + slug(a['id'])}",
                                       "l": esc(link)}
    return terms


def _is_plain(p):  # patterns written without capitals match case-insensitively; 'fI', 'A3/E', 'R2' must match exactly
    return p == p.lower()


_pats = {}  # escaped pattern -> (key, case-insensitive?)
for g in glossary:
    for p in filter(None, (x.strip() for x in g.get("match_words", "").split(";"))):
        _pats.setdefault(esc(p), (slug(g["term"]), _is_plain(p)))
for a in abbrevs:
    for p in filter(None, (x.strip() for x in a.get("match_in_keys", "").split(";"))):
        _pats.setdefault(esc(p), ("a-" + slug(a["id"]), _is_plain(p)))
_exact = {p: k for p, (k, ci) in _pats.items() if not ci}
_lower = {p.lower(): k for p, (k, ci) in _pats.items() if ci}
TERM_RX = re.compile(r"(?<![\w/+&#-])(" + "|".join(
    (f"(?i:{re.escape(p)})" if ci else re.escape(p)) for p, (k, ci) in sorted(_pats.items(), key=lambda x: -len(x[0]))
) + r")(?![\w/+-])") if _pats else None


def gloss(html_text, skip=None):
    """Wrap glossary terms/abbreviations in already-escaped HTML (first occurrence of each term per call).
    Text inside <a> links and inside tags is left alone."""
    if not TERM_RX or not html_text:
        return html_text
    done = {skip}
    out, in_a = [], 0
    for part in re.split(r"(<[^>]+>)", html_text):
        if part.startswith("<"):
            if re.match(r"<a[\s>]", part):
                in_a += 1
            elif part.startswith("</a"):
                in_a = max(0, in_a - 1)
            out.append(part)
            continue
        if in_a:
            out.append(part)
            continue

        def rep(m):
            k = _exact.get(m.group(1)) or _lower.get(m.group(1).lower())
            if not k or k in done:
                return m.group(0)
            done.add(k)
            return f'<span class="gt" tabindex="0" data-t="{k}">{m.group(1)}</span>'
        out.append(TERM_RX.sub(rep, part))
    return "".join(out)


def rich(text, skip=None):
    """italic names + glossary popups (used on the glossary page only)"""
    return gloss(italic_names(text), skip)


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


def taxon_cell(t, prefix=""):
    """Two-line taxon cell for tables: line 1 = name (link, never broken), line 2 = author, or the citation of an
    unnamed form, e.g. 'Idiophlebotomus sp. (Sunantaraporn et al. 2024)' -> 'Idiophlebotomus sp.' / '(Sunantaraporn et al. 2024)'."""
    name = t["taxon"]
    m = re.match(r"^(.*?\bspp?\.(?:\s*[\w-]+)?)\s+(\(.*\))$", name)
    main, extra = (m.group(1), m.group(2)) if m else (name, t.get("author", ""))
    return (f'<a class="tname" href="{prefix}taxa/{slug(name)}.html"><i>{esc(main)}</i></a>'
            + (f'<span class="tauth">{esc(extra)}</span>' if extra else ""))


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
NAV = [("index.html", "Home"), ("biology.html", "Biology & disease"), ("keys.html", "Identification keys"), ("taxa/index.html", "Species list"),
       *([(FOCUS_PAGE, f"{FOCUS} records")] if FOCUS else []), ("glossary.html", "Glossary"), ("figures.html", "Figures"),
       ("conflicts.html", "Conflicts & updates"), ("sources.html", "Sources"), ("about.html", "About / how to edit")]


def page(title, body, prefix="", active=""):
    nav = "".join(f'<li><a href="{prefix}{h}"{" class=on" if h == active else ""}>{esc(t)}</a></li>' for h, t in NAV)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} | {esc(SHORT)}</title>
<link rel="stylesheet" href="{prefix}assets/style.css">
<link rel="manifest" href="{prefix}manifest.webmanifest"><meta name="theme-color" content="#1f5c4a">
<link rel="icon" href="{prefix}assets/icons/icon-32.png"><link rel="apple-touch-icon" href="{prefix}assets/icons/icon-180.png">
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
<button type="button" class="scope" data-view="scope" title="Large high-contrast view for use beside the microscope">🔬 Microscope mode</button>
<button type="button" id="installbtn" class="install" hidden title="Install this site as an app on this device">⤓ Install app</button>
<span id="offline" class="offline" hidden aria-live="polite"></span></div></header>
<div class="wrap">
<nav class="side"><ul>{nav}</ul>
<form class="search" action="{prefix}taxa/index.html"><input name="q" placeholder="Find a species…" aria-label="Find a species"></form>
</nav>
<main>{body}</main></div>
<footer>Built {date.today().isoformat()} from <code>data/*.csv</code>. Key texts are transcribed from the cited
publications; check the original before formal identification. Figures © their authors (CC BY 4.0 where stated).</footer>
{'<script src="assets/terms.js"></script>' + chr(10) if active == "glossary.html" else ""}<script src="{prefix}assets/site.js"></script>
</body></html>"""


def write(rel, content):
    p = SITE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def cite(sid, prefix=""):
    s = sources.get(sid)
    # non-breaking spaces keep "Lewis 1978" / "et al. 2025" together and stop justified text from stretching them
    label = esc(s["short"] if s else sid).replace(" et al.", "&nbsp;et&nbsp;al.")
    label = re.sub(r" (\d{4}[a-z]?)$", r"&nbsp;\1", label)
    return f'<a href="{prefix}sources.html#{sid}">{label}</a>'


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
    det = "".join(f'<details class="{c}"><summary>{t}</summary><div class="body">{italic_names(n)}</div></details>'
                  for c, t, n in notes)
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
    rows = "".join(f'<tr><td class="tcell">{taxon_cell(t)}</td><td>{italic_names(t["focus_record"])}</td>'
                   f'<td>{italic_names(t["medical_note"])}</td></tr>' for t in sorted(th, key=lambda x: x["taxon"]))
    body = f"""<h1>Species recorded from {esc(FOCUS)}</h1>
<p>Only records stated in the sources of this project are listed ({len(th)} taxa). This is <b>not</b> a complete national
checklist. Add further records to the <code>focus_record</code> column of <code>data/taxa.csv</code>.</p>
<table class="list"><tr><th>Taxon</th><th>Record (source)</th><th>{esc(CFG.get("importance_label", "Importance"))}</th></tr>{rows}</table>"""
    write(FOCUS_PAGE, page(f"{FOCUS} records", body, "", FOCUS_PAGE))


# --------------------------------------------------------------------------- other pages
def term_usage(g):
    """Leads whose text mentions a glossary term (its match_words): {key_id: [lead_id, ...]}"""
    pats = [p.strip() for p in g.get("match_words", "").split(";") if p.strip()]
    if not pats:
        return {}
    rx = re.compile(r"(?<![\w/+-])(" + "|".join(
        f"(?i:{re.escape(p)})" if _is_plain(p) else re.escape(p) for p in sorted(pats, key=len, reverse=True)) + r")(?![\w/+-])")
    use = defaultdict(list)
    for l in leads:
        if rx.search(l["text"]):
            use[l["key_id"]].append(l["lead_id"])
    return use


SEX_LABEL = {"female": ("♀", "Female"), "male": ("♂", "Male"), "both": ("♀♂", "Both sexes")}


def build_glossary():
    absl = {a["id"]: a for a in abbrevs}
    # ---- diagram explorer
    tabs, panels = [], []
    for i, d in enumerate(diagrams):
        x0, y0, x1, y1 = map(int, d["crop"].split())
        W, H = x1 - x0, y1 - y0
        hs, chips, seen = [], [], []
        for h in (h for h in hotspots if h["diagram_id"] == d["diagram_id"]):
            k = term_key(h["entry"])
            kind, _, name = h["entry"].partition(":")
            if kind == "a":
                a = absl.get(name)
                target = slug(a["glossary_term"]) if a and a["glossary_term"] in gl_by_term else k
                label = a["abbr"] if a else name
                gl = slug(a["glossary_term"]) if a and a["glossary_term"] in gl_by_term else ""
            else:
                target, label, gl = k, name, k
            x, y, w, hh = (int(h[c]) for c in "xywh")
            hs.append(f'<a class="hs" href="#{target}" data-t="{k}" data-g="{gl}" aria-label="{esc(label)}" '
                      f'style="left:{(x - x0) / W * 100:.2f}%;top:{(y - y0) / H * 100:.2f}%;width:{w / W * 100:.2f}%;height:{hh / H * 100:.2f}%"></a>')
            if k not in seen:
                seen.append(k)
                chips.append(f'<a class="chip" href="#{target}" data-t="{k}" data-hs="{k}">{esc(label)}</a>')
        f = figures.get(d["figure_id"], {})
        did = d["diagram_id"]
        tabs.append(f'<button type="button" role="tab" data-d="{did}"{" class=on aria-selected=true" if i == 0 else ""}>{esc(d["title"])}</button>')
        panels.append(
            f'<div class="dpanel{" on" if i == 0 else ""}{" wide" if W / H > 1.4 else ""}" id="d-{did}" data-d="{did}" role="tabpanel">'
            f'<div class="dfig" style="aspect-ratio:{W}/{H};max-width:min(100%,calc(80vh*{W}/{H}))"><img src="{esc(d["file"])}" alt="{esc(d["title"])} with labelled parts" loading="lazy">{"".join(hs)}</div>'
            f'<div class="dside"><h3>{esc(d["title"])}</h3><p class="muted">{d["specimen"]}. '
            f'From <a href="figures.html#{esc(d["figure_id"])}">{esc(sources.get("galati2017", {}).get("short", "Galati et al. 2017"))} '
            f'{esc(f.get("figure", ""))}</a> ({esc(f.get("licence", "").split(" - ")[0])}).</p>'
            f'<p class="hint">Point at a label or a part of the drawing to see its name and meaning. Click to open its glossary entry.</p>'
            f'<div class="chips">{"".join(chips)}</div>'
            f'<label class="showall"><input type="checkbox"> Outline all parts</label></div></div>')
    explorer = (f'<section class="explorer" id="explorer" aria-label="Labelled diagrams"><div class="dtabs" role="tablist">{"".join(tabs)}</div>'
                f'{"".join(panels)}</section>') if diagrams else ""

    # which glossary terms have hotspots (directly or through an abbreviation), and on which diagram
    on_diag = defaultdict(set)
    for h in hotspots:
        kind, _, name = h["entry"].partition(":")
        g = name if kind == "g" else (absl.get(name, {}).get("glossary_term", ""))
        if g in gl_by_term:
            on_diag[slug(g)].add(h["diagram_id"])

    # ---- cards
    by_part = defaultdict(list)
    for g in glossary:
        by_part[g.get("body_part") or "Other"].append(g)
    parts = [p for p in BODY_PARTS if p in by_part] + [p for p in by_part if p not in BODY_PARTS]
    secs = []
    for p in parts:
        cards = []
        for g in by_part[p]:
            gid = slug(g["term"])
            sym, sexname = SEX_LABEL.get(g["sex"], ("", g["sex"]))
            figs = [figures[f] for f in g["figure_ids"].split(";") if f in figures]
            th = "".join(f'<a class="thumb" href="{esc(f["file"])}" title="{esc(f["figure"])}: {esc(f["caption"][:300])}">'
                         f'<img loading="lazy" src="{esc(f["file"])}" alt="{esc(f["figure"])}"></a>' for f in figs)
            use = term_usage(g)
            n_use = sum(len(v) for v in use.values())
            used = ""
            if n_use:
                li = "".join(
                    f'<li><b>{esc(sources[next(k for k in keys_index if k["key_id"] == kid)["source_id"]]["short"])}</b> '
                    f'<span class="muted">{esc(next(k for k in keys_index if k["key_id"] == kid)["title"])}</span>: '
                    + ", ".join(f'<a href="keys/{kid}.html#l{esc(lid)}">{esc(lid)}</a>' for lid in lids) + "</li>"
                    for kid, lids in use.items())
                used = f'<details class="used"><summary>Used in {n_use} lead{"s" if n_use > 1 else ""} of {len(use)} key{"s" if len(use) > 1 else ""}</summary><ul>{li}</ul></details>'
            locate = "".join(f'<button type="button" class="locate" data-d="{dd}" data-g="{gid}">Show on diagram</button>'
                             for dd in sorted(on_diag.get(gid, []))[:1])
            text = " ".join([g["term"], g["preferred_term"], g["synonyms"], g["definition"]]).lower()
            cards.append(
                f'<article class="gcard" id="{gid}" data-sex="{esc(g["sex"])}" data-part="{esc(p)}" data-text="{esc(text)}">'
                f'<header><h3>{esc(g["term"])}</h3><span class="sexb sex-{esc(g["sex"])}" title="{esc(sexname)}">{sym}</span></header>'
                + (f'<p class="pref">Preferred term: <b>{esc(g["preferred_term"])}</b></p>' if g["preferred_term"] != g["term"] else "")
                + (f'<p class="syn">Also called: {esc(g["synonyms"])}</p>' if g["synonyms"] else "")
                + f'<p class="def">{rich(g["definition"], skip=gid)}</p>'
                + (f'<div class="gthumbs">{th}</div>' if th else "")
                + f'<div class="gfoot">{locate}{used}</div></article>')
        secs.append(f'<section class="gsec" data-part="{esc(p)}"><h2>{esc(p)} <span class="count">{len(by_part[p])}</span></h2>'
                    f'<div class="gcards">{"".join(cards)}</div></section>')

    filt = (f'<div class="gfilter" role="search"><input id="gsearch" type="search" placeholder="Search terms, synonyms, meanings…" aria-label="Search the glossary">'
            f'<div class="seg" role="group" aria-label="Sex"><button type="button" data-sex="" class="on">All</button>'
            f'<button type="button" data-sex="female">♀ Female</button><button type="button" data-sex="male">♂ Male</button></div>'
            f'<div class="partchips">' + "".join(f'<button type="button" data-part="{esc(p)}">{esc(p)}</button>' for p in parts) + '</div>'
            f'<p class="gcount muted" aria-live="polite"></p></div>')

    # ---- abbreviation table
    ab_rows = []
    for p in BODY_PARTS + sorted({a["body_part"] for a in abbrevs} - set(BODY_PARTS)):
        rows_p = [a for a in abbrevs if a["body_part"] == p]
        if not rows_p:
            continue
        ab_rows.append(f'<tr class="grp"><th colspan="4">{esc(p)}</th></tr>')
        for a in rows_p:
            see = (f'<a href="#{slug(a["glossary_term"])}">{esc(a["glossary_term"])}</a>' if a["glossary_term"] in gl_by_term else "")
            ab_rows.append(f'<tr id="a-{slug(a["id"])}"><td><span class="gt" tabindex="0" data-t="a-{slug(a["id"])}"><b>{esc(a["abbr"])}</b></span></td>'
                           f'<td>{esc(a["full_name"])}</td><td>{italic_names(a["description"])}</td><td>{see}</td></tr>')
    abtable = (f'<h2 id="abbreviations">Abbreviations and labels <span class="count">{len(abbrevs)}</span></h2>'
               f'<p class="muted">Labels used in the diagrams above and abbreviations found in the keys (for example A3/E, R2/R2+3).</p>'
               f'<table class="list small abbr"><tr><th>Label</th><th>Full name</th><th>Meaning</th><th>Glossary</th></tr>{"".join(ab_rows)}</table>') if abbrevs else ""

    body = f"""<h1>Glossary of characters</h1>
{CFG.get("glossary_intro_html", "<p>Terms used in the keys, with preferred terms and synonyms. Thumbnails open the illustrating figure.</p>")}
<p class="tip">Tip: on this page, terms with a <span class="gt-demo">dotted underline</span> show their meaning when you point at them.</p>
{explorer}
{filt}
{"".join(secs)}
{abtable}"""
    write("glossary.html", page("Glossary", body, "", "glossary.html"))
    write("assets/terms.js", "// Generated by build_site.py from data/glossary.csv and data/abbreviations.csv: popup text for terms.\n"
          "window.SF_TERMS = " + json.dumps(make_terms(), ensure_ascii=False, separators=(",", ":")) + ";\n")


def build_misc():
    build_glossary()

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
    if (ROOT / "scripts" / "assets" / "biology.html").exists():  # hand-written page: biology, disease, vector role
        body = (ROOT / "scripts" / "assets" / "biology.html").read_text(encoding="utf-8")
        write("biology.html", page("Biology & disease", body, "", "biology.html"))

    n_th = sum(1 for t in taxa if t["focus_record"])
    start = CFG.get("start_key") or (keys_index[0]["key_id"] if keys_index else "")
    slides = CFG.get("home_slides") or ([{"src": CFG["home_image"], "alt": CFG.get("home_image_alt", ""),
                                          "caption_html": CFG.get("home_image_caption_html", "")}] if CFG.get("home_image") else [])
    img = ""
    if slides:
        sl = "".join(
            f'<div class="slide{" on" if i == 0 else ""}"><img src="{esc(s["src"])}" alt="{esc(s.get("alt", ""))}"'
            f'{"" if i == 0 else " loading=lazy"} style="object-position:{esc(s.get("pos", "50% 50%"))}">'
            f'{"<figcaption>" + s["caption_html"] + "</figcaption>" if s.get("caption_html") else ""}</div>'
            for i, s in enumerate(slides))
        dots = ("" if len(slides) < 2 else '<div class="dots" role="tablist" aria-label="Choose photo">' + "".join(
            f'<button type="button" aria-label="Photo {i + 1} of {len(slides)}"{" class=on" if i == 0 else ""}></button>'
            for i in range(len(slides))) + "</div>")
        img = (f'<figure class="hero-img slideshow" data-seconds="{int(CFG.get("home_slides_seconds", 10))}" '
               f'aria-roledescription="carousel">{sl}{dots}</figure>')
    focus_tile = (f'<a href="{FOCUS_PAGE}"><span class="ico">📍</span><b>{n_th}</b> recorded from {esc(FOCUS)}'
                  f'<span>in the sources used</span></a>' if FOCUS else "")
    start_btn = f'<a class="btn primary" href="keys/{esc(start)}.html">Start identifying →</a>' if start else ""
    quick = CFG.get("quick_start_html") or (
        f'<li>Open <a href="keys.html">the keys</a> and use <b>Step through</b>.</li>'
        '<li>Read any <span class="warn">⚠</span> note on the leads you passed.</li>'
        '<li>Open the species page and compare diagnostic notes, conflicts and figures.</li>')
    # keys grouped by the part of the title before ":" (e.g. "Sri Lanka: females")
    # (only a prefix shared by 2+ keys makes a group; the rest go under "Main keys", listed first)
    main_g = CFG.get("home_main_key_group", "Main keys")
    prefixes = [k["title"].partition(":")[0].strip() for k in keys_index if ":" in k["title"]]
    groups = {main_g: []}
    for k in keys_index:
        g, _, rest = k["title"].partition(":")
        g, label = (g.strip(), rest.strip()) if rest and prefixes.count(g.strip()) > 1 else (main_g, k["title"])
        groups.setdefault(g, []).append(
            f'<a class="keycard" href="keys/{esc(k["key_id"])}.html"><span class="kt">{italic_names(label)}</span>'
            f'<span class="ks">{esc(sources[k["source_id"]]["short"])}</span></a>')
    keyblocks = "".join(f'<h3>{esc(g)} <span class="count">{len(v)}</span></h3><div class="keygrid">{"".join(v)}</div>'
                        for g, v in groups.items())
    body = f"""<section class="hero">
<div class="hero-text"><p class="eyebrow">{esc(CFG.get("home_eyebrow", "Identification resource"))}</p>
<h1>{esc(SITE_TITLE)}</h1>
<div class="lede">{CFG.get("home_intro_html", "")}</div>
<p class="cta">{start_btn}<a class="btn" href="taxa/index.html">Browse species</a><a class="btn" href="glossary.html">Glossary</a></p></div>
{img}</section>
<div class="tiles">
<a href="keys.html"><span class="ico">🔑</span><b>{len(keys_index)}</b> identification keys<span>{len(leads)} leads, {len({l['key_id'] + l['couplet'] for l in leads})} couplets</span></a>
<a href="taxa/index.html"><span class="ico">🦟</span><b>{len(taxa)}</b> taxa<span>with key paths and notes</span></a>
{focus_tile}
<a href="conflicts.html"><span class="ico">⚖️</span><b>{len(conflicts)}</b> documented conflicts<span>plus {sum(1 for l in leads if l['update_note'])} update notes</span></a>
</div>
<h2>Quick start</h2>
<ol class="steps">{quick}</ol>
<h2>Keys</h2>{keyblocks}"""
    write("index.html", page("Home", body, "", "index.html"))


def build_offline():
    """Installable, offline-capable site: manifest.webmanifest + sw.js (service worker) listing every file with a
    content hash, so browsers save the whole site on the first visit and later download only changed files."""
    import hashlib
    manifest = {
        "name": SITE_TITLE, "short_name": SHORT, "description": SITE_SUB,
        "start_url": "./index.html", "scope": "./", "display": "standalone",
        "background_color": "#fbfaf7", "theme_color": "#1f5c4a",
        "icons": [{"src": "assets/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
                  {"src": "assets/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}],
    }
    write("manifest.webmanifest", json.dumps(manifest, ensure_ascii=False, indent=1))
    files = {}
    for p in sorted(SITE.rglob("*")):
        if p.is_file() and p.name != "sw.js" and not p.name.startswith("."):
            files[p.relative_to(SITE).as_posix()] = hashlib.md5(p.read_bytes()).hexdigest()[:10]
    version = hashlib.md5(json.dumps(files, sort_keys=True).encode()).hexdigest()[:10]
    tpl = (ASSETS / "sw.template.js").read_text(encoding="utf-8")
    write("sw.js", tpl.replace("__VERSION__", version).replace("__FILES__", json.dumps(files, separators=(",", ":"))))
    print(f"offline: {len(files)} files, {sum(p.stat().st_size for p in SITE.rglob('*') if p.is_file()) / 1e6:.1f} MB, version {version}")


def main():
    if (SITE / "assets").exists():
        shutil.rmtree(SITE / "assets")
    for d in ("keys", "taxa"):
        if (SITE / d).exists():
            shutil.rmtree(SITE / d)
    shutil.copytree(ASSETS, SITE / "assets", ignore=shutil.ignore_patterns("about.html", "biology.html", "sw.template.js"))
    build_keys()
    build_taxa()
    build_misc()
    build_offline()
    n = len(list(SITE.rglob("*.html")))
    print(f"site/: {n} HTML pages written. Open site/index.html")


if __name__ == "__main__":
    main()
