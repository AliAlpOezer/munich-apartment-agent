"""Serve the dashboard:  python -m apartment_agent.web  [--host H] [--port P]"""

from __future__ import annotations

import argparse
import logging


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the apartment-agent dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    import uvicorn

    from apartment_agent.web.app import default_app

    uvicorn.run(default_app(), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
