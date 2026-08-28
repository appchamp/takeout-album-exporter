"""Tkinter application for photo-date-restore."""
from __future__ import annotations

import queue
import threading
import traceback
from typing import Optional

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .. import pipeline, report
from ..exiftool_client import ExifToolError
from . import support


class PhotoDateRestoreApp:
    """A small GUI wrapper around the existing pipeline."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Photo Date Restore")
        self.root.minsize(720, 600)
        self.events: queue.Queue = queue.Queue()
        self.running_settings: Optional[support.GuiSettings] = None
        self.cancel_event: Optional[threading.Event] = None
        self.quit_when_idle = False

        self.input_dir = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.dry_run = tk.BooleanVar(value=True)
        self.verbose = tk.BooleanVar(value=True)
        self.timezone = tk.StringVar()
        self.overwrite_output = tk.BooleanVar(value=False)
        self.write_report = tk.BooleanVar(value=False)
        self.report_path = tk.StringVar()
        self.report_format = tk.StringVar(value="csv")
        self.status = tk.StringVar(value="Ready.")

        self._build_widgets()
        self._install_about_menu()
        self._set_report_widgets_state()
        self._check_exiftool_at_startup()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._drain_queue)

    def _build_widgets(self) -> None:
        container = ttk.Frame(self.root, padding=12)
        container.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(5, weight=1)

        ttk.Label(container, text="Input folder").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(container, textvariable=self.input_dir).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(container, text="Select...", command=self._select_input).grid(row=0, column=2, padx=(8, 0), pady=4)

        ttk.Label(container, text="Output folder").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(container, textvariable=self.output_dir).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(container, text="Select...", command=self._select_output).grid(row=1, column=2, padx=(8, 0), pady=4)

        options = ttk.LabelFrame(container, text="Options", padding=10)
        options.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 8))
        options.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            options, text="Dry run (analyze only, write nothing)", variable=self.dry_run
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=2)
        ttk.Checkbutton(
            options, text="Verbose output (show each processed file)", variable=self.verbose
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=2)
        ttk.Label(options, text="Timezone (optional, e.g. Asia/Tokyo)").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(options, textvariable=self.timezone).grid(row=2, column=1, columnspan=2, sticky="ew", pady=2)
        ttk.Checkbutton(
            options, text="Overwrite existing files in output folder", variable=self.overwrite_output
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=2)
        ttk.Checkbutton(
            options, text="Save audit report", variable=self.write_report,
            command=self._set_report_widgets_state,
        ).grid(row=4, column=0, sticky="w", pady=2)
        self.report_entry = ttk.Entry(options, textvariable=self.report_path)
        self.report_entry.grid(row=4, column=1, sticky="ew", pady=2)
        self.report_select = ttk.Button(options, text="Select...", command=self._select_report)
        self.report_select.grid(row=4, column=2, padx=(8, 0), pady=2)
        self.report_format_box = ttk.Combobox(
            options, textvariable=self.report_format, values=("csv", "jsonl"), state="readonly", width=8,
        )
        self.report_format_box.grid(row=4, column=3, padx=(8, 0), pady=2)

        buttons = ttk.Frame(container)
        buttons.grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.start_button = ttk.Button(buttons, text="Start", command=self._start)
        self.start_button.grid(row=0, column=0, padx=(0, 8))
        self.cancel_button = ttk.Button(
            buttons, text="Cancel", command=self._cancel, state="disabled",
        )
        self.cancel_button.grid(row=0, column=1, padx=(0, 8))
        self.open_output_button = ttk.Button(
            buttons, text="Open Output Folder", command=self._open_output, state="disabled",
        )
        self.open_output_button.grid(row=0, column=2)

        ttk.Label(container, textvariable=self.status).grid(row=4, column=0, sticky="w", pady=(0, 4))
        self.progress = ttk.Progressbar(container, mode="indeterminate")
        self.progress.grid(row=4, column=1, columnspan=2, sticky="ew", pady=(0, 4))
        self.log = scrolledtext.ScrolledText(container, state="disabled", wrap="word", height=18)
        self.log.grid(row=5, column=0, columnspan=3, sticky="nsew")

    def _settings(self) -> support.GuiSettings:
        return support.GuiSettings(
            input_dir=self.input_dir.get(),
            output_dir=self.output_dir.get(),
            dry_run=self.dry_run.get(),
            verbose=self.verbose.get(),
            timezone=self.timezone.get(),
            overwrite_output=self.overwrite_output.get(),
            write_report=self.write_report.get(),
            report_path=self.report_path.get(),
            report_format=self.report_format.get(),
        )

    def _install_about_menu(self) -> None:
        """Wire the macOS application About item and a portable Help fallback."""
        try:
            self.root.createcommand("tkAboutDialog", self._show_about)
        except tk.TclError:
            pass
        menubar = tk.Menu(self.root)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(
            label=f"About {support.APP_DISPLAY_NAME}", command=self._show_about
        )
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.configure(menu=menubar)

    def _show_about(self) -> None:
        messagebox.showinfo(
            f"About {support.APP_DISPLAY_NAME}", "\n".join(support.about_lines())
        )

    def _set_report_widgets_state(self) -> None:
        state = "normal" if self.write_report.get() else "disabled"
        self.report_entry.configure(state=state)
        self.report_select.configure(state=state)
        self.report_format_box.configure(state="readonly" if self.write_report.get() else "disabled")

    def _select_input(self) -> None:
        value = filedialog.askdirectory()
        if value:
            self.input_dir.set(value)

    def _select_output(self) -> None:
        value = filedialog.askdirectory()
        if value:
            self.output_dir.set(value)

    def _select_report(self) -> None:
        value = filedialog.asksaveasfilename(
            defaultextension=f".{self.report_format.get()}",
            filetypes=(("CSV", "*.csv"), ("JSON Lines", "*.jsonl")),
        )
        if value:
            self.report_path.set(value)

    def _append_log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _check_exiftool_at_startup(self) -> None:
        try:
            self._append_log(f"ExifTool: {support.locate_exiftool()}")
        except ExifToolError as exc:
            self._append_log(str(exc))
            self.status.set("Warning: ExifTool was not found.")

    def _start(self) -> None:
        self.start_button.configure(state="disabled")
        self.open_output_button.configure(state="disabled")
        self._clear_log()
        settings = self._settings()
        try:
            support.validate_settings(settings)
        except support.GuiValidationError as exc:
            messagebox.showerror("Invalid settings", str(exc))
            self.start_button.configure(state="normal")
            return
        try:
            exiftool_path = support.locate_exiftool()
        except ExifToolError:
            messagebox.showerror("ExifTool not found", support.EXIFTOOL_MISSING_MESSAGE)
            self.start_button.configure(state="normal")
            return

        self.running_settings = settings
        self.cancel_event = threading.Event()
        self.cancel_button.configure(state="normal")
        self._append_log("Mode: " + ("DRY RUN" if settings.dry_run else "APPLY"))
        self._append_log(f"Input: {settings.input_dir}")
        self._append_log(f"Output: {settings.output_dir}")
        self._append_log(f"Timezone: {settings.timezone.strip() or '(none)'}")
        self._append_log(f"Overwrite output: {'yes' if settings.overwrite_output else 'no'}")
        if settings.write_report:
            self._append_log(f"Report: {settings.report_path} ({settings.report_format})")
        self.status.set("Starting...")
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        threading.Thread(
            target=self._worker, args=(settings, exiftool_path, self.cancel_event), daemon=True,
        ).start()

    def _cancel(self) -> None:
        if self.cancel_event is not None:
            self.cancel_event.set()
        self.cancel_button.configure(state="disabled")
        self.status.set("Cancelling...")
        self._append_log("Cancelling... waiting for the current file to finish.")

    def _worker(
        self, settings: support.GuiSettings, exiftool_path: str, cancel_event: threading.Event,
    ) -> None:
        try:
            opts = support.build_options(settings, exiftool_path)
            file_progress = None
            if settings.verbose:
                file_progress = lambda index, row: self.events.put(
                    ("file", report.format_progress_line(index, row))
                )
            rows = pipeline.run(
                opts,
                progress=lambda done, total, directory: self.events.put(("progress", done, total, directory)),
                file_progress=file_progress,
                directory_start=lambda index, total, directory: self.events.put(
                    ("dirstart", index, total, directory)
                ),
                cancel_event=cancel_event,
            )
            if settings.write_report:
                report.write_report(
                    rows, support._resolve_user_path(settings.report_path), fmt=settings.report_format,
                )
            self.events.put(("done", rows))
        except BaseException:
            self.events.put(("error", traceback.format_exc()))

    def _drain_queue(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "progress":
                    _kind, done, total, directory = event
                    self.progress.stop()
                    self.progress.configure(mode="determinate", maximum=total, value=done)
                    self.status.set(f"Processing {done}/{total}: {directory.name}")
                    self._append_log(f"Processing {done}/{total}: {directory}")
                elif kind == "dirstart":
                    _kind, done, total, directory = event
                    self.status.set(f"Reading {done}/{total}: {directory.name}")
                    self._append_log(f"Reading metadata: {directory}")
                elif kind == "file":
                    self._append_log(event[1])
                elif kind == "done":
                    self._finish_success(event[1])
                elif kind == "error":
                    self._finish_error(event[1])
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._drain_queue)

    def _finish_success(self, rows: list[dict]) -> None:
        settings = self.running_settings
        assert settings is not None
        self.progress.stop()
        self._append_log("")
        cancelled = self.cancel_event is not None and self.cancel_event.is_set()
        lines = (
            support.cancelled_lines(rows)
            if cancelled else support.summary_lines(rows, apply=not settings.dry_run)
        )
        for line in lines:
            self._append_log(line)
        if settings.write_report:
            self._append_log(f"Report written: {settings.report_path}")
        self.status.set("Processing cancelled." if cancelled else "Processing completed.")
        self._reset_controls()
        self.open_output_button.configure(state="normal")
        if self.quit_when_idle:
            self.root.destroy()
            return
        messagebox.showinfo("Cancelled" if cancelled else "Completed", "\n".join(lines))

    def _finish_error(self, details: str) -> None:
        self.progress.stop()
        self._append_log(details)
        self.status.set("Failed.")
        self._reset_controls()
        if self.quit_when_idle:
            self.root.destroy()
            return
        last_line = next(line for line in reversed(details.splitlines()) if line.strip())
        messagebox.showerror("Error", f"{last_line}\n\nSee the log for details.")

    def _reset_controls(self) -> None:
        self.progress.stop()
        self.start_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.cancel_event = None

    def _on_close(self) -> None:
        if self.cancel_event is None:
            self.root.destroy()
            return
        if self.cancel_event.is_set():
            self.quit_when_idle = True
            self.status.set("Cancelling... will quit after the current file finishes.")
            self._append_log("Will quit after the current file finishes.")
            return
        if not messagebox.askyesno("Quit", "Processing is running. Cancel and quit?"):
            return
        self.quit_when_idle = True
        self._cancel()

    def _open_output(self) -> None:
        if self.running_settings is not None:
            support.open_in_finder(support._resolve_user_path(self.running_settings.output_dir))


def run_app() -> int:
    root = tk.Tk()
    PhotoDateRestoreApp(root)
    root.mainloop()
    return 0
