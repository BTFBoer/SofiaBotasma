"""Container health check: the bot writes a heartbeat file every minute.

python -m app.healthcheck     exit 0 if the heartbeat is fresh, 1 otherwise
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

MAX_AGE_SECONDS = 180


def main() -> int:
    data_dir = Path(os.environ.get("DATABASE_PATH", "./data/sofia.db")).parent
    path = Path(os.environ.get("HEARTBEAT_PATH", str(data_dir / "heartbeat")))
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        print(f"no heartbeat at {path}")
        return 1
    if age > MAX_AGE_SECONDS:
        print(f"heartbeat stale ({int(age)}s)")
        return 1
    print(f"ok ({int(age)}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
