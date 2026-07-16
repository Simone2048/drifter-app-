#!/usr/bin/env python3
"""
Drifter - Minimalist Time Scheduling Tool
Organize tasks, plan your day, stay on track with a floating widget.
"""

import customtkinter as ctk
import tkinter as tk
import json
import os
import sys
from dataclasses import dataclass, asdict
from typing import Optional, Callable
from pathlib import Path

APP_NAME = "Drifter"
DATA_DIR = Path.home() / ".drifter"
DATA_FILE = DATA_DIR / "tasks.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

DURATION_OPTIONS = ["5m", "10m", "15m", "20m", "25m", "30m", "45m", "1h", "1h 30m", "2h", "3h", "4h"]


def parse_duration(text: str) -> int:
    minutes = 0
    parts = text.lower().replace("h", "h ").replace("m", "").split()
    i = 0
    while i < len(parts):
        p = parts[i]
        if p.endswith("h"):
            minutes += int(p[:-1]) * 60
        elif p.isdigit():
            minutes += int(p)
        i += 1
    return max(1, minutes)


def format_duration(minutes: int) -> str:
    if minutes >= 60:
        h = minutes // 60
        m = minutes % 60
        return f"{h}h {m}m" if m else f"{h}h"
    return f"{minutes}m"


def format_time(seconds: int) -> str:
    if seconds < 0:
        seconds = 0
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_time_remaining(total_seconds: int, elapsed_seconds: int) -> str:
    remaining = max(0, total_seconds - elapsed_seconds)
    return format_time(remaining)


@dataclass
class Task:
    name: str = ""
    duration_minutes: int = 30


class Storage:
    @staticmethod
    def load_tasks() -> list[Task]:
        if DATA_FILE.exists():
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return [Task(**t) for t in data.get("tasks", [])]
            except Exception:
                pass
        return [
            Task("Write documentation", 30),
            Task("Code review", 20),
            Task("Deploy changes", 15),
            Task("Team meeting", 45),
        ]

    @staticmethod
    def save_tasks(tasks: list[Task]) -> None:
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump({"tasks": [asdict(t) for t in tasks]}, f, indent=2)
        except Exception:
            pass

    @staticmethod
    def load_settings() -> dict:
        sf = DATA_DIR / "settings.json"
        if sf.exists():
            try:
                with open(sf, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"widget_x": 100, "widget_y": 100, "widget_visible": True}

    @staticmethod
    def save_settings(settings: dict) -> None:
        try:
            with open(DATA_DIR / "settings.json", "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2)
        except Exception:
            pass


class DrifterWidget(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.master_app = master

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color="#0d1117")

        self._drag_x = 0
        self._drag_y = 0

        self.configure(width=320, height=100)

        self._progress = ctk.CTkProgressBar(self, height=6, corner_radius=0, fg_color="#161b22",
                                            progress_color="#58a6ff")
        self._progress.pack(fill="x", padx=0, pady=(0, 0))
        self._progress.set(0)

        content = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        content.pack(fill="both", expand=True, padx=12, pady=(6, 6))

        self._task_label = ctk.CTkLabel(content, text="No active task", font=ctk.CTkFont(size=15, weight="bold"),
                                        text_color="#e6edf3", anchor="w")
        self._task_label.pack(fill="x", pady=(2, 0))

        info_row = ctk.CTkFrame(content, fg_color="transparent", corner_radius=0)
        info_row.pack(fill="x", pady=(2, 0))

        self._time_label = ctk.CTkLabel(info_row, text="--:--", font=ctk.CTkFont(size=22, weight="bold"),
                                        text_color="#58a6ff")
        self._time_label.pack(side="left")

        self._next_label = ctk.CTkLabel(info_row, text="", font=ctk.CTkFont(size=11),
                                        text_color="#8b949e", anchor="e")
        self._next_label.pack(side="right", padx=(0, 4))

        self._close_btn = ctk.CTkButton(self, text="", width=28, height=20, corner_radius=4,
                                        fg_color="#161b22", hover_color="#30363d",
                                        command=self.hide_widget)
        self._close_btn.place(relx=1.0, x=-32, y=2, anchor="ne")

        self.bind("<Button-1>", self._start_move)
        self.bind("<B1-Motion>", self._on_move)
        self.bind("<Button-3>", self._right_click)

        self._task_label.bind("<Button-1>", self._start_move)
        self._task_label.bind("<B1-Motion>", self._on_move)
        self._time_label.bind("<Button-1>", self._start_move)
        self._time_label.bind("<B1-Motion>", self._on_move)
        self._next_label.bind("<Button-1>", self._start_move)
        self._next_label.bind("<B1-Motion>", self._on_move)
        content.bind("<Button-1>", self._start_move)
        content.bind("<B1-Motion>", self._on_move)

        self._menu = tk.Menu(self, tearoff=0, bg="#161b22", fg="#e6edf3",
                             activebackground="#30363d", activeforeground="#e6edf3",
                             font=("Segoe UI", 10))
        self._menu.add_command(label="Hide Widget", command=self.hide_widget)
        self._menu.add_command(label="Open Drifter", command=self.master_app.deiconify)
        self._menu.add_separator()
        self._menu.add_command(label="Quit Drifter", command=self.master_app.quit_app)

        self._last_x = 100
        self._last_y = 100
        self.protocol("WM_DELETE_WINDOW", self.hide_widget)

    def _start_move(self, event):
        self._drag_x = event.x_root - self.winfo_x()
        self._drag_y = event.y_root - self.winfo_y()
        self.configure(cursor="fleur")

    def _on_move(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.geometry(f"+{x}+{y}")
        self._last_x = x
        self._last_y = y

    def _right_click(self, event):
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def hide_widget(self):
        self.withdraw()
        self.master_app._widget_visible.set(False)

    def update_display(self, task_name: str, total_seconds: int, elapsed_seconds: int,
                       next_task_name: str, paused: bool):
        remaining = max(0, total_seconds - elapsed_seconds)
        progress = elapsed_seconds / total_seconds if total_seconds > 0 else 0
        self._progress.set(min(1.0, progress))

        self._task_label.configure(text=task_name)
        self._time_label.configure(text=format_time(remaining))
        self._next_label.configure(text=f"→ {next_task_name}" if next_task_name else "Last task")

        if paused:
            self._time_label.configure(text_color="#f0883e")
        else:
            self._time_label.configure(text_color="#58a6ff")


class TaskRow(ctk.CTkFrame):
    def __init__(self, master, index: int, task: Task, on_select: Callable,
                 on_delete: Callable, on_move_up: Callable, on_move_down: Callable):
        super().__init__(master, fg_color="#161b22", corner_radius=6, height=38)
        self.index = index
        self.task = task
        self._on_select = on_select
        self._selected = False

        self._inner = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self._inner.pack(fill="both", expand=True, padx=(8, 4), pady=2)

        self._num = ctk.CTkLabel(self._inner, text=str(index + 1), width=22,
                                 font=ctk.CTkFont(size=12), text_color="#484f58")
        self._num.pack(side="left")

        self._name = ctk.CTkLabel(self._inner, text=task.name, anchor="w",
                                  font=ctk.CTkFont(size=13), text_color="#c9d1d9")
        self._name.pack(side="left", fill="x", expand=True, padx=(6, 0))

        self._duration = ctk.CTkLabel(self._inner, text=format_duration(task.duration_minutes), width=50,
                                      font=ctk.CTkFont(size=12), text_color="#8b949e")
        self._duration.pack(side="left", padx=(4, 8))

        btn_frame = ctk.CTkFrame(self._inner, fg_color="transparent", corner_radius=0)
        btn_frame.pack(side="right")

        self._up_btn = ctk.CTkButton(btn_frame, text="▲", width=24, height=20, corner_radius=4,
                                     font=ctk.CTkFont(size=10), fg_color="#21262d",
                                     hover_color="#30363d", command=on_move_up)
        self._up_btn.pack(side="left", padx=(0, 2))

        self._down_btn = ctk.CTkButton(btn_frame, text="▼", width=24, height=20, corner_radius=4,
                                       font=ctk.CTkFont(size=10), fg_color="#21262d",
                                       hover_color="#30363d", command=on_move_down)
        self._down_btn.pack(side="left", padx=(0, 4))

        self._del_btn = ctk.CTkButton(btn_frame, text="✕", width=24, height=20, corner_radius=4,
                                      font=ctk.CTkFont(size=11), fg_color="#21262d",
                                      hover_color="#da3633", command=on_delete)
        self._del_btn.pack(side="left")

        self._inner.bind("<Button-1>", self._on_click)
        self._num.bind("<Button-1>", self._on_click)
        self._name.bind("<Button-1>", self._on_click)
        self._duration.bind("<Button-1>", self._on_click)
        self.bind("<Button-1>", self._on_click)

    def _on_click(self, event=None):
        self._on_select(self.index)

    def set_selected(self, selected: bool):
        self._selected = selected
        if selected:
            self.configure(fg_color="#1f6feb")
            self._name.configure(text_color="#ffffff")
            self._num.configure(text_color="#ffffff")
            self._duration.configure(text_color="#c9d1d9")
        else:
            self.configure(fg_color="#161b22")
            self._name.configure(text_color="#c9d1d9")
            self._num.configure(text_color="#484f58")
            self._duration.configure(text_color="#8b949e")


class DrifterApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(APP_NAME)
        self.geometry("780x560")
        self.minsize(640, 400)
        self.configure(fg_color="#0d1117")

        self._tasks: list[Task] = Storage.load_tasks()
        self._selected_index: int = -1
        self._task_rows: list[TaskRow] = []

        self._timer_running = False
        self._timer_paused = False
        self._current_task_idx = 0
        self._session_start = 0.0
        self._task_start = 0.0
        self._current_elapsed = 0
        self._after_id = None

        self._widget_visible = tk.BooleanVar(value=False)
        self._widget: Optional[DrifterWidget] = None

        self._build_ui()
        self._refresh_task_list()

        settings = Storage.load_settings()
        self._create_widget(settings.get("widget_x", 100), settings.get("widget_y", 100))
        if settings.get("widget_visible", True):
            self._show_widget()
        self._widget_visible.set(settings.get("widget_visible", True))

        self.protocol("WM_DELETE_WINDOW", self.quit_app)

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0, height=36)
        header.pack(fill="x", padx=0, pady=0)
        ctk.CTkLabel(header, text="DRIFTER", font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#58a6ff").pack(side="left", padx=(16, 0), pady=(8, 0))
        ctk.CTkLabel(header, text="time scheduling", font=ctk.CTkFont(size=11),
                     text_color="#484f58").pack(side="left", padx=(6, 0), pady=(11, 0))

        main_container = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        main_container.pack(fill="both", expand=True, padx=12, pady=(4, 8))

        left_col = ctk.CTkFrame(main_container, fg_color="transparent", corner_radius=0, width=360)
        left_col.pack(side="left", fill="both", expand=False, padx=(0, 6))
        left_col.pack_propagate(False)

        self._build_input_section(left_col)
        self._build_task_list_section(left_col)

        right_col = ctk.CTkFrame(main_container, fg_color="transparent", corner_radius=0)
        right_col.pack(side="left", fill="both", expand=True, padx=(6, 0))

        self._build_session_section(right_col)

        self._build_controls()

    def _build_input_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="#161b22", corner_radius=8)
        frame.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(frame, text="ADD / EDIT TASK", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#8b949e").pack(anchor="w", padx=12, pady=(10, 6))

        self._name_entry = ctk.CTkEntry(frame, placeholder_text="Task name...", height=34,
                                        font=ctk.CTkFont(size=13))
        self._name_entry.pack(fill="x", padx=12, pady=(0, 6))

        duration_row = ctk.CTkFrame(frame, fg_color="transparent", corner_radius=0)
        duration_row.pack(fill="x", padx=12, pady=(0, 6))

        self._duration_var = tk.StringVar(value="30m")
        self._duration_menu = ctk.CTkOptionMenu(duration_row, values=DURATION_OPTIONS,
                                                variable=self._duration_var, width=90,
                                                font=ctk.CTkFont(size=12))
        self._duration_menu.pack(side="left")

        ctk.CTkLabel(duration_row, text="", width=4).pack(side="left")

        self._custom_duration = ctk.CTkEntry(duration_row, placeholder_text="custom min",
                                             width=80, font=ctk.CTkFont(size=12))
        self._custom_duration.pack(side="left")

        btn_row = ctk.CTkFrame(frame, fg_color="transparent", corner_radius=0)
        btn_row.pack(fill="x", padx=12, pady=(0, 10))

        self._add_btn = ctk.CTkButton(btn_row, text="Add Task", width=90, height=30,
                                      corner_radius=6, font=ctk.CTkFont(size=12),
                                      command=self._add_task)
        self._add_btn.pack(side="left", padx=(0, 6))

        self._update_btn = ctk.CTkButton(btn_row, text="Update", width=70, height=30,
                                         corner_radius=6, font=ctk.CTkFont(size=12),
                                         fg_color="#21262d", hover_color="#30363d",
                                         command=self._update_task)
        self._update_btn.pack(side="left", padx=(0, 6))

        self._clear_btn = ctk.CTkButton(btn_row, text="Clear", width=60, height=30,
                                        corner_radius=6, font=ctk.CTkFont(size=12),
                                        fg_color="#21262d", hover_color="#30363d",
                                        command=self._clear_selection)
        self._clear_btn.pack(side="left")

    def _build_task_list_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="#161b22", corner_radius=8)
        frame.pack(fill="both", expand=True)

        list_header = ctk.CTkFrame(frame, fg_color="transparent", corner_radius=0)
        list_header.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(list_header, text="TASKS", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#8b949e").pack(side="left")
        self._task_count_label = ctk.CTkLabel(list_header, text="",
                                              font=ctk.CTkFont(size=10), text_color="#484f58")
        self._task_count_label.pack(side="right")

        self._task_scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent", corner_radius=0)
        self._task_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _build_session_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="#161b22", corner_radius=8)
        frame.pack(fill="both", expand=True)

        ctk.CTkLabel(frame, text="SESSION", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#8b949e").pack(anchor="w", padx=12, pady=(10, 4))

        self._current_task_label = ctk.CTkLabel(frame, text="No active session",
                                                font=ctk.CTkFont(size=14, weight="bold"),
                                                text_color="#c9d1d9", anchor="w")
        self._current_task_label.pack(fill="x", padx=12, pady=(6, 4))

        self._progress_bar = ctk.CTkProgressBar(frame, height=6, corner_radius=3,
                                                fg_color="#21262d", progress_color="#58a6ff")
        self._progress_bar.pack(fill="x", padx=12, pady=(4, 4))
        self._progress_bar.set(0)

        self._remaining_label = ctk.CTkLabel(frame, text="", font=ctk.CTkFont(size=24, weight="bold"),
                                             text_color="#e6edf3")
        self._remaining_label.pack(pady=(4, 0))

        self._next_task_label = ctk.CTkLabel(frame, text="",
                                             font=ctk.CTkFont(size=12), text_color="#484f58")
        self._next_task_label.pack(pady=(2, 0))

        self._status_label = ctk.CTkLabel(frame, text="Ready",
                                          font=ctk.CTkFont(size=11), text_color="#484f58")
        self._status_label.pack(pady=(8, 4))

        spacer = ctk.CTkFrame(frame, fg_color="transparent", corner_radius=0)
        spacer.pack(fill="both", expand=True)

        ctk.CTkLabel(frame, text="Total session time:", font=ctk.CTkFont(size=10),
                     text_color="#484f58").pack(anchor="w", padx=12, pady=(0, 0))
        self._total_time_label = ctk.CTkLabel(frame, text="",
                                              font=ctk.CTkFont(size=13), text_color="#8b949e",
                                              anchor="w")
        self._total_time_label.pack(fill="x", padx=12, pady=(0, 10))

    def _build_controls(self):
        control_bar = ctk.CTkFrame(self, fg_color="#161b22", corner_radius=8, height=48)
        control_bar.pack(fill="x", padx=12, pady=(0, 10))

        self._start_btn = ctk.CTkButton(control_bar, text="Start", width=80, height=32,
                                        corner_radius=6, font=ctk.CTkFont(size=13, weight="bold"),
                                        command=self._start_session)
        self._start_btn.pack(side="left", padx=(10, 4), pady=8)

        self._pause_btn = ctk.CTkButton(control_bar, text="Pause", width=70, height=32,
                                        corner_radius=6, font=ctk.CTkFont(size=12),
                                        fg_color="#21262d", hover_color="#30363d",
                                        state="disabled", command=self._pause_session)
        self._pause_btn.pack(side="left", padx=4, pady=8)

        self._skip_btn = ctk.CTkButton(control_bar, text="Skip", width=60, height=32,
                                       corner_radius=6, font=ctk.CTkFont(size=12),
                                       fg_color="#21262d", hover_color="#30363d",
                                       state="disabled", command=self._skip_task)
        self._skip_btn.pack(side="left", padx=4, pady=8)

        self._reset_btn = ctk.CTkButton(control_bar, text="Reset", width=60, height=32,
                                        corner_radius=6, font=ctk.CTkFont(size=12),
                                        fg_color="#21262d", hover_color="#30363d",
                                        command=self._reset_session)
        self._reset_btn.pack(side="left", padx=4, pady=8)

        ctk.CTkFrame(control_bar, fg_color="transparent", corner_radius=0).pack(
            side="left", fill="x", expand=True)

        self._widget_toggle = ctk.CTkSwitch(control_bar, text="Widget",
                                            variable=self._widget_visible,
                                            font=ctk.CTkFont(size=12),
                                            command=self._toggle_widget)
        self._widget_toggle.pack(side="right", padx=(0, 14), pady=8)

    def _refresh_task_list(self):
        for row in self._task_rows:
            row.destroy()
        self._task_rows.clear()

        for i, task in enumerate(self._tasks):
            row = TaskRow(
                self._task_scroll, i, task,
                on_select=self._select_task,
                on_delete=lambda idx=i: self._delete_task(idx),
                on_move_up=lambda idx=i: self._move_task_up(idx),
                on_move_down=lambda idx=i: self._move_task_down(idx),
            )
            row.pack(fill="x", pady=1)
            self._task_rows.append(row)
            if i == self._selected_index:
                row.set_selected(True)

        count = len(self._tasks)
        self._task_count_label.configure(text=f"{count} task{'s' if count != 1 else ''}")
        self._update_total_time()

    def _select_task(self, index: int):
        self._selected_index = index
        for i, row in enumerate(self._task_rows):
            row.set_selected(i == index)
        if 0 <= index < len(self._tasks):
            task = self._tasks[index]
            self._name_entry.delete(0, "end")
            self._name_entry.insert(0, task.name)
            self._duration_var.set(format_duration(task.duration_minutes))
        self._custom_duration.delete(0, "end")

    def _clear_selection(self):
        self._selected_index = -1
        for row in self._task_rows:
            row.set_selected(False)
        self._name_entry.delete(0, "end")
        self._duration_var.set("30m")
        self._custom_duration.delete(0, "end")

    def _get_duration_minutes(self) -> int:
        custom = self._custom_duration.get().strip()
        if custom and custom.isdigit():
            return max(1, int(custom))
        return parse_duration(self._duration_var.get())

    def _add_task(self):
        name = self._name_entry.get().strip()
        if not name:
            return
        minutes = self._get_duration_minutes()
        self._tasks.append(Task(name=name, duration_minutes=minutes))
        self._clear_selection()
        self._name_entry.delete(0, "end")
        self._refresh_task_list()
        self._save()

    def _update_task(self):
        if self._selected_index < 0 or self._selected_index >= len(self._tasks):
            return
        name = self._name_entry.get().strip()
        if not name:
            return
        self._tasks[self._selected_index].name = name
        self._tasks[self._selected_index].duration_minutes = self._get_duration_minutes()
        self._refresh_task_list()
        self._save()

    def _delete_task(self, index: int):
        if 0 <= index < len(self._tasks):
            del self._tasks[index]
            if self._selected_index == index:
                self._clear_selection()
            elif self._selected_index > index:
                self._selected_index -= 1
            self._refresh_task_list()
            self._save()

    def _move_task_up(self, index: int):
        if index > 0:
            self._tasks[index], self._tasks[index - 1] = self._tasks[index - 1], self._tasks[index]
            if self._selected_index == index:
                self._selected_index -= 1
            elif self._selected_index == index - 1:
                self._selected_index += 1
            self._refresh_task_list()
            self._save()

    def _move_task_down(self, index: int):
        if index < len(self._tasks) - 1:
            self._tasks[index], self._tasks[index + 1] = self._tasks[index + 1], self._tasks[index]
            if self._selected_index == index:
                self._selected_index += 1
            elif self._selected_index == index + 1:
                self._selected_index -= 1
            self._refresh_task_list()
            self._save()

    def _update_total_time(self):
        total = sum(t.duration_minutes for t in self._tasks)
        self._total_time_label.configure(text=format_duration(total))

    def _save(self):
        Storage.save_tasks(self._tasks)

    def _create_widget(self, x=100, y=100):
        if self._widget is None:
            self._widget = DrifterWidget(self)
            self._widget.geometry(f"320x100+{x}+{y}")

    def _show_widget(self):
        if self._widget is None:
            self._create_widget()
        self._widget.deiconify()
        self._widget.lift()
        self._widget_visible.set(True)

    def _hide_widget(self):
        if self._widget:
            self._widget.withdraw()
        self._widget_visible.set(False)

    def _toggle_widget(self):
        if self._widget_visible.get():
            self._show_widget()
        else:
            self._hide_widget()

    def _start_session(self):
        if not self._tasks:
            return
        self._timer_running = True
        self._timer_paused = False
        self._current_task_idx = 0
        self._session_start = __import__("time").time()
        self._task_start = self._session_start
        self._current_elapsed = 0

        self._start_btn.configure(state="disabled", fg_color="#21262d")
        self._pause_btn.configure(state="normal", text="Pause", fg_color="#21262d")
        self._skip_btn.configure(state="normal")
        self._reset_btn.configure(state="normal")
        self._status_label.configure(text="Running", text_color="#58a6ff")

        self._update_session_display()
        if self._widget and self._widget_visible.get():
            self._widget.deiconify()
            self._widget.lift()
        self._tick()

    def _pause_session(self):
        if not self._timer_running:
            return
        if self._timer_paused:
            self._timer_paused = False
            self._task_start = __import__("time").time() - self._current_elapsed
            self._pause_btn.configure(text="Pause")
            self._status_label.configure(text="Running", text_color="#58a6ff")
            self._update_session_display()
            if self._widget:
                self._update_widget()
            self._tick()
        else:
            self._timer_paused = True
            if self._after_id:
                self.after_cancel(self._after_id)
                self._after_id = None
            self._current_elapsed = int(__import__("time").time() - self._task_start)
            self._pause_btn.configure(text="Resume", fg_color="#1f6feb")
            self._status_label.configure(text="Paused", text_color="#f0883e")
            self._update_session_display()
            if self._widget:
                self._update_widget()

    def _skip_task(self):
        if not self._timer_running:
            return
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None
        self._current_task_idx += 1
        if self._current_task_idx >= len(self._tasks):
            self._complete_session()
            return
        self._task_start = __import__("time").time()
        self._current_elapsed = 0
        self._update_session_display()
        if self._widget:
            self._update_widget()
        self._tick()

    def _reset_session(self):
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None
        self._timer_running = False
        self._timer_paused = False
        self._current_task_idx = 0
        self._current_elapsed = 0

        self._start_btn.configure(state="normal", fg_color="#238636")
        self._pause_btn.configure(state="disabled", text="Pause", fg_color="#21262d")
        self._skip_btn.configure(state="disabled")
        self._reset_btn.configure(state="normal", fg_color="#21262d")
        self._status_label.configure(text="Ready", text_color="#484f58")
        self._current_task_label.configure(text="No active session")
        self._remaining_label.configure(text="")
        self._next_task_label.configure(text="")
        self._progress_bar.set(0)
        if self._widget:
            self._widget.update_display("No active task", 1, 0, "", False)

    def _complete_session(self):
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None
        self._timer_running = False
        self._timer_paused = False
        self._start_btn.configure(state="normal", fg_color="#238636")
        self._pause_btn.configure(state="disabled", text="Pause", fg_color="#21262d")
        self._skip_btn.configure(state="disabled")
        self._status_label.configure(text="All tasks complete!", text_color="#3fb950")
        self._current_task_label.configure(text="Session finished")
        self._remaining_label.configure(text="")
        self._next_task_label.configure(text="")
        self._progress_bar.set(1.0)
        if self._widget:
            self._widget.update_display("Done!", 1, 1, "", False)

    def _tick(self):
        if not self._timer_running or self._timer_paused:
            return

        if self._current_task_idx >= len(self._tasks):
            self._complete_session()
            return

        task = self._tasks[self._current_task_idx]
        total_seconds = task.duration_minutes * 60
        now = __import__("time").time()
        elapsed = int(now - self._task_start)

        if elapsed >= total_seconds:
            self._current_task_idx += 1
            if self._current_task_idx >= len(self._tasks):
                self._complete_session()
                return
            self._task_start = now
            elapsed = 0

        self._current_elapsed = elapsed
        self._update_session_display()
        if self._widget:
            self._update_widget()

        self._after_id = self.after(1000, self._tick)

    def _update_session_display(self):
        if not self._timer_running or self._current_task_idx >= len(self._tasks):
            return

        task = self._tasks[self._current_task_idx]
        total_seconds = task.duration_minutes * 60
        remaining = max(0, total_seconds - self._current_elapsed)
        progress = self._current_elapsed / total_seconds if total_seconds > 0 else 0

        status = "Paused" if self._timer_paused else "Running"
        status_color = "#f0883e" if self._timer_paused else "#58a6ff"

        self._current_task_label.configure(
            text=f"{self._current_task_idx + 1}. {task.name}")

        total_task_seconds = task.duration_minutes * 60
        self._remaining_label.configure(
            text=format_time_remaining(total_task_seconds, self._current_elapsed))

        next_idx = self._current_task_idx + 1
        if next_idx < len(self._tasks):
            self._next_task_label.configure(text=f"Next: {self._tasks[next_idx].name}")
        else:
            self._next_task_label.configure(text="Last task")

        self._progress_bar.set(min(1.0, progress))
        self._status_label.configure(text=status, text_color=status_color)

    def _update_widget(self):
        if not self._widget or not self._widget_visible.get():
            return
        if self._current_task_idx >= len(self._tasks):
            return
        task = self._tasks[self._current_task_idx]
        total_seconds = task.duration_minutes * 60
        next_name = ""
        next_idx = self._current_task_idx + 1
        if next_idx < len(self._tasks):
            next_name = self._tasks[next_idx].name
        self._widget.update_display(
            task.name, total_seconds, self._current_elapsed,
            next_name, self._timer_paused
        )

    def quit_app(self):
        if self._after_id:
            self.after_cancel(self._after_id)
        settings = {
            "widget_visible": self._widget_visible.get(),
            "widget_x": self._widget._last_x if self._widget else 100,
            "widget_y": self._widget._last_y if self._widget else 100,
        }
        Storage.save_settings(settings)
        self._save()
        if self._widget:
            self._widget.destroy()
        self.destroy()


def main():
    app = DrifterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
