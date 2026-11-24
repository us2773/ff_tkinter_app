"""Local settings, independent of the current working directory."""

from dataclasses import dataclass
import math
from pathlib import Path
import tomllib
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    base_url: str
    camera_index: int
    sample_video: Path
    recordings_directory: Path
    connect_timeout_seconds: float = 5
    response_timeout_seconds: float = 120


def load_settings(path: Path) -> Settings:
    path = path.expanduser().resolve()
    with path.open("rb") as stream:
        config = tomllib.load(stream)
    api = config.get("api", {})
    base_url = api.get("base_url", "http://127.0.0.1:8000")
    if not isinstance(base_url, str):
        raise ValueError("api.base_url は文字列で指定してください。")
    parsed = urlsplit(base_url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}):
        raise ValueError("api.base_url は http(s)://ホスト:ポート の形式にしてください。")
    # Accessing .port also validates malformed or out-of-range ports.
    parsed.port
    index = config.get("camera", {}).get("index", 0)
    if type(index) is not int or index < 0:
        raise ValueError("camera.index は0以上の整数にしてください。")

    def timeout(key: str, default: float) -> float:
        value = api.get(key, default)
        if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
            raise ValueError(f"api.{key} は正の有限数にしてください。")
        return float(value)

    def file_path(key: str, default: str) -> Path:
        value = config.get("files", {}).get(key, default)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"files.{key} は空でないパスにしてください。")
        target = Path(value).expanduser()
        return (path.parent / target).resolve()

    return Settings(
        base_url=base_url.rstrip("/"),
        camera_index=index,
        sample_video=file_path("sample_video", "samples/sample.mp4"),
        recordings_directory=file_path("recordings_directory", "recordings"),
        connect_timeout_seconds=timeout("connect_timeout_seconds", 5),
        response_timeout_seconds=timeout("response_timeout_seconds", 120),
    )
