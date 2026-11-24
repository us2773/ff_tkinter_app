"""Stream the video as the raw HTTP body; never multipart or base64."""

import http.client
import os
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from ..application.ports import ApiResponse


class HttpAnalysisClient:
    def __init__(self, base_url: str, connect_timeout_seconds: float = 5,
                 response_timeout_seconds: float = 120):
        self.url = urlsplit(base_url)
        self.connect_timeout = connect_timeout_seconds
        self.response_timeout = response_timeout_seconds

    def analyze(self, video: Path, on_waiting: Callable[[], None]) -> ApiResponse:
        media_type = {".mp4": "video/mp4", ".mov": "video/quicktime"}[video.suffix.lower()]
        connection_type = (http.client.HTTPSConnection if self.url.scheme == "https"
                           else http.client.HTTPConnection)
        connection = connection_type(self.url.hostname, self.url.port,
                                     timeout=self.connect_timeout)
        try:
            connection.connect()
            connection.sock.settimeout(self.response_timeout)
            with video.open("rb") as stream:
                connection.request(
                    "POST", "/v1/analyses?pipeline=daily", body=stream,
                    headers={"Content-Type": media_type,
                             "Content-Length": str(os.fstat(stream.fileno()).st_size),
                             "Accept": "application/json"},
                )
            on_waiting()
            response = connection.getresponse()
            body = response.read()
            encoding = response.headers.get_content_charset() or "utf-8"
            try:
                text = body.decode(encoding, errors="replace")
            except LookupError:
                text = body.decode("utf-8", errors="replace")
            return ApiResponse(response.status, text, response.getheader("X-Analysis-Mode"))
        finally:
            connection.close()
