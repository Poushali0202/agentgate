"""Load KEY=VALUE lines from .env into os.environ, so plain `uvicorn gateway.app:app` picks up its config.

Values already in the environment win. Tests set GATEWAY_SKIP_DOTENV so a developer's .env never leaks into them.
"""

import os


def load(path: str = ".env") -> None:
    if os.environ.get("GATEWAY_SKIP_DOTENV") or not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and value and key not in os.environ:
                os.environ[key] = value
