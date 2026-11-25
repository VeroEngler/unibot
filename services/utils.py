from pathlib import Path
import re
import unicodedata


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SUBJECTS_PATH = ROOT_DIR / "MATERIAS.txt"
DEFAULT_OPINION_TAGS_PATH = ROOT_DIR / "TAGS_OPINIONS.txt"
DEFAULT_LINKS_PATH = ROOT_DIR / "LINKS_UTILES.txt"


def normalize_channel_name(text: str) -> str:
    """Normalize a string into a valid Discord text channel name."""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-z0-9]+", "-", normalized.lower().strip())
    return cleaned.strip("-") or "canal"


def normalize_text(text: str) -> str:
    """Strip diacritics and casefold text for accent-insensitive comparisons."""
    without_accents = "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    )
    return without_accents.casefold().strip()


def load_subjects(file_path: str | Path = DEFAULT_SUBJECTS_PATH) -> list[str]:
    """Read unique, non-empty subject lines from MATERIAS.txt."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo {path.name}")

    subjects: list[str] = []
    seen: set[str] = set()

    for line in path.read_text(encoding="utf-8").splitlines():
        name = line.strip()
        if not name or name.startswith("#"):
            continue
        key = normalize_text(name)
        if key not in seen:
            seen.add(key)
            subjects.append(name)

    return subjects


# --------- Subject search ---------

_ARABIC_TO_ROMAN = {
    "1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v",
}
_ROMAN_TOKENS = frozenset(_ARABIC_TO_ROMAN.values())


def _search_tokens(text: str) -> list[str]:
    """Normalize text and convert arabic numerals to roman so '1' matches 'I'."""
    return [_ARABIC_TO_ROMAN.get(t, t) for t in normalize_text(text).split()]


def search_subjects(subjects: list[str], query: str) -> list[str]:
    """Subjects where every query token matches (roman numerals must match exactly)."""
    query_tokens = _search_tokens(query)
    if not query_tokens:
        return []

    results: list[str] = []
    for name in subjects:
        name_tokens = _search_tokens(name)
        name_joined = " ".join(name_tokens)
        if all(
            (tok in name_tokens) if tok in _ROMAN_TOKENS else (tok in name_joined)
            for tok in query_tokens
        ):
            results.append(name)
    return results


# --------- Opinions Tags ---------


def load_opinion_tags(
    file_path: str | Path = DEFAULT_OPINION_TAGS_PATH,
) -> tuple[list[str], list[str]]:
    """Read [CARRERAS] and [ANIOS] forum tag names from TAGS_OPINIONES.txt."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo {path.name}")

    careers: list[str] = []
    years: list[str] = []
    seen_careers: set[str] = set()
    seen_years: set[str] = set()
    current_section: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        header = normalize_text(line)
        if header == "[carreras]":
            current_section = "carreras"
            continue
        if header in {"[anios]", "[años]"}:
            current_section = "anios"
            continue

        key = normalize_text(line)
        if current_section == "carreras" and key not in seen_careers:
            seen_careers.add(key)
            careers.append(line)
        elif current_section == "anios" and key not in seen_years:
            seen_years.add(key)
            years.append(line)

    return careers, years


# --------- Useful Links ---------


DEFAULT_LINKS_PATH = ROOT_DIR / "LINKS_UTILES.txt"


def load_useful_links(
    file_path: str | Path = DEFAULT_LINKS_PATH,
) -> dict[str, dict[str, str]]:
    """Read useful student links from LINKS_UTILES.txt."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo {path.name}")

    links: dict[str, dict[str, str]] = {}

    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 5:
            raise ValueError(
                f"Formato inválido en {path.name} (línea {line_number}). "
                "Se esperaba: clave | titulo | descripcion | boton | url"
            )

        key, title, description, button_label, url = parts
        normalized_key = normalize_text(key)
        links[normalized_key] = {
            "title": title,
            "description": description,
            "button_label": button_label,
            "url": url,
        }

    return links
