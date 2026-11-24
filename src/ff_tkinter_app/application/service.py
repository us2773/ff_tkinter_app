"""All three input routes share exactly the same upload workflow."""

from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Callable
from uuid import uuid4

from .ports import AnalysisClient, AppEvent, OperationCancelled, Recorder


class VideoService:
    RECORDING_SECONDS = 10

    def __init__(self, recorder: Recorder, client: AnalysisClient,
                 recordings_directory: Path, sample_video: Path):
        self.recorder = recorder
        self.client = client
        self.recordings_directory = recordings_directory
        self.sample_video = sample_video

    def record_and_send(self, emit: Callable[[AppEvent], None], cancelled: Event):
        self._check_cancelled(cancelled)
        emit(AppEvent("status", "カメラを準備中"))
        emit(AppEvent("log", "カメラを準備しています。撮影は10秒で自動停止します。"))
        name = f"{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}.mp4"

        def recording(remaining: int):
            if remaining == self.RECORDING_SECONDS:
                emit(AppEvent("log", "撮影を開始しました。"))
            emit(AppEvent("status", f"撮影中（残り{remaining}秒）"))

        video = self.recorder.record(
            self.recordings_directory / name,
            self.RECORDING_SECONDS,
            recording,
            cancelled,
        )
        emit(AppEvent("log", f"撮影を終了し、保存しました：{video}"))
        self.send_video(video, emit, cancelled)

    def send_sample(self, emit: Callable[[AppEvent], None], cancelled: Event):
        emit(AppEvent("log", f"サンプル動画を使用します：{self.sample_video}"))
        self.send_video(self.sample_video, emit, cancelled)

    def send_video(self, video: Path, emit: Callable[[AppEvent], None], cancelled: Event):
        self._check_cancelled(cancelled)
        video = video.resolve()
        if not video.is_file():
            raise ValueError(f"動画が見つかりません：{video}")
        if video.suffix.lower() not in {".mp4", ".mov"}:
            raise ValueError("対応する動画形式はMP4とMOVです。")
        if video.stat().st_size == 0:
            raise ValueError("動画ファイルが空です。")
        emit(AppEvent("status", "送信中"))
        emit(AppEvent("log", f"動画を送信しています：{video}"))

        def waiting():
            emit(AppEvent("status", "レスポンス待ち"))
            emit(AppEvent("log", "送信しました。サーバのレスポンスを待っています。"))

        response = self.client.analyze(video, waiting)
        emit(AppEvent("log", f"レスポンスを受信しました（HTTP {response.status_code}）。"))
        if response.analysis_mode:
            emit(AppEvent("log", f"サーバの分析モード：{response.analysis_mode}"))
        # Keep the original text, including null, unknown fields and HTTP error bodies.
        emit(AppEvent("response", response.body))
        success = 200 <= response.status_code < 300
        emit(AppEvent("status", "受信完了" if success else f"失敗（HTTP {response.status_code}）"))
        emit(AppEvent("log", "処理が完了しました。" if success else "送信に失敗しました。上のレスポンス本文を確認してください。"))

    @staticmethod
    def _check_cancelled(cancelled: Event):
        if cancelled.is_set():
            raise OperationCancelled()
