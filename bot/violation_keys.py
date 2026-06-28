from __future__ import annotations

VIOLATION_KEY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("güncel bekleme ihlali:", "güncel bekleme ihlali"),
    ("mesai başlangıcı ihlali:", "mesai başlangıcı ihlali"),
    ("çağrı arası bekleme ihlali:", "çağrı arası bekleme ihlali"),
    ("mola öncesi çağrı bırakma ihlali:", "mola öncesi çağrı bırakma ihlali"),
    ("mola sonrası çağrı başlangıç ihlali:", "mola sonrası çağrı başlangıç ihlali"),
    ("mesai bitişi ihlali:", "mesai bitişi ihlali"),
)


def violation_key(violation: str) -> str:
    normalized = violation.casefold().strip()
    for prefix, key in VIOLATION_KEY_PREFIXES:
        if normalized.startswith(prefix):
            return key
    return " ".join(normalized.split())