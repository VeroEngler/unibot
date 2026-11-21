from pathlib import Path
import discord

from .utils import DEFAULT_SUBJECTS_PATH, load_subjects, normalize_channel_name

RED_UNAHUR_ROLE_ID: int = 1573303828898644018
HISTORY_CHECK_LIMIT: int = 20
DEFAULT_DELETE_HISTORY_LIMIT: int = 50

NOTES_NOTICE_MESSAGE: str = (
    "**Apuntes y material de la materia**\n\n"
    "Acá guardamos apuntes, resúmenes y guías para tener todo a mano sin que se pierda en el chat.\n\n"
    f"¿Tenés algo para sumar? Mandalo al canal de consultas de la materia arrobando a <@&{RED_UNAHUR_ROLE_ID}> "
    "y lo subimos acá. Solo contanos **de qué tema es** y adjuntá el archivo o enlace."
)


# ------------ Helper Functions -------------

# Locate the notes channel inside the subject category or across the guild.
def _find_notes_channel(guild: discord.Guild, subject: str) -> discord.TextChannel | None:
    """Locate the notes channel inside the subject category or across the guild."""
    category = discord.utils.get(guild.categories, name=subject)
    channel_name = normalize_channel_name(f"apuntes-{subject}")

    if category is not None:
        channel = discord.utils.get(category.text_channels, name=channel_name)
        if channel is not None:
            return channel

    return discord.utils.get(guild.text_channels, name=channel_name)

# Check if the notice message was already sent in the channel
async def _is_notice_already_sent(
    channel: discord.TextChannel,
    bot_user: discord.ClientUser | None,
) -> bool:
    """Check recent channel history to prevent duplicate notice messages."""
    if bot_user is None:
        return False

    async for message in channel.history(limit=HISTORY_CHECK_LIMIT):
        if message.author.id == bot_user.id and message.content == NOTES_NOTICE_MESSAGE:
            return True
    return False


# //////////////// Notice Services ////////////////


# ------------- Send Notes Notices -------------


# Send and pin the standard notice in subject notes channels
async def send_notes_notices(
    guild: discord.Guild,
    bot_user: discord.ClientUser | None,
    subjects_file: str | Path = DEFAULT_SUBJECTS_PATH,
    force: bool = False,
    pin: bool = True,
) -> str:
    """Send and optionally pin the standard notes notice in every subject notes channel."""
    subjects = load_subjects(subjects_file)
    if not subjects:
        return "El archivo `MATERIAS.txt` está vacío."

    sent_channels: list[str] = []
    skipped_channels: list[str] = []
    missing_channels: list[str] = []
    forbidden_channels: list[str] = []

    for subject in subjects:
        channel = _find_notes_channel(guild, subject)
        if channel is None:
            channel_name = normalize_channel_name(f"apuntes-{subject}")
            missing_channels.append(f"`{channel_name}` ({subject})")
            continue

        try:
            if not force and await _is_notice_already_sent(channel, bot_user):
                skipped_channels.append(channel.mention)
                continue

            sent_message = await channel.send(NOTES_NOTICE_MESSAGE)
            if pin:
                await sent_message.pin()
            sent_channels.append(channel.mention)
        except discord.Forbidden:
            forbidden_channels.append(channel.mention)

    lines: list[str] = []
    if sent_channels:
        lines.append(f"Avisos enviados ({len(sent_channels)}): " + ", ".join(sent_channels))
    if skipped_channels:
        lines.append(f"Ya tenían el aviso ({len(skipped_channels)}): " + ", ".join(skipped_channels))
    if forbidden_channels:
        lines.append(
            f"Sin permisos para enviar o fijar ({len(forbidden_channels)}): "
            + ", ".join(forbidden_channels)
        )
    if missing_channels:
        lines.append(f"Canales no encontrados ({len(missing_channels)}): " + ", ".join(missing_channels))

    return "\n".join(lines) if lines else "No se realizó ninguna acción."


# ------------- Delete Notes Notices -------------


# Unpin and delete bot notices along with system pin notifications
async def delete_notes_notices(
    guild: discord.Guild,
    bot_user: discord.ClientUser | None,
    subjects_file: str | Path = DEFAULT_SUBJECTS_PATH,
    history_limit: int = DEFAULT_DELETE_HISTORY_LIMIT,
) -> str:
    """Unpin and delete bot notes notices and their system pin notifications."""
    if bot_user is None:
        return "No se pudo identificar al usuario del bot."

    subjects = load_subjects(subjects_file)
    if not subjects:
        return "El archivo `MATERIAS.txt` está vacío."

    cleaned_channels: list[str] = []
    untouched_channels: list[str] = []
    forbidden_channels: list[str] = []
    missing_channels: list[str] = []

    for subject in subjects:
        channel = _find_notes_channel(guild, subject)
        if channel is None:
            channel_name = normalize_channel_name(f"apuntes-{subject}")
            missing_channels.append(f"`{channel_name}` ({subject})")
            continue

        deleted_notices = 0
        deleted_pin_notifications = 0

        try:
            async for message in channel.history(limit=history_limit):
                if message.author.id != bot_user.id:
                    continue

                if message.content == NOTES_NOTICE_MESSAGE:
                    if message.pinned:
                        await message.unpin()
                    await message.delete()
                    deleted_notices += 1
                elif message.type == discord.MessageType.pins_add:
                    await message.delete()
                    deleted_pin_notifications += 1
        except discord.Forbidden:
            forbidden_channels.append(channel.mention)
            continue

        if deleted_notices > 0 or deleted_pin_notifications > 0:
            cleaned_channels.append(
                f"{channel.mention} ({deleted_notices} aviso/s, {deleted_pin_notifications} notif. pin)"
            )
        else:
            untouched_channels.append(channel.mention)

    lines: list[str] = []
    if cleaned_channels:
        lines.append(f"Limpieza realizada ({len(cleaned_channels)}): " + ", ".join(cleaned_channels))
    if untouched_channels:
        lines.append(
            f"Sin avisos ni notificaciones pendientes ({len(untouched_channels)}): "
            + ", ".join(untouched_channels)
        )
    if forbidden_channels:
        lines.append(
            f"Sin permiso para leer historial, desfijar o borrar ({len(forbidden_channels)}): "
            + ", ".join(forbidden_channels)
        )
    if missing_channels:
        lines.append(f"Canales no encontrados ({len(missing_channels)}): " + ", ".join(missing_channels))

    return "\n".join(lines) if lines else "No se realizó ninguna acción."