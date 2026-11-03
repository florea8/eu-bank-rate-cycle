import argparse
import logging
import sys

from bankcycle import db
from bankcycle.ingest import eba, ecb
from bankcycle.logging_conf import log_step, setup_logging
from bankcycle.settings import get_settings

log = logging.getLogger("bankcycle")


def cmd_db_check(args: argparse.Namespace) -> None:
    s = get_settings()
    with log_step(log, "db-check"):
        if not db.is_up():
            raise RuntimeError(f"PostgreSQL not reachable at {s.pghost}:{s.pgport}/{s.pgdatabase}")


INGEST_SOURCES = ["eba", "ecb"]


def cmd_ingest(args: argparse.Namespace) -> None:
    sources = args.sources or INGEST_SOURCES
    if "eba" in sources:
        eba.run(force=args.force)
    if "ecb" in sources:
        ecb.run()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bankcycle")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("db-check", help="check that PostgreSQL answers")
    p.set_defaults(func=cmd_db_check)

    p = sub.add_parser("ingest", help="download source data and load it into the raw schema")
    p.add_argument("sources", nargs="*", choices=INGEST_SOURCES, help="default: all")
    p.add_argument("--force", action="store_true", help="re-download EBA files already on disk")
    p.set_defaults(func=cmd_ingest)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging()
    try:
        args.func(args)
    except Exception as exc:
        log.error("%s: %s", args.command, exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
