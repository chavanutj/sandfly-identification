# Sand fly identification: Oriental Phlebotominae

Dichotomous keys, species pages and a static website for identifying phlebotomine sand flies
(Diptera: Psychodidae: Phlebotominae) of the Oriental Region, with updates for Thailand and
neighbouring countries.

## What is here

| Path | Content |
|---|---|
| `data/transcriptions/*.txt` | Keys transcribed word for word from the sources (edit keys here) |
| `data/transcriptions/_update_notes.txt` | Notes from later literature linked to individual leads |
| `data/keys.csv` | **All keys in one table**: one row per lead (generated) |
| `data/keys_index.csv` | Key titles, sources, start couplets |
| `data/taxa.csv` | 161 taxa: author, classification, status, Thai records, medical and diagnostic notes |
| `data/conflicts.csv` | Disagreements between sources, each with both citations |
| `data/glossary.csv` | Terms used in the keys and the preferred terms (Galati et al. 2017) |
| `data/sources.csv`, `data/figures.csv` | References/licences; figures extracted from CC BY papers |
| `scripts/` | `extract_figures.py`, `build_data.py`, `build_site.py` |
| `site/` | The generated website (open `site/index.html`) |

### Keys included (644 leads, 322 couplets)

| key_id | Source | Scope |
|---|---|---|
| `lewis1978` | Lewis 1978 | All Oriental species and subspecies (199 couplets) |
| `quate1962` | Quate 1962 | Indo-China, including Thailand |
| `srilanka_female`, `srilanka_male` | Wijerathna & Gunathilaka 2020 | Sri Lanka, photo-illustrated |
| `lewis1982_subgenera`, `_idiophlebotomus`, `_euphlebotomus`, `_anaphlebotomus` | Lewis 1982 | Phlebotomus subgenera and Oriental groups |
| `lewis1987_grassomyia`, `lewis1987_babu` | Lewis 1987 | Grassomyia females; S. babu series females |
| `italy` | Dantas-Torres et al. 2014 | Mediterranean comparison |

### `keys.csv` columns

`key_id, couplet, lead (a/b), lead_id, text, goto, taxon, group, figures, note, page_ref, update_note, source_file`.
A lead ends in either `goto` (next couplet) or `taxon` (result).

## Updating when new articles are published

This project is built with the **key-builder** toolkit (installed in `~/.claude/skills/key-builder`,
agents `key-literature-scout` and `key-transcriber` in `~/.claude/agents`). Group-specific settings
(title, genera, regions, focus country, search terms, home-page text) are in `project.json`.

| You want to... | Do this (start Claude Code in this folder) |
|---|---|
| check for new literature | `/key-builder search` - new hits are added to `data/literature_log.csv` (status `pdf-needed`) |
| add papers | save PDFs into `inbox/`, then `/key-builder add` |
| both | `/key-builder update` |
| fix a typo / add a record by hand | edit the CSV or transcription, then double-click `update.bat` |
| publish | commit and push; GitHub Actions rebuilds and deploys the site |

One-time GitHub setup: Settings → Pages → Build and deployment → Source: **GitHub Actions**.

## Rebuild

```
pip install pymupdf                 # only for figure extraction
python scripts/extract_figures.py   # figures from the CC BY PDFs (PDFs must be in the repo root)
python scripts/build_data.py        # transcriptions -> data/keys.csv, with structural checks
python scripts/build_site.py        # data -> site/
```

To preview locally: `python -m http.server -d site 8000`, then open http://localhost:8000.

## Publishing

`site/` is a self-contained static site (GitHub Pages, university web space). Figures come only from
CC BY 4.0 papers and are credited. The figures in Lewis (1978, 1982, 1987) are cited by number but not
reproduced. The source PDFs are git-ignored because most are copyrighted.

## Caveats

* The transcriptions were made from page images and checked couplet by couplet. Verify against the
  original before formal identification or publication.
* Printing errors are corrected only when certain (Lewis 1978 couplet 1b: printed 43, should be 48),
  with the original wording kept in the note and in `conflicts.csv`.
* The Thailand list contains only records stated in these sources. It is not a national checklist.
* Several species recorded in Thailand (e.g. *P. shadenae*, *P. barguesae*, *P. mascomai*, *S. raynali*,
  *S. maiae*, *S. siamensis*, *S. hivernus*, *Chinius barbazani*) are reached by **no** printed key here.
  They are linked from the leads where the older key would end, with the separating characters.
