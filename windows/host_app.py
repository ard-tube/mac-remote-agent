import json
import os
import secrets
import sqlite3
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError as error:
    raise SystemExit(
        "MacRemote requires its bundled tray dependencies. Rebuild with windows/build-app.ps1."
    ) from error


APP_NAME = "MacRemote"
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
CONFIG_PATH = DATA_DIR / "config.json"
DATABASE_PATH = DATA_DIR / "pending_tasks.sqlite3"
LOG_PATH = DATA_DIR / "agent.log"


def agent_path():
    if getattr(sys, "frozen", False):
        bundled = Path(sys.executable).with_name("MacRemoteAgent.exe")
        if bundled.is_file():
            return bundled
    configured = os.environ.get("MRA_AGENT_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "agent.py"


def default_config():
    return {
        "bot_token": "",
        "allowed_user_ids": [],
        "pairing_pin": "",
        "google_drive_path": str(Path.home() / "Google Drive" / "My Drive"),
        "antigravity_bin": "",
        "claude_bin": "",
        "working_directory": str(Path.home()),
        "keep_awake": True,
    }


def read_config():
    try:
        with CONFIG_PATH.open(encoding="utf-8") as file:
            return {**default_config(), **json.load(file)}
    except FileNotFoundError:
        return default_config()


class MacRemoteWindow:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.root = tk.Tk()
        self.root.title("MacRemote")
        self.root.geometry("740x860")
        self.root.minsize(620, 700)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        self.root.bind("<Map>", lambda _event: self.root.after(150, self.refresh_tasks))
        self.config = read_config()
        self.process = None
        self.tray = None
        self.task_ids = []
        self.token_var = tk.StringVar(value=self.config.get("bot_token", ""))
        self.agy_var = tk.StringVar(value=self.config.get("antigravity_bin", ""))
        self.claude_var = tk.StringVar(value=self.config.get("claude_bin", ""))
        self.directory_var = tk.StringVar(value=self.config.get("working_directory", str(Path.home())))
        self.relay_url_var = tk.StringVar(value=self.config.get("relay_url", ""))
        self.relay_id_var = tk.StringVar(value=self.config.get("relay_host_id", ""))
        self.relay_token_var = tk.StringVar(value=self.config.get("relay_host_token", ""))
        self.pin_var = tk.StringVar(value=self.config.get("pairing_pin", ""))
        self.status_var = tk.StringVar(value="Starting MacRemote…")
        self.refresh_after_id = None
        self.build_ui()
        self.start_tray()
        self.start_agent()
        self.root.after(1000, self.refresh_tasks)

    def build_ui(self):
        self.root.configure(bg="#f4f6fb")
        outer = ttk.Frame(self.root, padding=22)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text="MacRemote", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(header, textvariable=self.status_var, font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 0))

        settings = ttk.LabelFrame(outer, text="Phone connection and agent settings", padding=14)
        settings.pack(fill="x", pady=(18, 14))
        self.add_setting(settings, "Telegram bot token", self.token_var, masked=True)
        self.add_setting(settings, "Antigravity CLI executable (optional)", self.agy_var)
        self.add_setting(settings, "Claude Code CLI executable (optional)", self.claude_var)
        self.add_setting(settings, "Working folder for approved tasks", self.directory_var)
        self.add_setting(settings, "Relay HTTPS URL (optional)", self.relay_url_var)
        self.add_setting(settings, "Relay host ID (optional)", self.relay_id_var)
        self.add_setting(settings, "Relay host token (optional)", self.relay_token_var, masked=True)

        controls = ttk.Frame(settings)
        controls.pack(fill="x", pady=(10, 0))
        ttk.Label(controls, textvariable=self.pin_var, font=("Consolas", 10)).pack(side="left")
        ttk.Button(controls, text="Save settings", command=self.save_settings).pack(side="right")

        queue_header = ttk.Frame(outer)
        queue_header.pack(fill="x", pady=(6, 8))
        ttk.Label(queue_header, text="Approval queue", font=("Segoe UI", 14, "bold")).pack(side="left")
        ttk.Label(queue_header, text="Requests do not run until approved here.").pack(side="right")

        columns = ("provider", "status", "created")
        self.task_list = ttk.Treeview(outer, columns=columns, show="headings", height=9, selectmode="browse")
        self.task_list.heading("provider", text="Agent")
        self.task_list.heading("status", text="Status")
        self.task_list.heading("created", text="Received")
        self.task_list.column("provider", width=140, stretch=False)
        self.task_list.column("status", width=110, stretch=False)
        self.task_list.column("created", width=170, stretch=False)
        self.task_list.pack(fill="x")
        self.task_list.bind("<<TreeviewSelect>>", self.show_selected_task)
        self.task_list.bind("<Double-1>", lambda _event: self.approve_selected())

        ttk.Label(outer, text="Submitted prompt", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(12, 5))
        self.prompt_text = tk.Text(outer, height=6, wrap="word", state="disabled", font=("Segoe UI", 10))
        self.prompt_text.pack(fill="both", expand=True)
        self.prompt_text.configure(background="white", relief="solid", borderwidth=1)

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Label(
            actions,
            text="Approval runs the selected CLI as your Windows user.",
            wraplength=410,
        ).pack(side="left")
        ttk.Button(actions, text="Open activity log", command=self.open_log).pack(side="right", padx=(8, 0))
        ttk.Button(actions, text="Reject", command=self.reject_selected).pack(side="right", padx=(8, 0))
        ttk.Button(actions, text="Approve task", command=self.approve_selected).pack(side="right")

    @staticmethod
    def add_setting(parent, label, variable, masked=False):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=38).pack(side="left")
        ttk.Entry(row, textvariable=variable, show="•" if masked else "").pack(side="left", fill="x", expand=True)

    def start_tray(self):
        image = Image.new("RGB", (64, 64), "#171a24")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((7, 7, 57, 57), radius=13, fill="#2f74ff")
        draw.text((21, 21), "M", fill="white")
        menu = pystray.Menu(
            pystray.MenuItem("Open MacRemote", lambda _icon, _item: self.root.after(0, self.show_window), default=True),
            pystray.MenuItem("Quit", lambda icon, _item: self.root.after(0, lambda: self.quit(icon))),
        )
        self.tray = pystray.Icon(APP_NAME, image, APP_NAME, menu)
        self.tray.run_detached()

    def start_agent(self):
        if self.process and self.process.poll() is None:
            return
        if not self.token_var.get().strip():
            self.status_var.set("Setup needed — enter a Telegram bot token.")
            return

        script = agent_path()
        if not script.is_file():
            self.status_var.set(f"Agent file was not found: {script}")
            return

        env = os.environ.copy()
        env["MRA_DATA_DIR"] = str(DATA_DIR)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with LOG_PATH.open("ab") as log:
                command = [str(script)] if script.suffix.lower() == ".exe" else [sys.executable, str(script)]
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                self.process = subprocess.Popen(
                    command,
                    cwd=str(Path(self.directory_var.get() or Path.home()).expanduser()),
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    startupinfo=startupinfo,
                )
            self.status_var.set("Host agent running. Telegram connection details are in the activity log.")
        except (OSError, ValueError) as error:
            self.status_var.set(f"Could not start the host agent: {error}")

    def stop_agent(self):
        if not self.process or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=4)
        self.process = None

    def save_settings(self):
        self.config.update(
            bot_token=self.token_var.get().strip(),
            antigravity_bin=self.agy_var.get().strip(),
            claude_bin=self.claude_var.get().strip(),
            working_directory=self.directory_var.get().strip() or str(Path.home()),
            relay_url=self.relay_url_var.get().strip(),
            relay_host_id=self.relay_id_var.get().strip(),
            relay_host_token=self.relay_token_var.get().strip(),
        )
        if not self.config.get("pairing_pin"):
            self.config["pairing_pin"] = str(secrets.randbelow(9000) + 1000)
        self.config.setdefault("allowed_user_ids", [])
        self.config.setdefault("google_drive_path", str(Path.home() / "Google Drive" / "My Drive"))
        self.config.setdefault("keep_awake", True)

        temp_path = CONFIG_PATH.with_suffix(".tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as file:
                json.dump(self.config, file, indent=2)
            os.replace(temp_path, CONFIG_PATH)
            self.pin_var.set(f"Telegram pairing PIN: {self.config['pairing_pin']}")
            self.stop_agent()
            self.start_agent()
        except OSError as error:
            messagebox.showerror("MacRemote", f"Could not save settings: {error}")

    def refresh_tasks(self):
        if not self.root.winfo_exists():
            return
        if self.refresh_after_id is not None:
            self.root.after_cancel(self.refresh_after_id)
            self.refresh_after_id = None
        if self.process and self.process.poll() is not None:
            self.status_var.set("Host agent stopped. Check the activity log.")
        elif self.process and self.process.poll() is None:
            self.status_var.set("Host agent running • Local approvals enabled")

        selected = self.task_list.selection()
        selected_id = selected[0] if selected else None
        try:
            with sqlite3.connect(DATABASE_PATH, timeout=1) as database:
                rows = database.execute(
                    "SELECT id, provider, prompt, status, created_at FROM agent_tasks "
                    "ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1 "
                    "WHEN 'running' THEN 2 ELSE 3 END, created_at DESC LIMIT 50"
                ).fetchall()
        except sqlite3.Error:
            rows = []

        self.task_list.delete(*self.task_list.get_children())
        self.task_ids.clear()
        for task_id, provider, prompt, status, created in rows:
            self.task_ids.append(task_id)
            self.task_list.insert("", "end", iid=task_id, values=(provider.title(), status.title(), created))
        if selected_id and selected_id in self.task_ids:
            self.task_list.selection_set(selected_id)
        elif self.task_ids:
            self.task_list.selection_set(self.task_ids[0])
        self.show_selected_task()
        self.refresh_after_id = self.root.after(2000, self.refresh_tasks)

    def show_selected_task(self, _event=None):
        selected = self.task_list.selection()
        prompt = ""
        if selected:
            try:
                with sqlite3.connect(DATABASE_PATH, timeout=1) as database:
                    row = database.execute(
                        "SELECT prompt FROM agent_tasks WHERE id = ?", (selected[0],)
                    ).fetchone()
                prompt = row[0] if row else ""
            except sqlite3.Error:
                prompt = ""
        self.prompt_text.configure(state="normal")
        self.prompt_text.delete("1.0", "end")
        self.prompt_text.insert("1.0", prompt)
        self.prompt_text.configure(state="disabled")

    def update_selected_task(self, status):
        selected = self.task_list.selection()
        if not selected:
            return
        try:
            with sqlite3.connect(DATABASE_PATH, timeout=2) as database:
                result = database.execute(
                    "UPDATE agent_tasks SET status = ? WHERE id = ? AND status = 'pending'",
                    (status, selected[0]),
                )
                if result.rowcount != 1:
                    messagebox.showinfo("MacRemote", "That task was already handled.")
            self.refresh_tasks()
        except sqlite3.Error as error:
            messagebox.showerror("MacRemote", f"Could not update the task: {error}")

    def approve_selected(self):
        self.update_selected_task("approved")

    def reject_selected(self):
        self.update_selected_task("rejected")

    def open_log(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        LOG_PATH.touch(exist_ok=True)
        os.startfile(LOG_PATH)

    def hide_window(self):
        self.root.withdraw()

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.refresh_tasks()

    def quit(self, icon=None):
        if icon:
            icon.stop()
        self.stop_agent()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    MacRemoteWindow().run()
