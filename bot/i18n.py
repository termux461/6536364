import json
from pathlib import Path

_LOCALES_DIR = Path(__file__).parent / "locales"
_CACHE: dict[str, dict[str, str]] = {}


def _load(locale: str) -> dict[str, str]:
    if locale not in _CACHE:
        path = _LOCALES_DIR / f"{locale}.json"
        if not path.exists():
            path = _LOCALES_DIR / "ru.json"
        _CACHE[locale] = json.loads(path.read_text(encoding="utf-8"))
    return _CACHE[locale]


def t(locale: str, key: str, **kwargs) -> str:
    strings = _load(locale)
    template = strings.get(key) or _load("ru").get(key, key)
    return template.format(**kwargs) if kwargs else template
