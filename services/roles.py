import asyncio
from pathlib import Path
import discord

from .utils import DEFAULT_SUBJECTS_PATH, load_subjects, normalize_text

RATE_LIMIT_DELAY_SECONDS: float = 0.5


async def create_subject_roles(
    guild: discord.Guild,
    author: discord.abc.User,
    subjects_file: str | Path = DEFAULT_SUBJECTS_PATH,
) -> str:
    """Create default-permission roles from MATERIAS.txt."""
    subjects = load_subjects(subjects_file)
    if not subjects:
        return "El archivo MATERIAS.txt está vacío."

    existing_names = {normalize_text(role.name) for role in guild.roles}

    created: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    for subject in subjects:
        if normalize_text(subject) in existing_names:
            skipped.append(subject)
            continue

        try:
            role = await guild.create_role(
                name=subject,
                permissions=discord.Permissions.none(),
                reason=f"Creación de roles de materias por {author}",
            )
            existing_names.add(normalize_text(role.name))
            created.append(role.name)
            await asyncio.sleep(RATE_LIMIT_DELAY_SECONDS)
        except discord.Forbidden:
            errors.append(f"{subject} (sin permiso o jerarquía insuficiente)")
        except discord.HTTPException as exc:
            errors.append(f"{subject} (error HTTP {exc.status})")

    summary: list[str] = []
    if created:
        summary.append(f"**Creados ({len(created)}):** {', '.join(created)}")
    if skipped:
        summary.append(f"**Omitidos por ya existir ({len(skipped)}):** {', '.join(skipped)}")
    if errors:
        summary.append(f"**Errores ({len(errors)}):** {', '.join(errors)}")

    return "\n".join(summary) or "No se procesaron roles."


async def delete_subject_roles(
    guild: discord.Guild,
    author: discord.abc.User,
    subjects_file: str | Path = DEFAULT_SUBJECTS_PATH,
) -> str:
    """Delete server roles matching the subjects in MATERIAS.txt."""
    subjects = load_subjects(subjects_file)
    if not subjects:
        return "El archivo MATERIAS.txt está vacío."

    target_names = {normalize_text(subject) for subject in subjects}
    roles_to_delete = [
        role for role in guild.roles if normalize_text(role.name) in target_names
    ]

    if not roles_to_delete:
        return "No se encontraron roles de materias para eliminar."

    deleted: list[str] = []
    errors: list[str] = []

    for role in roles_to_delete:
        try:
            await role.delete(reason=f"Eliminación masiva de materias por {author}")
            deleted.append(role.name)
            await asyncio.sleep(RATE_LIMIT_DELAY_SECONDS)
        except discord.Forbidden:
            errors.append(f"{role.name} (sin permiso o rol por encima del bot)")
        except discord.HTTPException as exc:
            errors.append(f"{role.name} (error HTTP {exc.status})")

    summary: list[str] = []
    if deleted:
        summary.append(f"**Eliminados ({len(deleted)}):** {', '.join(deleted)}")
    if errors:
        summary.append(f"**Errores ({len(errors)}):** {', '.join(errors)}")

    return "\n".join(summary) or "No se eliminó ningún rol."