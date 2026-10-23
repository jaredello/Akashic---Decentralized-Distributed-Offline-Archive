"""Entry point for the frozen DiscKit.app: no arguments opens the desktop app, otherwise acts as the CLI."""

import sys

from disckit.cli import main

if __name__ == "__main__":
    sys.argv = [a for a in sys.argv if not a.startswith("-psn_")]
    main(sys.argv[1:] or ["gui"])
