"""Tests for measure.py. Run: python3 -m pytest -q"""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import measure as m  # noqa: E402

# a 12 ft dimension drawn 450 px long at 150 dpi: 37.5 px per foot
DOC = {"dpi": 150, "calibration": {"points": [[0, 0], [450, 0]], "feet": 12.0, "dpi": 150},
       "runs": [{"name": "CW main", "size": '3/4"', "sheet": "P-101", "origin": [100, 100],
                 "points": [[0, 0], [375, 0], [375, 750]], "vertical_ft": 9.0}]}


def test_a_run_measures_through_an_importable_function_and_count_is_refused():
    r = m.measure(DOC)
    run = r["runs"][0]
    assert (run["plan_ft"], run["vertical_ft"], run["total_ft"], run["bends"], run["state"]) == (30.0, 9.0, 39.0, 1, "measured")
    assert r["totals"] == [{"size": '3/4"', "system": "CW main", "total_ft": 39.0, "bends": 1}]
    doc = copy.deepcopy(DOC)
    doc["runs"][0]["count"] = 5
    with pytest.raises(ValueError, match="building_count"):
        m.measure(doc)


@pytest.mark.parametrize("text, inches_per_foot", [
    ("1/4", 0.25), ('1/4" = 1\'-0"', 0.25), ('1/8"=1\'-0"', 0.125), ('3/32" = 1\'-0"', 0.09375),
    ('1 1/2" = 1\'-0"', 1.5), ('1" = 20\'', 0.05), ('1"=10\'-0"', 0.1), ("1:48", 0.25), (0.25, 0.25)])
def test_a_scale_is_read_the_way_it_is_written_on_a_drawing(text, inches_per_foot):
    assert m.parse_scale(text) == pytest.approx(inches_per_foot)
    for bad in ("NTS", "", "as noted", '0" = 1\'-0"'):
        with pytest.raises(ValueError, match="Scale"):
            m.parse_scale(bad)


def test_a_calibration_holds_when_the_run_was_traced_at_another_dpi():
    doc = copy.deepcopy(DOC)
    doc["runs"] = [{"name": "HW", "dpi": 300, "points": [[0, 0], [750, 0]]}]      # 750 px at 300 dpi = 375 px at 150 = 10 ft
    assert m.measure(doc)["runs"][0]["total_ft"] == 10.0
    del doc["calibration"]["dpi"]
    with pytest.raises(ValueError, match="dpi"):
        m.measure(doc)


def test_a_run_with_no_calibration_is_not_measured():
    doc = copy.deepcopy(DOC)
    del doc["calibration"]
    doc["scale"] = '1/4" = 1\'-0"'                       # 37.5 px per foot at 150 dpi, but nobody checked a dimension
    r = m.measure(doc)
    run = r["runs"][0]
    assert (run["state"], run["suggested_ft"], run["total_ft"]) == ("not_measured", 39.0, 0.0)
    assert r["totals"] == [] and any("not measured" in s.lower() for s in r["messages"])
    doc["runs"].append({"name": "Riser", "size": '3/4"', "vertical_ft": 12.0})
    assert m.measure(doc)["totals"] == [{"size": '3/4"', "system": "Riser", "total_ft": 12.0, "bends": 0}]
