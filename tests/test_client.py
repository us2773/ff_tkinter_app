from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

from ff_tkinter_app.infrastructure.api_client import HttpAnalysisClient


class ClientIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.video = Path(self.temp.name) / "video.MP4"
        self.payload = b"\x00\x00\x00\x18ftypmp42\x00\x01video-data" * 2000
        self.video.write_bytes(self.payload)
        self.received = {}
        self.status_code = 200
        self.body = '{"status":"succeeded", "unknown":null, "message":"受信しました"}'
        test = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                test.received.update(path=self.path, headers=self.headers,
                                     data=self.rfile.read(int(self.headers["Content-Length"])))
                encoded = test.body.encode("utf-8")
                self.send_response(test.status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("X-Analysis-Mode", "sample")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.addCleanup(self.temp.cleanup)
        self.client = HttpAnalysisClient(f"http://127.0.0.1:{self.server.server_port}", 1, 1)
        try:
            with socket.create_connection(self.server.server_address, timeout=1):
                pass
        except PermissionError:
            self.skipTest("Loopback connections are blocked by this execution environment")

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_raw_upload_and_exact_response(self):
        waiting = []
        response = self.client.analyze(self.video, lambda: waiting.append(True))
        self.assertEqual(self.received["path"], "/v1/analyses?pipeline=daily")
        self.assertEqual(self.received["data"], self.payload)
        self.assertEqual(self.received["headers"]["Content-Type"], "video/mp4")
        self.assertEqual(int(self.received["headers"]["Content-Length"]), len(self.payload))
        self.assertIsNone(self.received["headers"].get("Transfer-Encoding"))
        self.assertEqual(response.body, self.body)
        self.assertEqual(response.analysis_mode, "sample")
        self.assertEqual(waiting, [True])

    def test_http_errors_keep_full_body_and_client_can_be_reused(self):
        for code, body in [(400, '{"error":null}'), (409, '{"error":"busy"}'),
                           (500, "<html>server failed</html>")]:
            with self.subTest(code=code):
                self.status_code, self.body = code, body
                response = self.client.analyze(self.video, lambda: None)
                self.assertEqual((response.status_code, response.body), (code, body))

    def test_mov_content_type(self):
        video = self.video.with_suffix(".mov")
        video.write_bytes(self.payload)
        self.client.analyze(video, lambda: None)
        self.assertEqual(self.received["headers"]["Content-Type"], "video/quicktime")

    def test_connection_failure_is_not_a_fake_success(self):
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            port = reserved.getsockname()[1]
            client = HttpAnalysisClient(f"http://127.0.0.1:{port}", 0.2, 0.2)
            with self.assertRaises(OSError):
                client.analyze(self.video, lambda: None)


class ClientWireTests(unittest.TestCase):
    """Exercise Python's actual HTTP serializer/parser without network access."""

    def test_streamed_mp4_mov_and_error_bodies(self):
        class MemorySocket:
            def __init__(self, response):
                self.sent = bytearray()
                self.response = response
                self.closed = False

            def settimeout(self, _timeout):
                pass

            def sendall(self, data):
                self.sent.extend(data)

            def makefile(self, *_args):
                return BytesIO(self.response)

            def close(self):
                self.closed = True

        with TemporaryDirectory() as directory:
            payload = b"\x00\x00\x18ftypmp42\x00\xff" * 5000
            for suffix, media_type in [(".mp4", "video/mp4"), (".MOV", "video/quicktime")]:
                video = Path(directory) / ("video" + suffix)
                video.write_bytes(payload)
                for code in [200, 400, 409, 500]:
                    with self.subTest(suffix=suffix, code=code):
                        body = '{"status":"partial", "message":"日本語", "unknown":null}'
                        encoded = body.encode("utf-8")
                        wire_response = (
                            f"HTTP/1.1 {code} Test\r\nContent-Type: application/json; charset=utf-8\r\n"
                            f"Content-Length: {len(encoded)}\r\nX-Analysis-Mode: sample\r\n\r\n"
                        ).encode("ascii") + encoded
                        sock = MemorySocket(wire_response)
                        waiting = []
                        with patch("http.client.HTTPConnection.connect", lambda conn: setattr(conn, "sock", sock)):
                            result = HttpAnalysisClient("http://127.0.0.1:8000").analyze(video, lambda: waiting.append(True))
                        headers, transmitted = bytes(sock.sent).split(b"\r\n\r\n", 1)
                        self.assertTrue(headers.startswith(b"POST /v1/analyses?pipeline=daily HTTP/1.1\r\n"))
                        self.assertIn(f"Content-Type: {media_type}".encode(), headers)
                        self.assertIn(f"Content-Length: {len(payload)}".encode(), headers)
                        self.assertNotIn(b"Transfer-Encoding", headers)
                        self.assertEqual(transmitted, payload)
                        self.assertEqual((result.status_code, result.body, result.analysis_mode), (code, body, "sample"))
                        self.assertEqual(waiting, [True])
                        self.assertTrue(sock.closed)

    def test_transport_timeout_is_propagated(self):
        with TemporaryDirectory() as directory:
            video = Path(directory) / "video.mp4"
            video.write_bytes(b"video")
            with patch("http.client.HTTPConnection.connect", side_effect=TimeoutError("timed out")):
                with self.assertRaises(TimeoutError):
                    HttpAnalysisClient("http://127.0.0.1:8000").analyze(video, lambda: None)
