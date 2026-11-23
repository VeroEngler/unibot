"""Metrics board creation and live update service for the UNAHUR Discord bot."""

import logging
import os
from pathlib import Path


import discord


from .utils import DEFAULT_SUBJECTS_PATH, load_subjects, normalize_text

logger = logging.getLogger("unibot")

METRICS_CHANNEL_NAME: str = "📊・metricas"


def _parse_snowflake_id(env_var: str) -> int | None:
    """Safely parse a Discord snowflake ID (channel or role) from an environment variable."""
    raw_value = os.getenv(env_var, "").strip()
    return int(raw_value) if raw_value.isdigit() else None


def _get_career_roles() -> list[tuple[str, int | None]]:
    """Return career display labels paired with their configured role IDs."""
    return [
        ("🖥️ Informática", _parse_snowflake_id("ROLE_CAREER_INFORMATICA_ID")),
        ("🎮 Videojuegos", _parse_snowflake_id("ROLE_CAREER_VIDEOJUEGOS_ID")),
        ("🌐 Ciberseguridad", _parse_snowflake_id("ROLE_CAREER_CIBER_ID")),
        ("🤖 Inteligencia Artificial", _parse_snowflake_id("ROLE_CAREER_IA_ID")),
    ]


def _chunk_lines(lines: list[str], max_length: int = 1000) -> list[str]:
    """Split a list of lines into chunks that fit within Discord's 1024-char field limit."""
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_length = 0

    for line in lines:
        line_length = len(line)
        if current_chunk and current_length + line_length + 1 > max_length:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_length = line_length
        else:
            current_chunk.append(line)
            current_length += line_length + (1 if current_length > 0 else 0)

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


def _build_metrics_embed(
    guild: discord.Guild,
    subjects_file: str | Path = DEFAULT_SUBJECTS_PATH,
) -> discord.Embed:
    """Build the enrollment metrics embed grouped by career and subject."""
    roles_by_norm = {normalize_text(role.name): role for role in guild.roles}

    # 1. Career enrollment counts resolved by role ID from environment variables
    career_lines: list[str] = []
    for label, role_id in _get_career_roles():
        role = guild.get_role(role_id) if role_id is not None else None
        count = len(role.members) if role is not None else 0
        career_lines.append(f"• **{label}:** `{count}`")

    # 2. Subject enrollment counts loaded from MATERIAS.txt and sorted descending
    subject_names = load_subjects(subjects_file)
    subject_counts: list[tuple[str, int]] = []
    for name in subject_names:
        role = roles_by_norm.get(normalize_text(name))
        count = len(role.members) if role is not None else 0
        subject_counts.append((name, count))

    subject_counts.sort(key=lambda item: (-item[1], normalize_text(item[0])))
    subject_lines = [f"• **{name}:** `{count}`" for name, count in subject_counts]

    embed = discord.Embed(
        title="📊 Métricas Servidor Discord",
        description=f"Total de miembros en el servidor: **{guild.member_count}**",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="🎓 Alumnos por Carrera",
        value="\n".join(career_lines) if career_lines else "Sin carreras configuradas.",
        inline=False,
    )

    subject_chunks = _chunk_lines(subject_lines)
    if not subject_chunks:
        embed.add_field(
            name="📚 Inscriptos por Materia",
            value="No hay materias cargadas en MATERIAS.txt.",
            inline=False,
        )
    else:
        for index, chunk in enumerate(subject_chunks):
            field_name = (
                "📚 Inscriptos por Materia" if index == 0 else "📚 Inscriptos por Materia (cont.)"
            )
            embed.add_field(name=field_name, value=chunk, inline=False)

    embed.set_footer(text="Se actualiza automáticamente o mediante /actualizar_metricas")
    return embed


async def _get_or_create_metrics_channel(guild: discord.Guild) -> discord.TextChannel:
    """Resolve the metrics channel via METRICS_CHANNEL_ID, falling back to name or creation."""
    channel_id = _parse_snowflake_id("METRICS_CHANNEL_ID")
    if channel_id is not None:
        existing_by_id = guild.get_channel(channel_id)
        if isinstance(existing_by_id, discord.TextChannel):
            return existing_by_id
        logger.warning(
            "METRICS_CHANNEL_ID (%s) no corresponde a un canal de texto válido; buscando por nombre.",
            channel_id,
        )

    for channel in guild.text_channels:
        if channel.name == METRICS_CHANNEL_NAME:
            return channel

    # Hide the channel from @everyone and grant read-only access to the moderator role
    overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False,
            send_messages=False,
            add_reactions=False,
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_messages=True,
            embed_links=True,
        ),
    }

    mod_role_id = _parse_snowflake_id("ROLE_MODERADOR_ID")
    if mod_role_id is not None:
        mod_role = guild.get_role(mod_role_id)
        if mod_role is not None:
            overwrites[mod_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=False,
                add_reactions=False,
                read_message_history=True,
            )

    created = await guild.create_text_channel(
        name=METRICS_CHANNEL_NAME,
        overwrites=overwrites,
        reason="Creación automática del canal privado de métricas",
    )
    logger.info(
        "Canal de métricas creado (%s | ID: %s). Guardalo en METRICS_CHANNEL_ID.",
        created.name,
        created.id,
    )
    return created


async def update_metrics_board(
    guild: discord.Guild,
    bot_user: discord.ClientUser | None,
    subjects_file: str | Path = DEFAULT_SUBJECTS_PATH,
) -> str:
    """Create or update the pinned enrollment metrics message in the metrics channel."""
    channel = await _get_or_create_metrics_channel(guild)
    embed = _build_metrics_embed(guild, subjects_file=subjects_file)

    # Reuse the existing pinned message authored by the bot to avoid clutter
    pinned_messages = await channel.pins()
    bot_pinned = next(
        (msg for msg in pinned_messages if bot_user is not None and msg.author.id == bot_user.id),
        None,
    )

    if bot_pinned is not None:
        await bot_pinned.edit(content=None, embed=embed)
        return f"✅ Tablero de métricas actualizado en {channel.mention}."

    sent_message = await channel.send(embed=embed)
    await sent_message.pin(reason="Fijar tablero principal de métricas")

    # Remove the system notification generated when pinning the message
    async for msg in channel.history(limit=5):
        if msg.type == discord.MessageType.pins_add:
            await msg.delete()
            break

    return f"✅ Canal {channel.mention} configurado y tablero de métricas fijado."
