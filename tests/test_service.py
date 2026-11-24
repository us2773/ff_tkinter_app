from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import Mock

from ff_tkinter_app.application.ports import ApiResponse, OperationCancelled
from ff_tkinter_app.application.service import VideoService


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.video = self.directory / "sample.mp4"
        self.video.write_bytes(b"video")
        self.events = []
        self.cancelled = Event()
        self.recorder = Mock()
        self.client = Mock()
        self.response = ApiResponse(200, '{"status":"partial","unknown":null}')
        self.client.analyze.side_effect = lambda path, waiting: (waiting(), self.response)[1]
        self.service = VideoService(self.recorder, self.client, self.directory, self.video)

    def test_file_and_sample_share_the_upload_path(self):
        self.service.send_video(self.video, self.events.append, self.cancelled)
        self.service.send_sample(self.events.append, self.cancelled)
        self.assertEqual(self.client.analyze.call_count, 2)
        self.assertTrue(all(call.args[0] == self.video for call in self.client.analyze.call_args_list))
        self.assertEqual([e.text for e in self.events if e.kind == "response"], [self.response.body] * 2)

    def test_record_ten_seconds_then_upload_closed_file(self):
        steps = []

        def record(destination, seconds, remaining, cancelled):
            self.assertEqual(seconds, 10)
            remaining(10)
            destination.write_bytes(b"recorded")
            steps.append("saved_and_released")
            return destination

        def analyze(video, waiting):
            self.assertEqual(steps, ["saved_and_released"])
            self.assertEqual(video.read_bytes(), b"recorded")
            steps.append("upload")
            return self.response

        self.recorder.record.side_effect = record
        self.client.analyze.side_effect = analyze
        self.service.record_and_send(self.events.append, self.cancelled)
        self.assertEqual(steps, ["saved_and_released", "upload"])
        self.assertTrue(any("撮影中（残り10秒）" == e.text for e in self.events))

    def test_record_failure_does_not_upload(self):
        self.recorder.record.side_effect = RuntimeError("camera unavailable")
        with self.assertRaises(RuntimeError):
            self.service.record_and_send(self.events.append, self.cancelled)
        self.client.analyze.assert_not_called()

    def test_cancel_before_upload_does_not_send(self):
        self.cancelled.set()
        with self.assertRaises(OperationCancelled):
            self.service.send_video(self.video, self.events.append, self.cancelled)
        self.client.analyze.assert_not_called()

    def test_invalid_inputs_do_not_send(self):
        empty = self.directory / "empty.mp4"
        empty.touch()
        wrong_type = self.directory / "sample.txt"
        wrong_type.write_text("text")
        for video in [self.directory / "missing.mp4", empty, wrong_type]:
            with self.subTest(video=video), self.assertRaises(ValueError):
                self.service.send_video(video, self.events.append, self.cancelled)
        self.client.analyze.assert_not_called()

    def test_http_error_body_is_displayed(self):
        self.response = ApiResponse(409, '{"status":"failed","result":null}')
        self.service.send_sample(self.events.append, self.cancelled)
        self.assertIn(self.response.body, [e.text for e in self.events if e.kind == "response"])
        self.assertIn("失敗（HTTP 409）", [e.text for e in self.events if e.kind == "status"])
