import logging
import discord

from .utils import load_useful_links, normalize_text

logger = logging.getLogger(__name__)

MAX_COMPONENTS = 25


class LinkNotFoundError(LookupError):
    """La clave solicitada no existe en los enlaces útiles."""


# ------------ Auxiliary Functions -------------

def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _is_valid(data: dict) -> bool:
    required = ("title", "description", "button_label", "url")
    return all(data.get(k) for k in required) and data["url"].startswith(
        ("http://", "https://")
    )


def _make_button(data: dict) -> discord.ui.Button:
    return discord.ui.Button(
        label=_clip(data["button_label"], 80),
        url=data["url"],
        style=discord.ButtonStyle.link,
    )


# ------------ Link Response Builders -------------


def build_link_response(key: str) -> tuple[discord.Embed, discord.ui.View]:
    links = load_useful_links()
    data = links.get(normalize_text(key))

    if data is None:
        raise LinkNotFoundError(key)
    if not _is_valid(data):
        logger.error("Entrada inválida para la clave %r", key)
        raise ValueError(f"Entrada inválida para '{key}'")

    embed = discord.Embed(
        title=_clip(data["title"], 256),
        description=_clip(data["description"], 4096),
        color=discord.Color.green(),
    )
    view = discord.ui.View(timeout=None)
    view.add_item(_make_button(data))
    return embed, view


def build_all_links_response() -> tuple[discord.Embed, discord.ui.View]:
    links = load_useful_links()
    valid = [d for d in links.values() if _is_valid(d)]

    if len(valid) < len(links):
        logger.warning("Se descartaron %d entradas inválidas", len(links) - len(valid))
    if len(valid) > MAX_COMPONENTS:
        logger.warning("Hay %d enlaces; se muestran solo %d", len(valid), MAX_COMPONENTS)
        valid = valid[:MAX_COMPONENTS]

    embed = discord.Embed(
        title="🔗 Enlaces Útiles - UNAHUR",
        description=(
            "Accesos directos a las plataformas y secciones principales "
            "de la universidad:"
        ),
        color=discord.Color.green(),
    )
    view = discord.ui.View(timeout=None)

    for data in valid:
        embed.add_field(
            name=_clip(data["title"], 256),
            value=_clip(data["description"], 1024),
            inline=False,
        )
        view.add_item(_make_button(data))

    return embed, view