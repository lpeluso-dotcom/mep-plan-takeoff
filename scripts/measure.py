#!/usr/bin/env python3
"""Turn traced pipe or duct runs into linear feet, so lengths are computed, not eyeballed.

Usage:  python3 measure.py runs.json
runs.json:
{ "dpi": 150,                      # dpi of the tiles the points were read from
  "scale": "1/4\" = 1'-0\"",        # the scale as written on the drawing; 1" = 20' and 1:48 read too
  "calibration": {"points": [[x1,y1],[x2,y2]], "feet": 12.0, "dpi": 150},   # strongly preferred: a known dimension
  "runs": [ {"name": "CW main", "size": "3/4\"", "sheet": "P-101", "origin": [0,0],
             "points": [[120,340],[480,340],[480,610]], "vertical_ft": 9.0} ] }
`origin` is the tile's x,y pixel offset (it is in the tile filename). `vertical_ft` adds risers and drops that a plan
view cannot show; a run with no `points` is vertical only. Interior vertices are reported as bends. A run may carry
its own `scale` or `calibration` when it comes from a different sheet or view than the file-level one, or only its
own `dpi` when it was traced from tiles at another dpi (the file's calibration is scaled to it), and a `system`, a
`note` and a `confidence` that print with it. A calibration states the `dpi` of the image its points were read from.
If calibration is given it overrides `scale`, and the two are compared so a mis-scaled PDF is caught.
A run traced with no calibration behind it is not measured: it comes back with a suggested length and adds
nothing to a total.
This script measures one building and never multiplies: identical buildings are the estimate's `building_count`,
with the line marked `per_building`.

From Python: measure.measure(doc) returns {"runs": [...], "totals": [...], "messages": [...]} and raises ValueError
with one sentence when the input cannot be measured.
"""
import json
import math
import re
import sys
from fractions import Fraction

_PAPER = r"(\d+(?:\.\d+)?\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?|\.\d+)"          # 1 1/2, 1/4, 0.25
_AS_DRAWN = re.compile(_PAPER + r"""\s*"\s*=\s*(\d+(?:\.\d+)?)\s*'(?:\s*-?\s*(\d+(?:\.\d+)?)\s*")?""")
_RATIO = re.compile(r"1\s*:\s*(\d+(?:\.\d+)?)")


def parse_scale(text) -> float:
    """Inches on paper per foot of building, from a scale as it is written on a drawing:
    1/4" = 1'-0" (0.25), 1" = 20' (0.05), 1:48 (0.25), or the bare paper side, 1/4 or 0.25."""
    def refuse():
        return ValueError(f'Scale {text!r} cannot be read. Write it as on the drawing, such as 1/4" = 1\'-0" or 1" = 20\'.')

    def paper(s):
        return float(sum(Fraction(part) for part in s.split()))
    try:
        if isinstance(text, (int, float)) and not isinstance(text, bool):
            value = float(text)
        else:
            s = str(text).strip()
            if m := _AS_DRAWN.fullmatch(s):
                value = paper(m.group(1)) / (float(m.group(2)) + float(m.group(3) or 0) / 12)
            elif m := _RATIO.fullmatch(s):
                value = 12 / float(m.group(1))
            elif re.fullmatch(_PAPER, s):
                value = paper(s)
            else:
                raise refuse()
    except ZeroDivisionError:
        raise refuse() from None
    if not value > 0 or math.isinf(value):
        raise refuse()
    return value


def _feet_per_pixel(scale, calibration, dpi, label: str, messages: list):
    """(feet per pixel, calibrated) for an image rendered at `dpi`, from a noted scale and/or a known dimension;
    feet per pixel is None if neither is given. A calibration carries the dpi of the image its two points were read
    from, so it holds for a run traced at another dpi. `calibrated` is False when only the noted scale stands
    behind the figure."""
    f = None
    if scale:
        if not dpi:
            raise ValueError(f"{label} gives a scale but no dpi. Add the dpi of the tiles the points were read from.")
        f = 1 / (parse_scale(scale) * dpi)                     # a paper inch is dpi pixels; the scale is inches per foot
    if calibration:
        (a, b), feet = calibration["points"], calibration["feet"]
        if not calibration.get("dpi"):
            raise ValueError(f"The calibration for {label} has no dpi. Add the dpi of the image its two points were read from.")
        if math.dist(a, b) == 0:
            raise ValueError(f"The calibration for {label} has two identical points. Pick the two ends of a known dimension.")
        cal = feet / math.dist(a, b) * calibration["dpi"] / (dpi or calibration["dpi"])
        if f and abs(cal - f) / f > 0.05:
            messages.append(f"WARNING ({label}): noted scale gives {f:.4f} ft/px but the known dimension gives {cal:.4f} "
                            f"ft/px ({(cal / f - 1) * 100:+.0f}%). Using the known dimension. The PDF is probably not at "
                            "its stated scale.")
        f = cal
    return f, bool(calibration)


def measure(doc: dict) -> dict:
    """Lengths for every run in a runs.json document. Nothing is printed and nothing is multiplied."""
    if not isinstance(doc, dict) or not isinstance(doc.get("runs"), list):
        raise ValueError('The runs file has no "runs" list.')
    messages, runs, tot = [], [], {}
    file_fc = _feet_per_pixel(doc.get("scale"), doc.get("calibration"), doc.get("dpi"), "the file", messages)
    for i, r in enumerate(doc["runs"], 1):
        name = str(r.get("name") or "").strip()
        if not name:
            raise ValueError(f"Run {i} has no name. Give it one someone could find on the sheet.")
        if "count" in r:
            raise ValueError(f'Run "{name}" carries count {r["count"]}. measure.py no longer multiplies. Measure one '
                             "building and set building_count in the estimate, with the line marked per_building.")
        ox, oy = r.get("origin", [0, 0])
        pts = [(x + ox, y + oy) for x, y in r.get("points", [])]
        dpi = r.get("dpi", doc.get("dpi"))
        if "scale" in r or "calibration" in r:              # another sheet or view: its own scale, its own known dimension
            f, calibrated = _feet_per_pixel(r.get("scale"), r.get("calibration"), dpi, f'run "{name}"', messages)
        elif "dpi" in r:                                    # the file's view, traced from tiles at another dpi
            f, calibrated = _feet_per_pixel(doc.get("scale"), doc.get("calibration"), dpi, f'run "{name}"', messages)
        else:
            f, calibrated = file_fc
        if len(pts) > 1 and not f:
            raise ValueError(f'Run "{name}" has points but no scale or calibration.')
        plan = sum(math.dist(pts[k], pts[k + 1]) for k in range(len(pts) - 1)) * f if len(pts) > 1 else 0.0
        vertical = r.get("vertical_ft", 0) or 0
        run = {"name": name, "sheet": r.get("sheet", ""), "size": r.get("size", ""), "system": r.get("system", name),
               "plan_ft": round(plan, 1), "vertical_ft": round(float(vertical), 1), "total_ft": round(plan + vertical, 1),
               "bends": max(0, len(pts) - 2), "state": "measured", "confidence": r.get("confidence", ""),
               "note": r.get("note", "")}
        runs.append(run)
        if len(pts) > 1 and not calibrated:
            # the length rests on a scale nobody checked against a dimension: a suggestion, never part of a total
            run.update(state="not_measured", suggested_ft=run["total_ft"], total_ft=0.0)
            messages.append(f'{name}: not measured. No known dimension was checked on {run["sheet"] or "its sheet"}, so the '
                            f'noted scale is unverified. The scale suggests {run["suggested_ft"]:.1f} ft. Calibrate on a '
                            f'dimension, or enter the line with qty 0, qty_status not_measured and suggested_qty '
                            f'{run["suggested_ft"]:.0f}.')
            continue
        t = tot.setdefault((run["size"], run["system"]), [0.0, 0])
        t[0] += run["total_ft"]
        t[1] += run["bends"]
    totals = [{"size": size, "system": system, "total_ft": round(lf, 1), "bends": bends}
              for (size, system), (lf, bends) in sorted(tot.items())]
    return {"runs": runs, "totals": totals, "messages": messages}


def _print(result: dict) -> None:
    print(f'{"sheet":8} {"name":34} {"size":8} {"plan LF":>8} {"vert LF":>8} {"total LF":>12} {"bends":>5}')
    for r in result["runs"]:
        total = "not measured" if r["state"] == "not_measured" else f'{r["total_ft"]:.1f}'
        print(f'{r["sheet"]:8} {r["name"][:34]:34} {r["size"]:8} {r["plan_ft"]:8.1f} {r["vertical_ft"]:8.1f} '
              f'{total:>12} {r["bends"]:5}  {r["confidence"]} {r["note"]}')
    print("\nTOTALS by size and system")
    for t in result["totals"]:
        print(f'  {t["size"]:8} {t["system"][:40]:40} {t["total_ft"]:9.1f} LF  {t["bends"]} bends')
    if result["messages"]:
        print()
    for line in result["messages"]:
        print(line)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        with open(sys.argv[1]) as src:
            _print(measure(json.load(src)))
    except (ValueError, KeyError, TypeError, OSError) as e:        # json.JSONDecodeError is a ValueError
        sys.exit(f"Not measured: {e}")
