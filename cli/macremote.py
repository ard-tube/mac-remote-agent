#!/usr/bin/env python3
"""MacRemote's terminal-first host controller and local dashboard."""

from __future__ import annotations

import argparse
import json
import os
import platform
import secrets
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
APP_HOME = SCRIPT_PATH.parent
if not (APP_HOME / "agent.py").is_file() and (APP_HOME.parent / "agent.py").is_file():
    APP_HOME = APP_HOME.parent

if platform.system() == "Darwin":
    DATA_DIR = Path.home() / "Library" / "Application Support" / "MacRemote"
else:
    DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "MacRemote"

PID_FILE = DATA_DIR / "macremote.pid"
LOG_FILE = DATA_DIR / "macremote.log"
AUTH_FILE = DATA_DIR / "dashboard.token"
CONFIG_KEYS = {
    "bot_token",
    "allowed_user_ids",
    "pairing_pin",
    "antigravity_bin",
    "claude_bin",
    "working_directory",
    "relay_url",
    "relay_host_id",
    "relay_host_token",
    "relay_phone_token",
    "keep_awake",
}
HOST = "127.0.0.1"
PORT = 39173
MAX_REQUEST_BYTES = 64 * 1024


def _agent_module():
    if str(APP_HOME) not in sys.path:
        sys.path.insert(0, str(APP_HOME))
    import agent

    return agent


def _atomic_write(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, mode=0o700, exist_ok=True)
    if os.name != "nt":
        os.chmod(DATA_DIR, 0o700)


def _open_private_log():
    _ensure_data_dir()
    descriptor = os.open(LOG_FILE, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
    if os.name != "nt":
        os.fchmod(descriptor, 0o600)
    return os.fdopen(descriptor, "a", encoding="utf-8")


def _runtime_agent_path() -> Path:
    source = APP_HOME / "agent.py"
    target = DATA_DIR / "agent.py"
    content = source.read_text(encoding="utf-8")
    try:
        installed = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        installed = ""
    if installed != content:
        _atomic_write(target, content)
    return target


def _dashboard_token() -> str:
    _ensure_data_dir()
    for _ in range(50):
        try:
            token = AUTH_FILE.read_text(encoding="utf-8").strip()
            if len(token) >= 40:
                if os.name != "nt":
                    os.chmod(AUTH_FILE, 0o600)
                return token
        except FileNotFoundError:
            token = secrets.token_urlsafe(36)
            try:
                descriptor = os.open(AUTH_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                time.sleep(0.01)
                continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                output.write(token)
                output.flush()
                os.fsync(output.fileno())
            return token
        time.sleep(0.01)
    raise RuntimeError(f"Dashboard token file is invalid or could not be initialized: {AUTH_FILE}")


def _pid_command(pid: int) -> str:
    if pid <= 0:
        return ""
    try:
        return subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "command="],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _terminate_agent(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2)


def _service_pid() -> int | None:
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None
    command = _pid_command(pid)
    if str(SCRIPT_PATH) in command and "daemon" in command and "--foreground" in command:
        return pid
    return None


def _dashboard_url() -> str:
    return f"http://{HOST}:{PORT}/"


def _request_json(path: str, token: str, method: str = "GET", data: Any = None) -> Any:
    payload = None if data is None else json.dumps(data).encode("utf-8")
    request = urllib.request.Request(
        f"{_dashboard_url()}{path}",
        data=payload,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def _agent_process_running() -> bool:
    try:
        return bool(_request_json("/api/status", _dashboard_token()).get("agent_running"))
    except (OSError, urllib.error.URLError, ValueError):
        return False


def _dashboard_ready() -> bool:
    try:
        _request_json("/api/status", _dashboard_token())
        return True
    except (OSError, urllib.error.URLError, ValueError):
        return False


def _connection_configured(config: dict[str, Any]) -> bool:
    if str(config.get("bot_token", "")).strip():
        return True
    relay_url = str(config.get("relay_url", "")).strip()
    host_id = str(config.get("relay_host_id", "")).strip()
    host_token = str(config.get("relay_host_token", "")).strip()
    return (
        _valid_relay_url(relay_url)
        and 16 <= len(host_id) <= 64
        and all(character.isascii() and (character.isalnum() or character in "_-") for character in host_id)
        and bool(host_token)
    )


def _start_host_agent(
    config: dict[str, Any], runtime_agent_path: Path, log_handle: Any
) -> subprocess.Popen | None:
    if not _connection_configured(config):
        print(
            "Host connection not configured. Open the dashboard and choose Telegram or a relay.",
            file=log_handle,
            flush=True,
        )
        return None
    try:
        return subprocess.Popen(
            [sys.executable, str(runtime_agent_path)],
            cwd=str(APP_HOME),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as error:
        print(f"Could not start the host agent: {error}", file=log_handle, flush=True)
        return None


def _supervise_host_agent(
    stop_event: threading.Event,
    server: ThreadingHTTPServer,
    agent: Any,
    runtime_agent_path: Path,
    log_handle: Any,
) -> None:
    while not stop_event.wait(0.5):
        if server.agent_restart_event.is_set():
            server.agent_restart_event.clear()
            if server.agent_process is not None:
                _terminate_agent(server.agent_process)
                server.agent_process = None
            config = agent.load_config()
            if _connection_configured(config):
                server.agent_message = "Starting host agent."
                server.agent_process = _start_host_agent(config, runtime_agent_path, log_handle)
            else:
                server.agent_message = "No connection configured. Choose Telegram or a relay in Settings."
                print(server.agent_message, file=log_handle, flush=True)
        if server.agent_process is not None and server.agent_process.poll() is not None:
            status = server.agent_process.returncode
            server.agent_process = None
            server.agent_message = (
                f"Host agent stopped with exit code {status}. Check Live logs and your connection settings."
            )
            print(server.agent_message, file=log_handle, flush=True)


def command_status(_: argparse.Namespace) -> int:
    pid = _service_pid()
    agent_running = _agent_process_running() if pid else False
    config = {}
    try:
        config = _agent_module().load_config()
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        print(f"Configuration unavailable: {error}")

    terminal_width = max(50, min(80, shutil_terminal_width()))
    line = "─" * terminal_width
    print(f"\033[1;96m╭{'─' * (terminal_width - 2)}╮\033[0m")
    print(f"\033[1;96m│{'MACREMOTE · HOST CONTROL'.center(terminal_width - 2)}│\033[0m")
    print(f"\033[1;96m╰{'─' * (terminal_width - 2)}╯\033[0m")
    print(f"  Service     \033[1;32m● Running · PID {pid}\033[0m" if pid else "  Service     \033[1;31m● Stopped\033[0m")
    print(f"  Host agent  \033[1;32m● Running\033[0m" if agent_running else "  Host agent  \033[1;33m● Not running\033[0m")
    print(f"  Dashboard   {_dashboard_url()}" if pid else "  Dashboard   Start with `macremote start`")
    print(f"  Relay       {config.get('relay_url') or 'Not configured'}")
    print(f"  Data        {DATA_DIR}")
    print(f"  Approvals   Coding-agent requests always require local approval")
    print(f"\033[2m{line}\033[0m")
    print("  Commands: start · daemon · stop · status · logs · ui · pairing")
    return 0


def shutil_terminal_width() -> int:
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 72


def command_start(args: argparse.Namespace) -> int:
    existing_pid = _service_pid()
    if existing_pid:
        print(f"MacRemote is already running (PID {existing_pid}).")
    else:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with _open_private_log() as log:
                process = subprocess.Popen(
                    [sys.executable, str(SCRIPT_PATH), "daemon", "--foreground"],
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    close_fds=True,
                )
        except OSError as error:
            print(f"Could not start the MacRemote daemon: {error}", file=sys.stderr)
            return 1
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if _service_pid() and _dashboard_ready():
                break
            if process.poll() is not None:
                break
            time.sleep(0.2)
        if not _service_pid() or not _dashboard_ready():
            print("MacRemote did not start. Recent logs:")
            command_logs(argparse.Namespace(follow=False, lines=20))
            return 1
        print("MacRemote host service started.")

    if args.open:
        token = urllib.parse.quote(_dashboard_token(), safe="")
        webbrowser.open(f"{_dashboard_url()}#token={token}")
        print(f"Dashboard: {_dashboard_url()}")
    return 0


def command_daemon(args: argparse.Namespace) -> int:
    if args.foreground:
        return run_foreground_daemon()
    return command_start(args)


def command_stop(_: argparse.Namespace) -> int:
    pid = _service_pid()
    if not pid:
        print("MacRemote is not running.")
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print("MacRemote has already stopped.")
        return 0
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and _service_pid() == pid:
        time.sleep(0.2)
    if _service_pid() == pid:
        print("MacRemote did not stop after the graceful shutdown request.")
        return 1
    print("MacRemote stopped.")
    return 0


def command_logs(args: argparse.Namespace) -> int:
    if not LOG_FILE.exists():
        print("No logs yet. Start MacRemote with `macremote start`.")
        return 0
    if args.follow:
        try:
            subprocess.run(["tail", "-n", str(args.lines), "-f", str(LOG_FILE)], check=False)
        except OSError as error:
            print(f"Unable to follow logs: {error}", file=sys.stderr)
            return 1
        return 0
    lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    print("\n".join(lines[-args.lines :]))
    return 0


def command_ui(_: argparse.Namespace) -> int:
    if not _service_pid():
        print("The dashboard is not running. Start MacRemote with `macremote start`.")
        return 1
    token = urllib.parse.quote(_dashboard_token(), safe="")
    webbrowser.open(f"{_dashboard_url()}#token={token}")
    print(f"Opened {_dashboard_url()}")
    return 0


def command_pairing(_: argparse.Namespace) -> int:
    try:
        config = _agent_module().load_config()
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        print(f"Unable to load MacRemote configuration: {error}", file=sys.stderr)
        return 1
    uri = make_pairing_uri(config)
    if not uri:
        print(
            "Pairing is not configured. Set relay_url, relay_host_id, and "
            "relay_phone_token in the local dashboard first.",
            file=sys.stderr,
        )
        return 1
    try:
        qr = subprocess.run(
            ["qrencode", "-t", "UTF8", uri],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        print(qr.stdout, end="")
    except FileNotFoundError:
        print(f"Install qrencode to display a terminal QR code. Pairing link:\n{uri}")
        return 1
    except subprocess.SubprocessError as error:
        print(f"Could not generate pairing QR code: {error}", file=sys.stderr)
        return 1
    return 0


def make_pairing_uri(config: dict[str, Any]) -> str | None:
    relay_url = str(config.get("relay_url", "")).strip().rstrip("/")
    host_id = str(config.get("relay_host_id", "")).strip()
    phone_token = str(config.get("relay_phone_token", "")).strip()
    if (
        not _valid_relay_url(relay_url)
        or not 16 <= len(host_id) <= 64
        or not all(character.isascii() and (character.isalnum() or character in "_-") for character in host_id)
        or not 40 <= len(phone_token) <= 512
    ):
        return None
    query = urllib.parse.urlencode(
        {"relay_url": relay_url, "host_id": host_id, "phone_token": phone_token}
    )
    return f"macremote://pair?{query}"


def _json_response(handler: BaseHTTPRequestHandler, status: int, data: Any) -> None:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(body)


def _load_config() -> dict[str, Any]:
    return _agent_module().load_config()


def _save_config(updates: dict[str, Any]) -> dict[str, Any]:
    invalid = set(updates) - CONFIG_KEYS
    if invalid:
        raise ValueError(f"Unsupported setting: {', '.join(sorted(invalid))}")
    config = _load_config()
    for key, value in updates.items():
        if key in {"bot_token", "relay_host_token", "relay_phone_token"}:
            if not isinstance(value, str) or len(value) > 4096:
                raise ValueError(f"{key} must be a string of at most 4096 characters")
        elif key == "allowed_user_ids":
            if not isinstance(value, list) or len(value) > 100:
                raise ValueError("allowed_user_ids must be a list of at most 100 IDs")
            parsed_ids = []
            for item in value:
                if isinstance(item, bool) or not (
                    isinstance(item, int)
                    or isinstance(item, str) and item.lstrip("-").isdigit()
                ):
                    raise ValueError("allowed_user_ids must contain integers")
                parsed_ids.append(int(item))
            config[key] = parsed_ids
            continue
        elif key == "pairing_pin":
            if not isinstance(value, str) or (value and not (len(value) == 4 and value.isdigit())):
                raise ValueError("pairing_pin must be empty or exactly four digits")
        elif key == "keep_awake":
            if not isinstance(value, bool):
                raise ValueError("keep_awake must be a boolean")
        elif key == "relay_url":
            if not isinstance(value, str) or value and not _valid_relay_url(value):
                raise ValueError("relay_url must be an HTTPS origin without a path or credentials")
        elif key == "relay_host_id":
            if not isinstance(value, str) or value and not (
                16 <= len(value) <= 64
                and all(char.isascii() and (char.isalnum() or char in "_-") for char in value)
            ):
                raise ValueError("relay_host_id has an invalid format")
        else:
            if not isinstance(value, str) or len(value) > 4096:
                raise ValueError(f"{key} must be a string of at most 4096 characters")
        config[key] = value
    agent = _agent_module()
    _atomic_write(Path(agent.CONFIG_FILE), json.dumps(config, indent=2) + "\n")
    return config


def _valid_relay_url(value: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(value.strip().rstrip("/"))
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and parsed.path in ("", "/")
        and not parsed.query
        and not parsed.fragment
        and (port is None or 1 <= port <= 65535)
    )


def _task_rows() -> list[dict[str, Any]]:
    agent = _agent_module()
    database = Path(agent.TASK_DB_FILE)
    if not database.exists():
        return []
    with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=2)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT id, provider, prompt, status, result FROM agent_tasks "
            "ORDER BY rowid DESC LIMIT 50"
        ).fetchall()
    return [dict(row) for row in rows]


def _set_task_status(task_id: str, status: str) -> bool:
    if not task_id or len(task_id) > 128:
        raise ValueError("Invalid task ID")
    database = Path(_agent_module().TASK_DB_FILE)
    if not database.exists():
        return False
    with closing(sqlite3.connect(database, timeout=2)) as connection, connection:
        cursor = connection.execute(
            "UPDATE agent_tasks SET status = ? WHERE id = ? AND status = 'pending'",
            (status, task_id),
        )
        return cursor.rowcount == 1


def _pairing_response() -> dict[str, Any]:
    config = _load_config()
    uri = make_pairing_uri(config)
    if not uri:
        return {"configured": False, "uri": "", "svg": ""}
    try:
        result = subprocess.run(
            ["qrencode", "-t", "SVG", "-o", "-"],
            input=uri,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError as error:
        raise RuntimeError("QR generation requires qrencode; install it with Homebrew.") from error
    except subprocess.SubprocessError as error:
        raise RuntimeError(f"QR generation failed: {error}") from error
    return {"configured": True, "uri": uri, "svg": result.stdout}


def _make_handler(token: str):
    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "MacRemoteLocal/1"
        sys_version = ""

        def log_message(self, format_string: str, *args: Any) -> None:
            if self.path.startswith("/api/logs"):
                return
            with _open_private_log() as log:
                log.write("%s - %s\n" % (self.address_string(), format_string % args))

        def _authorized(self) -> bool:
            supplied = self.headers.get("Authorization", "")
            return secrets.compare_digest(supplied, f"Bearer {token}")

        def _read_json(self) -> dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as error:
                raise ValueError("Invalid request length") from error
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("Request body must be between 1 byte and 64 KiB")
            try:
                value = json.loads(self.rfile.read(length))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("Request body must be valid JSON") from error
            if not isinstance(value, dict):
                raise ValueError("Request body must be a JSON object")
            return value

        def _api_auth(self) -> bool:
            if not self._authorized():
                _json_response(self, 401, {"error": "Dashboard authentication required"})
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in (f"http://{HOST}:{PORT}", f"http://localhost:{PORT}"):
                _json_response(self, 403, {"error": "Cross-origin requests are not allowed"})
                return False
            return True

        def do_GET(self) -> None:
            path = urllib.parse.urlsplit(self.path).path
            if path == "/":
                self._serve_asset("index.html", "text/html; charset=utf-8")
                return
            if path in ("/app.css", "/app.js"):
                file_name = path.removeprefix("/")
                content_type = "text/css; charset=utf-8" if file_name.endswith(".css") else "text/javascript; charset=utf-8"
                self._serve_asset(file_name, content_type)
                return
            if not path.startswith("/api/"):
                _json_response(self, 404, {"error": "Not found"})
                return
            if not self._api_auth():
                return
            try:
                if path == "/api/status":
                    agent_running = self.server.agent_process is not None and self.server.agent_process.poll() is None
                    config = _load_config()
                    _json_response(
                        self,
                        200,
                        {
                            "service_running": True,
                            "agent_running": agent_running,
                            "platform": platform.platform(),
                            "connection_configured": _connection_configured(config),
                            "connection_message": getattr(self.server, "agent_message", ""),
                            "relay_url": config.get("relay_url", ""),
                        },
                    )
                elif path == "/api/config":
                    _json_response(self, 200, _load_config())
                elif path == "/api/tasks":
                    _json_response(self, 200, {"tasks": _task_rows()})
                elif path == "/api/pairing":
                    _json_response(self, 200, _pairing_response())
                elif path == "/api/logs":
                    query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                    offset = max(0, int(query.get("offset", ["0"])[0]))
                    text, next_offset = _read_log(offset)
                    _json_response(self, 200, {"text": text, "offset": next_offset})
                else:
                    _json_response(self, 404, {"error": "Not found"})
            except (OSError, sqlite3.Error, ImportError, RuntimeError, ValueError) as error:
                _json_response(self, 500, {"error": str(error)})

        def do_POST(self) -> None:
            if not self._api_auth():
                return
            path = urllib.parse.urlsplit(self.path).path
            try:
                data = self._read_json()
                if path == "/api/config":
                    saved_config = _save_config(data)
                    restart_event = getattr(self.server, "agent_restart_event", None)
                    if restart_event is not None:
                        restart_event.set()
                    _json_response(self, 200, {"config": saved_config})
                elif path.startswith("/api/tasks/") and path.endswith("/approve"):
                    task_id = urllib.parse.unquote(path[len("/api/tasks/") : -len("/approve")].strip("/"))
                    if not _set_task_status(task_id, "approved"):
                        _json_response(self, 409, {"error": "Task is no longer pending"})
                    else:
                        _json_response(self, 200, {"status": "approved"})
                elif path.startswith("/api/tasks/") and path.endswith("/reject"):
                    task_id = urllib.parse.unquote(path[len("/api/tasks/") : -len("/reject")].strip("/"))
                    if not _set_task_status(task_id, "rejected"):
                        _json_response(self, 409, {"error": "Task is no longer pending"})
                    else:
                        _json_response(self, 200, {"status": "rejected"})
                else:
                    _json_response(self, 404, {"error": "Not found"})
            except (OSError, sqlite3.Error, ImportError, RuntimeError, ValueError) as error:
                _json_response(self, 400, {"error": str(error)})

        def _serve_asset(self, name: str, content_type: str) -> None:
            try:
                body = (APP_HOME / "dashboard" / name).read_bytes()
            except OSError:
                _json_response(self, 404, {"error": "Dashboard asset is missing"})
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

    return DashboardHandler


def _read_log(offset: int) -> tuple[str, int]:
    try:
        size = LOG_FILE.stat().st_size
        start = offset
        if size - start > 1024 * 1024:
            start = max(0, size - 1024 * 1024)
        with LOG_FILE.open("rb") as log:
            log.seek(start)
            content = log.read(64 * 1024)
        return content.decode("utf-8", errors="replace"), start + len(content)
    except FileNotFoundError:
        return "", 0


def run_foreground_daemon() -> int:
    if platform.system() != "Darwin":
        print("The MacRemote host daemon currently supports macOS only.", file=sys.stderr)
        return 1
    if _service_pid():
        print("A MacRemote service is already running.", file=sys.stderr)
        return 1
    _ensure_data_dir()
    token = _dashboard_token()
    agent = _agent_module()
    config = agent.load_config()
    runtime_agent_path = _runtime_agent_path()
    log_handle = _open_private_log()
    try:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((HOST, PORT))
        server = ThreadingHTTPServer((HOST, PORT), _make_handler(token))
        server.daemon_threads = True
        server.agent_process = None
        server.agent_restart_event = threading.Event()
        server.agent_message = "No connection configured. Choose Telegram or a relay in Settings."
    except OSError as error:
        log_handle.close()
        print(f"Could not bind the local dashboard to {HOST}:{PORT}: {error}", file=sys.stderr)
        return 1

    stop_event = threading.Event()

    def request_shutdown(_: int, __: Any) -> None:
        stop_event.set()

    server_thread = None
    try:
        _atomic_write(PID_FILE, str(os.getpid()))
        signal.signal(signal.SIGTERM, request_shutdown)
        signal.signal(signal.SIGINT, request_shutdown)
        server_thread = threading.Thread(target=server.serve_forever, name="macremote-dashboard", daemon=True)
        server_thread.start()
        print(f"MacRemote daemon ready at {_dashboard_url()}", flush=True)
        if _connection_configured(config):
            server.agent_message = "Starting host agent."
            server.agent_process = _start_host_agent(config, runtime_agent_path, log_handle)
        else:
            print(server.agent_message, file=log_handle, flush=True)
        _supervise_host_agent(stop_event, server, agent, runtime_agent_path, log_handle)
        return 0
    finally:
        if server_thread is not None and server_thread.is_alive():
            server.shutdown()
        server.server_close()
        if server.agent_process is not None:
            _terminate_agent(server.agent_process)
        log_handle.close()
        try:
            if PID_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
                PID_FILE.unlink()
        except FileNotFoundError:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="macremote", description="MacRemote terminal-first host controller")
    subparsers = parser.add_subparsers(dest="command")
    start = subparsers.add_parser("start", help="Start the host and open its local dashboard")
    start.add_argument("--no-open", dest="open", action="store_false", help="Do not open a browser")
    start.set_defaults(handler=command_start, open=True)
    daemon = subparsers.add_parser("daemon", help="Run the service in the background")
    daemon.add_argument("--foreground", action="store_true", help=argparse.SUPPRESS)
    daemon.set_defaults(handler=command_daemon, open=False)
    stop = subparsers.add_parser("stop", help="Stop the service and host agent")
    stop.set_defaults(handler=command_stop)
    status = subparsers.add_parser("status", help="Show host, relay, and dashboard status")
    status.set_defaults(handler=command_status)
    logs = subparsers.add_parser("logs", help="Show service and host logs")
    logs.add_argument("--follow", "-f", action="store_true", help="Follow new log output")
    logs.add_argument("--lines", "-n", type=int, default=50, help="Number of lines to display")
    logs.set_defaults(handler=command_logs)
    ui = subparsers.add_parser("ui", help="Open the local web dashboard")
    ui.set_defaults(handler=command_ui)
    pairing = subparsers.add_parser("pairing", help="Show a QR code for Android pairing")
    pairing.set_defaults(handler=command_pairing)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        args = argparse.Namespace()
        return command_status(args)
    if getattr(args, "lines", 50) < 1 or getattr(args, "lines", 50) > 10000:
        parser.error("--lines must be between 1 and 10000")
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
