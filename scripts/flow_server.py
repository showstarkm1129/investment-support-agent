#!/usr/bin/env python3
"""Local UI server for running and editing flow scripts."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
FLOW_SCRIPT_DIR = ROOT / "system" / "config" / "flow_scripts"
AUTO_SEARCH_PATH = ROOT / "system" / "config" / "auto_search.example.json"
SCRIPT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
JST = timezone(timedelta(hours=9))
PROVIDERS = {"manual", "codex", "claude", "openai_api", "anthropic_api", "gemini_api"}
MODES = {"prepare", "dry-run", "simulate", "live"}


def today_jst() -> str:
    return datetime.now(JST).date().isoformat()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def script_path(script_id: str) -> Path:
    if not SCRIPT_ID_RE.match(script_id):
        raise ValueError("script_id must contain lowercase letters, numbers, hyphen, or underscore")
    return FLOW_SCRIPT_DIR / f"{script_id}.json"


def script_summary(path: Path) -> dict[str, Any]:
    script = load_json(path)
    target = script.get("target", {}) if isinstance(script, dict) else {}
    return {
        "script_id": script.get("script_id", path.stem),
        "display_name": script.get("display_name", path.stem),
        "description": script.get("description", ""),
        "flow": script.get("flow", ""),
        "provider": script.get("provider", "manual"),
        "model": script.get("model", "default"),
        "mode": script.get("mode", "prepare"),
        "depth": script.get("depth", "normal"),
        "target_id": target.get("target_id", ""),
        "target_type": target.get("target_type", ""),
        "themes": target.get("themes", []),
    }


def list_scripts() -> list[dict[str, Any]]:
    FLOW_SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    return [script_summary(path) for path in sorted(FLOW_SCRIPT_DIR.glob("*.json"))]


class FlowHandler(SimpleHTTPRequestHandler):
    server_version = "FlowScriptServer/1.0"

    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_json_body(self) -> Any:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        data = self.rfile.read(length).decode("utf-8")
        return json.loads(data)

    def send_error_json(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        self.send_json({"ok": False, "error": message}, status=status)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/scripts":
            self.send_json({"ok": True, "scripts": list_scripts()})
            return
        if path.startswith("/api/scripts/"):
            script_id = unquote(path.rsplit("/", 1)[1])
            try:
                path_obj = script_path(script_id)
                if not path_obj.exists():
                    self.send_error_json("script not found", HTTPStatus.NOT_FOUND)
                    return
                self.send_json({"ok": True, "script": load_json(path_obj)})
            except ValueError as exc:
                self.send_error_json(str(exc))
            return
        if path == "/api/automation":
            payload = load_json(AUTO_SEARCH_PATH) if AUTO_SEARCH_PATH.exists() else {"schema_version": "auto_search_config_v1", "timezone": "Asia/Tokyo", "routes": []}
            self.send_json({"ok": True, "automation": payload})
            return
        if path == "/":
            self.path = "/flow_builder.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            body = self.read_json_body()
        except json.JSONDecodeError as exc:
            self.send_error_json(f"invalid JSON: {exc}")
            return

        if parsed.path == "/api/run":
            self.api_run(body)
            return
        if parsed.path == "/api/scripts":
            self.api_save_script(body)
            return
        if parsed.path == "/api/automation":
            self.api_save_automation(body)
            return
        self.send_error_json("unknown endpoint", HTTPStatus.NOT_FOUND)

    def api_run(self, body: Any) -> None:
        if not isinstance(body, dict):
            self.send_error_json("request body must be an object")
            return
        script_id = str(body.get("script_id") or "")
        provider = str(body.get("provider") or "manual")
        model = str(body.get("model") or "default")
        mode = str(body.get("mode") or "simulate")
        date = str(body.get("date") or today_jst())
        try:
            script_path(script_id)
        except ValueError as exc:
            self.send_error_json(str(exc))
            return
        if provider not in PROVIDERS:
            self.send_error_json("unknown provider")
            return
        if mode not in MODES:
            self.send_error_json("unknown mode")
            return

        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "run_flow.py"),
            "--script",
            script_id,
            "--provider",
            provider,
            "--model",
            model,
            "--mode",
            mode,
            "--date",
            date,
        ]
        result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False, timeout=180)
        self.send_json(
            {
                "ok": result.returncode == 0,
                "returncode": result.returncode,
                "command": cmd,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
            status=HTTPStatus.OK if result.returncode == 0 else HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    def api_save_script(self, body: Any) -> None:
        script = body.get("script") if isinstance(body, dict) and "script" in body else body
        if not isinstance(script, dict):
            self.send_error_json("script must be an object")
            return
        script_id = str(script.get("script_id") or "")
        try:
            path = script_path(script_id)
        except ValueError as exc:
            self.send_error_json(str(exc))
            return
        if script.get("schema_version") != "flow_script_v1":
            self.send_error_json("schema_version must be flow_script_v1")
            return
        if not script.get("display_name") or not script.get("flow") or not script.get("target"):
            self.send_error_json("script must include display_name, flow, and target")
            return
        write_json(path, script)
        self.send_json({"ok": True, "path": str(path.relative_to(ROOT)).replace("\\", "/"), "script": script_summary(path)})

    def api_save_automation(self, body: Any) -> None:
        automation = body.get("automation") if isinstance(body, dict) and "automation" in body else body
        if not isinstance(automation, dict):
            self.send_error_json("automation must be an object")
            return
        automation.setdefault("schema_version", "auto_search_config_v1")
        automation.setdefault("timezone", "Asia/Tokyo")
        automation.setdefault("routes", [])
        write_json(AUTO_SEARCH_PATH, automation)
        self.send_json({"ok": True, "path": str(AUTO_SEARCH_PATH.relative_to(ROOT)).replace("\\", "/"), "automation": automation})


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the local flow builder UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    def handler(*handler_args: Any, **handler_kwargs: Any) -> FlowHandler:
        return FlowHandler(*handler_args, directory=str(APP_DIR), **handler_kwargs)

    server = ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://{args.host}:{args.port}/flow_builder.html"
    print(f"Flow builder: {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
