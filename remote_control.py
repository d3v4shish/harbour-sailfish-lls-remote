#!/usr/bin/env python3
"""Minimal LLs vPlayer remote-control HTTP scaffold.

This script exposes the intended control surface but does not control playback
until a real LLs vPlayer adapter is wired in.
"""

import argparse
import hmac
import importlib
import json
import logging
import math
import os
import secrets
import sys
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

VERSION = "0.1.1"
APP_NAME = "llv-remote-control"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8091
MAX_BODY_BYTES = 8192
LOOP_MODES = {"off", "one", "all"}
COMMANDS = {
    "play": "play",
    "pause": "pause",
    "toggle": "toggle",
    "stop": "stop",
    "next": "next",
    "previous": "previous",
    "seek": "seek",
    "loop": "set_loop",
    "volume": "set_volume",
}


class AdapterError(Exception):
    def __init__(self, code, message, http_status=409, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details or {}


class MissingAdapter:
    connected = False

    def _missing(self):
        raise AdapterError(
            "no_adapter",
            "No real LLs vPlayer adapter is connected.",
            503,
            {"adapter_connected": False},
        )

    def get_status(self):
        self._missing()

    def play(self):
        self._missing()

    def pause(self):
        self._missing()

    def toggle(self):
        self._missing()

    def stop(self):
        self._missing()

    def next(self):
        self._missing()

    def previous(self):
        self._missing()

    def seek(self, position_ms=None, delta_ms=None):
        self._missing()

    def set_loop(self, mode):
        self._missing()

    def set_volume(self, level):
        self._missing()


@dataclass
class Config:
    host: str
    port: int
    token: str
    config_path: Path
    log_path: Path
    adapter_module: str = ""
    created: bool = False


def config_path():
    value = os.environ.get("LLS_REMOTE_CONFIG")
    if value:
        return Path(value).expanduser()
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")).expanduser()
    return root / APP_NAME / "config.json"


def log_path():
    value = os.environ.get("LLS_REMOTE_LOG")
    if value:
        return Path(value).expanduser()
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")).expanduser()
    return root / APP_NAME / "remote-control.log"


def parse_port(value):
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise ValueError("invalid port: %r" % (value,))
    if port < 1 or port > 65535:
        raise ValueError("port out of range: %s" % port)
    return port


def write_config(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def secure_config(path):
    """Keep the bearer token from being readable by other local users."""
    try:
        path.chmod(0o600)
    except OSError:
        # This can fail on unusual filesystems.  Starting the service is still
        # preferable to silently replacing an existing user configuration.
        pass


def load_config(args):
    path = Path(args.config).expanduser() if args.config else config_path()
    created = False
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("config must be a JSON object")
        secure_config(path)
    else:
        data = {
            "host": os.environ.get("LLS_REMOTE_HOST", DEFAULT_HOST),
            "port": parse_port(os.environ.get("LLS_REMOTE_PORT", DEFAULT_PORT)),
            "token": secrets.token_urlsafe(32),
            "adapter_module": os.environ.get("LLS_REMOTE_ADAPTER_MODULE", ""),
        }
        write_config(path, data)
        created = True

    host = args.host or os.environ.get("LLS_REMOTE_HOST") or data.get("host") or DEFAULT_HOST
    port = parse_port(args.port or os.environ.get("LLS_REMOTE_PORT") or data.get("port") or DEFAULT_PORT)
    token = args.token or os.environ.get("LLS_REMOTE_TOKEN") or data.get("token")
    if not token:
        raise ValueError("control token is missing")

    adapter_module = (
        args.adapter_module
        or os.environ.get("LLS_REMOTE_ADAPTER_MODULE")
        or data.get("adapter_module")
        or ""
    )
    path_to_log = Path(args.log_file).expanduser() if args.log_file else log_path()
    return Config(str(host), port, str(token), path, path_to_log, str(adapter_module), created)


def rotate_token(path):
    data = {}
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data.update(loaded)
    data["token"] = secrets.token_urlsafe(32)
    data.setdefault("host", os.environ.get("LLS_REMOTE_HOST", DEFAULT_HOST))
    data.setdefault("port", parse_port(os.environ.get("LLS_REMOTE_PORT", DEFAULT_PORT)))
    data.setdefault("adapter_module", os.environ.get("LLS_REMOTE_ADAPTER_MODULE", ""))
    write_config(path, data)
    return data["token"]


def setup_logger(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def load_adapter(config, logger):
    if not config.adapter_module:
        logger.warning("No adapter configured; commands will return no_adapter")
        return MissingAdapter()

    module = importlib.import_module(config.adapter_module)
    if hasattr(module, "create_adapter"):
        return module.create_adapter(
            {
                "host": config.host,
                "port": config.port,
                "config_path": str(config.config_path),
                "log_path": str(config.log_path),
            }
        )
    if hasattr(module, "ADAPTER"):
        return module.ADAPTER
    raise ValueError("adapter module must expose create_adapter(config) or ADAPTER")


def error_body(code, message, details=None, command=None, adapter_connected=None):
    body = {
        "ok": False,
        "error": {"code": code, "message": message, "details": details or {}},
    }
    if command:
        body["command"] = command
    if adapter_connected is not None:
        body["adapter_connected"] = adapter_connected
    return body


class ControlServer(ThreadingHTTPServer):
    def __init__(self, address, config, adapter, logger):
        super().__init__(address, ControlHandler)
        self.config = config
        self.adapter = adapter
        self.logger = logger


class ControlHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path_only()
        if path in ("/discovery", "/.well-known/lls-remote-control.json"):
            self.send_json(200, self.discovery())
            return
        if path == "/control":
            self.send_json(200, self.control_index())
            return
        if path == "/status":
            if self.require_auth():
                self.handle_status()
            return
        self.send_json(404, error_body("not_found", "Unknown endpoint: %s" % path))

    def do_POST(self):
        path = self.path_only()
        if not path.startswith("/control/"):
            self.send_json(404, error_body("not_found", "Unknown endpoint: %s" % path))
            return

        command = path[len("/control/") :]
        if command not in COMMANDS:
            self.send_json(404, error_body("unknown_command", "Unknown command: %s" % command))
            return
        if not self.require_auth():
            return

        try:
            body = self.read_body()
            result = self.run_command(command, body)
        except AdapterError as exc:
            self.server.logger.info("command=%s failed code=%s", command, exc.code)
            self.send_json(
                exc.http_status,
                error_body(exc.code, exc.message, exc.details, command, self.adapter_connected()),
            )
            return
        except ValueError as exc:
            self.send_json(
                400,
                error_body("bad_request", str(exc), command=command, adapter_connected=self.adapter_connected()),
            )
            return
        except Exception as exc:
            self.server.logger.exception("command=%s adapter failure", command)
            self.send_json(
                500,
                error_body(
                    "adapter_failure",
                    "The connected adapter raised an unexpected error.",
                    {"exception": exc.__class__.__name__},
                    command,
                    self.adapter_connected(),
                ),
            )
            return

        self.server.logger.info("command=%s ok", command)
        self.send_json(
            200,
            {
                "ok": True,
                "adapter_connected": self.adapter_connected(),
                "command": command,
                "result": result if result is not None else {},
            },
        )

    def handle_status(self):
        try:
            status = self.call_adapter("get_status")
            self.send_json(200, {"ok": True, "adapter_connected": self.adapter_connected(), "status": status})
        except AdapterError as exc:
            self.server.logger.info("status failed code=%s", exc.code)
            self.send_json(
                exc.http_status,
                error_body(exc.code, exc.message, exc.details, adapter_connected=self.adapter_connected()),
            )
        except Exception as exc:
            self.server.logger.exception("status adapter failure")
            self.send_json(
                500,
                error_body(
                    "adapter_failure",
                    "The connected adapter raised an unexpected error.",
                    {"exception": exc.__class__.__name__},
                    adapter_connected=self.adapter_connected(),
                ),
            )

    def run_command(self, command, body):
        method = COMMANDS[command]
        if command == "seek":
            position_ms = body.get("position_ms")
            delta_ms = body.get("delta_ms")
            if (position_ms is None) == (delta_ms is None):
                raise ValueError("seek requires exactly one of position_ms or delta_ms")
            if position_ms is not None:
                position_ms = parse_non_negative_int("position_ms", position_ms)
            if delta_ms is not None:
                delta_ms = parse_int("delta_ms", delta_ms)
            return self.call_adapter(method, position_ms=position_ms, delta_ms=delta_ms)
        if command == "loop":
            mode = body.get("mode")
            if mode not in LOOP_MODES:
                raise ValueError("loop requires mode to be one of: off, one, all")
            return self.call_adapter(method, mode)
        if command == "volume":
            return self.call_adapter(method, parse_volume(body.get("level")))
        if body:
            raise ValueError("%s does not accept a request body" % command)
        return self.call_adapter(method)

    def call_adapter(self, method, *args, **kwargs):
        func = getattr(self.server.adapter, method, None)
        if not callable(func):
            raise AdapterError("adapter_method_missing", "Adapter does not implement %s." % method, 501)
        result = func(*args, **kwargs)
        return result if result is not None else {}

    def discovery(self):
        base = self.base_url()
        return {
            "service": "lls-vplayer-remote-control",
            "version": VERSION,
            "auth": {"type": "bearer", "header": "Authorization"},
            "adapter_connected": self.adapter_connected(),
            "lls.control_url": base + "/control",
            "lls.status_url": base + "/status",
        }

    def control_index(self):
        base = self.base_url()
        body = self.discovery()
        body["endpoints"] = {
            "status": base + "/status",
            "play": base + "/control/play",
            "pause": base + "/control/pause",
            "toggle": base + "/control/toggle",
            "stop": base + "/control/stop",
            "next": base + "/control/next",
            "previous": base + "/control/previous",
            "seek": base + "/control/seek",
            "loop": base + "/control/loop",
            "volume": base + "/control/volume",
        }
        return body

    def require_auth(self):
        auth = self.headers.get("Authorization", "")
        token = ""
        if auth.startswith("Bearer "):
            token = auth[len("Bearer ") :].strip()
        elif self.headers.get("X-LLS-Control-Token"):
            token = self.headers.get("X-LLS-Control-Token", "").strip()

        if hmac.compare_digest(token, self.server.config.token):
            return True

        self.server.logger.warning("unauthorized path=%s remote=%s", self.path_only(), self.client_address[0])
        self.send_json(
            401,
            error_body("unauthorized", "Missing or invalid control token.", {"auth": "Authorization: Bearer <token>"}),
            {"WWW-Authenticate": "Bearer"},
        )
        return False

    def read_body(self):
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            raise ValueError("invalid Content-Length")
        if length < 0:
            raise ValueError("invalid Content-Length")
        if length > MAX_BODY_BYTES:
            raise ValueError("request body is too large")
        if length == 0:
            return {}

        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("request body must be a JSON object")
        if not isinstance(body, dict):
            raise ValueError("request body must be a JSON object")
        return body

    def adapter_connected(self):
        return bool(getattr(self.server.adapter, "connected", True))

    def base_url(self):
        host = self.headers.get("Host")
        if host:
            return "http://" + host
        return "http://%s:%s" % (self.server.config.host, self.server.config.port)

    def path_only(self):
        path = urlparse(self.path).path.rstrip("/")
        return path or "/"

    def send_json(self, status, body, headers=None):
        payload = json.dumps(body, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        self.server.logger.info("http %s - %s", self.address_string(), fmt % args)


def parse_int(name, value):
    if isinstance(value, bool):
        raise ValueError("%s must be an integer" % name)
    if isinstance(value, float) and not value.is_integer():
        raise ValueError("%s must be an integer" % name)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError("%s must be an integer" % name)


def parse_non_negative_int(name, value):
    parsed = parse_int(name, value)
    if parsed < 0:
        raise ValueError("%s must be >= 0" % name)
    return parsed


def parse_volume(value):
    if isinstance(value, bool):
        raise ValueError("volume requires level between 0.0 and 1.0")
    try:
        level = float(value)
    except (TypeError, ValueError):
        raise ValueError("volume requires level between 0.0 and 1.0")
    if not math.isfinite(level) or level < 0.0 or level > 1.0:
        raise ValueError("volume requires level between 0.0 and 1.0")
    return level


def serve(config):
    logger = setup_logger(config.log_path)
    adapter = load_adapter(config, logger)
    server = ControlServer((config.host, config.port), config, adapter, logger)
    base = "http://%s:%s" % (config.host, config.port)
    logger.info("starting on %s", base)
    print_startup(config, base)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        logger.info("stopping after keyboard interrupt")
    finally:
        server.server_close()


def print_startup(config, base):
    if config.created:
        print("Created config: %s" % config.config_path)
    print("LLs vPlayer remote-control prototype")
    print("Real playback control requires a connected LLs vPlayer adapter.")
    print("Discovery: %s/discovery" % base)
    print("Control: %s/control" % base)
    print("Status: %s/status" % base)
    print("Config: %s" % config.config_path)
    print("Log: %s" % config.log_path)


def build_parser():
    parser = argparse.ArgumentParser(
        description="LLs vPlayer remote-control scaffold. Commands return no_adapter until a real adapter is connected."
    )
    parser.add_argument("--host", help="bind host, default from config or %s" % DEFAULT_HOST)
    parser.add_argument("--port", help="bind port, default from config or %s" % DEFAULT_PORT)
    parser.add_argument("--token", help="runtime token override; LLS_REMOTE_TOKEN also works")
    parser.add_argument("--config", help="config path; LLS_REMOTE_CONFIG also works")
    parser.add_argument("--log-file", help="log path; LLS_REMOTE_LOG also works")
    parser.add_argument("--adapter-module", help="module exposing create_adapter(config) or ADAPTER")
    parser.add_argument("--show-paths", action="store_true", help="print config/log paths and exit")
    parser.add_argument("--show-token", action="store_true", help="print token and exit")
    parser.add_argument("--rotate-token", action="store_true", help="rotate saved token and exit")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.rotate_token:
            path = Path(args.config).expanduser() if args.config else config_path()
            print(rotate_token(path))
            print("config=%s" % path)
            return 0

        config = load_config(args)
        if args.show_paths:
            print("config=%s" % config.config_path)
            print("log=%s" % config.log_path)
            return 0
        if args.show_token:
            print(config.token)
            return 0

        serve(config)
        return 0
    except Exception as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
