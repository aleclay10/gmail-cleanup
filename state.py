import json
import os
from dataclasses import dataclass, field

from config import CHECKPOINT_FILE


@dataclass
class RunState:
    all_message_ids: list = field(default_factory=list)
    processed: dict = field(default_factory=dict)   # id -> "important" | "low_priority"
    labeled: set = field(default_factory=set)

    def save(self):
        os.makedirs(os.path.dirname(CHECKPOINT_FILE), exist_ok=True)
        data = {
            "all_message_ids": self.all_message_ids,
            "processed": self.processed,
            "labeled": list(self.labeled),
        }
        tmp = CHECKPOINT_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, CHECKPOINT_FILE)

    @classmethod
    def load(cls):
        if not os.path.exists(CHECKPOINT_FILE):
            return None
        with open(CHECKPOINT_FILE) as f:
            data = json.load(f)
        state = cls(
            all_message_ids=data["all_message_ids"],
            processed=data["processed"],
            labeled=set(data.get("labeled", [])),
        )
        return state

    @classmethod
    def clear(cls):
        if os.path.exists(CHECKPOINT_FILE):
            os.remove(CHECKPOINT_FILE)
