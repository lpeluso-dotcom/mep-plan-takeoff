# MEP plan takeoff

Python scripts and a Claude skill for taking quantities off plumbing, mechanical and electrical plan
PDFs: index the sheets, read the schedules, count fixture and equipment tags, and measure pipe and duct
runs.

The approach is to read what the PDF already stores before reading pixels. A vector PDF holds its text
with exact positions, so a script can count tags. A model or a person then checks the result on
marked-up tiles and handles what the text cannot give: scanned sheets, text drawn as outlines, and
judgment about which views show the same room.

This is a takeoff tool. It does not price anything.

## What is here

| File | What it does |
|---|---|
| `scripts/plan_index.py` | One row per page: sheet number, discipline, amount of text, scale notes, hints such as schedule or riser. `--text <page>` prints a page set out in columns, for reading schedules. |
| `scripts/render_sheet.py` | Renders a page to PNG tiles of at most 1,900 px, each named with its pixel origin. `--crop` takes one region. `--mark tags.json` boxes the tags the counter found. |
| `scripts/tag_count.py` | Counts tags such as `WC-1` or `EF-2` from the PDF's text and sorts each into on the plan, in a schedule, or in a note. |
| `scripts/measure.py` | Turns traced points into feet, checks the scale note against a known dimension, and refuses to total a run that has no calibration. |
| `SKILL.md` | The method, written as a Claude skill. |
| `references/takeoff-method.md` | How to measure lengths from a plan image. |

## Install

Python 3 (tested on 3.11 and 3.12) and one PDF backend:

- poppler's command-line tools (`pdfinfo`, `pdftotext`, `pdftoppm`), or
- `pip install pypdfium2 pillow`

With poppler, only `--mark` needs Pillow (`pip install pillow`).

To use it as a Claude skill, put this folder where your Claude client reads skills, for example
`~/.claude/skills/mep-plan-takeoff` for Claude Code.

## Use

```bash
python3 scripts/plan_index.py plans.pdf --out index.json          # which sheet is which
python3 scripts/plan_index.py plans.pdf --text 9                  # read a schedule page
python3 scripts/tag_count.py plans.pdf --pages 7,9-11 --tags WC-1,LAV-1,FD-1 --out tags.json
python3 scripts/render_sheet.py plans.pdf 7 tiles/ --dpi 200 --mark tags.json
python3 scripts/measure.py runs.json                              # see references/takeoff-method.md
```

On the marked tiles a red box is a tag that was counted, a blue box is a tag that was seen in a
schedule, a list or a note and left out, and a tag with no box is one the script never saw.

## How well the tag counter works

It was checked on 23 plan sheets from real bid sets. Those sheets are not in this repository.

- On 8 sheets with checked labels it found 115 of 135 plan tags, and every tag it reported was right.
  Fifteen of the 20 misses were on one sheet whose text is drawn as strokes, so the PDF holds no text
  for it. The labels were machine-assisted and have not been checked by an estimator.
- On 15 more sheets it agreed with an automatic key on about 98% of tags.

## Limits

- It counts tags, not fixtures. A fixture tagged on two views of the same floor is counted twice.
- It sees only text the PDF stores. Scanned sheets and text drawn as outlines must be counted by eye.
- A plan tag beside a same-size word, such as a room name, can be taken for a schedule row. It shows
  as a blue box on the plan.
- One-letter prefixes (`L-1`, `P-2`) also match panel circuit numbers on electrical sheets. Pass
  `--tags` with the tags from the schedule.
- Lengths are traced from an image. Treat them as medium confidence at best.

## Tests

```bash
pip install pytest reportlab pillow
python3 -m pytest scripts -q
```

The tests draw their own PDFs. Tests for a backend that is not installed are skipped.

## Plan sets

Plan sets usually belong to the architect, engineer or owner. Do not commit them here; `.gitignore`
leaves out every PDF.

## License

MIT, see `LICENSE`. The scripts call other software and include none of it: pypdfium2
(Apache-2.0 or BSD-3-Clause), Pillow (MIT-CMU), and poppler (GPL), which runs as a separate program.
