---
name: mep-plan-takeoff
description: Use when taking quantities off plumbing, mechanical or electrical plan PDFs - counting fixture, equipment or device tags, reading schedules, measuring pipe, duct or conduit runs, or indexing a plan set to find the sheets for a trade. Also use when a takeoff count looks wrong, a sheet is scanned or has little text, or a length was measured with no scale check.
---

# MEP plan takeoff

Quantities from a plan PDF: counts by tag and lengths by system and size. The scripts do the reading
and the arithmetic wherever the PDF stores the answer. You do what a script cannot: choose the sheets,
read the notes, check the script's work on marked tiles, and say how far each number can be trusted.

Read what the PDF stores before you read pixels. A vector PDF holds its text with exact positions, so
a script counts tags better than eyes do. Eyes are for scanned sheets, text drawn as outlines, and
judgment about which views show the same room.

Run the scripts with `python3 scripts/<name>.py` from this folder. They need poppler (`pdfinfo`,
`pdftotext`, `pdftoppm`) or the `pypdfium2` library, and Pillow for `--mark`.

## 1. Index the set

```bash
python3 scripts/plan_index.py plans.pdf --out index.json
```

One row per page: sheet number, discipline, how much text the page holds, scale notes and hints
(schedule, riser, floor plan, demolition). A zip or a folder of PDFs works too. Pages marked `LOWTEXT`
hold little text: the drawing may be outlines or a scan, and the guessed sheet number may be wrong.
Render those small and read the title blocks yourself:

```bash
python3 scripts/render_sheet.py plans.pdf 12 tiles/ --dpi 50
```

Write down which sheets you will use for each trade and which you are skipping. Read the general notes
and specification sheets for the trade before counting anything.

## 2. Read the schedules

```bash
python3 scripts/plan_index.py plans.pdf --text 9
```

This prints one page's text set out in columns, so a fixture or equipment schedule reads row by row.
For a `LOWTEXT` page, read a cropped render instead (`--crop x,y,w,h` as fractions of the sheet; about
130 dpi reads a schedule). The schedule says what each tag is. The plan says how many.

## 3. Count the tags

Count with the script first, then check its work on marked tiles:

```bash
python3 scripts/tag_count.py plans.pdf --pages 7,9-11 --tags WC-1,LAV-1,FD-1 --out tags.json
python3 scripts/render_sheet.py plans.pdf 7 tiles/ --dpi 200 --mark tags.json
```

`--pages` is the plan sheets only (no schedule, detail or riser sheets) and `--tags` is the tags the
schedules name. The script reads the PDF's own text and counts tags, not fixtures. It is exact for the
tags in the text. It misses a tag drawn as outlines or on a scanned sheet, and it counts a fixture
twice when two views tag it. The marked tiles show what it did. A red box is a tag it counted. A blue
box is a tag it saw in a schedule, a list or a note and left out. A tag with no box is one it never
saw. Read every tile of every counted sheet and correct the count:

- Add each plan tag with no box, and each blue box that stands on the plan. A tag beside a room name
  or another label is the usual one. Tiles overlap, so a tag can show in two of them: count one you
  add only in the tile whose core holds it (`render_sheet.py` prints each tile's core).
- Take off each red box that is not one more installed item: in a schedule or legend, in a detail or
  riser, in an enlarged view of a room already counted, or on a second plan of the same floor. A waste
  plan and a water plan each tag the same fixture; count it once.

A page the script reports as "not counted" has no tag in its text. That is not a zero: count that
page by eye from 200 dpi tiles. The script also lists marks with a common fixture or equipment prefix
that were not asked for. A real tag among them is missing from the schedule: raise it as a question.
Panel circuit numbers (`L-15`) and sheet references are not tags. The script does not know every
prefix, so also note any tag you see on the tiles that the schedule does not name.

A tag on the plan that is not in the schedule, or the reverse, is an open question. Do not settle it
by guessing.

## 4. Measure the lengths

Read `references/takeoff-method.md` before measuring. In short: render tiles, calibrate the scale
against a known dimension, trace each run as points, and let `scripts/measure.py` do the arithmetic.
A run with no calibration behind it is not measured: the script gives the length the scale note
suggests and adds nothing to a total.

If someone hands you measured quantities, use theirs and mark them `provided`.

## 5. Report

Give every quantity its source and a confidence label, and list what is unsettled.

| Label | Use when |
|---|---|
| `high` | Counted from a schedule and reconciled with the plan, or a quantity someone measured and gave you |
| `medium` | Traced with a calibrated scale on a clean sheet; counted on plan with no schedule to confirm |
| `low` | Scanned or crowded sheet, routing not shown (you assumed a path), or an allowance |

Say which sheets were counted from the text and which by eye, which sheets you skipped, and every open
question.

## Common mistakes

| Mistake | What to do |
|---|---|
| Reading "not counted" as zero | The page has no tags in its text. Count it by eye. |
| Counting both plans of one floor | Count each fixture once. |
| Counting tags in a schedule, legend, detail or riser | Leave those sheets out of `--pages` and take off red boxes in tables. |
| Measuring from the scale note alone | Calibrate against a known dimension. Half-size sets are common. |
| Reading an image wider or taller than about 1,900 px | It is shrunk when read and traced points no longer match. Let the script pick the tile grid. |
| Taking a length from a riser diagram or isometric | They are not to scale. Use them for sizes and connections only. |
