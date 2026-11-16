"""Tests for render_sheet.py's tile arithmetic. Run: python3 -m pytest -q"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import render_sheet as rs  # noqa: E402


@pytest.mark.parametrize("size, grid", [((5400, 3600), (4, 3)), ((1500, 1000), (1, 1)), ((6300, 4500), (4, 3)),
                                        ((1638, 1638), (1, 1)), ((1639, 1000), (2, 1))])
def test_the_tile_grid_keeps_every_tile_within_1900_pixels(size, grid):
    assert rs.tile_grid(*size) == grid
    cols, rows = grid
    assert int(size[0] / cols * 1.16) <= 1900 and int(size[1] / rows * 1.16) <= 1900


def test_tile_cores_cover_the_sheet_exactly_once():
    W, H = 5401, 3601                                   # odd sizes: no pixel may be lost to rounding
    boxes = rs.tile_boxes(W, H, *rs.tile_grid(W, H))
    assert len(boxes) == 12 and boxes[0]["core"][:2] == (0, 0) and boxes[-1]["core"][2:] == (W, H)
    assert sum((c[2] - c[0]) * (c[3] - c[1]) for c in (b["core"] for b in boxes)) == W * H
    for a in boxes:
        ax0, ay0, ax1, ay1 = a["core"]
        bx0, by0, bx1, by1 = a["box"]
        assert 0 <= bx0 <= ax0 < ax1 <= bx1 <= W and 0 <= by0 <= ay0 < ay1 <= by1 <= H
        for b in boxes:
            if a is not b:
                cx0, cy0, cx1, cy1 = b["core"]
                assert ax1 <= cx0 or cx1 <= ax0 or ay1 <= cy0 or cy1 <= ay0


def test_a_crop_with_tiles_is_cut_into_tiles_within_1900_pixels(tmp_path):
    """Baseline eval 2026-11-15: --crop with --tiles gave one oversize image."""
    import subprocess
    pytest.importorskip("reportlab")
    from PIL import Image
    from reportlab.pdfgen.canvas import Canvas
    pdf = tmp_path / "sheet.pdf"
    c = Canvas(str(pdf), pagesize=(1224, 792))           # 17 x 11 in
    c.drawString(100, 700, "M-1")
    c.save()
    out = tmp_path / "tiles"
    # the right 60% of the sheet at 300 dpi is about 3060 x 3300 px: too big for one image
    r = subprocess.run([sys.executable, str(Path(__file__).parent / "render_sheet.py"), str(pdf), "1", str(out),
                        "--dpi", "300", "--crop", "0.4,0,0.6,1", "--tiles", "auto"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    pngs = sorted(out.glob("*.png"))
    assert len(pngs) > 1 and "WARNING" not in r.stdout
    for p in pngs:
        assert max(Image.open(p).size) <= 1900, p.name
    # every tile sits inside the crop, and its filename origin is in sheet pixels
    x0 = int(0.4 * 1224 * 300 / 72)
    assert all(int(p.stem.split("_x")[1].split("_")[0]) >= x0 for p in pngs)


def test_crop_tiles_cover_the_crop_exactly_once():
    W, H = 5100, 3300
    crop = (0.4, 0.1, 0.6, 0.8)
    tiles = rs.plan_boxes(W, H, "auto", 0.08, crop)
    cx, cy, cw, ch = int(0.4 * W), int(0.1 * H), int(0.6 * W), int(0.8 * H)
    assert sum((t["core"][2] - t["core"][0]) * (t["core"][3] - t["core"][1]) for t in tiles) == cw * ch
    for t in tiles:
        bx0, by0, bx1, by1 = t["box"]
        assert cx <= bx0 < bx1 <= cx + cw and cy <= by0 < by1 <= cy + ch
        assert max(bx1 - bx0, by1 - by0) <= 1900
