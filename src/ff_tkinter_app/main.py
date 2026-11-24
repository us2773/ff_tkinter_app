"""Composition root: connect the three layers here only."""

import argparse
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from .application.service import VideoService
from .infrastructure.api_client import HttpAnalysisClient
from .infrastructure.camera import OpenCvRecorder
from .presentation.window import MainWindow
from .settings import load_settings


def main():
    parser = argparse.ArgumentParser(description="動画撮影・送信クライアント")
    parser.add_argument("--config", type=Path, default=Path("config.local.toml"),
                        help="設定ファイルの場所（既定：config.local.toml）")
    args = parser.parse_args()
    root = tk.Tk()
    root.withdraw()
    try:
        settings = load_settings(args.config)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        messagebox.showerror("設定を読み込めません", f"{exc}\n\nconfig.example.tomlをconfig.local.tomlにコピーして設定してください。", parent=root)
        root.destroy()
        return
    client = HttpAnalysisClient(settings.base_url, settings.connect_timeout_seconds,
                                settings.response_timeout_seconds)
    service = VideoService(OpenCvRecorder(settings.camera_index), client,
                           settings.recordings_directory, settings.sample_video)
    MainWindow(root, service, settings.base_url)
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
