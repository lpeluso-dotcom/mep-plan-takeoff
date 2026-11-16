#!/usr/bin/env python3
"""Count plan tags (WC-1, EF-2, RTU-1) from a PDF's own text, with where each one sits on the sheet.

Usage:  python3 tag_count.py <plans.pdf> --pages 7,9-11 [--tags WC-1,LAV-1,FD-1] [--out tags.json]
--pages  the plan sheets to count, by PDF page number. Leave out schedule, detail and riser sheets.
--tags   the tags to count, as the schedules name them. Other tag-like marks on the plan are listed as
         "not asked for". Without --tags, every mark with a common fixture or equipment prefix is counted.
--out    saves every tag found with its box (points from the sheet's top-left), for
         `render_sheet.py --mark tags.json`, which draws the boxes on the tiles.

A tag counts when it stands on the plan. One in a schedule column, a tag list ("EF-1, EF-2"), a labelled row
("HB-1 HOSE BIBB") or a sentence of a note is seen and not counted.

This counts tags, not fixtures. Text drawn as outlines and anything on a scanned sheet is not in the PDF's
text, so it is not seen here, and a fixture tagged in two views (a waste plan and a water plan of one floor)
is counted twice. A page where no tag at all is found is "not counted", never zero: count it by eye.
Needs poppler or pypdfium2, like plan_index.py.
"""
import json, os, re, sys

import plan_index as pi

# Common fixture, equipment, air-device and panel prefixes on plumbing, mechanical and electrical plans.
TAG_PREFIX = (
    "WC|EWC|L|LAV|UR|S|SK|MS|MB|DF|EDF|BF|FD|FS|FCO|CO|WCO|GCO|HB|WH|EWH|GWH|IWH|TMV|MV|WHA|SH|SHR|TS|"
    "RTU|AHU|HP|CU|ACCU|FC|FCU|EF|SF|RF|TF|KEF|ERV|DOAS|UH|EUH|CUH|EWB|VAV|CD|SD|RD|RG|EG|TG|SG|SR|LV|"
    "MAU|DH|BB|ECU|MSHP|IDU|ODU|LP|PP|DP|MDP|RP|EP|T|J|F|X|R|E|P|B|G|AH|AC|FFU|MH|WM|ET|BFP|RPZ|PRV|GD|CH|BLR|EX|MOP|SS"
)
TAG_RE = re.compile(rf"^({TAG_PREFIX})-?\d{{1,3}}[A-Z]?$")
TAG_ONE = re.compile(r"^[A-Z]\d")      # "S2", "F2": a one-letter mark needs its hyphen, or it is a grid or note mark
# Words that sit beside a real plan tag ("EF-1 ON ROOF", "WH-1 ABOVE CLG") and so do not make a table row.
CALLOUT_WORDS = {"ABOVE", "BELOW", "DOWN", "ROOF", "CEILING", "CLG", "EXIST", "EXISTING", "RELOCATED", "RELOCATE",
                 "REMOVE", "REMOVED", "TYPICAL", "SEE", "NOTE", "FLOOR", "WALL", "MOUNTED", "UNDER", "OVER", "ONLY",
                 "SIMILAR", "ABV", "FUTURE", "ALT", "ALTERNATE"}


def tag_like(token):
    return bool(TAG_RE.match(token)) and not TAG_ONE.match(token)


def find_tags(words, asked=None):
    """Every tag in these words as {tag, x0, y0, x1, y1}, the box being its word's. A word is cut at anything
    but a letter, a digit or a hyphen, so "(BF-1)", "EF-2," and "KEH-1/KEF-1" give their tags and "CU-1"
    inside "CRAC-CU-1" is not one. With `asked`, those tags are found whatever their prefix."""
    out = []
    for text, x0, y0, x1, y1 in words:
        for token in re.split(r"[^A-Z0-9-]+", text.upper()):
            if (asked and token in asked) or tag_like(token):
                out.append({"tag": token, "x0": x0, "y0": y0, "x1": x1, "y1": y1})
    return out


def row_context(box, words, is_tag, max_gap=5.0, base_tol=0.25):
    """`schedule`, `note` or None for a tag box, from the words on its own text line.

    A schedule row or a note sentence puts a real word (4 or more letters, the same text size, the same
    baseline) within max_gap text-heights of the tag, or lists tags with commas. A plan callout sits beside
    other tags, one-letter circuit marks, values under a leader line or a larger room name, which this ignores.
    Three such words make a note. Works along the sheet or up it (text turned 90 degrees)."""
    vertical = (box["y1"] - box["y0"]) > 1.5 * (box["x1"] - box["x0"])
    a0, a1, c0, c1 = (2, 4, 1, 3) if vertical else (1, 3, 2, 4)     # along the line, across it
    b = (None, box["x0"], box["y0"], box["x1"], box["y1"])
    h = b[c1] - b[c0]
    if h <= 0:
        return None
    content, comma = 0, False
    for w in words:
        if abs(w[c1] - b[c1]) > base_tol * h:
            continue
        if min(w[a1], b[a1]) - max(w[a0], b[a0]) > 0.5 * (b[a1] - b[a0]):   # the tag's own word: "EF-2,", "(BF-1)"
            comma = comma or w[0].rstrip().endswith(",")
            continue
        gap = w[a0] - b[a1] if w[a0] >= b[a1] else b[a0] - w[a1]
        if gap < -0.2 * h or gap > max_gap * h:      # text over the tag is another label (a room name), not a row
            continue
        size = (w[c1] - w[c0]) / h
        t = w[0].strip(".,:;()").upper()
        if w[0].endswith(",") and is_tag(t) and gap < 1.5 * h and 0.8 <= size <= 1.3:
            comma = True
        elif 0.85 <= size <= 1.2 and sum(c.isalpha() for c in t) >= 4 and not is_tag(t) and t not in CALLOUT_WORDS:
            content += 1
    return "note" if content >= 3 else "schedule" if content or comma else None


def classify(boxes, words, asked=None, tol=1.5):
    """Sets `where` on each tag box: `plan`, `schedule` or `note`. A schedule's MARK column is three or more
    different tags sharing a left edge, or three or more entries stacked tight (gaps under 2.5 text-heights),
    such as one unit tag repeated down a column. The rest are judged by their own text line (row_context).
    Checked 2026-11-16 against 23 labelled plan sheets: what is left wrong is a plan tag beside a same-size
    word ("WC-1 SHOWER", a room name) or lined up by chance with two others on a crowded sheet, read as
    `schedule`. render_sheet.py --mark shows those as blue boxes on the plan."""
    cols = []
    for b in sorted(boxes, key=lambda b: b["x0"]):       # a column: left edges within tol points of its first
        if cols and b["x0"] - cols[-1][0]["x0"] <= tol:
            cols[-1].append(b)
        else:
            cols.append([b])
    height = lambda b: min(b["x1"] - b["x0"], b["y1"] - b["y0"])     # the text size, also for a tag turned 90 degrees
    for col in cols:
        if len({b["tag"] for b in col}) >= 3:
            for b in col:
                b["where"] = "schedule"
        col = sorted(col, key=lambda b: b["y0"])
        run = col[:1]
        for b in col[1:] + [None]:
            if b is not None and b["y0"] - run[-1]["y1"] <= 2.5 * height(run[-1]):
                run.append(b)
                continue
            if len(run) >= 3:
                for r in run:
                    r["where"] = "schedule"
            run = [b]
    is_tag = lambda t: (asked and t in asked) or tag_like(t) or bool(re.match(r"^[A-Z]-\d", t))
    for b in boxes:
        if "where" not in b:
            b["where"] = row_context(b, words, is_tag) or "plan"
    return boxes


def count(pdf, pages, tags=None, backend=None):
    """Counts for the given pages. Per page: every tag found with its box and `where`, `counts` of the tags
    standing on the plan (the asked tags, zeros included, or every tag found), `unlisted` for plan tags that
    were not asked for, and `counted` False with `counts` None when the page's text holds no tag at all."""
    backend = backend or pi.pdf_backend()
    asked = [t.strip().upper() for t in tags if t.strip()] if tags else None
    out = {"pdf": os.path.basename(pdf), "asked": asked, "pages": [], "totals": {t: 0 for t in asked or []}, "not_counted": []}
    for p in pages:
        words = pi.page_words(pdf, p, backend)
        W, H = pi.page_size(pdf, p, backend)
        in_title_block = lambda b: (b[1] + b[3]) / 2 > W * .78 and (b[2] + b[4]) / 2 > H * .55    # as plan_index reads it
        sheet = pi.pick_sheet([w for w in words if in_title_block(w)])
        # the sheet's own number in its title block ("P-1") is not a fixture tag
        hits = [b for b in find_tags(words, set(asked or []))
                if not (sheet and b["tag"].replace("-", "") == sheet and in_title_block((0, b["x0"], b["y0"], b["x1"], b["y1"])))]
        found = classify(hits, words, set(asked or []))
        on_plan = {}
        for b in found:
            if b["where"] == "plan":
                on_plan[b["tag"]] = on_plan.get(b["tag"], 0) + 1
        row = {"page": p, "sheet": sheet, "text_chars": sum(len(w[0]) for w in words), "counted": bool(found), "tags": found,
               "counts": None, "unlisted": {}}
        if not found:
            out["not_counted"].append(p)
        else:
            row["counts"] = {t: on_plan.get(t, 0) for t in asked} if asked else on_plan
            row["unlisted"] = {t: n for t, n in on_plan.items() if asked and t not in asked}
            for t, n in row["counts"].items():
                out["totals"][t] = out["totals"].get(t, 0) + n
        out["pages"].append(row)
    return out


def summary(result):
    lines = []
    for p in result["pages"]:
        if not p["counted"]:
            lines.append(f'p{p["page"]}{" " + p["sheet"] if p["sheet"] else ""}: not counted. No tag in this page\'s text (drawn as outlines, or scanned): count it by eye.')
            continue
        out = {}
        for t in p["tags"]:
            if t["where"] != "plan" and (not result["asked"] or t["tag"] in result["asked"]):
                out[t["tag"]] = out.get(t["tag"], 0) + 1
        each = lambda d: ", ".join(f"{t} x{n}" for t, n in d.items())
        lines.append(f'p{p["page"]}{" " + p["sheet"] if p["sheet"] else ""}: ' + (each(p["counts"]) or "no plan tags")
                     + (f'; not asked for: {each(p["unlisted"])}' if p["unlisted"] else "")
                     + (f"; left out (in a schedule, a list or a note): {each(out)}" if out else ""))
    lines.append("total on plan: " + (", ".join(f"{t} x{n}" for t, n in result["totals"].items()) or "nothing"))
    if result["not_counted"]:
        lines.append("not counted (no tags in the text): page " + ", ".join(map(str, result["not_counted"])))
    lines.append("These are tags in the PDF's text. A tag drawn as outlines or scanned is not seen, and a fixture tagged "
                 "in two views is counted twice. Check the marked tiles (render_sheet.py --mark).")
    return "\n".join(lines)


def parse_pages(spec, n):
    """"1,3-5" as [1, 3, 4, 5]; every page must be within 1..n."""
    pages = []
    for part in spec.split(","):
        m = re.fullmatch(r"\s*(\d+)(?:\s*-\s*(\d+))?\s*", part)
        a, b = (int(m.group(1)), int(m.group(2) or m.group(1))) if m else (0, 0)
        if not 1 <= a <= b <= n:
            sys.exit(f"--pages needs page numbers from 1 to {n}, such as 7,9-11; {spec!r} was given.")
        pages += range(a, b + 1)
    return pages


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or "--help" in a or "-h" in a:
        print(__doc__)
        sys.exit(0 if a else 2)
    get = lambda flag: a[a.index(flag) + 1] if flag in a and a.index(flag) + 1 < len(a) else None
    if not os.path.isfile(a[0]):
        sys.exit(f"{a[0]} is not a PDF file.")
    if not get("--pages"):
        sys.exit("--pages is needed: the plan sheets to count, by PDF page number, such as --pages 7,9-11.")
    result = count(a[0], parse_pages(get("--pages"), pi.page_count(a[0])), get("--tags").split(",") if get("--tags") else None)
    if get("--out"):
        json.dump(result, open(get("--out"), "w"), indent=1)
    print(summary(result))
