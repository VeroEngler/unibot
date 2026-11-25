import discord

from .utils import load_useful_links, normalize_text

# ------------ Link Response Builders -------------


def build_link_response(key: str) -> tuple[discord.Embed, discord.ui.View]:
    """Build an embed and link button for an entry in LINKS_UTILES.txt."""
    links = load_useful_links()
    normalized_key = normalize_text(key)

    if normalized_key not in links:
        raise KeyError(f"No se encontró la clave '{key}' en LINKS_UTILES.txt")

    data = links[normalized_key]
    embed = discord.Embed(
        title=data["title"],
        description=data["description"],
        color=discord.Color.green(),
    )
    view = discord.ui.View()
    view.add_item(
        discord.ui.Button(
            label=data["button_label"],
            url=data["url"],
            style=discord.ButtonStyle.link,
        )
    )
    return embed, view


def build_all_links_response() -> tuple[discord.Embed, discord.ui.View]:
    """Build an embed and button view with all entries from LINKS_UTILES.txt."""
    links = load_useful_links()

    embed = discord.Embed(
        title="🔗 Enlaces Útiles - UNAHUR",
        description=(
            "Accesos directos a las plataformas y secciones principales "
            "de la universidad:"
        ),
        color=discord.Color.green(),
    )
    view = discord.ui.View()

    for data in links.values():
        embed.add_field(
            name=data["title"],
            value=data["description"],
            inline=False,
        )
        view.add_item(
            discord.ui.Button(
                label=data["button_label"],
                url=data["url"],
                style=discord.ButtonStyle.link,
            )
        )

    return embed, view
