"""Name and address normalisation, and the string similarities the matcher uses."""

from __future__ import annotations

import re
import unicodedata

LEGAL = re.compile(r"\b(gmbh|e\.?\s?k\.?|ag|ug|kg|ohg)\b\.?", re.I)
FOLD = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "é": "e"})
SYNONYMS = {"backstube": "baeckerei", "cafe": "cafe", "str": "strasse"}


def name_key(name: str) -> str:
    s = LEGAL.sub(" ", name.lower()).translate(FOLD)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    tokens = [SYNONYMS.get(t, t) for t in re.findall(r"[a-z0-9]+", s)]
    return " ".join(sorted(tokens))


def street_key(street: str) -> str:
    s = street.lower().translate(FOLD).replace("str.", "strasse")
    return re.sub(r"[^a-z0-9]", "", s)


def trigrams(s: str) -> set[str]:
    s = f"  {s} "
    return {s[i : i + 3] for i in range(len(s) - 2)}


def similarity(a: str, b: str) -> float:
    """Trigram Jaccard on normalised names: robust to word order, hyphens and suffixes."""
    ta, tb = trigrams(name_key(a)), trigrams(name_key(b))
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0
