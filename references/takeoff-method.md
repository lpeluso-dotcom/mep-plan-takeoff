# Measuring lengths from a PDF plan

You are reading a picture of a drawing. That works well for reading sizes and only moderately well for
measuring. The method below keeps the measuring honest: every length comes from traced points and
arithmetic, the scale is checked against something known, and the result is labeled with how far to
trust it.

## 1. Look at the whole sheet first

```bash
python3 scripts/render_sheet.py plans.pdf 7 tiles/ --dpi 100 --tiles 1x1
```

Read the full-sheet image. Find the plan views, the north arrow, the scale under each view title, the
key plan, and which views are enlarged copies of another (don't measure the same pipe twice). Note
match lines.

## 2. Tile it so sizes are legible

```bash
python3 scripts/render_sheet.py plans.pdf 7 tiles/ --dpi 150
```

The script picks the tile grid: the fewest tiles that each stay within 1,900 px. Go to 200 dpi if pipe
sizes or tags are unreadable, or crop straight to one view with `--crop x,y,w,h` (fractions of the
sheet) when the plan fills a small part of it. A crop too big for one image is cut into tiles the same
way. Each tile's filename holds its pixel origin (`_x1200_y0`); that origin goes in `runs.json` so
points from different tiles line up. The script also prints each tile's core box, in that tile's own
pixels. Count a symbol only in the tile whose core contains it. The overlap is there so a symbol on an
edge can be read whole, not so it can be counted in both tiles.

Keep every image under about 1,900 px on its long side. Larger ones are shrunk when read, and points
traced from a shrunk image no longer match the scale. The script warns when an image is too big.

## 3. Calibrate the scale

The scale note (1/4" = 1'-0") is only true if the PDF is at full sheet size. Half-size sets are common.
Find one known dimension on the same view: a dimension string, the graphic scale bar, a 3'-0" door, a
column grid spacing, a room size from the architectural sheet. Put its two end points, its length and
the dpi of the image you read the points from in `calibration`. The dpi lets the calibration hold when
a run is traced later from tiles at another dpi: give that run its own `dpi` and the script scales the
calibration to it. A calibration with no `dpi` is refused.

`measure.py` compares the calibration with the noted scale and warns when they disagree by more than
5%. A run without a calibration is not measured: the script gives the length the noted scale suggests
and adds nothing to a total. Report it as not measured, with the suggestion, and let a person decide.

## 4. Trace runs as points

For each run, follow the line from start to end and write a point at every change of direction.
One run per pipe size and system (3/4" cold water main, 2" vent, 14" supply trunk). Break a run where
the size changes. Give each a name someone could find on the sheet ("CW from meter to water heater").

```json
{"dpi": 150, "scale": "1/4\" = 1'-0\"",
 "calibration": {"points": [[410, 220], [860, 220]], "feet": 12.0, "dpi": 150},
 "runs": [{"name": "CW main to WH", "system": "cold water", "size": "3/4\"", "sheet": "P-101",
           "origin": [1200, 0], "points": [[120, 340], [480, 340], [480, 610]],
           "vertical_ft": 9.0}]}
```

```bash
python3 scripts/measure.py runs.json
```

It returns plan length, vertical length and a bend count per run, and totals by size and system. Keep
`runs.json` with the takeoff; it is the record an estimator can audit.

Write `scale` the way the drawing writes it: `1/4" = 1'-0"`, `1 1/2" = 1'-0"`, an engineering scale
such as `1" = 20'`, or a ratio such as `1:48`. A bare `1/4` still means a quarter inch to the foot. A
scale the script cannot read (`NTS`, `as noted`) is refused.

`measure.py` measures one building and never multiplies; a run that carries `count` is refused. When
identical buildings repeat, measure one and multiply once, in one stated place.

## 5. Add what a plan view hides

- **Vertical pipe**: drops to each fixture, rises to above-ceiling mains, risers between floors, vents
  through the roof. Use ceiling and floor-to-floor heights from the architectural sections. A common
  check is one drop per fixture connection at ceiling height minus rough-in height.
- **Underground**: below-slab sanitary and water are separate lines with different material and labor,
  and usually need trenching or saw-cutting.
- **Riser diagrams and isometrics** are not to scale. Use them for sizes and for what connects to what,
  never for length.

## 6. Fittings, hangers, insulation

- Bends from `measure.py` are a floor for elbows. Add tees at each branch you traced and the fittings
  at each fixture and equipment connection.
- Hangers: by spacing from the specification. With no specification, use the plumbing and mechanical
  code tables your jurisdiction has adopted, cite the table, and state the spacing used.
- Insulation length follows the pipe it covers. Read the specification for which systems are insulated.
- No specification book in the set: pipe material, insulation and duct construction are then undefined.
  Take them from the general notes and schedules if they say, otherwise state an assumption and raise
  a question.

## 7. Confidence labels

| Label | Use when |
|---|---|
| `high` | Counted from a schedule and reconciled with the plan, or a quantity someone measured and gave you |
| `medium` | Traced with a calibrated scale on a clean sheet; counted on plan with no schedule to confirm |
| `low` | Scanned or crowded sheet, routing not shown (you assumed a path), or an allowance |

Lengths traced from an image are `medium` at best and `low` on a crowded or scanned sheet.

## 8. Sanity checks

- Per-fixture check: total domestic water length divided by fixture count should look like a real
  building, tens of feet per fixture, not ones or hundreds.
- If a typical building is repeated, check one building's numbers alone before multiplying.
