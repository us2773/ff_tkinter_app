from datetime import datetime
import http.client
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
import tkinter as tk
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable

from ..application.ports import AppEvent, OperationCancelled
from ..application.service import VideoService


class MainWindow:
    def __init__(self, root: tk.Tk, service: VideoService, base_url: str):
        self.root = root
        self.service = service
        self.events: Queue[AppEvent] = Queue()
        self.cancelled = Event()
        self.worker: Thread | None = None
        self.busy = False
        self.closing = False
        root.title("疲労分析クライアント")
        root.geometry("800x580")
        root.minsize(650, 400)
        root.rowconfigure(0, weight=1)
        root.columnconfigure(0, weight=1)
        content = ttk.Frame(root, padding=16)
        content.grid(sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(3, weight=1)
        actions = ttk.Frame(content)
        actions.grid(row=0, column=0, sticky="w", pady=(0, 12))
        self.buttons = [
            ttk.Button(actions, text="撮影する（10秒）", command=lambda: self._start(service.record_and_send)),
            ttk.Button(actions, text="動画を選択して送信", command=self._select_video),
            ttk.Button(actions, text="サンプル動画を送信", command=lambda: self._start(service.send_sample)),
        ]
        for column, button in enumerate(self.buttons):
            button.grid(row=0, column=column, padx=(0, 8))
        self.status = tk.StringVar(value="状態：待機中")
        ttk.Label(content, textvariable=self.status).grid(row=1, column=0, sticky="w", pady=(0, 12))
        ttk.Label(content, text="処理ログ・受信JSON").grid(row=2, column=0, sticky="w", pady=(0, 4))
        self.output = ScrolledText(content, wrap=tk.WORD, font=("Consolas", 11), state=tk.DISABLED)
        self.output.grid(row=3, column=0, sticky="nsew")
        # Explicit selection/copy shortcuts also work while the log is read-only.
        self.output.bind("<Control-a>", self._select_all)
        self.output.bind("<Control-A>", self._select_all)
        root.protocol("WM_DELETE_WINDOW", self._close)
        self._log("アプリを起動しました。")
        self._log(f"接続先：{base_url}/v1/analyses?pipeline=daily")
        self.poll_id = root.after(50, self._poll)

    def _select_all(self, _event):
        self.output.tag_add(tk.SEL, "1.0", "end-1c")
        return "break"

    def _select_video(self):
        if self.busy or self.closing:
            return
        filename = filedialog.askopenfilename(
            parent=self.root, title="送信する動画を選択",
            filetypes=[("MP4 / MOV 動画", "*.mp4 *.mov *.MP4 *.MOV"), ("すべてのファイル", "*.*")],
        )
        if filename:
            self._start(lambda emit, cancelled: self.service.send_video(Path(filename), emit, cancelled))

    def _start(self, action: Callable):
        if self.busy or self.closing:
            return
        self.busy = True
        self.cancelled.clear()
        for button in self.buttons:
            button.state(["disabled"])

        def run():
            try:
                action(self.events.put, self.cancelled)
            except OperationCancelled:
                self.events.put(AppEvent("log", "終了操作により処理を中止しました。"))
            except (OSError, http.client.HTTPException, ValueError, RuntimeError) as exc:
                self.events.put(AppEvent("status", "失敗"))
                self.events.put(AppEvent("log", f"処理に失敗しました：{type(exc).__name__}: {exc}"))
            except Exception as exc:
                self.events.put(AppEvent("status", "失敗"))
                self.events.put(AppEvent("log", f"予期しないエラー：{type(exc).__name__}: {exc}"))

        self.worker = Thread(target=run, name="video-worker", daemon=True)
        self.worker.start()

    def _poll(self):
        # This method and every widget update run on Tk's main thread.
        try:
            while True:
                event = self.events.get_nowait()
                if event.kind == "status":
                    self.status.set(f"状態：{event.text}")
                elif event.kind == "response":
                    self._append(event.text + "\n")
                else:
                    self._log(event.text)
        except Empty:
            pass
        if self.busy and self.worker is not None and not self.worker.is_alive():
            self.busy = False
            for button in self.buttons:
                button.state(["!disabled"])
        if self.closing:
            if not self.busy:
                self._destroy()
                return
            self.status.set("状態：終了処理中")
        self.poll_id = self.root.after(50, self._poll)

    def _append(self, text: str):
        self.output.configure(state=tk.NORMAL)
        self.output.insert(tk.END, text)
        self.output.configure(state=tk.DISABLED)
        self.output.see(tk.END)

    def _log(self, text: str):
        self._append(f"[{datetime.now():%H:%M:%S}] {text}\n")

    def _close(self):
        if self.closing:
            return
        self.closing = True
        self.cancelled.set()
        for button in self.buttons:
            button.state(["disabled"])
        if self.busy:
            self._log("終了処理中です。カメラの解放・通信処理の終了を待っています。")
        else:
            self._destroy()

    def _destroy(self):
        self.root.after_cancel(self.poll_id)
        self.root.destroy()
