import os
import time
import logging
from collections.abc import Awaitable, Callable

import discord
from discord import app_commands
from discord.ext import commands

from dotenv import load_dotenv

from services import (
    create_subject_channels,
    delete_subject_channels,
    create_subject_roles,
    delete_subject_roles,
    send_notes_notices,
    delete_notes_notices,
    update_metrics_board,
    OpinionTagsView,
)

from ui import ask_confirmation_and_run, send_followup_chunks

load_dotenv()

# Loging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("unibot")

# Track last automatic metrics refresh per guild to prevent rate-limit bursts
METRICS_UPDATE_COOLDOWN_SECONDS: float = 30.0
_last_metrics_update: dict[int, float] = {}

intents = discord.Intents.default()
intents.guilds = True
intents.members = True


class UnahurBot(commands.Bot):
    """Discord bot client with automatic slash command synchronization."""

    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self) -> None:
        await self.tree.sync()


bot = UnahurBot()

# ------------ Helper Functions -------------


async def _run_slash_guild_task(
    interaction: discord.Interaction,
    task: Callable[[], Awaitable[str]],
    forbidden_message: str = "No tengo permisos suficientes para completar la operación.",
    ephemeral: bool = False,
) -> None:
    """Validate guild context, defer interaction response, and execute an async task."""
    if interaction.guild is None:
        await interaction.response.send_message(
            "Este comando solo funciona dentro de un servidor.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=ephemeral)

    try:
        result = await task()
    except FileNotFoundError as exc:
        await interaction.followup.send(f"Error: {exc}", ephemeral=ephemeral)
        return
    except discord.Forbidden:
        await interaction.followup.send(forbidden_message, ephemeral=ephemeral)
        return

    await send_followup_chunks(interaction, result, ephemeral=ephemeral)


# ------------ Bot Events -------------


@bot.event
async def on_ready() -> None:
    """Log bot readiness and connected guilds."""
    if bot.user is not None:
        logger.info("Bot conectado como %s (ID: %s)", bot.user, bot.user.id)
    logger.info("Servidores conectados:")
    for guild in bot.guilds:
        logger.info("- %s (ID: %s)", guild.name, guild.id)


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member) -> None:
    """Automatically refresh the pinned metrics board when a member's roles change."""
    if before.roles == after.roles:
        return

    guild_id = after.guild.id
    now = time.monotonic()
    if now - _last_metrics_update.get(guild_id, 0.0) < METRICS_UPDATE_COOLDOWN_SECONDS:
        return

    _last_metrics_update[guild_id] = now
    try:
        await update_metrics_board(guild=after.guild, bot_user=bot.user)
    except (FileNotFoundError, discord.Forbidden):
        pass


# //////////////// Bot Commands ////////////////


# ------------- Subject Roles -------------


# Command to create subject roles
@bot.tree.command(
    name="crear_roles_materias",
    description="Lee MATERIAS.txt y crea los roles de las materias.",
)
@app_commands.default_permissions(manage_roles=True)
@app_commands.guild_only()
async def create_subjects_slash(interaction: discord.Interaction) -> None:
    await _run_slash_guild_task(
        interaction=interaction,
        task=lambda: create_subject_roles(interaction.guild, interaction.user),
        forbidden_message="No tengo permisos suficientes (**Gestionar roles**).",
    )


# Command to delete subject roles


@bot.tree.command(
    name="borrar_roles_materias",
    description="Lee MATERIAS.txt y elimina los roles de las materias.",
)
@app_commands.default_permissions(manage_roles=True)
@app_commands.guild_only()
async def delete_subjects_slash(interaction: discord.Interaction) -> None:
    await ask_confirmation_and_run(
        interaction=interaction,
        prompt_message=(
            "¿Estás seguro de que querés **eliminar los roles** de las materias "
            "listadas en `MATERIAS.txt`? Esta acción no se puede deshacer."
        ),
        task=lambda: delete_subject_roles(interaction.guild, interaction.user),
        forbidden_message="No tengo permisos suficientes (**Gestionar roles**).",
    )


# ------------- Subject Channels -------------


# Command to create subject channels
@bot.tree.command(
    name="crear_canales",
    description="Lee MATERIAS.txt y configura categorías y canales por materia.",
)
@app_commands.default_permissions(manage_channels=True)
@app_commands.guild_only()
async def create_channels_slash(interaction: discord.Interaction) -> None:
    await _run_slash_guild_task(
        interaction=interaction,
        task=lambda: create_subject_channels(interaction.guild),
        forbidden_message=("No tengo permisos suficientes"
                           "(**Gestionar canales** y **Gestionar roles**)."),
    )


# Command to delete subject channels


@bot.tree.command(
    name="borrar_canales",
    description="Lee MATERIAS.txt y elimina las categorías y canales de las materias.",
)
@app_commands.default_permissions(manage_channels=True)
@app_commands.guild_only()
async def delete_channels_slash(interaction: discord.Interaction) -> None:
    await ask_confirmation_and_run(
        interaction=interaction,
        prompt_message=(
            "¿Estás seguro de que querés **eliminar los canales** de las materias "
            "listadas en `MATERIAS.txt`? Esta acción no se puede deshacer."
        ),
        task=lambda: delete_subject_channels(interaction.guild),
        forbidden_message="No tengo permisos suficientes (**Gestionar canales**).",
    )


# ------------- Subject Notices -------------


# Command to send notes notices
@bot.tree.command(
    name="aviso_apuntes",
    description="Envía y fija el aviso estándar en los canales de apuntes.",
)
@app_commands.describe(forzar="Reenviar el aviso aunque ya exista en el canal")
@app_commands.default_permissions(manage_channels=True)
@app_commands.guild_only()
async def send_notes_notice_slash(
    interaction: discord.Interaction,
    forzar: bool = False,
) -> None:
    await _run_slash_guild_task(
        interaction=interaction,
        task=lambda: send_notes_notices(
            guild=interaction.guild,
            bot_user=bot.user,
            force=forzar,
        ),
        forbidden_message="No tengo permisos suficientes en alguno de los canales.",
    )


# Command to delete notes notices


@bot.tree.command(
    name="borrar_aviso_apuntes",
    description="Desfija y elimina los avisos de apuntes y sus notificaciones.",
)
@app_commands.default_permissions(manage_channels=True)
@app_commands.guild_only()
async def delete_notes_notice_slash(interaction: discord.Interaction) -> None:
    await ask_confirmation_and_run(
        interaction=interaction,
        prompt_message=(
            "¿Estás seguro de que querés **desfijar y eliminar los avisos de apuntes** "
            "en todos los canales listados en `MATERIAS.txt`?"
        ),
        task=lambda: delete_notes_notices(
            guild=interaction.guild,
            bot_user=bot.user,
        ),
        forbidden_message="No tengo permisos suficientes en alguno de los canales.",
    )


# ------------- Metrics -------------


@bot.tree.command(
    name="metrics_update",
    description="Crea o actualiza el mensaje fijado en #📊・metricas",
)
@app_commands.default_permissions(manage_channels=True)
@app_commands.guild_only()
async def update_metrics_slash(interaction: discord.Interaction) -> None:
    await _run_slash_guild_task(
        interaction=interaction,
        task=lambda: update_metrics_board(
            guild=interaction.guild,
            bot_user=bot.user,
        ),
        forbidden_message=(
            "No tengo permisos suficientes "
            "(**Gestionar canales** y **Gestionar mensajes**)."
        ),
    )


# ------------- Anonymous Course Reviews -------------


@bot.tree.command(
    name="opinar_comision",
    description="Publica una opinión anónima sobre una materia o docente.",
)
@app_commands.guild_only()
async def opinion_comision_slash(interaction: discord.Interaction) -> None:
    try:
        view = OpinionTagsView(author_id=interaction.user.id)
    except (FileNotFoundError, ValueError) as exc:
        await interaction.response.send_message(
            f"Error de configuración: {exc}. Avisá a moderación.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        content="Seleccioná las etiquetas de la materia para continuar:",
        view=view,
        ephemeral=True,
    )


# ------------- Token Validation and Startup -------------

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Falta DISCORD_TOKEN en el archivo .env o en las variables de entorno.")
    bot.run(token, log_handler=None)
