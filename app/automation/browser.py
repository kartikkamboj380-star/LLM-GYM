"""Optional Playwright runner for websites you own or are permitted to test.

Install requirements-automation.txt before using this module. The core app does not
need Playwright or a browser download.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse


class AutomationError(RuntimeError):
    pass


@dataclass
class ExecutionLog:
    events: list[dict] = field(default_factory=list)

    def add(self, event: str, **details: Any) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "event": event,
            **details,
        }
        self.events.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)

    def write(self, path: str | Path) -> None:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(json.dumps(event, ensure_ascii=False) for event in self.events) + "\n", encoding="utf-8")


@dataclass
class AutomationConfig:
    url: str
    actions: list[dict[str, Any]]
    timeout_seconds: float = 30
    retries: int = 2

    @classmethod
    def from_dict(cls, data: dict) -> "AutomationConfig":
        url = str(data.get("url", ""))
        if urlparse(url).scheme not in {"http", "https"}:
            raise ValueError("Automation URL must use HTTP or HTTPS")
        actions = data.get("actions")
        if not isinstance(actions, list) or not actions:
            raise ValueError("Automation requires a non-empty actions list")
        for action in actions:
            if action.get("type") not in {"wait_for", "fill", "click"}:
                raise ValueError("Allowed actions: wait_for, fill, click")
            if not isinstance(action.get("selector"), str) or not action["selector"].strip():
                raise ValueError("Every automation action needs a selector")
            if action["type"] == "fill" and not isinstance(action.get("value"), str):
                raise ValueError("Fill actions need a string value")
        timeout = float(data.get("timeout_seconds", 30))
        retries = int(data.get("retries", 2))
        if not 1 <= timeout <= 120:
            raise ValueError("Automation timeout must be between 1 and 120 seconds")
        if not 0 <= retries <= 5:
            raise ValueError("Automation retries must be between 0 and 5")
        return cls(url, actions, timeout, retries)

    @classmethod
    def load(cls, path: str | Path) -> "AutomationConfig":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _retry(operation: Callable[[], Any], retries: int, log: ExecutionLog, name: str) -> Any:
    for attempt in range(retries + 1):
        try:
            return operation()
        except Exception as exc:
            log.add("action_error", action=name, attempt=attempt + 1, error_type=type(exc).__name__)
            if attempt >= retries:
                raise
            # This bounded exponential backoff is only for retrying failures. Element
            # readiness itself always uses Playwright's locator wait_for(), not sleep.
            time.sleep(0.25 * (2**attempt))


def run_authorized_flow(config: AutomationConfig) -> ExecutionLog:
    log = ExecutionLog()
    log.add("started", url=config.url, timeout_seconds=config.timeout_seconds, retries=config.retries)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise AutomationError(
            "Playwright is optional. Install requirements-automation.txt and run 'playwright install chromium'."
        ) from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_default_timeout(config.timeout_seconds * 1000)
            _retry(lambda: page.goto(config.url, wait_until="domcontentloaded"), config.retries, log, "navigate")
            log.add("navigated", url=page.url)
            for index, action in enumerate(config.actions):
                action_type = action["type"]
                selector = action["selector"]

                def perform(action_type: str = action_type, selector: str = selector, action: dict = action) -> None:
                    locator = page.locator(selector).first
                    locator.wait_for(state="visible")
                    if action_type == "fill":
                        # Environment expansion keeps test credentials out of config and logs.
                        locator.fill(os.path.expandvars(action["value"]))
                    elif action_type == "click":
                        locator.click()

                _retry(perform, config.retries, log, f"{index}:{action_type}")
                # Never log filled values; they can contain credentials.
                log.add("action_completed", index=index, action=action_type, selector=selector)
            log.add("completed", action_count=len(config.actions))
        except Exception as exc:
            log.add("failed", error_type=type(exc).__name__)
            raise
        finally:
            browser.close()
    return log


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", help="JSON flow for a site you are authorized to test")
    parser.add_argument("--log", help="Optional JSONL execution-log output")
    args = parser.parse_args()
    log = run_authorized_flow(AutomationConfig.load(args.config))
    if args.log:
        log.write(args.log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
