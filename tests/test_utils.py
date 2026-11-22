from services.utils import load_opinion_tags, load_subjects, normalize_channel_name, normalize_text

# Normalize channel names and text


def test_normalize_channel_name():
    assert normalize_channel_name("Programación Concurrente I") == "programacion-concurrente-i"
    assert normalize_channel_name("   ") == "canal"

# Load subjects from MATERIAS.txt and deduplicate


def test_normalize_text():
    assert normalize_text("Ciberseguridad") == normalize_text("ciberseguridad")
    assert normalize_text("Matemática Discreta") == "matematica discreta"

# Load subjects from MATERIAS.txt and deduplicate


def test_load_subjects_deduplicates(tmp_path):
    sample = tmp_path / "MATERIAS.txt"
    sample.write_text("Algoritmos\nalgoritmos\n\n# Comentario\nBase de Datos\n", encoding="utf-8")
    assert load_subjects(sample) == ["Algoritmos", "Base de Datos"]

# Load subjects from MATERIAS.txt and ignore empty lines and comments


def test_load_opinion_tags(tmp_path):
    sample = tmp_path / "TAGS_OPINIONES.txt"
    sample.write_text(
        "[CARRERAS]\nInformática\nVideojuegos\n\n[ANIOS]\n1er Año\n2do Año\n",
        encoding="utf-8",
    )
    careers, years = load_opinion_tags(sample)
    assert careers == ["Informática", "Videojuegos"]
    assert years == ["1er Año", "2do Año"]
