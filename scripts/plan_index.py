#!/usr/bin/env python3
"""Index a plan set: one row per PDF page with sheet number, title-block text and schedule hints.

text_chars counts non-space characters. LOWTEXT pages (under 2,500) carry only a title block or seal:
their drawings and schedules are outlines or images, so read them from rendered tiles, and do not
trust the sheet number guessed here.

The sheet number is the largest sheet-number-like text in the title block (bottom-right corner), never one in a
revision date or named in a note such as "REFER TO SHEET E-601", so poppler and pypdfium2 give the same answer.

Usage:  python3 plan_index.py <plans.pdf | plans.zip | folder> [--out index.json]
        python3 plan_index.py <plans.pdf> --text <page>     one page's text laid out in columns, for schedules
Needs poppler (pdfinfo, pdftotext), or the pypdfium2 library (4 or newer) where poppler is not installed.
Zips are unpacked next to the zip in <name>_unzipped/, or in a temp folder when that place cannot be written.
"""
import json, os, re, shutil, subprocess, sys, tempfile, zipfile
from html import unescape

# sheet numbers start with a discipline letter; "OF" (as in "1 OF 13") and plain words are not sheet numbers,
# and neither is a project number such as P12-3456 (three or more digits after the dash) or a revision date
# such as "A 01-15-2024" or "B 1/15/24"
SHEET = re.compile(r'(?<![A-Z0-9])((?:FP|FA|FS|ES|MP|ME|EP|[PMEASCGTLKHD]))[-. ]?(\d{1,2}[.-]\d{1,2}|\d{1,3})'
                   r'(?![0-9]|[.-][0-9]{3}|[./-]\d{1,2}[./-]\d{2})')
HINTS = ["SCHEDULE", "RISER", "ISOMETRIC", "LEGEND", "GENERAL NOTES", "DETAILS", "FLOOR PLAN", "ROOF PLAN", "DEMOLITION", "SPECIFICATION"]
DISC = {"P": "Plumbing", "M": "Mechanical", "H": "Mechanical", "E": "Electrical", "FP": "Fire protection", "A": "Architectural",
        "S": "Structural", "C": "Civil", "G": "General", "T": "General", "L": "Landscape", "FS": "Food service", "K": "Food service"}

def run(*a):
    return subprocess.run(a, capture_output=True, text=True).stdout

def pdfs(path):
    if os.path.isdir(path):
        return sorted(os.path.join(d, f) for d, _, fs in os.walk(path) for f in fs if f.lower().endswith(".pdf"))
    if path.lower().endswith(".zip"):
        dest = os.path.splitext(path)[0] + "_unzipped"
        try:
            os.makedirs(dest, exist_ok=True)
        except OSError:                       # an uploads folder that cannot be written
            dest = tempfile.mkdtemp(prefix="plans_")
        with zipfile.ZipFile(path) as z:
            for m in z.infolist():  # refuse paths that escape dest
                if os.path.realpath(os.path.join(dest, m.filename)).startswith(os.path.realpath(dest) + os.sep):
                    z.extract(m, dest)
        return pdfs(dest)
    return [path]

def pdf_backend():
    """poppler when its command-line tools are installed, otherwise the pypdfium2 Python library."""
    return "poppler" if all(shutil.which(t) for t in ("pdfinfo", "pdftotext", "pdftoppm")) else "pdfium"

def _pdfium(pdf):
    import pypdfium2
    return pypdfium2.PdfDocument(pdf)

def page_count(pdf, backend=None):
    if (backend or pdf_backend()) == "pdfium":
        return len(_pdfium(pdf))
    return int(re.search(r"Pages:\s+(\d+)", run("pdfinfo", pdf)).group(1))

def page_size(pdf, page, backend=None):
    """Width and height in points as the page is displayed (rotation applied). Pages count from 1."""
    if (backend or pdf_backend()) == "pdfium":
        return tuple(_pdfium(pdf)[page - 1].get_size())
    info = run("pdfinfo", "-f", str(page), "-l", str(page), pdf)
    m = re.search(r"Page\s+%d size:\s+([\d.]+) x ([\d.]+)" % page, info)
    w, h = (float(m.group(1)), float(m.group(2))) if m else (2448.0, 1584.0)
    rot = re.search(r"Page\s+%d rot:\s+(\d+)" % page, info)
    return (h, w) if rot and int(rot.group(1)) in (90, 270) else (w, h)

def page_text(pdf, page, backend=None, crop=None):
    """Text of one page, within the crop box (the sheet as shown). crop = (x, y, width, height) in points from
    the top-left corner; cropped text comes back one line per text line, top to bottom."""
    if crop:
        x, y, w, h = crop
        inside = [t for t in page_words(pdf, page, backend) if x <= (t[1] + t[3]) / 2 <= x + w and y <= (t[2] + t[4]) / 2 <= y + h]
        return "\n".join(" ".join(t[0] for t in line) for line in text_lines(inside))
    if (backend or pdf_backend()) == "pdfium":
        return _pdfium(pdf)[page - 1].get_textpage().get_text_range()
    return run("pdftotext", "-f", str(page), "-l", str(page), "-cropbox", "-layout", pdf, "-")

def page_words(pdf, page, backend=None):
    """Words of one page as (text, x0, y0, x1, y1): points on the sheet as shown, from the top-left corner,
    rotation applied. Box height follows the font size on both backends. Text off the crop box is dropped."""
    if (backend or pdf_backend()) != "pdfium":
        html = run("pdftotext", "-bbox", "-cropbox", "-f", str(page), "-l", str(page), pdf, "-")
        return [(unescape(t), float(a), float(b), float(c), float(d)) for a, b, c, d, t in
                re.findall(r'<word xMin="([-\d.]+)" yMin="([-\d.]+)" xMax="([-\d.]+)" yMax="([-\d.]+)">(.*?)</word>', html)]
    import pypdfium2.raw as raw
    pg = _pdfium(pdf)[page - 1]
    tp = pg.get_textpage()
    W, H = pg.get_size()
    left, bottom = pg.get_bbox()[:2]
    rot = pg.get_rotation() % 360

    def shown(sx, sy):        # stored coordinates (page box origin, before rotation) to the sheet as shown
        sx, sy = sx - left, sy - bottom
        return {0: (sx, H - sy), 90: (sy, sx), 180: (W - sx, sy), 270: (W - sy, H - sx)}[rot]
    words, cur, last = [], None, None
    for i in range(tp.count_chars()):
        ch = chr(raw.FPDFText_GetUnicode(tp, i))
        if ch.isspace() or ch == "\x00":            # pdfium puts a space or line break between separate runs
            cur = None
            continue
        l, b, r, t = tp.get_charbox(i, loose=True)   # loose: the font's full height, not the glyph's ink
        (xa, ya), (xb, yb) = shown(l, b), shown(r, t)
        box = [min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb)]
        reach = .5 * max(box[2] - box[0], box[3] - box[1])
        # same word: touches the character before it and sits in line with it, across or down the sheet;
        # text along a slant or a curve (a road name on a site plan) is split, as poppler splits it
        if cur and max(box[0] - last[2], last[0] - box[2], box[1] - last[3], last[1] - box[3]) < reach and \
                min(abs(box[0] + box[2] - last[0] - last[2]), abs(box[1] + box[3] - last[1] - last[3])) / 2 \
                < .2 * min(box[2] - box[0], box[3] - box[1]):
            cur[0] += ch
            cur[1:] = [min(cur[1], box[0]), min(cur[2], box[1]), max(cur[3], box[2]), max(cur[4], box[3])]
        else:
            cur = [ch] + box
            words.append(cur)
        last = box
    return [tuple(w) for w in words if -1 < (w[1] + w[3]) / 2 < W + 1 and -1 < (w[2] + w[4]) / 2 < H + 1]

def text_lines(words):
    """Words grouped into lines, top to bottom; each line is its words left to right. Independent of the order
    the PDF drew them in, so both backends give the same lines."""
    lines = []
    for w in sorted(words, key=lambda w: (w[2] + w[4]) / 2):
        yc, h = (w[2] + w[4]) / 2, w[4] - w[2]
        if lines and abs(yc - lines[-1][0]) < .5 * min(h, lines[-1][1]):
            lines[-1][2].append(w)
        else:
            lines.append([yc, h, [w]])
    return [sorted(ws, key=lambda w: w[1]) for _, _, ws in lines]

def layout_text(words):
    """The page as plain text with words set in columns by their place on the sheet, as pdftotext -layout does,
    so a schedule reads row by row."""
    if not words:
        return ""
    widths = sorted((w[3] - w[1]) / len(w[0]) for w in words)
    cw = max(widths[len(widths) // 2], 1.0)
    out = []
    for line in text_lines(words):
        s = ""
        for w in line:
            col = int(w[1] / cw)
            s += (" " * (col - len(s)) if col > len(s) else (" " if s else "")) + w[0]
        out.append(s)
    return "\n".join(out) + "\n"

# a sheet number named in a note ("REFER TO ... SHEET E-601", "SEE M-501") points at another sheet
XREF = re.compile(r"\b(?:REFER|REFERENCE|SEE|ON|TO|PER|SHEETS?|DWGS?|DRAWINGS?|DETAIL)\.?:?\s*$")
# plainly a note: "REFER TO SHEET E-601", "SEE M-501", "SEE DETAIL 3 ON SHEET P-401"
NOTE = re.compile(r"\b(?:REFER(?:ENCE)?|SEE|PER)\b(?:\s+\S+){0,3}\s*$|\b(?:ON|TO)\s+(?:SHEETS?|DWGS?|DRAWINGS?)\.?:?\s*$")

def pick_sheet(words):
    """The sheet number among these words: the largest sheet-number-like text, as a title block draws its sheet
    number biggest; among those of about that size, one not under a label a note might use, then the lowest,
    then the rightmost. Never the order the text came back in, which differs between poppler and pdfium.

    A number that reads as part of a note pointing at another sheet ("REFER TO SHEET E-601", "SEE M-501",
    "E-601 FOR POWER", and the "M-502" of "SEE M-501 AND M-502") is never the answer, so a page whose own
    number is drawn as outlines comes back blank, not as the sheet the note names."""
    cands = []
    for line in text_lines(words):
        text, spans = "", []
        for w in line:
            text += (" " if text else "") + w[0]
            spans.append((len(text) - len(w[0]), len(text), w))
        noted = None                                  # the last match that was part of a note
        for m in SHEET.finditer(text):
            before, after = text[:m.start()], text[m.end():]
            if (NOTE.search(before) or re.match(r"\s+FOR\b", after) or (XREF.search(before) and after.strip())
                    or (noted and re.fullmatch(r"\s*(?:,|&|AND|OR|THRU|THROUGH)?\s*", text[noted.end():m.start()]))):
                noted = m
                continue
            ws = [w for a, b, w in spans if a < m.end() and b > m.start()]
            size = max(w[4] - w[2] for w in ws)
            cands.append((size, not XREF.search(text[:m.start()]), max(w[4] for w in ws), max(w[3] for w in ws), "".join(m.groups())))
    if not cands:
        return ""
    top = max(c[0] for c in cands)
    return max((c for c in cands if c[0] >= .85 * top), key=lambda c: c[1:4])[4]

def index(pdf):
    backend = pdf_backend()
    rows = []
    for p in range(1, page_count(pdf, backend) + 1):
        w, h = page_size(pdf, p, backend)
        full = page_text(pdf, p, backend)
        words = page_words(pdf, p, backend)
        # title block: the right 22% of the sheet, bottom 45%; failing that, the whole sheet
        tb = [x for x in words if (x[1] + x[3]) / 2 > w * .78 and (x[2] + x[4]) / 2 > h * .55]
        sheet = pick_sheet(tb) or pick_sheet(words)
        prefix = re.match(r"[A-Z]+", sheet).group(0) if sheet else ""
        disc = DISC.get(prefix) or DISC.get(prefix[:1], "")
        up = full.upper()
        rows.append({"file": os.path.basename(pdf), "page": p, "sheet": sheet, "discipline": disc,
                     "title_block": " | ".join(" ".join(x[0] for x in line) for line in text_lines(tb))[-220:],
                     "text_chars": len("".join(full.split())), "low_text": len("".join(full.split())) < 2500,
                     "hints": [k for k in HINTS if k in up],
                     "scales": sorted(set(re.findall(r'(?:SCALE:?\s*)?(\d/\d+"\s*=\s*1\'-0")', up)))[:4]})
    return rows

if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        sys.exit(0)
    if len(sys.argv) < 2: sys.exit(__doc__)
    if "--text" in sys.argv:
        at = sys.argv.index("--text") + 1
        pg, backend = (sys.argv[at] if at < len(sys.argv) else None), pdf_backend()
        if not os.path.isfile(sys.argv[1]):
            sys.exit(f"--text reads one page of one PDF file; {sys.argv[1]} is not a file.")
        n = page_count(sys.argv[1], backend)
        if pg is None or not re.fullmatch(r"\d+", pg) or not 1 <= int(pg) <= n:
            sys.exit(f"--text needs a page number from 1 to {n}: {os.path.basename(sys.argv[1])} has {n} page{'s' if n != 1 else ''}"
                     f"{'' if pg is None else ', and ' + repr(pg) + ' was asked for'}.")
        pg = int(pg)
        sys.stdout.write(page_text(sys.argv[1], pg, backend) if backend == "poppler" else layout_text(page_words(sys.argv[1], pg, backend)))
        sys.exit(0)
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    rows = [r for f in pdfs(sys.argv[1]) for r in index(f)]
    if out: json.dump(rows, open(out, "w"), indent=1)
    for r in rows:
        print(f'{r["file"][:28]:28} p{r["page"]:<3} {r["sheet"]:7} {r["discipline"][:11]:11} {("LOWTEXT " if r["low_text"] else "") + str(r["text_chars"])+"ch":14} {",".join(r["scales"])[:24]:24} {",".join(r["hints"])}')
