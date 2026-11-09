#!/usr/bin/env python3
"""Start the local-first LLM-GYM application."""

from __future__ import annotations

import argparse
import logging

from app.api import create_server
from app.config import Settings, load_env_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: phone-only loopback)")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("Port must be between 0 and 65535")
    load_env_file()
    settings = Settings.from_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = create_server(args.host, args.port, settings)
    shown_port = server.server_address[1]
    print(f"LLM-GYM is running at http://{args.host}:{shown_port}")
    print(f"Database: {settings.database_path}")
    print("Press Ctrl+C to stop. Provider keys are read only from the server environment.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping LLM-GYM")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
