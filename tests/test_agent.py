import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest import mock

import agent


class AgentTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.temp_dir.name, "tasks.sqlite3")
        self.data_dir_patch = mock.patch.object(agent, "DATA_DIR", self.temp_dir.name)
        self.database_patch = mock.patch.object(agent, "TASK_DB_FILE", self.database_path)
        self.config_path_patch = mock.patch.object(
            agent, "CONFIG_FILE", os.path.join(self.temp_dir.name, "config.json")
        )
        self.legacy_config_patch = mock.patch.object(
            agent, "LEGACY_CONFIG_FILE", os.path.join(self.temp_dir.name, "legacy.json")
        )
        self.data_dir_patch.start()
        self.database_patch.start()
        self.config_path_patch.start()
        self.legacy_config_patch.start()
        agent.initialize_task_store()

    def tearDown(self):
        self.legacy_config_patch.stop()
        self.config_path_patch.stop()
        self.database_patch.stop()
        self.data_dir_patch.stop()
        self.temp_dir.cleanup()

    def test_initial_config_is_saved_with_private_permissions(self):
        config = agent.load_config()

        self.assertRegex(config["pairing_pin"], r"^\d{4}$")
        self.assertTrue(os.path.isfile(agent.CONFIG_FILE))
        if os.name != "nt":
            self.assertEqual(os.stat(agent.CONFIG_FILE).st_mode & 0o777, 0o600)

    def test_invalid_config_is_not_overwritten(self):
        with open(agent.CONFIG_FILE, "w", encoding="utf-8") as file:
            file.write("{invalid json")

        with self.assertRaisesRegex(RuntimeError, "Unable to load configuration"):
            agent.load_config()

        with open(agent.CONFIG_FILE, encoding="utf-8") as file:
            self.assertEqual(file.read(), "{invalid json")

    def test_agent_tasks_wait_for_local_approval(self):
        task_id = agent.enqueue_agent_task("claude", "Review my project", 42, 100)
        bot = mock.Mock()

        with mock.patch.object(agent.SystemActions, "run_agent_cli") as run_cli:
            agent.process_approved_agent_tasks(bot)

        run_cli.assert_not_called()
        bot.send_message.assert_not_called()
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            status = connection.execute(
                "SELECT status FROM agent_tasks WHERE id = ?", (task_id,)
            ).fetchone()[0]
        self.assertEqual(status, "pending")

    def test_agent_task_queue_rejects_empty_oversized_and_excessive_tasks(self):
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            agent.enqueue_agent_task("claude", "  ", 42, 100)
        with self.assertRaisesRegex(ValueError, "4,000 characters"):
            agent.enqueue_agent_task("claude", "x" * 4001, 42, 100)

        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.executemany(
                "INSERT INTO agent_tasks (id, provider, prompt, requester_id, chat_id, status) "
                "VALUES (?, 'claude', 'prompt', 42, 100, 'pending')",
                [(f"task-{number}",) for number in range(100)],
            )
        with self.assertRaisesRegex(ValueError, "queue is full"):
            agent.enqueue_agent_task("claude", "Review my project", 42, 100)

    def test_approved_task_runs_once_and_reports_result(self):
        task_id = agent.enqueue_agent_task("antigravity", "Summarize recent commits", 42, 100)
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute(
                "UPDATE agent_tasks SET status = 'approved' WHERE id = ?", (task_id,)
            )
        bot = mock.Mock()

        with mock.patch.object(agent.SystemActions, "run_agent_cli", return_value="Done") as run_cli:
            agent.process_approved_agent_tasks(bot)

        run_cli.assert_called_once_with("antigravity", "Summarize recent commits")
        bot.send_message.assert_called_once()
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            status, result = connection.execute(
                "SELECT status, result FROM agent_tasks WHERE id = ?", (task_id,)
            ).fetchone()
        self.assertEqual((status, result), ("completed", "Done"))

    def test_agent_cli_receives_a_prompt_without_shell_execution(self):
        completed = mock.Mock(returncode=0)
        completed.communicate.return_value = ("Completed", "")
        agent.config = {"working_directory": self.temp_dir.name}
        with mock.patch.object(agent.SystemActions, "find_cli_bin", return_value="/usr/local/bin/claude"), \
                mock.patch.object(agent.subprocess, "Popen", return_value=completed) as run:
            result = agent.SystemActions.run_agent_cli("claude", "Review this repository")

        self.assertEqual(result, "Completed")
        self.assertEqual(run.call_args.args[0], ["/usr/local/bin/claude", "-p", "Review this repository"])
        self.assertNotIn("shell", run.call_args.kwargs)
        self.assertEqual(run.call_args.kwargs["cwd"], self.temp_dir.name)
        self.assertIsNone(agent.active_cli_process)

    def test_agent_cli_does_not_run_if_working_directory_is_missing(self):
        agent.config = {"working_directory": os.path.join(self.temp_dir.name, "missing")}
        with mock.patch.object(agent.SystemActions, "find_cli_bin", return_value="/usr/local/bin/claude"), \
                mock.patch.object(agent.subprocess, "Popen") as run:
            result = agent.SystemActions.run_agent_cli("claude", "Review this repository")

        self.assertIn("working directory does not exist", result)
        run.assert_not_called()

    def test_remote_shell_command_is_not_executed(self):
        agent.config = {"allowed_user_ids": [42], "pairing_pin": ""}
        bot = mock.Mock()
        message = {
            "chat": {"id": 100},
            "from": {"id": 42, "username": "owner"},
            "text": "/sh echo unsafe",
        }

        with mock.patch.object(agent, "load_config", return_value=agent.config), \
                mock.patch.object(agent.SystemActions, "run_agent_cli") as run_cli:
            agent.handle_message(bot, message)

        run_cli.assert_not_called()
        response = bot.send_message.call_args.args[1]
        self.assertIn("Remote shell commands are disabled", response)

    def test_agent_prompts_are_queued_instead_of_running_immediately(self):
        agent.config = {"allowed_user_ids": [42], "pairing_pin": ""}
        bot = mock.Mock()
        messages = [
            {"chat": {"id": 100}, "from": {"id": 42}, "text": "/agy inspect this project"},
            {"chat": {"id": 100}, "from": {"id": 42}, "text": "/claude review this project"},
        ]

        with mock.patch.object(agent, "load_config", return_value=agent.config), \
                mock.patch.object(agent.SystemActions, "run_agent_cli") as run_cli:
            for message in messages:
                agent.handle_message(bot, message)

        run_cli.assert_not_called()
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            tasks = connection.execute(
                "SELECT provider, status FROM agent_tasks ORDER BY provider"
            ).fetchall()
        self.assertEqual(tasks, [("antigravity", "pending"), ("claude", "pending")])

    def test_relay_agent_task_waits_for_local_approval_and_is_idempotent(self):
        relay = agent.RelayClient("https://relay.example", "h" * 24, "t" * 43)
        command = {
            "id": "c0d6611f-1254-4c62-ae8a-4a56a4983fe8",
            "action": "agent_task",
            "payload": {"provider": "claude", "prompt": "Review this project"},
        }

        with mock.patch.object(relay, "report_command") as report, \
                mock.patch.object(agent.SystemActions, "run_agent_cli") as run_cli:
            agent.handle_relay_command(relay, None, command)
            agent.handle_relay_command(relay, None, command)

        run_cli.assert_not_called()
        self.assertEqual(report.call_count, 2)
        self.assertEqual(report.call_args.args[1], "awaiting_approval")
        with closing(sqlite3.connect(self.database_path)) as connection:
            rows = connection.execute(
                "SELECT id, delivery_channel, relay_command_id FROM agent_tasks"
            ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1:], ("relay", command["id"]))

    def test_approved_relay_task_result_is_returned_to_relay(self):
        relay = mock.Mock()
        task_id = agent.enqueue_agent_task(
            "claude",
            "Review this project",
            0,
            0,
            delivery_channel="relay",
            relay_host_id="h" * 24,
            relay_command_id="c0d6611f-1254-4c62-ae8a-4a56a4983fe8",
        )
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute(
                "UPDATE agent_tasks SET status = 'approved' WHERE id = ?", (task_id,)
            )

        with mock.patch.object(agent.SystemActions, "run_agent_cli", return_value="Reviewed") as run_cli:
            agent.process_approved_agent_tasks(None, relay)

        run_cli.assert_called_once_with("claude", "Review this project")
        relay.report_command.assert_called_once_with(
            "c0d6611f-1254-4c62-ae8a-4a56a4983fe8",
            "completed",
            {"taskId": task_id, "text": "Reviewed"},
        )


if __name__ == "__main__":
    unittest.main()
