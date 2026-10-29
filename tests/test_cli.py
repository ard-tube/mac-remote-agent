import contextlib
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from cli import macremote


class MacRemoteCliTests(unittest.TestCase):
    def test_release_archive_checksum_matches_formula_and_installer(self):
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "MacRemote-CLI.tar"
            subprocess.run(
                [sys.executable, str(repository / "cli" / "package_release.py"), str(archive)],
                check=True,
                cwd=repository,
            )
            checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        formula = (repository / "Formula" / "macremote.rb").read_text(encoding="utf-8")
        installer = (repository / "install.sh").read_text(encoding="utf-8")
        self.assertIn(checksum, formula)
        self.assertIn(checksum, installer)

    def test_pairing_uri_requires_https_and_valid_credentials(self):
        config = {
            "relay_url": "https://relay.example.com",
            "relay_host_id": "h" * 24,
            "relay_phone_token": "p" * 48,
        }
        uri = macremote.make_pairing_uri(config)
        self.assertTrue(uri.startswith("macremote://pair?"))
        self.assertIn("relay_url=https%3A%2F%2Frelay.example.com", uri)
        self.assertIsNone(macremote.make_pairing_uri({**config, "relay_url": "http://relay.example.com"}))
        self.assertIsNone(macremote.make_pairing_uri({**config, "relay_url": "https://relay.example.com:99999"}))
        self.assertIsNone(macremote.make_pairing_uri({**config, "relay_url": "https://[broken"}))
        self.assertIsNone(macremote.make_pairing_uri({**config, "relay_phone_token": "short"}))
        self.assertIsNone(macremote.make_pairing_uri({**config, "relay_host_id": "é" * 24}))

    def test_config_updates_are_allowlisted_validated_and_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "config.json"
            original = {"bot_token": "old-secret", "unrelated": "preserved"}
            config_path.write_text(json.dumps(original), encoding="utf-8")
            fake_agent = SimpleNamespace(
                CONFIG_FILE=str(config_path),
                load_config=lambda: json.loads(config_path.read_text(encoding="utf-8")),
            )
            with mock.patch.object(macremote, "_agent_module", return_value=fake_agent):
                updated = macremote._save_config({"bot_token": "new-secret", "keep_awake": False})
                self.assertEqual(updated["bot_token"], "new-secret")
                self.assertEqual(updated["unrelated"], "preserved")
                with self.assertRaisesRegex(ValueError, "Unsupported setting"):
                    macremote._save_config({"auto_approve": True})
                with self.assertRaisesRegex(ValueError, "HTTPS origin"):
                    macremote._save_config({"relay_url": "http://example.com"})
                with self.assertRaisesRegex(ValueError, "contain integers"):
                    macremote._save_config({"allowed_user_ids": [2.5]})
            if os.name != "nt":
                self.assertEqual(config_path.stat().st_mode & 0o777, 0o600)

    def test_dashboard_approval_updates_only_pending_tasks(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "tasks.sqlite3"
            with contextlib.closing(sqlite3.connect(database)) as connection, connection:
                connection.execute(
                    "CREATE TABLE agent_tasks (id TEXT PRIMARY KEY, provider TEXT, prompt TEXT, "
                    "status TEXT, result TEXT)"
                )
                connection.executemany(
                    "INSERT INTO agent_tasks VALUES (?, 'claude', 'Review', ?, '')",
                    [("pending-task", "pending"), ("completed-task", "completed")],
                )
            fake_agent = SimpleNamespace(TASK_DB_FILE=str(database))
            with mock.patch.object(macremote, "_agent_module", return_value=fake_agent):
                self.assertTrue(macremote._set_task_status("pending-task", "approved"))
                self.assertFalse(macremote._set_task_status("pending-task", "rejected"))
                self.assertFalse(macremote._set_task_status("completed-task", "approved"))
            with contextlib.closing(sqlite3.connect(database)) as connection:
                statuses = dict(connection.execute("SELECT id, status FROM agent_tasks"))
            self.assertEqual(statuses["pending-task"], "approved")
            self.assertEqual(statuses["completed-task"], "completed")

    def test_runtime_agent_copy_is_writable_and_updated_atomically(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_dir = root / "source"
            data_dir = root / "Application Support" / "MacRemote"
            source_dir.mkdir()
            source = source_dir / "agent.py"
            source.write_text("print('first')\n", encoding="utf-8")
            with mock.patch.object(macremote, "APP_HOME", source_dir), \
                    mock.patch.object(macremote, "DATA_DIR", data_dir):
                runtime_script = macremote._runtime_agent_path()
                self.assertEqual(runtime_script.read_text(encoding="utf-8"), "print('first')\n")
                source.write_text("print('updated')\n", encoding="utf-8")
                self.assertEqual(macremote._runtime_agent_path(), runtime_script)
                self.assertEqual(runtime_script.read_text(encoding="utf-8"), "print('updated')\n")
            if os.name != "nt":
                self.assertEqual(runtime_script.stat().st_mode & 0o777, 0o600)

    def test_dashboard_requires_token_and_rejects_cross_origin_posts(self):
        token = "local-secret-token"
        with tempfile.TemporaryDirectory() as temporary:
            log_path = Path(temporary) / "macremote.log"
            with mock.patch.object(macremote, "DATA_DIR", Path(temporary)), \
                    mock.patch.object(macremote, "LOG_FILE", log_path):
                server = macremote.ThreadingHTTPServer(("127.0.0.1", 0), macremote._make_handler(token))
                server.agent_process = SimpleNamespace(poll=lambda: None)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base_url = f"http://127.0.0.1:{server.server_port}"
                try:
                    with self.assertRaises(urllib.error.HTTPError) as unauthorized:
                        urllib.request.urlopen(f"{base_url}/api/status", timeout=2)
                    self.assertEqual(unauthorized.exception.code, 401)
                    unauthorized.exception.close()

                    request = urllib.request.Request(
                        f"{base_url}/api/status",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    with mock.patch.object(macremote, "_load_config", return_value={"relay_url": ""}):
                        with urllib.request.urlopen(request, timeout=2) as response:
                            self.assertTrue(json.loads(response.read())["agent_running"])

                    request = urllib.request.Request(
                        f"{base_url}/api/config",
                        data=b"{}",
                        method="POST",
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Origin": "https://attacker.example",
                            "Content-Type": "application/json",
                        },
                    )
                    with self.assertRaises(urllib.error.HTTPError) as cross_origin:
                        urllib.request.urlopen(request, timeout=2)
                    self.assertEqual(cross_origin.exception.code, 403)
                    cross_origin.exception.close()
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)

    def test_parser_exposes_daemon_controls_and_log_bounds(self):
        parsed = macremote.build_parser().parse_args(["logs", "--lines", "12"])
        self.assertEqual(parsed.lines, 12)
        self.assertEqual(parsed.command, "logs")
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                macremote.main(["logs", "--lines", "0"])


if __name__ == "__main__":
    unittest.main()
