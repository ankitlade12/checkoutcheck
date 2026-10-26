import argparse
import json
import sys
from pathlib import Path

from .evaluator import canonical, compare, digest, score, validate_suite


def read(path):
    path = Path(path)
    if path.stat().st_size > 10_000_000:
        raise ValueError("JSON inputs must be at most 10 MB")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(path.read_text(), object_pairs_hook=unique,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError(f"Invalid number: {v}")))


def main():
    parser = argparse.ArgumentParser(description="CheckoutCheck offline evaluator")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Validate and hash a frozen suite")
    validate.add_argument("suite")
    evaluate = commands.add_parser("score", help="Score imported predictions")
    evaluate.add_argument("suite")
    evaluate.add_argument("predictions")
    evaluate.add_argument("--output")
    comparison = commands.add_parser("compare", help="Compare predictions on the exact same suite")
    comparison.add_argument("suite")
    comparison.add_argument("baseline")
    comparison.add_argument("candidate")
    comparison.add_argument("--output")
    export = commands.add_parser("export", help="Export a self-contained scoring bundle (no media)")
    export.add_argument("suite")
    export.add_argument("predictions")
    export.add_argument("directory")
    verify = commands.add_parser("verify", help="Reproduce an exported scoring bundle")
    verify.add_argument("directory")
    args = parser.parse_args()
    try:
        if args.command == "verify":
            directory = Path(args.directory)
            result = score(read(directory / "suite.json"), read(directory / "predictions.json"))
            if canonical(result) != canonical(read(directory / "report.json")):
                raise ValueError("Report does not reproduce with this evaluator and these inputs")
            print("Verified: report reproduced exactly")
            return 0
        suite = read(args.suite)
        validate_suite(suite)
        if args.command == "validate":
            print(digest(suite))
            return 0
        if args.command == "compare":
            result = compare(suite, read(args.baseline), read(args.candidate))
        else:
            predictions = read(args.predictions)
            result = score(suite, predictions)
        if args.command == "export":
            if any(not c["rights_valid"] for c in suite["cases"]):
                raise ValueError("Export blocked: suite contains cases without valid evaluation rights")
            directory = Path(args.directory)
            directory.mkdir(parents=True, exist_ok=False)
            for name, value in (("suite", suite), ("predictions", predictions), ("report", result)):
                (directory / f"{name}.json").write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
            (directory / "README.txt").write_text(
                "Private scoring bundle; contains reference annotations. No publication rights inferred.\n"
                "Requires CheckoutCheck 0.1.0 and Python 3.11+. From its repository run:\n"
                "python3 -m checkoutcheck verify /path/to/this/bundle\n"
                "This reproduces scoring of imported predictions, not video inference.\n")
            print(f"Exported {directory}")
        else:
            output = json.dumps(result, indent=2, allow_nan=False) + "\n"
            if args.output:
                Path(args.output).write_text(output)
            else:
                print(output, end="")
        return 0
    except (ValueError, OSError, TypeError, RecursionError) as error:
        print(f"checkoutcheck: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
