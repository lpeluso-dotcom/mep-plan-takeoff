"""Tests for tag_count.py (plan tags counted from the PDF's text layer) and render_sheet.py --mark.
The pdfium tests need pypdfium2; run them with
  uv run --with pypdfium2 --with pillow --with pytest --with reportlab python -m pytest <this file> -q
where pypdfium2 is not installed."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import plan_index as pi  # noqa: E402
import tag_count as tc  # noqa: E402

BACKENDS = ["poppler", "pdfium"]


def need(backend):
    if backend == "pdfium":
        pytest.importorskip("pypdfium2")
    elif not all(pi.shutil.which(t) for t in ("pdfinfo", "pdftotext", "pdftoppm")):
        pytest.skip("poppler is not installed")


@pytest.fixture
def pdf(tmp_path):
    """Page 1: a plan with tags, a schedule, a tag list, a labelled row and a note. Page 2: a title block only."""
    from reportlab.pdfgen.canvas import Canvas
    path = tmp_path / "plans.pdf"
    c = Canvas(str(path), pagesize=(1224, 792))
    c.setFont("Helvetica", 8)
    for x, y, s in [(100, 600, "WC-1"), (300, 600, "WC-1"), (100, 400, "WC-1"),      # three on the plan
                    (200, 500, "LAV-1"), (350, 450, "LAV-1"),                        # two on the plan
                    (250, 350, "(FD-1)"),                                            # punctuation round a tag
                    (150, 300, "CRAC-CU-1"),                                         # CU-1 is not in here
                    (400, 300, "EF-1 ON ROOF"),                                      # a plan callout
                    (800, 700, "WC-1"), (835, 700, "WATER CLOSET FLOOR MOUNT"),      # schedule MARK column
                    (800, 688, "LAV-1"), (835, 688, "LAVATORY WALL HUNG"),
                    (800, 676, "FD-1"), (835, 676, "FLOOR DRAIN"),
                    (1000, 500, "HP-1"), (1000, 490, "HP-1"), (1000, 480, "HP-1"),   # one tag stacked tight
                    (600, 200, "EF-1, EF-2"),                                        # a tag list
                    (600, 150, "HB-1 HOSE BIBB"),                                    # a labelled row
                    (600, 100, "PROVIDE WH-1 WITH EXPANSION TANK PER MANUFACTURER")]:  # a note
        c.drawString(x, y, s)
    c.showPage()
    c.setFont("Helvetica", 14)
    c.drawString(1050, 60, "P-102")
    c.showPage()
    c.save()
    return str(path)


def where(result, page=1):
    out = {}
    for t in result["pages"][page - 1]["tags"]:
        out.setdefault(t["tag"], []).append(t["where"])
    return {k: sorted(v) for k, v in out.items()}


@pytest.mark.parametrize("backend", BACKENDS)
def test_plan_tags_are_counted_and_table_cells_are_not(pdf, backend):
    need(backend)
    r = tc.count(pdf, [1], backend=backend)
    w = where(r)
    assert w["WC-1"] == ["plan"] * 3 + ["schedule"]
    assert w["LAV-1"] == ["plan"] * 2 + ["schedule"]
    assert w["FD-1"] == ["plan", "schedule"]                 # "(FD-1)" on the plan, FD-1 in the MARK column
    assert w["EF-1"] == ["plan", "schedule"]                 # "EF-1 ON ROOF" is a callout; "EF-1, EF-2" is a list
    assert w["EF-2"] == ["schedule"]
    assert w["HP-1"] == ["schedule"] * 3                     # the same tag stacked tight is a table column
    assert w["HB-1"] == ["schedule"]                         # "HB-1 HOSE BIBB" is a row, not a callout
    assert w["WH-1"] == ["note"]
    assert "CU-1" not in w                                   # a match inside a longer word is not a tag
    assert r["totals"] == {"WC-1": 3, "LAV-1": 2, "FD-1": 1, "EF-1": 1}
    assert r["pages"][0]["counts"]["WC-1"] == 3 and r["pages"][0]["counted"] is True


@pytest.mark.parametrize("backend", BACKENDS)
def test_asked_tags_are_counted_and_the_rest_are_listed(pdf, backend):
    need(backend)
    r = tc.count(pdf, [1], tags=["wc-1", "UR-1", "CU-1"], backend=backend)
    p = r["pages"][0]
    assert p["counts"] == {"WC-1": 3, "UR-1": 0, "CU-1": 0}      # asked for and not there is a real zero
    assert p["unlisted"] == {"LAV-1": 2, "FD-1": 1, "EF-1": 1}   # on the plan, not asked for
    assert r["totals"] == {"WC-1": 3, "UR-1": 0, "CU-1": 0}


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_page_with_no_text_tags_is_not_counted_and_is_never_a_zero(pdf, backend):
    need(backend)
    r = tc.count(pdf, [1, 2], tags=["WC-1"], backend=backend)
    p2 = r["pages"][1]
    assert p2["counted"] is False and p2["counts"] is None and p2["tags"] == []
    assert r["not_counted"] == [2] and r["totals"] == {"WC-1": 3}
    text = tc.summary(r)
    assert "p2" in text and "not counted" in text and "by eye" in text


def test_pages_are_read_as_a_list_with_ranges():
    assert tc.parse_pages("1,3-5,9", 12) == [1, 3, 4, 5, 9]
    for bad in ("0", "13", "4-2", "x", ""):
        with pytest.raises(SystemExit):
            tc.parse_pages(bad, 12)


def test_command_line_prints_counts_and_writes_the_points(pdf, tmp_path):
    out = tmp_path / "tags.json"
    r = subprocess.run([sys.executable, str(HERE / "tag_count.py"), pdf, "--pages", "1-2", "--tags", "WC-1,LAV-1",
                        "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "WC-1 x3" in r.stdout and "LAV-1 x2" in r.stdout and "not counted" in r.stdout
    assert "left out (in a schedule, a list or a note): WC-1 x1, LAV-1 x1" in r.stdout      # named, so they can be found
    assert "twice" in r.stdout and "floor" not in r.stdout       # two views of one room double a count: not a floor
    saved = json.loads(out.read_text())
    assert saved["totals"] == {"WC-1": 3, "LAV-1": 2}
    box = next(t for t in saved["pages"][0]["tags"] if t["tag"] == "WC-1" and t["where"] == "plan")
    assert 95 < box["x0"] < 105 and 180 < box["y0"] < 200          # points from the top-left: 792 - 600 - text height
    no_pages = subprocess.run([sys.executable, str(HERE / "tag_count.py"), pdf], capture_output=True, text=True)
    assert no_pages.returncode != 0 and "--pages" in no_pages.stderr


def test_render_sheet_marks_the_counted_tags(pdf, tmp_path):
    Image = pytest.importorskip("PIL.Image")
    out = tmp_path / "tags.json"
    json.dump(tc.count(pdf, [1]), open(out, "w"))
    r = subprocess.run([sys.executable, str(HERE / "render_sheet.py"), pdf, "1", str(tmp_path / "t"), "--dpi", "100",
                        "--tiles", "1x1", "--mark", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    im = Image.open(next((tmp_path / "t").glob("*.png"))).convert("RGB")
    saved = json.loads(out.read_text())["pages"][0]["tags"]

    def edge(t):                                                   # the top-left corner of the drawn box
        return im.getpixel((round(t["x0"] * 100 / 72) - 3, round(t["y0"] * 100 / 72) - 3))
    plan = next(t for t in saved if t["tag"] == "WC-1" and t["where"] == "plan")
    cell = next(t for t in saved if t["tag"] == "HP-1")
    assert edge(plan) == (229, 72, 77)                             # red: counted on the plan
    assert edge(cell) == (62, 99, 221)                             # blue: seen, and not counted
    assert im.getpixel((round(150 * 100 / 72) - 3, round((792 - 300 - 8) * 100 / 72))) == (255, 255, 255)  # CRAC-CU-1: no box
