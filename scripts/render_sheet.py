#!/usr/bin/env python3
"""Render one plan page to PNG so it can be read with the Read tool. Optionally cut it into tiles.

Usage:  python3 render_sheet.py <plans.pdf> <page> <outdir> [--dpi 100] [--tiles auto] [--overlap 0.08]
        python3 render_sheet.py <plans.pdf> <page> <outdir> --dpi 150 --crop 0.55,0.10,0.40,0.35
        python3 render_sheet.py <plans.pdf> <page> <outdir> --dpi 200 --mark tags.json
--tiles auto (the default) cuts the sheet into the fewest tiles that each stay within 1,900 px; --tiles 3x2
sets the grid by hand, and --tiles 1x1 gives the whole sheet as one image.
--mark tags.json boxes the tags `tag_count.py --out tags.json` found: red for a tag counted on the plan, blue
for one seen in a schedule, a list or a note and not counted. A tag with no box is one the script did not see.
--crop takes x,y,width,height as fractions of the sheet (0-1 from the top-left): use it for one schedule
block or one plan view. --tiles applies to the cropped region, so a large crop is cut into tiles too. Each filename carries the tile's pixel origin so points map back to the sheet.
Tiles overlap so a symbol on an edge can be read whole. Each printed line gives the tile's core box in
the tile's own pixels: count a symbol only in the tile whose core contains it.
Images wider or taller than about 1,900 px get shrunk when read, which silently breaks traced
coordinates, so the script warns; let it pick the grid or tighten the crop instead of reading those.
"""
import os, subprocess, sys

import plan_index as pi

def arg(flag, default):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default

def tile_grid(W: int, H: int, overlap: float = 0.08, max_px: int = 1900) -> tuple:
    """The smallest (cols, rows) that keeps every tile, overlap included, within max_px on each side."""
    def fewest(size):
        n = 1
        while int(size / n * (1 + 2 * overlap)) > max_px:
            n += 1
        return n
    return fewest(W), fewest(H)

def tile_boxes(W: int, H: int, cols: int, rows: int, overlap: float = 0.08) -> list:
    """The tiles of a W x H sheet, row by row, in sheet pixels. Each has a `core` and a `box`, both
    (x0, y0, x1, y1). The cores tile the sheet exactly once with no overlap. The box is the core grown by
    `overlap` times the core's size on every side, clipped to the sheet: it is what gets rendered, so a
    symbol on an edge can be read whole, while only the tile whose core holds it counts it."""
    xs = [round(W * i / cols) for i in range(cols + 1)]
    ys = [round(H * i / rows) for i in range(rows + 1)]
    out = []
    for r in range(rows):
        for c in range(cols):
            x0, y0, x1, y1 = xs[c], ys[r], xs[c + 1], ys[r + 1]
            gx, gy = int((x1 - x0) * overlap), int((y1 - y0) * overlap)
            out.append({"col": c, "row": r, "core": (x0, y0, x1, y1),
                        "box": (max(0, x0 - gx), max(0, y0 - gy), min(W, x1 + gx), min(H, y1 + gy))})
    return out

def plan_boxes(W: int, H: int, tiles: str = "auto", overlap: float = 0.08, crop=None) -> list:
    """The tiles to render for a W x H sheet, as tile_boxes() gives them, in sheet pixels. crop is
    (x, y, width, height) as fractions of the sheet; the grid then covers only that region, so a large crop
    is cut into tiles within 1,900 px like a whole sheet ("auto"), or into the grid given ("3x2")."""
    x0, y0, w, h = (0, 0, W, H) if crop is None else (int(crop[0] * W), int(crop[1] * H), int(crop[2] * W), int(crop[3] * H))
    cols, rows = tile_grid(w, h, overlap) if tiles.lower() == "auto" else (int(v) for v in tiles.lower().split("x"))
    out = []
    for t in tile_boxes(w, h, cols, rows, overlap):
        shift = lambda b: (b[0] + x0, b[1] + y0, b[2] + x0, b[3] + y0)
        out.append({**t, "core": shift(t["core"]), "box": shift(t["box"])})
    return out

def sheet_pixels(pdf, page, dpi, backend=None):
    """Pixel width and height of the page as rendered at dpi (rotation applied)."""
    w, h = pi.page_size(pdf, page, backend)
    return int(w * dpi / 72), int(h * dpi / 72)

def render(pdf, page, dpi, box, out_png, backend=None):
    """Render box = (x, y, width, height) in pixels at dpi, from the top-left, to out_png."""
    x, y, w, h = box
    if (backend or pi.pdf_backend()) == "pdfium":
        import pypdfium2
        image = pypdfium2.PdfDocument(pdf)[page - 1].render(scale=dpi / 72).to_pil()
        image.crop((x, y, x + w, y + h)).save(out_png)
        return
    stem = out_png[:-4] if out_png.lower().endswith(".png") else out_png
    # -cropbox: draw the sheet as shown; by default pdftoppm draws the whole media box, which shifts every crop
    subprocess.run(["pdftoppm", "-cropbox", "-f", str(page), "-l", str(page), "-r", str(dpi), "-x", str(x), "-y", str(y),
                    "-W", str(w), "-H", str(h), "-png", "-singlefile", pdf, stem], check=True, stderr=subprocess.DEVNULL)

def mark(png, tags, dpi, origin):
    """Box the tags tag_count.py found on a rendered tile: red for one counted on the plan, blue for one seen
    in a schedule, a list or a note and not counted. A tag with no box was not counted by the script."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        sys.exit("--mark needs the Pillow library, which is not installed. The tiles were written without boxes.")
    im = Image.open(png).convert("RGB")
    draw, k = ImageDraw.Draw(im), dpi / 72
    for t in tags:
        box = (round(t["x0"] * k) - origin[0] - 3, round(t["y0"] * k) - origin[1] - 3,
               round(t["x1"] * k) - origin[0] + 3, round(t["y1"] * k) - origin[1] + 3)
        draw.rectangle(box, outline=(229, 72, 77) if t["where"] == "plan" else (62, 99, 221), width=2)
    im.save(png)

if __name__ == "__main__":
    if len(sys.argv) < 4: sys.exit(__doc__)
    pdf, page, outdir = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    dpi, tiles, ov = int(arg("--dpi", "100")), arg("--tiles", "auto"), float(arg("--overlap", "0.08"))
    os.makedirs(outdir, exist_ok=True)
    W, H = sheet_pixels(pdf, page, dpi)
    crop = tuple(float(v) for v in arg("--crop", "").split(",")) if "--crop" in sys.argv else None
    boxes = [(t["row"], t["col"], t["box"][0], t["box"][1], t["box"][2] - t["box"][0], t["box"][3] - t["box"][1],
              t["core"]) for t in plan_boxes(W, H, tiles, ov, crop)]
    marks = None
    if "--mark" in sys.argv:
        import json
        marks = [t for p in json.load(open(arg("--mark", "")))["pages"] if p["page"] == page for t in p["tags"]]
    for r, c, x, y, w, h, core in boxes:
        out = os.path.join(outdir, f"p{page}_dpi{dpi}_r{r}c{c}_x{x}_y{y}.png")
        render(pdf, page, dpi, (x, y, w, h), out)
        if marks is not None:
            mark(out, marks, dpi, (x, y))
        # the core in the tile's own pixels: count a symbol only in the tile whose core contains it
        inside = f"  core {core[0] - x},{core[1] - y} to {core[2] - x},{core[3] - y}" if core else ""
        print(out, f"origin {x},{y}", f"{w}x{h}px", f'1px = {72/dpi:.3f}pt' + inside,
              "  WARNING: over 1900 px, will be shrunk when read" if max(w, h) > 1900 else "")
