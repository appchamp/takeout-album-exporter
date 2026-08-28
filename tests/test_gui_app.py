"""GUI event handling tests without constructing a Tk window."""
import queue
import sys
import threading
import types
from types import SimpleNamespace

try:
    import tkinter  # noqa: F401
except ModuleNotFoundError:
    # The test exercises queue/event methods only.  Supply import-time names
    # when the project Python was built without Tk support.
    tkinter = types.ModuleType("tkinter")
    tkinter.Tk = object
    tkinter.TclError = Exception
    tkinter.Menu = object
    tkinter.StringVar = object
    tkinter.BooleanVar = object
    for name in ("filedialog", "messagebox", "scrolledtext", "ttk"):
        module = types.ModuleType(f"tkinter.{name}")
        setattr(tkinter, name, module)
        sys.modules[f"tkinter.{name}"] = module
    sys.modules["tkinter"] = tkinter

from photo_date_restore.gui import app as gui_app
from photo_date_restore.gui.app import PhotoDateRestoreApp


class _Value:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value


class _Widget:
    def __init__(self):
        self.calls = []

    def configure(self, **kwargs):
        self.calls.append(kwargs)

    def stop(self):
        self.calls.append({"stop": True})


class _Root:
    def __init__(self):
        self.after_calls = []
        self.destroyed = False

    def after(self, *args):
        self.after_calls.append(args)

    def destroy(self):
        self.destroyed = True


def _bare_app():
    app = object.__new__(PhotoDateRestoreApp)
    app.root = _Root()
    app.events = queue.Queue()
    app.status = _Value()
    app.progress = _Widget()
    app.cancel_button = _Widget()
    app.start_button = _Widget()
    app.open_output_button = _Widget()
    app.quit_when_idle = False
    app.logs = []
    app._append_log = app.logs.append
    return app


def test_metadata_progress_updates_reading_status_through_the_final_total():
    app = _bare_app()
    directory = __import__("pathlib").Path("/input/album")
    app.events.put(("metaprogress", directory, 0, 250))

    app._drain_queue()

    assert app.status.value == "Reading metadata: album — 0 / 250"

    app.events.put(("metaprogress", directory, 100, 250))
    app.events.put(("metaprogress", directory, 250, 250))

    app._drain_queue()

    assert "[100/250] Reading metadata..." in app.logs
    assert app.status.value == "Reading metadata: album — 250 / 250"
    assert app.progress.calls[-1] == {"value": 250}


def test_metadata_progress_bar_is_monotonic_and_other_progress_events_do_not_reconfigure_it():
    app = _bare_app()
    directory = __import__("pathlib").Path("/input/album")
    app.events.put(("metaprogress", directory, 0, 120))
    app.events.put(("metaprogress", directory, 50, 120))
    app.events.put(("metaprogress", directory, 40, 120))
    app.events.put(("metaprogress", directory, 120, 120))
    app.events.put(("progress", 1, 3, directory))
    app.events.put(("dirstart", 2, 3, directory))

    app._drain_queue()

    values = [call["value"] for call in app.progress.calls if "value" in call]
    assert values == [0, 50, 50, 120]
    assert app.status.value == "Reading 2/3: album"
    assert {"mode": "determinate", "maximum": 3, "value": 1} not in app.progress.calls


def test_analysis_progress_updates_stage_and_then_prepares_results():
    app = _bare_app()
    directory = __import__("pathlib").Path("/input/album")
    app.events.put(("metaprogress", directory, 120, 120))
    app.events.put(("analysisprogress", directory, 0, 120))
    app.events.put(("analysisprogress", directory, 50, 120))
    app.events.put(("analysisprogress", directory, 40, 120))
    app.events.put(("analysisprogress", directory, 120, 120))

    app._drain_queue()

    assert "[50/120] Analyzing metadata..." in app.logs
    assert app.status.value == "Preparing results: album"
    assert app.progress.calls[-1] == {"value": 120}
    assert {"mode": "determinate", "maximum": 120, "value": 0} in app.progress.calls
    assert [call["value"] for call in app.progress.calls if "value" in call] == [120, 0, 50, 50, 120]


def test_reset_stage_progress_starts_a_new_run_at_zero_for_the_same_directory():
    app = _bare_app()
    directory = __import__("pathlib").Path("/input/album")
    app._update_stage_progress("reading", directory, 50, 200)

    app._reset_stage_progress()
    app._update_stage_progress("reading", directory, 0, 300)

    assert app.progress.calls[-1] == {"mode": "determinate", "maximum": 300, "value": 0}


def test_drain_queue_limits_each_tick_and_preserves_all_file_events_in_order():
    app = _bare_app()
    total = gui_app.MAX_EVENTS_PER_DRAIN + 50
    for index in range(total):
        app.events.put(("file", f"file-{index}"))

    app._drain_queue()

    assert app.logs == [f"file-{index}" for index in range(gui_app.MAX_EVENTS_PER_DRAIN)]
    assert app.events.qsize() == 50
    assert app.root.after_calls

    app._drain_queue()

    assert app.logs == [f"file-{index}" for index in range(total)]
    assert app.events.empty()


def test_finish_success_has_no_completion_popup_for_normal_or_cancel(monkeypatch):
    popups = []
    monkeypatch.setattr(gui_app.messagebox, "showinfo", lambda *args: popups.append(args), raising=False)
    for cancelled in (False, True):
        app = _bare_app()
        app.running_settings = SimpleNamespace(dry_run=True, write_report=False)
        app.cancel_event = threading.Event()
        if cancelled:
            app.cancel_event.set()
        app._finish_success([{"status": "NO_CHANGE"}])
        assert app.status.value == ("Processing cancelled." if cancelled else "Processing completed.")
    assert popups == []


def test_finish_error_still_shows_error_popup(monkeypatch):
    app = _bare_app()
    popups = []
    monkeypatch.setattr(gui_app.messagebox, "showerror", lambda *args: popups.append(args), raising=False)

    app._finish_error("Traceback\nRuntimeError: boom")

    assert app.status.value == "Failed."
    assert popups == [("Error", "RuntimeError: boom\n\nSee the log for details.")]


def test_close_while_cancelling_keeps_worker_alive_until_idle():
    app = _bare_app()
    app.cancel_event = threading.Event()
    app.cancel_event.set()

    app._on_close()

    assert app.quit_when_idle is True
    assert app.root.destroyed is False
    assert app.status.value == "Cancelling... will quit after the current file finishes."
