import os
from pathlib import Path


def load_dotenv(path: str | None = None) -> None:
    env_file = Path(path or ".env")
    if not env_file.is_file():
        return
    for line in env_file.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))