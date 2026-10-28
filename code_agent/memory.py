from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MemoryEntry:
    scope: str
    text: str


class FileMemory:
    """Small local long-term memory backend with scope isolation."""
    def __init__(self, workspace: Path) -> None:
        self.path = workspace / ".code-agent" / "memory.jsonl"

    def remember(self, scope: str, text: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"scope": scope, "text": text}, ensure_ascii=False) + "\n")

    def recall(self, scope: str, query: str, limit: int = 5) -> list[MemoryEntry]:
        if not self.path.exists():
            return []
        terms = set(re.findall(r"\w+", query.lower()))
        candidates = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            if item.get("scope") != scope:
                continue
            score = len(terms & set(re.findall(r"\w+", item["text"].lower())))
            if score:
                candidates.append((score, MemoryEntry(scope, item["text"])))
        return [entry for _, entry in sorted(candidates, key=lambda pair: pair[0], reverse=True)[:limit]]

