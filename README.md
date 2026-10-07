# LUEFlow — 光伏器件光谱与性能数据处理工具链

[![Checks](https://github.com/Ho-boop/lueflow/actions/workflows/tests.yml/badge.svg)](https://github.com/Ho-boop/lueflow/actions/workflows/tests.yml)

An independently developed Python toolchain for weighted transmittance calculations, light-utilization efficiency, and formatted device-performance tables.

## What it does

- Parse instrument-style Abs / %T files, skip peak tables, restore ascending wavelength order, and convert OD×10 values.
- Compute human-response AVT (380–780 nm) and an exploratory plant-response metric (400–700 nm).
- Combine AVT and device PCE into LUE, with formulas and numerator/denominator integrals in a JSON report.
- Provide Tkinter desktop workflows for batch file selection, drag-to-reorder lists, and formatted Excel exports.
- Verify physical bounds, analytic constant-spectrum solutions, tab alignment, units, and end-to-end synthetic examples.

## Quick start

Python 3.10+; the desktop tools need a Python installation with Tkinter (normally included with python.org Windows installers).

```bash
git clone https://github.com/Ho-boop/lueflow.git LUEFlow
cd LUEFlow
python -m pip install -e ".[dev,desktop]"
python -m lue_calculator.cli examples/synthetic_T.txt --performance examples/synthetic_performance.txt --output outputs/report.json
python -m pytest tests -q
python interactive_launcher.py
python opv_performance_tool.py
```

The installed `lueflow` command accepts the same arguments. A 50% constant spectrum with synthetic PCE=12% produces AVT=50% and LUE=6% in both modes. Examples are generated fixtures; no measured devices or private research files are distributed.

See the generated [synthetic JSON report](docs/synthetic-report.json), including the integration terms and unit-normalized performance values.

## Architecture

`data_parser.py` handles instrument text and unit conversions; `spectra.py` provides tabulated/interpolated reference curves; `avt.py` integrates spectra; `lue.py` handles derived results and reports; `cli.py` exposes a portable public entry point. The package import remains `lue_calculator` for compatibility with the original desktop application.

## AI Coding and validation

The author independently developed the tools using AI-assisted coding, and reviewed outputs against scientific constraints. Typical failure cases were peak tables being treated as spectrum rows, OD×10 being mistaken for raw absorbance, and leading-tab fields being shifted. The public release replaces research-data-dependent checks with reproducible synthetic regression fixtures. See [AI_WORKFLOW.md](AI_WORKFLOW.md).

## Scientific limits

The bundled solar and visual-response tables are coarse tabulations interpolated onto the integration grid; this release does not independently certify their accuracy. The plant-response curve is a manually constructed approximation, suitable for exploratory comparison rather than an absolute published plant metric. Only instrument formats represented by the parser are supported. Abs inputs are interpreted as OD×10; use explicit conversion in the API for other conventions. LUE uses percentage inputs and divides AVT×PCE by 100. MIT covers the author's code; reference curves should be checked against their source standards before scientific publication.
