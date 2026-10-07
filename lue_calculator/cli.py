"""Portable command-line entry point for the public LUEFlow release."""
import argparse
import json
from dataclasses import asdict
from pathlib import Path
from .avt import AVTEngine
from .lue import LUEEngine
from .data_parser import parse_performance_file

def main(argv=None):
    parser = argparse.ArgumentParser(description="LUEFlow: weighted spectral AVT and LUE")
    parser.add_argument("spectrum", type=Path)
    parser.add_argument("--performance", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not args.spectrum.is_file():
        parser.error("spectrum file does not exist")
    result = {mode: asdict(value) for mode, value in AVTEngine().calculate_both_from_file(str(args.spectrum), return_details=True).items()}
    if args.performance:
        performance = parse_performance_file(str(args.performance))
        result["performance"] = performance
        result["lue_percent"] = {mode: LUEEngine().calculate(result[mode]["avt"], performance["pce"]) for mode in ("human", "plant")}
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
