"""Small background jobs the agent can leave running, such as watching a folder."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path


class BackgroundTasks:
    def __init__(self, notify: Callable[[str], None]) -> None:
        self.notify = notify
        self.jobs: dict[str, str] = {}

    def watch_folder(self, folder: str, job_id: str) -> str:
        path = Path(folder)
        if not path.is_dir():
            return "That folder does not exist."
        seen = {item.name for item in path.iterdir()}
        self.jobs[job_id] = "watching"

        def _run() -> None:
            while self.jobs.get(job_id) == "watching":
                current = {item.name for item in path.iterdir()} if path.is_dir() else set()
                added = current - seen
                if added:
                    self.notify(f"New in {path.name}: {', '.join(sorted(added))}")
                    seen.update(added)
                time.sleep(5)
            self.jobs.pop(job_id, None)

        threading.Thread(target=_run, name=f"watch-{job_id}", daemon=True).start()
        return f"Watching {path}."

    def stop_all(self) -> None:
        """End every running watch. New watches can still be started afterwards (kill switch, then resume)."""
        self.jobs.clear()
