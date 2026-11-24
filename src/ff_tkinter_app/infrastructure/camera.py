"""Record without a preview. Sampling uses elapsed time, not frame count."""

import math
from pathlib import Path
import sys
import time
from threading import Event
from typing import Callable

from ..application.ports import OperationCancelled


class OpenCvRecorder:
    FPS = 30

    def __init__(self, camera_index: int):
        self.camera_index = camera_index

    def record(self, destination: Path, duration_seconds: int,
               on_remaining: Callable[[int], None], cancelled: Event) -> Path:
        if cancelled.is_set():
            raise OperationCancelled()
        # File upload can still be used when a camera/dependency is unavailable.
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("撮影にはopencv-pythonが必要です。依存パッケージをインストールしてください。") from exc
        destination.parent.mkdir(parents=True, exist_ok=True)
        capture = None
        writer = None
        completed = False
        try:
            backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
            capture = cv2.VideoCapture(self.camera_index, backend)
            if not capture.isOpened():
                raise RuntimeError(f"カメラ{self.camera_index}を起動できません。設定・カメラ権限・他のアプリによる使用を確認してください。")
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            capture.set(cv2.CAP_PROP_FPS, self.FPS)
            ok, frame = capture.read()
            if not ok or frame is None:
                raise RuntimeError("カメラから映像を取得できません。")
            height, width = frame.shape[:2]
            writer = cv2.VideoWriter(str(destination), cv2.VideoWriter_fourcc(*"mp4v"),
                                     self.FPS, (width, height))
            if not writer.isOpened():
                raise RuntimeError("MP4動画の保存を開始できません。保存先とコーデックを確認してください。")
            started = time.monotonic()
            total_frames = duration_seconds * self.FPS
            written = 0
            last_remaining = None
            # Resample to constant FPS so a slower camera does not shorten playback.
            while True:
                if cancelled.is_set():
                    raise OperationCancelled()
                elapsed = time.monotonic() - started
                remaining = max(0, math.ceil(duration_seconds - elapsed))
                if remaining != last_remaining:
                    on_remaining(remaining)
                    last_remaining = remaining
                due = min(total_frames, int(elapsed * self.FPS) + 1)
                while written < due:
                    writer.write(frame)
                    written += 1
                if elapsed >= duration_seconds:
                    break
                ok, next_frame = capture.read()
                if not ok or next_frame is None:
                    raise RuntimeError("撮影中にカメラから映像を取得できなくなりました。送信を中止します。")
                if next_frame.shape[:2] != (height, width):
                    raise RuntimeError("撮影中に映像サイズが変わりました。送信を中止します。")
                frame = next_frame
                # Avoid a busy loop with unusually fast or buffered camera drivers.
                time.sleep(min(0.005, max(0, duration_seconds - elapsed)))
            writer.release()
            writer = None
            if not destination.is_file() or destination.stat().st_size == 0:
                raise RuntimeError("動画を保存できませんでした。")
            completed = True
            return destination
        finally:
            if writer is not None:
                writer.release()
            if capture is not None:
                capture.release()
            if not completed:
                destination.unlink(missing_ok=True)
