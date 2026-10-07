from pathlib import Path
import json
import numpy as np
import pytest
from lue_calculator import AVTEngine
from lue_calculator.data_parser import parse_spectrum_file, parse_performance_file
from lue_calculator.cli import main
from opv_performance_tool import OPVDataProcessor, MainApp
from openpyxl import load_workbook

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

@pytest.mark.parametrize("name,mode", [("synthetic_T.txt", "%T"), ("synthetic_abs.txt", "Abs")])
def test_synthetic_instrument_grid_and_modes(name, mode):
    wavelengths, values, actual_mode = parse_spectrum_file(str(EXAMPLES / name))
    assert actual_mode == mode
    assert len(wavelengths) == 295
    assert wavelengths[0] == 306 and wavelengths[-1] == 894
    assert np.all(np.diff(wavelengths) == 2)
    for result in AVTEngine().calculate_both_from_file(str(EXAMPLES / name)).values():
        assert result == pytest.approx(50, abs=1e-8)

def test_tab_alignment_unit_conversion_and_cross_check():
    result = parse_performance_file(str(EXAMPLES / "synthetic_performance.txt"))
    assert result == {"jsc": 20, "voc": .8, "ff": 75, "pce": 12}
    assert result["jsc"] * result["voc"] * result["ff"] / 100 == result["pce"]
    assert OPVDataProcessor.parse_file(str(EXAMPLES / "synthetic_performance.txt"))["pce"] == 12

def test_cli_report_contains_integrals_and_lue(tmp_path):
    output = tmp_path / "report.json"
    assert main([str(EXAMPLES / "synthetic_T.txt"), "--performance", str(EXAMPLES / "synthetic_performance.txt"), "--output", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["human"]["avt"] == pytest.approx(50)
    assert report["human"]["numerator"] / report["human"]["denominator"] == pytest.approx(.5)
    assert report["lue_percent"]["human"] == pytest.approx(6)
    assert report["lue_percent"]["plant"] == pytest.approx(6)

def test_excel_export_preserves_values_without_gui(tmp_path):
    data = OPVDataProcessor.parse_file(str(EXAMPLES / "synthetic_performance.txt"))
    output = tmp_path / "performance.xlsx"
    MainApp._create_excel(None, [data], str(output))
    workbook = load_workbook(output)
    assert list(workbook.active.values)[1] == ("synthetic_performance", 20, .8, 75, 12)
    workbook.close()
