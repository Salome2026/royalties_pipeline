"""Server-side windows over the fully ranked dashboard results."""
from dataclasses import dataclass
from hashlib import sha256
import json

PAGE_SIZE = 50
CATEGORIES = ("artist", "title")


def rank_snapshot(*parts: object) -> str:
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return sha256(payload.encode()).hexdigest()


class RankSnapshotChanged(ValueError):
    pass


@dataclass(frozen=True)
class RankPage:
    category: str | None = None
    offset: int = 0
    expected_snapshot: str | None = None

    def __post_init__(self):
        if self.category not in (None, *CATEGORIES) or not 0 <= self.offset <= 1000000:
            raise ValueError("Página de ranking inválida.")
        if self.offset and (not self.category or self.offset % PAGE_SIZE):
            raise ValueError("Página de ranking inválida.")

    def predicate(self, position: str, limit: str, *, category: str = "category") -> str:
        target = f"{category} IN ('artist', 'title')"
        if self.category:
            return f"{category} = '{self.category}' AND {position} BETWEEN {self.offset + 1} AND {self.offset + PAGE_SIZE + 1}"
        return f"{position} <= IF({target}, {PAGE_SIZE + 1}, {limit})"

    def response(self, result: dict) -> dict:
        if self.expected_snapshot and self.expected_snapshot != result.get("ranking_snapshot"):
            raise RankSnapshotChanged("Los datos cambiaron. Actualizá el dashboard para seguir explorando.")
        rankings = dict(result["rankings"])
        next_offsets = {}
        for category in (self.category,) if self.category else CATEGORIES:
            rows = rankings[category]
            next_offsets[category] = self.offset + PAGE_SIZE if len(rows) > PAGE_SIZE else None
            rankings[category] = rows[:PAGE_SIZE]
        if self.category:
            return {"rows": rankings[self.category], "next_offset": next_offsets[self.category]}
        return {**result, "rankings": rankings, "ranking_next": next_offsets}
