"""Approved credit-name equivalences, never contractual beneficiary identities."""
from __future__ import annotations

import re
import unicodedata


ALIASES = {
    "matias mareco": "Matias Mareco", "matias mareco dj": "Matias Mareco",
    "alan gomez": "Alan Gomez", "dj alan gomez": "Alan Gomez",
}


def key(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    return re.sub(r"\s+", " ", "".join(c for c in value if not unicodedata.combining(c))).strip().casefold()


def canonical(value):
    return ALIASES.get(key(value), value)


def comparison_key(value):
    return key(canonical(value))


def unique(names):
    result, seen = [], set()
    for raw in names:
        name = canonical(raw)
        token = key(name)
        if token and token not in seen:
            seen.add(token)
            result.append(name)
    return result
