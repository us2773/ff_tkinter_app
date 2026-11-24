from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ff_tkinter_app.application.ports import OperationCancelled
from ff_tkinter_app.infrastructure.camera import OpenCvRecorder


class CameraTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = Path(self.temp.name) / "new" / "capture.mp4"
        self.clock = 0.0
        self.capture = Mock()
        self.capture.isOpened.return_value = True
        self.frame = SimpleNamespace(shape=(480, 640, 3))
        self.reads = 0

        def read():
            self.reads += 1
            # Simulate a camera slower than the output FPS.
            self.clock += 0.1
            return True, self.frame

        self.capture.read.side_effect = read
        self.writer = Mock()
        self.writer.isOpened.return_value = True
        self.writer.release.side_effect = lambda: self.destination.write_bytes(b"finalized-mp4")
        self.cv2 = SimpleNamespace(
            VideoCapture=Mock(return_value=self.capture), VideoWriter=Mock(return_value=self.writer),
            VideoWriter_fourcc=Mock(return_value=123), CAP_DSHOW=700, CAP_ANY=0,
            CAP_PROP_FRAME_WIDTH=3, CAP_PROP_FRAME_HEIGHT=4, CAP_PROP_FPS=5,
        )
        self.patches = [patch.dict("sys.modules", {"cv2": self.cv2}),
                        patch("ff_tkinter_app.infrastructure.camera.time.monotonic", lambda: self.clock),
                        patch("ff_tkinter_app.infrastructure.camera.time.sleep", self.sleep)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def sleep(self, duration):
        self.clock += duration

    def test_ten_seconds_produces_300_frames_and_releases_resources(self):
        remaining = []
        result = OpenCvRecorder(0).record(self.destination, 10, remaining.append, Event())
        self.assertEqual(result, self.destination)
        self.assertEqual(self.writer.write.call_count, 300)
        self.assertEqual(remaining, list(range(10, -1, -1)))
        self.assertGreaterEqual(self.clock, 10)
        self.assertLess(self.clock, 10.3)
        self.writer.release.assert_called_once()
        self.capture.release.assert_called_once()
        self.assertEqual(self.destination.read_bytes(), b"finalized-mp4")

    def test_capture_failure_removes_incomplete_video_and_releases_camera(self):
        self.capture.read.side_effect = [(True, self.frame), (False, None)]
        with self.assertRaisesRegex(RuntimeError, "撮影中"):
            OpenCvRecorder(0).record(self.destination, 10, lambda _: None, Event())
        self.assertFalse(self.destination.exists())
        self.writer.release.assert_called_once()
        self.capture.release.assert_called_once()

    def test_window_close_cancels_and_removes_partial_file(self):
        cancelled = Event()
        with self.assertRaises(OperationCancelled):
            OpenCvRecorder(0).record(self.destination, 10, lambda _: cancelled.set(), cancelled)
        self.assertFalse(self.destination.exists())
        self.capture.release.assert_called_once()

    def test_camera_open_failure_releases_resource(self):
        self.capture.isOpened.return_value = False
        with self.assertRaisesRegex(RuntimeError, "起動できません"):
            OpenCvRecorder(0).record(self.destination, 10, lambda _: None, Event())
        self.capture.release.assert_called_once()
        self.cv2.VideoWriter.assert_not_called()


class EncoderTests(unittest.TestCase):
    def test_real_encoder_creates_ten_second_decodable_mp4(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("OpenCV is not installed in this execution environment")
        clock = [0.0]
        frame = np.zeros((48, 64, 3), dtype=np.uint8)
        capture = Mock()
        capture.isOpened.return_value = True

        def read():
            clock[0] += 0.1
            return True, frame

        def sleep(seconds):
            clock[0] += seconds

        capture.read.side_effect = read
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "synthetic.mp4"
            with patch.object(cv2, "VideoCapture", return_value=capture), \
                 patch("ff_tkinter_app.infrastructure.camera.time.monotonic", lambda: clock[0]), \
                 patch("ff_tkinter_app.infrastructure.camera.time.sleep", sleep):
                OpenCvRecorder(0).record(destination, 10, lambda _: None, Event())
            decoder = cv2.VideoCapture(str(destination))
            try:
                self.assertTrue(decoder.isOpened())
                self.assertEqual(int(decoder.get(cv2.CAP_PROP_FRAME_COUNT)), 300)
                self.assertAlmostEqual(decoder.get(cv2.CAP_PROP_FPS), 30)
                ok, decoded = decoder.read()
                self.assertTrue(ok)
                self.assertEqual(decoded.shape[:2], (48, 64))
            finally:
                decoder.release()
            capture.release.assert_called_once()
