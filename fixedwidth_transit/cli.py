import argparse
import csv
import json
import sys

from . import __version__
from ._files import InputError
from .core import convert


def main(argv=None):
    parser = argparse.ArgumentParser(description="Convert explicit byte layouts and UTF-8 CSV.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("mode", choices=["decode", "encode"])
    parser.add_argument("input")
    parser.add_argument("--layout", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--force", action="store_true", help="replace an existing output on success"
    )
    args = parser.parse_args(argv)
    try:
        result = convert(args.mode, args.layout, args.input, args.output, args.force)
    except (InputError, OSError, UnicodeError, csv.Error) as exc:
        message = (
            str(exc)
            if isinstance(exc, InputError)
            else f"input/output error ({type(exc).__name__})"
        )
        print(json.dumps({"status": "error", "message": message}), file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0
