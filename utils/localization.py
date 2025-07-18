import json
from pathlib import Path

# Diccionario en caché para evitar recargar archivos en cada uso
_loaded_translations = {}

def get_translation(language: str, key: str, **kwargs) -> str:
    global _loaded_translations

    def load_language(lang):
        if lang not in _loaded_translations:
            lang_path = Path("locales") / f"{lang}.json"
            try:
                with lang_path.open("r", encoding="utf-8") as f:
                    _loaded_translations[lang] = json.load(f)
            except FileNotFoundError:
                _loaded_translations[lang] = {}

    load_language(language)
    if language != "en":
        load_language("en")
    if language != "es":
        load_language("es")

    text = (
        _loaded_translations[language].get(key)
        or _loaded_translations.get("en", {}).get(key)
        or _loaded_translations.get("es", {}).get(key)
    )

    if text is None:
        return f"[Missing translation: {key}]"

    # Reemplazar variables dinámicas
    try:
        return text.format(**kwargs)
    except KeyError as e:
        return f"[Translation error: missing {e.args[0]}]"