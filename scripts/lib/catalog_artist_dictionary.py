"""Approved credit-name equivalences, never contractual beneficiary identities."""
from __future__ import annotations

import re
import unicodedata


ALIASES = {
    "matias mareco": "Matias Mareco", "matias mareco dj": "Matias Mareco",
    "alan gomez": "Alan Gomez", "dj alan gomez": "Alan Gomez",
    "acit x": "Acita", "acita": "Acita",
}

# The catalog owner confirmed this artist rename in this chat on 2026-11-02.
# Source literals and contractual beneficiary keys remain original evidence.
APPROVED_RENAMES = ({"previous": "ACIT x", "current": "Acita",
    "confirmed_by": "Ruben Mariano Elkowich", "confirmed_on": "2026-11-02",
    "reference_isrc": "ARDL12500074",
    "reference_url": "https://open.spotify.com/track/4GfGk24RCr2G7pXo9PboQ6"},)


def _credit_pattern(name):
    name = r"\s+".join(re.escape(part) for part in name.split())
    return (r"(?i)(^|[,;/|&]\s*|\s+(?:and|featuring|feat\.?|ft\.?)\s+)" + name
            + r"($|\s*[,;/|&]|\s+(?:and|featuring|feat\.?|ft\.?)\s+)")


def display_credit(value):
    """Rename confirmed credited people, retaining collaborators and punctuation."""
    if not isinstance(value, str):
        return value
    for change in APPROVED_RENAMES:
        for name in (change["previous"], change["current"]):
            pattern = _credit_pattern(name)
            for _ in range(2):
                value = re.sub(pattern, lambda m: m[1] + change["current"] + m[2], value)
    return value


def display_credit_expr(expr):
    from app.royalty_scope import is_wml
    if is_wml():
        return expr
    for change in APPROVED_RENAMES:
        for name in (change["previous"], change["current"]):
            for _ in range(2):
                expr = expr.str.replace_all(_credit_pattern(name), "${1}" + change["current"] + "${2}")
    return expr


def search_terms(value):
    """Both confirmed names find historical source rows without rewriting them."""
    from app.royalty_scope import is_wml
    if is_wml():
        return [value]
    terms = [value, display_credit(value)]
    for change in APPROVED_RENAMES:
        terms.append(re.sub(_credit_pattern(change["current"]),
            lambda m: m[1] + change["previous"] + m[2], str(value)))
    return list(dict.fromkeys(terms))


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
