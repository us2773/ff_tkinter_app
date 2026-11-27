from pathlib import Path
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from ff_tkinter_app.application.ports import AppEvent
from ff_tkinter_app.presentation.window import MainWindow


class WindowTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"GUI display unavailable: {exc}")
        self.root.withdraw()
        self.service = Mock()
        self.window = MainWindow(self.root, self.service, "http://127.0.0.1:8000")
        self.addCleanup(self.window._destroy)

    def pump_until_idle(self):
        deadline = time.monotonic() + 3
        while self.window.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertFalse(self.window.busy, "Background task did not complete")

    def test_sample_button_runs_off_main_thread_and_displays_pretty_json(self):
        worker_ids = []
        gate = threading.Event()

        def action(emit, _cancelled):
            worker_ids.append(threading.get_ident())
            gate.wait(1)
            emit(AppEvent("response", '{"message":"日本語", "unknown":null}'))

        self.service.send_sample.side_effect = action
        self.window.buttons[2].invoke()
        self.assertTrue(all(button.instate(["disabled"]) for button in self.window.buttons))
        gate.set()
        self.pump_until_idle()
        self.assertNotEqual(worker_ids[0], threading.get_ident())
        self.assertIn('{\n  "message": "日本語",\n  "unknown": null\n}', self.window.output.get("1.0", "end"))
        self.assertTrue(all(not button.instate(["disabled"]) for button in self.window.buttons))
        self.assertEqual(self.window.output.cget("state"), tk.DISABLED)

    def test_non_json_response_is_displayed_unchanged(self):
        self.window.events.put(AppEvent("response", "<html>Server error</html>"))
        self.window._poll()
        self.assertIn("<html>Server error</html>", self.window.output.get("1.0", "end"))

    def test_file_dialog_cancel_does_not_send_and_selection_does(self):
        with patch("ff_tkinter_app.presentation.window.filedialog.askopenfilename", return_value=""):
            self.window.buttons[1].invoke()
        self.service.send_video.assert_not_called()
        with patch("ff_tkinter_app.presentation.window.filedialog.askopenfilename", return_value="C:/video.mp4"):
            self.window.buttons[1].invoke()
        self.pump_until_idle()
        self.assertEqual(self.service.send_video.call_args.args[0], Path("C:/video.mp4"))

    def test_failure_is_logged_and_buttons_are_restored(self):
        self.service.record_and_send.side_effect = RuntimeError("camera unavailable")
        self.window.buttons[0].invoke()
        self.pump_until_idle()
        self.assertEqual(self.window.status.get(), "状態：失敗")
        self.assertIn("camera unavailable", self.window.output.get("1.0", "end"))
        self.assertTrue(all(not button.instate(["disabled"]) for button in self.window.buttons))

    def test_duplicate_start_is_ignored(self):
        gate = threading.Event()
        self.service.send_sample.side_effect = lambda *_: gate.wait(1)
        self.window._start(self.service.send_sample)
        self.window._start(self.service.send_sample)
        gate.set()
        self.pump_until_idle()
        self.service.send_sample.assert_called_once()
