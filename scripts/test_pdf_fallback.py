"""Tests for the PDF backend choice in plan_index.py and render_sheet.py.
The pdfium tests need pypdfium2 and Pillow; run them with
  uv run --with pypdfium2 --with pillow --with pytest --with reportlab python -m pytest <this file> -q
where pypdfium2 is not installed."""
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import plan_index as pi  # noqa: E402
import render_sheet as rs  # noqa: E402


@pytest.fixture
def pdf(tmp_path):
    from reportlab.pdfgen.canvas import Canvas
    path = tmp_path / "plans.pdf"
    c = Canvas(str(path), pagesize=(1224, 792))            # 17 x 11 in
    for sheet in ("P-101", "M-201"):
        c.setFont("Helvetica", 14)
        c.drawString(72, 700, "PLUMBING FLOOR PLAN  FIXTURE SCHEDULE")
        c.drawString(1050, 60, sheet)                      # title block, bottom right
        c.showPage()
    c.save()
    return str(path)


def need(backend):
    """Skip a test whose backend is not on this machine: poppler's command-line tools, or the pypdfium2 library."""
    if backend == "pdfium":
        pytest.importorskip("pypdfium2")
    elif not all(pi.shutil.which(t) for t in ("pdfinfo", "pdftotext", "pdftoppm")):
        pytest.skip("poppler is not installed")


def png_size(path):
    data = Path(path).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_backend_falls_back_when_poppler_is_missing(monkeypatch):
    need("poppler")
    assert pi.pdf_backend() == "poppler"
    monkeypatch.setattr(pi.shutil, "which", lambda name: None)
    assert pi.pdf_backend() == "pdfium"


@pytest.mark.parametrize("backend", ["poppler", "pdfium"])
def test_page_facts_agree_across_backends(pdf, backend):
    need(backend)
    assert pi.page_count(pdf, backend) == 2
    assert pi.page_size(pdf, 1, backend) == pytest.approx((1224, 792), abs=1)
    assert "FIXTURE SCHEDULE" in pi.page_text(pdf, 1, backend)
    block = pi.page_text(pdf, 2, backend, crop=(1224 * .78, 792 * .55, 1224 * .22, 792 * .45))
    assert "M-201" in block and "SCHEDULE" not in block


@pytest.mark.parametrize("backend", ["poppler", "pdfium"])
def test_index_finds_sheets_on_either_backend(pdf, backend, monkeypatch):
    need(backend)
    monkeypatch.setattr(pi, "pdf_backend", lambda: backend)
    rows = pi.index(pdf)
    assert [r["sheet"] for r in rows] == ["P101", "M201"] and rows[0]["discipline"] == "Plumbing" and "SCHEDULE" in rows[0]["hints"]


@pytest.mark.parametrize("backend", ["poppler", "pdfium"])
def test_render_box_has_the_asked_size(pdf, backend, tmp_path):
    need(backend)
    if backend == "pdfium":
        pytest.importorskip("PIL")
    out = tmp_path / f"{backend}.png"
    rs.render(pdf, 1, 100, (200, 100, 600, 400), str(out), backend)      # x, y, w, h in pixels at 100 dpi
    assert png_size(out) == (600, 400)


def raw_pdf(path, box=(0, 0, 1224, 792), rotate=0, texts=(), crop=None, upright=False):
    """A one-page PDF written by hand, so the page box can start away from 0,0 and the page can be rotated.
    texts = [(x, y, words)] or [(x, y, words, size)] in the page's own coordinates (before rotation, measured
    from the PDF origin), drawn in the order given; size defaults to 14 pt, and a fifth item "a b c d" turns that
    text. crop sets a CropBox. upright turns all text with a page rotated 90 degrees so it reads left to right on
    screen, as a plotted sheet's text does."""
    tm = "0 1 -1 0" if upright else "1 0 0 1"
    full = [tuple(t) + (14, tm)[len(t) - 3:] for t in texts]
    stream = b"BT " + b" ".join(f"/F1 {s} Tf {m} {x} {y} Tm ({t}) Tj".encode() for x, y, t, s, m in full) + b" ET"
    cropbox = f"/CropBox [{crop[0]} {crop[1]} {crop[2]} {crop[3]}] " if crop else ""
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            f"<< /Type /Page /Parent 2 0 R /MediaBox [{box[0]} {box[1]} {box[2]} {box[3]}] {cropbox}/Rotate {rotate} "
            "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>".encode(),
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    Path(path).write_bytes(out)
    return str(path)


@pytest.mark.parametrize("backend", ["poppler", "pdfium"])
def test_title_block_is_found_when_the_page_box_does_not_start_at_zero(tmp_path, backend):
    need(backend)
    # the sheet is 1224 x 792 but its box starts at (300, 200), as plotted sheets often do
    f = raw_pdf(tmp_path / "offset.pdf", box=(300, 200, 1524, 992), texts=[(372, 900, "FIXTURE SCHEDULE"), (1350, 260, "M-201")])
    assert pi.page_size(f, 1, backend) == pytest.approx((1224, 792), abs=1)
    block = pi.page_text(f, 1, backend, crop=(1224 * .78, 792 * .55, 1224 * .22, 792 * .45))
    assert "M-201" in block and "SCHEDULE" not in block


@pytest.mark.parametrize("backend", ["poppler", "pdfium"])
def test_title_block_is_found_on_a_rotated_page(tmp_path, backend):
    need(backend)
    # stored tall (792 x 1224) and turned 90 degrees to show wide; a point shown at (X, Y from the top) is stored at (Y, X)
    f = raw_pdf(tmp_path / "rot.pdf", box=(0, 0, 792, 1224), rotate=90, texts=[(740, 1050, "M-201"), (100, 80, "FIXTURE SCHEDULE")])
    assert pi.page_size(f, 1, backend) == pytest.approx((1224, 792), abs=1)
    block = pi.page_text(f, 1, backend, crop=(1224 * .78, 792 * .55, 1224 * .22, 792 * .45))
    assert "M-201" in block and "SCHEDULE" not in block


def test_a_project_number_is_not_taken_for_a_sheet_number():
    assert pi.SHEET.findall("PROJECT NO. P12-3456") == [] and pi.SHEET.findall("JOB M12-3456 REV 2") == []
    assert ["".join(m) for m in pi.SHEET.findall("SHEET P-101 OF 13")] == ["P101"]
    assert ["".join(m) for m in pi.SHEET.findall("M2.1  A-101.1")] == ["M2.1", "A101"]


def test_a_zip_in_a_folder_that_cannot_be_written_is_unpacked_elsewhere(tmp_path, pdf):
    import os
    import zipfile
    ro = tmp_path / "uploads"
    ro.mkdir()
    with zipfile.ZipFile(ro / "set.zip", "w") as z:
        z.write(pdf, "plans.pdf")
    os.chmod(ro, 0o555)
    try:
        found = pi.pdfs(str(ro / "set.zip"))
    finally:
        os.chmod(ro, 0o755)
    assert len(found) == 1 and os.path.isfile(found[0]) and not found[0].startswith(str(ro))


@pytest.fixture
def busy_title_blocks(tmp_path):
    """Title blocks as real sets draw them: the sheet number is the large text, with a revision row, a note that
    names another sheet and a detail tag in small text around it, in no helpful order."""
    from reportlab.pdfgen.canvas import Canvas
    path = tmp_path / "busy.pdf"
    c = Canvas(str(path), pagesize=(1224, 792))
    c.setFont("Helvetica-Bold", 40); c.drawString(1050, 120, "M-601")           # drawn first
    c.setFont("Helvetica", 8)
    c.drawString(1000, 300, "REFER TO SHEET E-601 FOR POWER SUPPLY")
    c.drawString(1000, 250, "A 01-15-2024 DESIGN DEVELOPMENT")                   # a revision row, drawn last
    c.showPage()
    c.setFont("Helvetica-Bold", 40); c.drawString(1080, 120, "P1")
    c.setFont("Helvetica", 8); c.drawString(1000, 40, "SEE DETAIL P-5")          # small text below the number
    c.showPage()
    c.save()
    return str(path)


@pytest.mark.parametrize("backend", ["poppler", "pdfium"])
def test_the_sheet_number_is_the_large_text_in_the_title_block(busy_title_blocks, backend, monkeypatch):
    need(backend)
    monkeypatch.setattr(pi, "pdf_backend", lambda: backend)
    assert [r["sheet"] for r in pi.index(busy_title_blocks)] == ["M601", "P1"]


# Title blocks as plan sets draw them, drawn small, with the sheet number drawn large in its box at the bottom right.
# pdfium hands text back in the order it was drawn and poppler in reading order, so each is drawn both ways.
# x, y are on a 1224 x 792 sheet measured from the bottom-left; the title block is x > 955, y < 356.
REVISION_DATE = [(980, 150, "NO. DATE DESCRIPTION", 7), (980, 140, "A 01-15-2024 DESIGN DEVELOPMENT", 7),
                 (980, 130, "0 2024-03-01 ISSUED FOR PERMIT", 7), (1100, 80, "SHEET", 7)]
CROSS_REFERENCE = [(1100, 80, "SHEET", 7), (980, 200, "REFER MECHANICAL EQUIPMENT SCHEDULE ON", 7),
                   (980, 191, "SHEET E-601 FOR REQUIRED POWER SUPPLY", 7)]


@pytest.mark.parametrize("backend", ["poppler", "pdfium"])
@pytest.mark.parametrize("number_drawn", ["first", "last"])
@pytest.mark.parametrize("notes, number, sheet, trade", [(REVISION_DATE, "A-701", "A701", "Architectural"),
                                                         (CROSS_REFERENCE, "M-601", "M601", "Mechanical")],
                         ids=["revision-date", "cross-reference"])
def test_sheet_number_beats_dates_and_notes_in_the_title_block(tmp_path, monkeypatch, backend, number_drawn, notes, number, sheet, trade):
    need(backend)
    big = [(1100, 40, number, 28)]
    f = raw_pdf(tmp_path / "tb.pdf", texts=big + notes if number_drawn == "first" else notes + big)
    monkeypatch.setattr(pi, "pdf_backend", lambda: backend)
    row = pi.index(f)[0]
    assert (row["sheet"], row["discipline"]) == (sheet, trade)


@pytest.mark.parametrize("backend", ["poppler", "pdfium"])
def test_sheet_number_is_chosen_by_place_and_size_on_a_rotated_page(tmp_path, monkeypatch, backend):
    need(backend)
    # stored tall and turned 90 degrees: a point shown at (X, Y from the top) is stored at (Y, X)
    texts = [(750, 1100, "M-601", 28), (600, 980, "REFER MECHANICAL EQUIPMENT SCHEDULE ON", 7),
             (609, 980, "SHEET E-601 FOR REQUIRED POWER SUPPLY", 7), (100, 80, "FIXTURE SCHEDULE")]
    for order in (texts, texts[::-1]):
        f = raw_pdf(tmp_path / "rot.pdf", box=(0, 0, 792, 1224), rotate=90, texts=order, upright=True)
        monkeypatch.setattr(pi, "pdf_backend", lambda: backend)
        assert pi.index(f)[0]["sheet"] == "M601"


@pytest.mark.parametrize("backend", ["poppler", "pdfium"])
def test_slanted_text_is_not_taken_for_a_sheet_number(tmp_path, monkeypatch, backend):
    need(backend)
    # a site plan's road name running at 45 degrees through the title-block corner ("OAK ROAD S-25");
    # the sheet number itself is drawn as outlines, so there is no text sheet number to find
    f = raw_pdf(tmp_path / "site.pdf", texts=[(1000, 150, "OAK ROAD S-25", 14, "0.7071 0.7071 -0.7071 0.7071"),
                                              (1100, 80, "SHEET", 7)])
    monkeypatch.setattr(pi, "pdf_backend", lambda: backend)
    assert pi.index(f)[0]["sheet"] == ""


def test_a_date_is_not_taken_for_a_sheet_number():
    assert pi.SHEET.findall("A 01-15-2024") == [] and pi.SHEET.findall("REV A 1/15/24") == []
    assert pi.SHEET.findall("E 03.01.2024") == []
    assert ["".join(m) for m in pi.SHEET.findall("A-701  M2.1  P-1.01")] == ["A701", "M2.1", "P1.01"]


@pytest.mark.parametrize("backend", ["poppler", "pdfium"])
def test_text_outside_the_crop_box_is_not_read(tmp_path, monkeypatch, backend):
    need(backend)
    # the stored page is bigger than the sheet shown; E-999 sits off the visible sheet to the right
    f = raw_pdf(tmp_path / "crop.pdf", box=(0, 0, 1524, 992), crop=(0, 0, 1224, 792),
                texts=[(72, 700, "FIXTURE SCHEDULE"), (1100, 60, "M-201", 28), (1400, 60, "E-999", 28)])
    assert pi.page_size(f, 1, backend) == pytest.approx((1224, 792), abs=1)
    block = pi.page_text(f, 1, backend, crop=(1224 * .78, 792 * .55, 1224 * .22, 792 * .45))
    assert "M-201" in block and "E-999" not in block
    monkeypatch.setattr(pi, "pdf_backend", lambda: backend)
    assert pi.index(f)[0]["sheet"] == "M201"


SCHEDULE = [(72, 700, "PLUMBING FIXTURE SCHEDULE", 10), (72, 680, "MARK", 8), (200, 680, "DESCRIPTION", 8), (420, 680, "QTY", 8),
            (72, 668, "WC-1", 8), (200, 668, "WATER CLOSET", 8), (420, 668, "12", 8),
            (72, 656, "LAV-1", 8), (200, 656, "LAVATORY", 8), (420, 656, "10", 8)]


@pytest.mark.parametrize("backend", ["poppler", "pdfium"])
def test_page_text_cli_prints_a_schedule_row_by_row(tmp_path, backend):
    import subprocess
    need(backend)
    # drawn column by column, the way a CAD export often writes a table; the rows must still come out whole
    cols = sorted(SCHEDULE, key=lambda t: (t[0], -t[1]))
    f = raw_pdf(tmp_path / "sched.pdf", texts=cols)
    env = None
    if backend == "pdfium":                            # hide poppler the way a sandbox without it does
        import os
        env = dict(os.environ, PATH=str(tmp_path / "nobin"))
    out = subprocess.run([sys.executable, pi.__file__, f, "--text", "1"], capture_output=True, text=True, env=env)
    assert out.returncode == 0, out.stderr
    lines = [" ".join(l.split()) for l in out.stdout.splitlines() if l.strip()]
    assert "MARK DESCRIPTION QTY" in lines and "WC-1 WATER CLOSET 12" in lines and "LAV-1 LAVATORY 10" in lines
    assert lines.index("MARK DESCRIPTION QTY") < lines.index("WC-1 WATER CLOSET 12") < lines.index("LAV-1 LAVATORY 10")


@pytest.mark.parametrize("backend", ["poppler", "pdfium"])
def test_render_shows_the_sheet_inside_the_crop_box(tmp_path, backend):
    need(backend)
    Image = pytest.importorskip("PIL.Image")
    f = raw_pdf(tmp_path / "crop.pdf", box=(0, 0, 1524, 992), crop=(0, 0, 1224, 792), texts=[(1100, 60, "M-201", 28)])
    assert rs.sheet_pixels(f, 1, 72, backend) == (1224, 792)
    out = tmp_path / f"{backend}.png"
    rs.render(f, 1, 72, (1000, 700, 224, 92), str(out), backend)           # the bottom-right corner, where M-201 is
    ink = Image.eval(Image.open(out).convert("L"), lambda v: 255 - v).getbbox()
    assert ink is not None, "the title-block corner rendered blank"


# ---------------- second review pass ----------------

@pytest.mark.parametrize("backend", ["poppler", "pdfium"])
@pytest.mark.parametrize("page", ["0", "-1", "3", "x", None])
def test_page_text_cli_refuses_a_page_the_set_does_not_have(tmp_path, backend, page):
    import os
    import subprocess
    need(backend)
    f = raw_pdf(tmp_path / "sched.pdf", texts=SCHEDULE)
    env = dict(os.environ, PATH=str(tmp_path / "nobin")) if backend == "pdfium" else None
    out = subprocess.run([sys.executable, pi.__file__, f, "--text"] + ([page] if page is not None else []),
                         capture_output=True, text=True, env=env)
    assert out.returncode != 0 and out.stdout == "" and "Traceback" not in out.stderr
    assert "page" in out.stderr and "1 page" in out.stderr


NOTE_ONLY = [[(980, 200, "REFER TO SHEET E-601 FOR POWER CONNECTIONS.", 7)],
             [(300, 400, "SEE SHEET M-501 FOR DETAILS", 9)],
             [(980, 200, "SEE DETAIL 3 ON SHEET P-401", 7)],
             [(980, 200, "REFER MECHANICAL EQUIPMENT SCHEDULE ON", 7), (980, 191, "SHEET E-601 FOR REQUIRED POWER SUPPLY", 7)]]


@pytest.mark.parametrize("backend", ["poppler", "pdfium"])
@pytest.mark.parametrize("texts", NOTE_ONLY, ids=["refer-to-sheet", "see-sheet", "on-sheet", "note-over-two-lines"])
def test_a_sheet_named_only_in_a_note_is_not_this_sheet(tmp_path, monkeypatch, backend, texts):
    """When the sheet number is drawn as outlines, the only sheet-number text on the page may be one a note points
    to. A blank is right then: a wrong sheet and trade is worse than none."""
    need(backend)
    f = raw_pdf(tmp_path / "note.pdf", texts=texts + [(1100, 80, "SHEET", 7)])
    monkeypatch.setattr(pi, "pdf_backend", lambda: backend)
    assert pi.index(f)[0]["sheet"] == ""


@pytest.mark.parametrize("backend", ["poppler", "pdfium"])
def test_a_sheet_number_under_its_own_label_is_still_found(tmp_path, monkeypatch, backend):
    need(backend)
    f = raw_pdf(tmp_path / "lab.pdf", texts=[(1040, 40, "SHEET: M-201", 12)])
    monkeypatch.setattr(pi, "pdf_backend", lambda: backend)
    assert pi.index(f)[0]["sheet"] == "M201"


def test_a_note_does_not_hide_the_sheet_number_drawn_on_the_same_line():
    w = lambda x, y, text, size: (text, x, y, x + 6 * len(text), y + size)      # noqa: E731
    line = [w(900 + 40 * i, 700, t, 7) for i, t in enumerate("SHEET E-601 FOR REQUIRED POWER SUPPLY".split())]
    assert pi.pick_sheet(line + [w(1200, 684, "M-601", 40)]) == "M601"
    listed = [w(100 + 40 * i, 700, t, 7) for i, t in enumerate("SEE SHEETS M-501 AND M-502".split())]
    assert pi.pick_sheet(listed) == ""
    clipped = [w(100 + 40 * i, 700, t, 7) for i, t in enumerate("E-601 FOR POWER CONNECTIONS.".split())]
    assert pi.pick_sheet(clipped) == ""
