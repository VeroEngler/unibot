import asyncio
from pathlib import Path
import discord

from .utils import DEFAULT_SUBJECTS_PATH, load_subjects, normalize_channel_name, normalize_text

MOD_ROLE_ID: int = 1573303828898644018
GENERAL_SLOWMODE_SECONDS: int = 15
RATE_LIMIT_DELAY_SECONDS: float = 0.5


# Crear Categoría y canales por materia


def build_category_overwrites(
    guild: discord.Guild,
    subject_role: discord.Role | None,
    mod_role: discord.Role | None,
) -> dict[discord.Role | discord.Member, discord.PermissionOverwrite]:
    """Build permission overwrites for a subject category."""
    overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
    }
    if subject_role is not None:
        overwrites[subject_role] = discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
        )
    if mod_role is not None:
        overwrites[mod_role] = discord.PermissionOverwrite(
            view_channel=True,
            manage_messages=True,
            read_message_history=True,
        )
    return overwrites


def build_notes_overwrites(
    guild: discord.Guild,
    subject_role: discord.Role | None,
    mod_role: discord.Role | None,
) -> dict[discord.Role | discord.Member, discord.PermissionOverwrite]:
    """Build read-only permission overwrites for a subject notes channel."""
    overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
    }
    if subject_role is not None:
        overwrites[subject_role] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=False,
            read_message_history=True,
        )
    if mod_role is not None:
        overwrites[mod_role] = discord.PermissionOverwrite(
            view_channel=True,
            manage_messages=True,
            read_message_history=True,
        )
    return overwrites


async def create_subject_channels(
    guild: discord.Guild,
    subjects_file: str | Path = DEFAULT_SUBJECTS_PATH,
) -> str:
    """Create or update categories and text channels for each subject."""
    subjects = load_subjects(subjects_file)
    if not subjects:
        return "El archivo `MATERIAS.txt` está vacío."

    mod_role = guild.get_role(MOD_ROLE_ID)
    summary: list[str] = []
    missing_roles: list[str] = []

    for subject in subjects:
        subject_role = discord.utils.get(guild.roles, name=subject)
        if subject_role is None:
            missing_roles.append(subject)

        category_overwrites = build_category_overwrites(guild, subject_role, mod_role)
        category = discord.utils.get(guild.categories, name=subject)

        if category is None:
            category = await guild.create_category(
                name=subject,
                overwrites=category_overwrites,
            )
        else:
            await category.edit(overwrites=category_overwrites)

        general_name = normalize_channel_name(f"general-{subject}")
        general_channel = discord.utils.get(category.text_channels, name=general_name)
        if general_channel is None:
            general_channel = await guild.create_text_channel(
                name=general_name,
                category=category,
                topic=f"Consultas y chat general de {subject} (slowmode de {GENERAL_SLOWMODE_SECONDS}s).",
                slowmode_delay=GENERAL_SLOWMODE_SECONDS,
            )
        else:
            await general_channel.edit(
                slowmode_delay=GENERAL_SLOWMODE_SECONDS,
                sync_permissions=True,
            )

        notes_name = normalize_channel_name(f"apuntes-{subject}")
        notes_channel = discord.utils.get(category.text_channels, name=notes_name)
        notes_overwrites = build_notes_overwrites(guild, subject_role, mod_role)
        if notes_channel is None:
            notes_channel = await guild.create_text_channel(
                name=notes_name,
                category=category,
                topic=f"Material y apuntes de {subject} (solo lectura para alumnos).",
                overwrites=notes_overwrites,
            )
        else:
            await notes_channel.edit(overwrites=notes_overwrites)

        summary.append(
            f"**{category.name}** → {general_channel.mention} ({GENERAL_SLOWMODE_SECONDS}s) "
            f"| {notes_channel.mention} (solo lectura)"
        )

    output = ["Estructura creada/actualizada:\n" + "\n".join(summary)]
    if mod_role is None:
        output.append(f"\nAviso — no se encontró el rol con ID `{MOD_ROLE_ID}`.")
    if missing_roles:
        formatted_roles = ", ".join(f"`{role}`" for role in missing_roles)
        output.append(
            f"\nAviso — no se encontraron estos roles exactos (ejecuta `/crear_roles_materias` primero): {formatted_roles}"
        )

    return "\n".join(output)


# Eliminar Categoría y canales por materia


async def delete_subject_channels(
    guild: discord.Guild,
    subjects_file: str | Path = DEFAULT_SUBJECTS_PATH,
) -> str:
    """Delete categories and their channels matching the subjects in MATERIAS.txt."""
    subjects = load_subjects(subjects_file)
    if not subjects:
        return "El archivo `MATERIAS.txt` está vacío."

    target_names = {normalize_text(subject) for subject in subjects}
    categories_to_delete = [
        category
        for category in guild.categories
        if normalize_text(category.name) in target_names
    ]

    if not categories_to_delete:
        return "No se encontraron categorías ni canales de materias para eliminar."

    deleted_categories: list[str] = []
    deleted_channels_count: int = 0
    errors: list[str] = []

    for category in categories_to_delete:
        category_failed = False

        # En Discord, eliminar una categoría no borra automáticamente sus canales hijos
        for channel in list(category.channels):
            try:
                await channel.delete(reason="Eliminación masiva de canales de materias.")
                deleted_channels_count += 1
                await asyncio.sleep(RATE_LIMIT_DELAY_SECONDS)
            except discord.Forbidden:
                errors.append(f"#{channel.name} (sin permiso)")
                category_failed = True
            except discord.HTTPException as exc:
                errors.append(f"#{channel.name} (error HTTP {exc.status})")
                category_failed = True

        if category_failed:
            errors.append(f"Categoría **{category.name}** conservada porque quedaron canales sin borrar")
            continue

        try:
            await category.delete(reason="Eliminación masiva de categorías de materias.")
            deleted_categories.append(category.name)
            await asyncio.sleep(RATE_LIMIT_DELAY_SECONDS)
        except discord.Forbidden:
            errors.append(f"Categoría **{category.name}** (sin permiso)")
        except discord.HTTPException as exc:
            errors.append(f"Categoría **{category.name}** (error HTTP {exc.status})")

    summary: list[str] = []
    if deleted_categories:
        summary.append(
            f"**Categorías eliminadas ({len(deleted_categories)}):** {', '.join(deleted_categories)}"
        )
    if deleted_channels_count:
        summary.append(f"**Canales internos eliminados:** {deleted_channels_count}")
    if errors:
        summary.append(f"**Errores ({len(errors)}):** {', '.join(errors)}")

    return "\n".join(summary) or "No se eliminó ninguna categoría ni canal."