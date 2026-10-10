"""CLI for long-result conversion and original-job backfill."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.outputs.sqlite_store import import_source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--mode", choices=["long", "raw-jobs"], default="long")
    parser.add_argument("--month", help="Only supplies a missing month; does not replace a source value")
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        result = import_source(args.input, args.db, mode=args.mode, month=args.month,
                               batch_size=args.batch_size, overwrite=args.overwrite)
    except Exception as exc:
        parser.exit(1, f"Import failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
