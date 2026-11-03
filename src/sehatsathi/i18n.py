"""Language registry — all 22 Eighth-Schedule languages + English.

Each language lives in ``langs/<code>.py`` as a STRINGS dict with:
``native_name``, ``actions`` (per category), ``reminder_normal``,
``reminder_critical``, ``caregiver_normal``, ``caregiver_critical`` and
``ui`` (page chrome). Templates use the placeholders {name} {first}
{action} {due} {signs} {place}; the emergency digits 112/108 and the
terms ASHA/PHC stay constant in every language by design.

VERIFICATION records how each translation was checked. "verified"
means desk-checked string-by-string against the English source by
the maintainers (a maintainer review, NOT a native-speaker
certification); "provisional" languages are careful translations
whose semantics the maintainers could not fully verify — they are
structurally test-verified (script, placeholders, numbers) and need
a native-speaker read before field use. That status is part of the
product's honesty, not a hidden caveat.
Structural correctness (presence, placeholders, native script,
encoding) is enforced for EVERY language by automated tests.
"""
from __future__ import annotations

import importlib

# code -> (English name, verification status)
LANGUAGE_META: dict[str, tuple[str, str]] = {
    "en": ("English", "verified"),
    "hi": ("Hindi", "verified"),
    "kn": ("Kannada", "verified"),
    "as": ("Assamese", "verified"),
    "bn": ("Bengali", "verified"),
    "brx": ("Bodo", "provisional"),
    "doi": ("Dogri", "provisional"),
    "gu": ("Gujarati", "verified"),
    "kok": ("Konkani", "verified"),
    "ks": ("Kashmiri", "provisional"),
    "mai": ("Maithili", "provisional"),
    "ml": ("Malayalam", "verified"),
    "mni": ("Manipuri (Meitei)", "provisional"),
    "mr": ("Marathi", "verified"),
    "ne": ("Nepali", "verified"),
    "or": ("Odia", "verified"),
    "pa": ("Punjabi", "verified"),
    "sa": ("Sanskrit", "provisional"),
    "sat": ("Santali", "provisional"),
    "sd": ("Sindhi", "provisional"),
    "ta": ("Tamil", "verified"),
    "te": ("Telugu", "verified"),
    "ur": ("Urdu", "verified"),
}

# Expected native-script Unicode block per language, (low, high)
# codepoints — used by tests to prove strings render in the right
# script, not transliteration.
SCRIPT_RANGE: dict[str, tuple[int, int]] = {
    "en": (0x0041, 0x007A),
    "hi": (0x0900, 0x097F), "brx": (0x0900, 0x097F), "doi": (0x0900, 0x097F),
    "kok": (0x0900, 0x097F), "mai": (0x0900, 0x097F), "mr": (0x0900, 0x097F),
    "ne": (0x0900, 0x097F), "sa": (0x0900, 0x097F),
    "as": (0x0980, 0x09FF), "bn": (0x0980, 0x09FF),
    "pa": (0x0A00, 0x0A7F), "gu": (0x0A80, 0x0AFF),
    "or": (0x0B00, 0x0B7F), "ta": (0x0B80, 0x0BFF),
    "te": (0x0C00, 0x0C7F), "kn": (0x0C80, 0x0CFF),
    "ml": (0x0D00, 0x0D7F),
    "ur": (0x0600, 0x06FF), "ks": (0x0600, 0x06FF), "sd": (0x0600, 0x06FF),
    "mni": (0xABC0, 0xABFF), "sat": (0x1C50, 0x1C7F),
}


def _load() -> dict[str, dict]:
    langs: dict[str, dict] = {}
    for code in LANGUAGE_META:
        try:
            module = importlib.import_module(f".langs.{code}", __package__)
        except ImportError:
            continue
        langs[code] = module.STRINGS
    return langs


LANGUAGES: dict[str, dict] = _load()

DEFAULT_LANG = "en"


def get_strings(code: str | None) -> dict:
    """String table for `code`, falling back to English."""
    if code and code in LANGUAGES:
        return LANGUAGES[code]
    return LANGUAGES[DEFAULT_LANG]


def language_options() -> list[tuple[str, str, str]]:
    """(code, native name, English name) for pickers — English first,
    then alphabetical by English name."""
    opts = [
        (code, LANGUAGES[code]["native_name"], LANGUAGE_META[code][0])
        for code in LANGUAGES
    ]
    opts.sort(key=lambda t: (t[0] != "en", t[2]))
    return opts
