"""Text utilities for lexical matching, de-duplication and embeddings (NL + EN)."""

from __future__ import annotations

import math
import re
import unicodedata
from array import array
from collections.abc import Iterable, Sequence

_STOPWORDS = frozenset(
    """
    a an the and or but if then than so to of in on at by for with from up down out over under again
    is are was were be been being am do does did doing have has had having i me my mine myself you your
    yours yourself he him his himself she her hers herself it its itself we us our ours they them their
    theirs what which who whom this that these those there here when where why how all any both each few
    more most other some such no nor not only own same too very can will just should now would could
    about into through during before after above below between also yeah yes okay ok lol haha really
    just like get got gonna wanna still even much many one thing things something anything nothing
    de het een en of maar dan dus te van in op aan bij voor met uit naar over onder om tot door als
    ik mij me mijn jij je jou jouw u uw hij hem zijn zij ze haar wij we ons onze jullie hun hen
    die dat deze dit daar hier wat wie welk welke waar wanneer waarom hoe al alle ook nog wel niet
    geen meer veel weinig is ben bent zijn was waren wordt worden werd heb hebt heeft hebben had
    kan kunnen zal zullen zou moet moeten mag wil willen ga gaat gaan doe doet doen er toch maar
    nou ja nee oke oké echt even gewoon heel erg iets niets alles want omdat zo
    bram sofia
    """.split()
)

_WORD_RE = re.compile(r"[a-z0-9]+")
_KEY_LEN = 6  # crude stemming: compare the first 6 characters ("techno"/"technonacht")


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize(text: str) -> str:
    """Lowercase, accent-free, punctuation-free, single-spaced."""
    lowered = strip_accents(text.lower())
    return " ".join(_WORD_RE.findall(lowered))


def tokens(text: str) -> list[str]:
    return [w for w in normalize(text).split() if len(w) > 1 and w not in _STOPWORDS]


def token_keys(text: str) -> set[str]:
    return {w[:_KEY_LEN] for w in tokens(text)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def containment(query: set[str], doc: set[str]) -> float:
    """Share of query keys that occur in the document."""
    if not query or not doc:
        return 0.0
    return len(query & doc) / len(query)


def cosine(a: Sequence[float] | None, b: Sequence[float] | None) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def pack_embedding(vector: Iterable[float] | None) -> bytes | None:
    if vector is None:
        return None
    return array("f", vector).tobytes()


def unpack_embedding(blob: bytes | None) -> list[float] | None:
    if not blob:
        return None
    arr = array("f")
    arr.frombytes(blob)
    return arr.tolist()


def estimate_tokens(text: str) -> int:
    """Cheap token estimate (no tokenizer dependency); errs on the high side."""
    return max(1, int(len(text) / 3.6) + 4)


def keyword_hit(text: str, keywords: Iterable[str]) -> bool:
    """Whole-word / whole-phrase match, accent- and case-insensitive."""
    norm = f" {normalize(text)} "
    for kw in keywords:
        kw_norm = normalize(kw)
        if kw_norm and f" {kw_norm} " in norm:
            return True
    return False


def truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"
