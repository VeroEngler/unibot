from pathlib import Path
import re
import unicodedata

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SUBJECTS_PATH = ROOT_DIR / "MATERIAS.txt"


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
        if not name:
            continue
        key = normalize_text(name)
        if key not in seen:
            seen.add(key)
            subjects.append(name)

    return subjects