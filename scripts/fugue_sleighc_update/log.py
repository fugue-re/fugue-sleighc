import sys

BLUE = "\033[1;34m"
GREEN = "\033[1;32m"
RED = "\033[1;31m"
YELLOW = "\033[1;33m"
DIM = "\033[2m"
RESET = "\033[0m"


def status(msg: str) -> None:
    print(f"{BLUE}==>{RESET} {msg}", file=sys.stderr, flush=True)


def warn(msg: str) -> None:
    print(f"{YELLOW}warning:{RESET} {msg}", file=sys.stderr, flush=True)


def die(msg: str):
    print(f"{RED}error:{RESET} {msg}", file=sys.stderr, flush=True)
    raise SystemExit(1)
