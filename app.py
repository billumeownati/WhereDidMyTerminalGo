import os
import sys
import subprocess
import threading
import ctypes
import time
import tkinter as tk
from tkinter import filedialog, messagebox, font as tkfont
from pathlib import Path

import pystray
from PIL import Image, ImageTk


APP_NAME = "WhereDidMyTerminalGo"
APP_VERSION = "2026.1"

# ---------- Theme ----------
BG = "#080C11"
SURFACE = "#0F151D"
SURFACE_2 = "#141C26"
SURFACE_HOVER = "#1A2531"
BORDER = "#202C39"
DIVIDER = "#17222D"

TEXT = "#F6F9FC"
SECONDARY = "#DCE5EE"
MUTED = "#98A7B6"
SUBTLE = "#71808F"

ACCENT = "#5AA9FF"
ACCENT_HOVER = "#79B9FF"
ACCENT_PRESSED = "#368FEF"

SUCCESS = "#43E0A0"
DANGER = "#FF6672"
DANGER_HOVER = "#FF7E88"
WARNING = "#F6C35B"

INPUT_BG = "#0A1017"
INPUT_BORDER = "#2A3948"
INPUT_FOCUS = "#5AA9FF"

CMD_NOT_FOUND = 9009
STARTUP_GRACE_MS = 1600


def resource_path(filename):
    """Return an asset path both in development and PyInstaller."""
    if getattr(sys, "frozen", False):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parent
    return base_path / filename


def get_log_directory():
    """Keep logs outside the temporary PyInstaller one-file extraction folder."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home()
    path = base / APP_NAME / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def set_windows_app_id():
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_NAME)
    except Exception:
        pass


def enable_dark_title_bar(hwnd):
    if sys.platform != "win32":
        return
    try:
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            20,  # DWMWA_USE_IMMERSIVE_DARK_MODE
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except Exception:
        pass


def safe_icon_image(path, size=(36, 36)):
    try:
        image = Image.open(path).convert("RGBA")
        image.thumbnail(size, Image.Resampling.LANCZOS)
        return image
    except Exception:
        return None


class BackgroundRunner:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1040x900")
        self.root.minsize(960, 820)
        self.root.configure(bg=BG)

        set_windows_app_id()

        self.processes = []
        self.stopping = False
        self.tray_icon = None
        self.command_widgets = []
        self.error_shown_pids = set()
        self.command_area_pointer_inside = False

        self.log_dir = get_log_directory()
        self.directory_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready to launch")
        self.command_count_var = tk.StringVar(value="2 commands")

        self.commands = [
            {"name": "Application / API", "command": "uv run src/main.py"},
            {"name": "Tunnel", "command": "cloudflared tunnel run"},
        ]

        # Window icon
        icon_path = resource_path("icon.ico")
        if icon_path.exists():
            try:
                self.root.iconbitmap(str(icon_path))
            except Exception:
                pass

        self.root.update_idletasks()
        enable_dark_title_bar(self.root.winfo_id())

        self._build_ui()
        self._setup_tray()

        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.root.after(500, self.refresh_status)

    # ---------- UI ----------
    def font(self, size=10, weight="normal"):
        families = set(tkfont.families(self.root))
        family = "Segoe UI Variable" if "Segoe UI Variable" in families else "Segoe UI"
        return (family, size, weight)

    def make_entry(self, parent, variable, mono=False, height_pad=8):
        entry = tk.Entry(
            parent,
            textvariable=variable,
            bg=INPUT_BG,
            fg=TEXT,
            insertbackground=TEXT,
            selectbackground="#24538A",
            selectforeground="#FFFFFF",
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=INPUT_BORDER,
            highlightcolor=INPUT_FOCUS,
            font=("Cascadia Mono", 10) if mono else self.font(10),
        )
        entry.pack_configure(ipady=height_pad) if False else None
        return entry

    def button(self, parent, text, command, bg, hover, fg=TEXT, width=110, height=36):
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=hover,
            activeforeground=fg,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=self.font(10, "bold"),
            width=max(1, width // 9),
            height=1,
            padx=10,
            pady=max(3, (height - 28) // 2),
        )

        def enter(_):
            if str(btn["state"]) != "disabled":
                btn.configure(bg=hover)

        def leave(_):
            btn.configure(bg=bg if str(btn["state"]) != "disabled" else SURFACE_2)

        btn.bind("<Enter>", enter)
        btn.bind("<Leave>", leave)
        return btn

    def _build_ui(self):
        # Use a grid-based root layout so the action bar and footer always remain visible.
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        content = tk.Frame(self.root, bg=BG)
        content.grid(row=0, column=0, sticky="nsew", padx=44, pady=(28, 0))
        content.grid_rowconfigure(2, weight=1, minsize=360)
        content.grid_columnconfigure(0, weight=1)

        # Header
        header = tk.Frame(content, bg=BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 22))
        header.grid_columnconfigure(1, weight=1)

        logo_path = resource_path("icon.png")
        self.logo_photo = None
        logo = safe_icon_image(logo_path, (52, 52)) if logo_path.exists() else None
        if logo is not None:
            self.logo_photo = ImageTk.PhotoImage(logo)
            tk.Label(header, image=self.logo_photo, bg=BG, bd=0).grid(
                row=0, column=0, rowspan=2, padx=(0, 14), sticky="n"
            )

        tk.Label(
            header, text=APP_NAME, bg=BG, fg=TEXT,
            font=self.font(29, "bold"), anchor="w"
        ).grid(row=0, column=1, sticky="w")

        tk.Label(
            header,
            text="Run your development stack quietly, reliably and out of the way.",
            bg=BG, fg=MUTED, font=self.font(10), anchor="w"
        ).grid(row=1, column=1, sticky="w", pady=(3, 0))

        tk.Label(
            header, text="2026", bg=BG, fg=ACCENT,
            font=self.font(9, "bold")
        ).grid(row=0, column=2, sticky="ne", padx=(10, 2))

        # Project directory
        project = tk.Frame(content, bg=BG)
        project.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        project.grid_columnconfigure(0, weight=1)

        top = tk.Frame(project, bg=BG)
        top.pack(fill="x")
        tk.Label(
            top, text="PROJECT DIRECTORY", bg=BG, fg=MUTED,
            font=self.font(9, "bold")
        ).pack(side="left")
        tk.Label(
            top, text="Working directory for every command", bg=BG, fg=SUBTLE,
            font=self.font(9)
        ).pack(side="right")

        dir_row = tk.Frame(project, bg=BG)
        dir_row.pack(fill="x", pady=(8, 0))
        dir_row.grid_columnconfigure(0, weight=1)

        self.directory_entry = self.make_entry(dir_row, self.directory_var)
        self.directory_entry.grid(row=0, column=0, sticky="ew", ipady=10)

        self.button(
            dir_row, "Browse", self.choose_directory, SURFACE_2, SURFACE_HOVER,
            width=104, height=42
        ).grid(row=0, column=1, padx=(10, 0), sticky="e")

        # Commands section
        commands_section = tk.Frame(content, bg=SURFACE, bd=0, highlightthickness=0)
        commands_section.grid(row=2, column=0, sticky="nsew", pady=(0, 16))
        commands_section.grid_rowconfigure(2, weight=1)
        commands_section.grid_columnconfigure(0, weight=1)

        tk.Frame(commands_section, bg=ACCENT, height=3).grid(
            row=0, column=0, sticky="ew"
        )

        commands_header = tk.Frame(commands_section, bg=SURFACE)
        commands_header.grid(row=1, column=0, sticky="ew", padx=24, pady=(18, 12))
        commands_header.grid_columnconfigure(1, weight=1)

        title_wrap = tk.Frame(commands_header, bg=SURFACE)
        title_wrap.grid(row=0, column=0, sticky="w")

        tk.Label(
            title_wrap, text="BACKGROUND COMMANDS", bg=SURFACE, fg=TEXT,
            font=self.font(12, "bold")
        ).pack(side="left")
        tk.Label(
            title_wrap, text="  /  launch sequence", bg=SURFACE, fg=SUBTLE,
            font=self.font(9)
        ).pack(side="left", pady=(2, 0))

        tk.Label(
            commands_header, textvariable=self.command_count_var,
            bg=SURFACE, fg=MUTED, font=self.font(9, "bold")
        ).grid(row=0, column=2, sticky="e")

        tk.Label(
            commands_header,
            text="Every configured row must be valid before anything starts.",
            bg=SURFACE, fg=MUTED, font=self.font(9)
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(5, 0))

        area = tk.Frame(commands_section, bg=SURFACE)
        area.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 8))
        area.grid_rowconfigure(0, weight=1)
        area.grid_columnconfigure(0, weight=1)

        self.command_canvas = tk.Canvas(
            area, bg=SURFACE, highlightthickness=0, bd=0
        )
        self.command_canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(
            area, orient="vertical", command=self.command_canvas.yview,
            bg=SURFACE_2, troughcolor=SURFACE, activebackground="#3A4A5B",
            relief="flat", bd=0, width=9
        )
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(8, 0))

        self.command_canvas.configure(yscrollcommand=scrollbar.set)
        self.command_list = tk.Frame(self.command_canvas, bg=SURFACE)
        self.canvas_window = self.command_canvas.create_window(
            (0, 0), window=self.command_list, anchor="nw"
        )
        self.command_list.bind("<Configure>", self._update_command_scroll_region)
        self.command_canvas.bind("<Configure>", self._resize_command_canvas_window)
        self.command_canvas.bind("<Enter>", lambda _e: setattr(self, "command_area_pointer_inside", True))
        self.command_canvas.bind("<Leave>", lambda _e: setattr(self, "command_area_pointer_inside", False))
        self.command_canvas.bind("<MouseWheel>", self._mousewheel_commands)

        self.render_commands()

        add_row = tk.Frame(commands_section, bg=SURFACE)
        add_row.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 16))

        self.button(
            add_row, "+  Add command", self.add_command, SURFACE_2, SURFACE_HOVER,
            fg=SECONDARY, width=142, height=38
        ).pack(side="left")

        tk.Label(
            add_row, text="Tip: keep names short and commands copy-pasteable.",
            bg=SURFACE, fg=SUBTLE, font=self.font(8)
        ).pack(side="left", padx=(12, 0))

        # Action bar with guaranteed space.
        action = tk.Frame(self.root, bg=BG, height=88)
        action.grid(row=1, column=0, sticky="ew", padx=44, pady=(0, 8))
        action.grid_propagate(False)

        status = tk.Frame(action, bg=BG)
        status.pack(side="left", fill="y")

        self.status_dot = tk.Label(
            status, text="●", bg=BG, fg=DANGER, font=self.font(13, "bold")
        )
        self.status_dot.pack(side="left", pady=12)

        status_text_frame = tk.Frame(status, bg=BG)
        status_text_frame.pack(side="left", padx=(8, 0), pady=9)

        tk.Label(
            status_text_frame, textvariable=self.status_var, bg=BG, fg=TEXT,
            font=self.font(11, "bold")
        ).pack(anchor="w")

        tk.Label(
            status_text_frame, text="Processes stop automatically when you exit.",
            bg=BG, fg=SUBTLE, font=self.font(9)
        ).pack(anchor="w", pady=(2, 0))

        self.stop_button = self.button(
            action, "Stop All", self.stop_all, "#35191E", "#4A242B",
            fg="#FFDCE0", width=140, height=52
        )
        self.stop_button.pack(side="right", padx=(12, 0), pady=12)
        self.stop_button.config(state="disabled", disabledforeground="#6E5B60")

        self.start_button = self.button(
            action, "Start All", self.start_all, ACCENT, ACCENT_HOVER,
            fg="#07111A", width=140, height=52
        )
        self.start_button.pack(side="right", pady=12)

        # Footer
        footer = tk.Frame(self.root, bg=BG, height=42)
        footer.grid(row=2, column=0, sticky="ew", padx=44, pady=(0, 12))
        footer.grid_propagate(False)

        tk.Frame(footer, bg=DIVIDER, height=1).pack(fill="x", side="top")

        tk.Label(
            footer, text="Made by BiLLuMiNaTi", bg=BG, fg=SECONDARY,
            font=self.font(10, "bold")
        ).pack(side="left", pady=(8, 0))

        tk.Label(
            footer, text=f"v{APP_VERSION}  ·  2026", bg=BG, fg=SUBTLE,
            font=self.font(9)
        ).pack(side="right", pady=(9, 0))

    # ---------- Command list ----------
    def _update_command_scroll_region(self, _event=None):
        self.command_canvas.configure(scrollregion=self.command_canvas.bbox("all"))

    def _resize_command_canvas_window(self, event):
        self.command_canvas.itemconfigure(self.canvas_window, width=max(1, event.width))

    def _mousewheel_commands(self, event):
        if self.command_area_pointer_inside:
            self.command_canvas.yview_scroll(int(-event.delta / 120), "units")

    def render_commands(self):
        for widget in self.command_list.winfo_children():
            widget.destroy()

        self.command_widgets.clear()

        count = len(self.commands)
        self.command_count_var.set(f"{count} command" if count == 1 else f"{count} commands")

        for index, command in enumerate(self.commands):
            self.create_command_row(index, command)

        self.command_list.update_idletasks()
        self._update_command_scroll_region()

    def create_command_row(self, index, command):
        row = tk.Frame(
            self.command_list,
            bg=SURFACE_2,
            highlightthickness=0,
            bd=0,
        )
        row.pack(fill="x", pady=(0, 7))

        top = tk.Frame(row, bg=SURFACE_2)
        top.pack(fill="x", padx=14, pady=(10, 5))
        top.grid_columnconfigure(1, weight=1)

        tk.Label(
            top,
            text=f"{index + 1:02d}",
            bg=ACCENT,
            fg="#06111A",
            font=self.font(8, "bold"),
            padx=8,
            pady=3,
        ).grid(row=0, column=0, sticky="w")

        name_var = tk.StringVar(value=command["name"])
        command_var = tk.StringVar(value=command["command"])

        name_entry = tk.Entry(
            top,
            textvariable=name_var,
            bg=SURFACE_2,
            fg=TEXT,
            insertbackground=TEXT,
            selectbackground="#24538A",
            selectforeground="#FFFFFF",
            relief="flat",
            bd=0,
            font=self.font(10, "bold"),
        )
        name_entry.grid(row=0, column=1, sticky="ew", padx=(10, 8), ipady=2)

        self.button(
            top,
            "Delete",
            lambda i=index: self.delete_command(i),
            "#2A161B",
            "#3F2027",
            fg="#FFC4CA",
            width=72,
            height=30,
        ).grid(row=0, column=2, sticky="e")

        tk.Label(
            row,
            text="COMMAND",
            bg=SURFACE_2,
            fg=SUBTLE,
            font=self.font(8, "bold"),
        ).pack(anchor="w", padx=14, pady=(2, 4))

        command_entry = self.make_entry(row, command_var, mono=True)
        command_entry.pack(fill="x", padx=14, pady=(0, 11), ipady=8)

        self.command_widgets.append({
            "name_var": name_var,
            "command_var": command_var,
        })

    def add_command(self):
        self.commands.append({
            "name": f"Command {len(self.commands) + 1}",
            "command": "",
        })
        self.render_commands()
        self.command_canvas.after(50, lambda: self.command_canvas.yview_moveto(1.0))

    def delete_command(self, index):
        if self.processes:
            messagebox.showwarning(
                APP_NAME,
                "Stop all running commands before editing the command list.",
            )
            return

        command = self.commands[index]
        if not messagebox.askyesno(APP_NAME, f"Delete '{command['name']}'?"):
            return

        self.commands.pop(index)
        self.render_commands()

    # ---------- Validation ----------
    def collect_commands(self):
        """Return commands only after validating every configured row."""
        collected = []
        errors = []

        for index, widget in enumerate(self.command_widgets):
            name = widget["name_var"].get().strip()
            command = widget["command_var"].get().strip()

            if not name:
                errors.append(f"Command {index + 1}: name is empty.")

            if not command:
                errors.append(f"Command {index + 1} ({name or 'Unnamed'}): command is blank.")

            collected.append((name or f"Command {index + 1}", command))

            if index < len(self.commands):
                self.commands[index]["name"] = name or f"Command {index + 1}"
                self.commands[index]["command"] = command

        if errors:
            return None, errors

        return collected, []

    # ---------- Process management ----------
    def _write_log_handle(self, name, command):
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip() or "command"
        log_path = self.log_dir / f"{safe_name}.log"
        f = open(log_path, "a", encoding="utf-8", buffering=1)
        f.write("\n\n")
        f.write(f"===== START: {command} =====\n")
        f.flush()
        return f, log_path

    def _launch(self, name, command, cwd):
        command = command.strip()
        if not command:
            raise ValueError(f"{name}: command is empty.")

        log_handle, log_path = self._write_log_handle(name, command)

        try:
            # Invoke cmd.exe explicitly so Windows command resolution behaves
            # like a normal terminal, including PATH tools, .cmd/.bat files,
            # pipes, redirection, &&, quoted arguments, etc.
            proc = subprocess.Popen(
                ["cmd.exe", "/d", "/s", "/c", command],
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
                shell=False,
                text=True,
                env=os.environ.copy(),
            )
        except FileNotFoundError as exc:
            try:
                log_handle.close()
            except Exception:
                pass
            raise RuntimeError(
                f"Windows could not start '{name}'.\n\n"
                f"Command:\n{command}\n\nDetails:\n{exc}"
            ) from exc
        except PermissionError as exc:
            try:
                log_handle.close()
            except Exception:
                pass
            raise RuntimeError(
                f"Permission was denied while starting '{name}'.\n\n"
                f"Command:\n{command}\n\nDetails:\n{exc}"
            ) from exc
        except Exception as exc:
            try:
                log_handle.close()
            except Exception:
                pass
            raise RuntimeError(
                f"Could not start '{name}'.\n\nCommand:\n{command}\n\nDetails:\n{exc}"
            ) from exc

        item = {
            "name": name,
            "command": command,
            "proc": proc,
            "log_handle": log_handle,
            "log_path": log_path,
        }
        self.processes.append(item)
        return item

    def _wait_for_startup(self, item, timeout_ms=1500):
        """Wait briefly for a command to prove it stayed alive.

        This catches missing executables, invalid commands and immediate
        startup failures before the next configured command is launched.
        """
        proc = item["proc"]
        start_time = time.monotonic()

        while (time.monotonic() - start_time) * 1000 < timeout_ms:
            return_code = proc.poll()
            if return_code is not None:
                return return_code

            # Keep Tk responsive while we wait.
            self.root.update_idletasks()
            self.root.update()
            time.sleep(0.05)

        return None

    def start_all(self):
        if any(item["proc"].poll() is None for item in self.processes):
            return

        self._cleanup_finished_processes()

        directory = self.directory_var.get().strip()
        if not directory:
            messagebox.showwarning(APP_NAME, "Choose a project directory first.")
            return

        cwd = Path(directory)
        if not cwd.is_dir():
            messagebox.showerror(APP_NAME, "The selected project directory does not exist.")
            return

        commands, errors = self.collect_commands()
        if errors:
            messagebox.showerror(
                f"{APP_NAME} — Fix Commands",
                "Every configured command must be complete before anything starts.\n\n"
                + "\n".join(f"• {error}" for error in errors),
            )
            return

        self.error_shown_pids.clear()
        self.status_dot.config(fg=ACCENT)
        self.status_var.set("Starting…")
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.root.update_idletasks()

        started = []
        try:
            for name, command in commands:
                item = self._launch(name, command, cwd)

                return_code = self._wait_for_startup(item, timeout_ms=STARTUP_GRACE_MS)
                if return_code is not None:
                    if return_code != 0:
                        # Show the real command output once, then stop anything
                        # that may already have been started.
                        self.show_process_error(item, immediate=True)
                        self.stop_all()
                        return
                    # A command that exits successfully is still a valid command.
                    # Continue to the next configured command.

                started.append(name)

            count = len(started)
            self.status_dot.config(fg=SUCCESS)
            self.status_var.set(f"Running · {count} command" + ("" if count == 1 else "s"))

        except Exception as exc:
            self.stop_all()
            self.status_dot.config(fg=DANGER)
            messagebox.showerror(
                f"{APP_NAME} — Start Error",
                f"Could not start the command sequence.\n\n{exc}",
            )

    def stop_all(self):
        self.stopping = True

        for item in list(self.processes):
            proc = item["proc"]
            if proc.poll() is None:
                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        check=False,
                    )
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

        for item in self.processes:
            try:
                item["log_handle"].write("===== STOPPED =====\n")
                item["log_handle"].close()
            except Exception:
                pass

        self.processes.clear()
        self.status_dot.config(fg=DANGER)
        self.status_var.set("Ready to launch")
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self.stopping = False

    def _cleanup_finished_processes(self):
        remaining = []
        for item in self.processes:
            if item["proc"].poll() is None:
                remaining.append(item)
            else:
                try:
                    item["log_handle"].close()
                except Exception:
                    pass
        self.processes = remaining

    def _read_log_tail(self, log_path, max_chars=3500):
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            if len(content) <= max_chars:
                return content
            return f"…(showing last {max_chars} characters)…\n\n{content[-max_chars:]}"
        except Exception as exc:
            return f"Could not read log file:\n{exc}"

    def show_process_error(self, item, immediate=False):
        proc = item["proc"]
        pid = proc.pid
        return_code = proc.poll()

        if return_code is None:
            return
        if pid in self.error_shown_pids and not immediate:
            return

        self.error_shown_pids.add(pid)
        try:
            item["log_handle"].flush()
        except Exception:
            pass

        output = self._read_log_tail(item["log_path"])
        if return_code == CMD_NOT_FOUND:
            explanation = (
                "Windows reported that the command could not be found. "
                "Check the command name and PATH available to this app."
            )
        else:
            explanation = f"The command exited with code {return_code}."

        messagebox.showerror(
            f"{APP_NAME} — Command Failed",
            f"{item['name']}\n\n"
            f"Command:\n{item['command']}\n\n"
            f"{explanation}\n\n"
            f"Output:\n{output}\n\n"
            f"Log file:\n{item['log_path']}",
        )

    def refresh_status(self):
        if not self.stopping and self.processes:
            running_count = 0
            failed_count = 0

            for item in list(self.processes):
                proc = item["proc"]
                return_code = proc.poll()

                if return_code is None:
                    running_count += 1
                    continue

                if return_code != 0:
                    failed_count += 1
                    self.show_process_error(item)

                try:
                    item["log_handle"].flush()
                    item["log_handle"].close()
                except Exception:
                    pass

            if running_count == 0:
                self.processes.clear()
                self.status_dot.config(fg=DANGER if failed_count else DANGER)
                self.status_var.set(
                    f"Stopped · {failed_count} failed" if failed_count else "Stopped · Commands finished"
                )
                self.start_button.config(state="normal")
                self.stop_button.config(state="disabled")
            else:
                self.status_dot.config(fg=SUCCESS)
                self.status_var.set(
                    f"Running · {running_count} active"
                    + (f" · {failed_count} failed" if failed_count else "")
                )

        self.root.after(500, self.refresh_status)

    # ---------- Window / tray ----------
    def choose_directory(self):
        path = filedialog.askdirectory(title="Choose your project directory")
        if path:
            self.directory_var.set(path)

    def hide_to_tray(self):
        self.root.withdraw()

    def show_window(self):
        self.root.after(0, self._show_window)

    def _show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(100, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

    def _make_tray_image(self):
        png_path = resource_path("icon.png")
        if png_path.exists():
            try:
                return Image.open(png_path).convert("RGBA")
            except Exception:
                pass

        ico_path = resource_path("icon.ico")
        if ico_path.exists():
            try:
                return Image.open(ico_path).convert("RGBA")
            except Exception:
                pass

        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image) if False else None
        return image

    def _setup_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Open", lambda icon, item: self.show_window(), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start", lambda icon, item: self.start_all()),
            pystray.MenuItem("Stop", lambda icon, item: self.stop_all()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", lambda icon, item: self.exit_app()),
        )

        self.tray_icon = pystray.Icon(
            APP_NAME,
            self._make_tray_image(),
            APP_NAME,
            menu,
        )

        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def exit_app(self):
        self.stop_all()
        try:
            if self.tray_icon:
                self.tray_icon.stop()
        finally:
            self.root.after(0, self.root.destroy)


def main():
    set_windows_app_id()
    root = tk.Tk()
    BackgroundRunner(root)
    root.mainloop()


if __name__ == "__main__":
    main()
