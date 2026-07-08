#!/usr/bin/env python3
"""draille — unified CLI. Dispatches to the standalone tools.

Usage: draille <init|record|prime|outcome|search|handover|doctor|status|migrate> [args...]
Each subcommand is also a standalone script (draille/<name>.py) — same args.
"""
import sys

from . import record, prime, outcome, migrate, init, search, handover, doctor, status

CMDS = {"record": record.main, "prime": prime.main,
        "outcome": outcome.main, "migrate": migrate.main,
        "init": init.main, "search": search.main, "handover": handover.main,
        "doctor": doctor.main, "status": status.main}


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if len(argv) < 2 or argv[1] not in CMDS:
        sys.stderr.write("usage: draille <%s> [args...]  (each also runs standalone: python3 draille/<name>.py)\n"
                         % "|".join(CMDS))
        return 2
    # sub-mains parse argv[1:], so pass a synthetic argv[0] carrying the subcommand name
    return CMDS[argv[1]](["draille-" + argv[1]] + argv[2:])


if __name__ == "__main__":
    sys.exit(main())
