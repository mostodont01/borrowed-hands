"""Command line entry point (`hands`)."""

import argparse

from borrowed_hands import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hands", description=__doc__)
    parser.add_argument("--version", action="version", version=f"hands {__version__}")
    parser.parse_args(argv)
    parser.print_help()
    return 0
