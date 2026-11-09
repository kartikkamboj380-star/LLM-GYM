"""Run an authorized browser flow against a fresh, temporary local demo server."""

from __future__ import annotations

import argparse
import tempfile
import threading
from pathlib import Path

from app.api import create_server
from app.config import Settings

from .browser import AutomationConfig, run_authorized_flow


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", help="Local-demo JSON flow")
    parser.add_argument("--log", help="Optional sanitized JSONL report")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="llm-gym-e2e-") as directory:
        root = Path(directory)
        server = create_server("127.0.0.1", 0, Settings(data_dir=root, database_path=root / "e2e.db"))
        # Deterministic only on this isolated E2E server; the normal demo stays random.
        server.app.demo.code_factory = lambda: "654321"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config = AutomationConfig.load(args.config)
            config.url = config.url.replace("127.0.0.1:8000", f"127.0.0.1:{server.server_address[1]}")
            log = run_authorized_flow(config)
            if args.log:
                log.write(args.log)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
    print(f"Browser E2E passed: {args.config}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
