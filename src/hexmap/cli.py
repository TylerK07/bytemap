from __future__ import annotations

import argparse
import os
import sys

from hexmap.app import HexmapApp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hexmap", description="Hexmap binary viewer (Textual)")
    parser.add_argument("path", help="Path to binary file")
    args = parser.parse_args(argv)

    if not os.path.exists(args.path):
        print(f"hexmap: file not found: {args.path}", file=sys.stderr)
        return 2

    app = HexmapApp(args.path)
    app.run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

