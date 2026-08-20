"""HeatOps CLI — run a plain-language heat brief end to end.

Usage:
    python cli.py "Find the hottest of these 5 bus stops in Phoenix at 2pm
                   on 2025-07-15 and recommend which to shade first"
"""

import json
import sys

from heatops.agent import HeatOpsAgent


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    brief = " ".join(sys.argv[1:])

    agent = HeatOpsAgent()
    print(f"\n=== BRIEF ===\n{brief}\n\n=== AGENT RUN ===")
    answer = agent.run(brief)
    print(f"\n=== FINAL ANSWER ===\n{answer}")
    print("\n=== AUDIT TRAIL ===")
    print(json.dumps(agent.audit_trail, indent=2))


if __name__ == "__main__":
    main()
