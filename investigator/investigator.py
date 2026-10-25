import json
from pathlib import Path
from typing import Optional


class DecisionLog:
    def __init__(self, path: str):
        self.path = Path(path)

    def _load(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def get_recent_events(self, limit: int = 10):
        events = self._load()
        return events[-limit:]

    def get_event(self, event_id: str) -> Optional[dict]:
        events = self._load()

        for event in events:
            if event.get("event_id") == event_id:
                return event

        return None

    def search_events(self, scenario: str):
        events = self._load()
        return [
            event for event in events
            if event.get("scenario") == scenario
        ]