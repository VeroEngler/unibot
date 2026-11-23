import asyncio
import logging
import os
from collections.abc import Awaitable, Callable

import discord
from discord import app_commands
from dotenv import load_dotenv

from services import (
    OpinionTagsView,
    create_subject_channels,
    create_subject_roles,
    delete_notes_notices,
    delete_subject_channels,
    delete_subject_roles,
    send_notes_notices,
    update_metrics_board,
)
from ui import DEFAULT_EPHEMERAL, ask_confirmation_and_run, send_followup_chunks

load_dotenv()

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("unibot")

# ------------ Constants -------------

# Delay before an automatic metrics refresh runs after a role change.
# Multiple role changes within this window are collapsed into a single refresh.
METRICS_UPDATE_DELAY_SECONDS: float = 30.0

GENERIC_ERROR_MESSAGE = "Ocurrió un error inesperado. Avisá a moderación si se repite."


def _parse_int_env(name: str) -> int | None:
    """Read an optional integer environment variable."""
    value = os.getenv(name)
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        logger.warning("La variable %s no es un entero válido: %r", name, value)
        return None


# Optional: if set, commands are synced only to this guild (instant, ideal for development).
TEST_GUILD_ID: int | None = _parse_int_env("TEST_GUILD_ID")
# Global sync is only performed when explicitly requested (SYNC_COMMANDS=1).
SYNC_COMMANDS: bool = os.getenv("SYNC_COMMANDS", "0") == "1"


class UnahurBot(discord.Client):
    """Discord bot client with controlled slash command synchronization."""

    def __init__(self) -> None:
        # Default intents already include `guilds`.
        # `members` is privileged: it must be enabled in the Developer Portal.
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(intents=intents)

        self.tree = app_commands.CommandTree(self)
        # Pending (deferred) metrics refreshes, one per guild.
        self._pending_metrics_updates: dict[int, asyncio.Task[None]] = {}

    async def setup_hook(self) -> None:
        if TEST_GUILD_ID is not None:
            guild = discord.Object(id=TEST_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("Comandos sincronizados en el servidor de pruebas %s", TEST_GUILD_ID)
        elif SYNC_COMMANDS:
            await self.tree.sync()
            logger.info("Comandos sincronizados globalmente")
        else:
            logger.info("Sincronización de comandos omitida (usar SYNC_COMMANDS=1 para forzarla)")

    async def close(self) -> None:
        for task in self._pending_metrics_updates.values():
            task.cancel()
        self._pending_metrics_updates.clear()
        await super().close()

    # ---- Deferred metrics refresh ----

    def schedule_metrics_update(self, guild: discord.Guild) -> None:
        """Schedule a metrics refresh for the guild unless one is already pending.

        The refresh runs after a delay and reads the guild state at that moment,
        so it always reflects the most recent changes.
        """
        if guild.id in self._pending_metrics_updates:
            return
        self._pending_metrics_updates[guild.id] = asyncio.create_task(
            self._delayed_metrics_update(guild)
        )

    async def _delayed_metrics_update(self, guild: discord.Guild) -> None:
        try:
            await asyncio.sleep(METRICS_UPDATE_DELAY_SECONDS)
            await update_metrics_board(guild=guild, bot_user=self.user)
        except asyncio.CancelledError:
            raise
        except (FileNotFoundError, discord.Forbidden):
            logger.warning("No se pudo actualizar el tablero de métricas en %s", guild.id)
        except Exception:
            logger.exception("Error inesperado actualizando métricas en %s", guild.id)
        finally:
            self._pending_metrics_updates.pop(guild.id, None)


bot = UnahurBot()

# ------------ Helper Functions -------------


def _get_guild(interaction: discord.Interaction) -> discord.Guild:
    """Return the interaction guild or raise if the command was used outside a server."""
    if interaction.guild is None:
        raise app_commands.NoPrivateMessage()
    return interaction.guild


async def _run_slash_guild_task(
    interaction: discord.Interaction,
    task: Callable[[discord.Guild], Awaitable[str]],
    forbidden_message: str = "No tengo permisos suficientes para completar la operación.",
    ephemeral: bool = DEFAULT_EPHEMERAL,
) -> None:
    """Validate guild context, defer the response, and execute an async task."""
    if interaction.guild is None:
        await interaction.response.send_message(
            "Este comando solo funciona dentro de un servidor.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=ephemeral)

    try:
        result = await task(interaction.guild)
    except FileNotFoundError:
        logger.exception("Archivo de configuración faltante en /%s",
                         interaction.command.name if interaction.command else "?")
        await interaction.followup.send(
            "Falta un archivo de configuración (por ejemplo, `MATERIAS.txt`). Avisá a moderación.",
            ephemeral=ephemeral,
        )
        return
    except discord.Forbidden:
        await interaction.followup.send(forbidden_message, ephemeral=ephemeral)
        return
    except discord.HTTPException:
        logger.exception("Error HTTP de Discord")
        await interaction.followup.send(
            "Discord devolvió un error. Intentá de nuevo en unos minutos.",
            ephemeral=ephemeral,
        )
        return
    except Exception:
        logger.exception("Error inesperado ejecutando un comando")
        await interaction.followup.send(GENERIC_ERROR_MESSAGE, ephemeral=ephemeral)
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
    """Schedule a refresh of the pinned metrics board when a member's roles change."""
    if before.roles == after.roles:
        return
    bot.schedule_metrics_update(after.guild)


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    """Global fallback handler for slash command errors."""
    if isinstance(error, app_commands.MissingPermissions):
        message = "No tenés permisos para usar este comando."
    elif isinstance(error, app_commands.NoPrivateMessage):
        message = "Este comando solo funciona dentro de un servidor."
    else:
        logger.error("Error en comando de aplicación", exc_info=error)
        message = GENERIC_ERROR_MESSAGE

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


# //////////////// Bot Commands ////////////////


# ------------- Subject Roles -------------


@bot.tree.command(
    name="crear_roles_materias",
    description="Lee MATERIAS.txt y crea los roles de las materias.",
)
@app_commands.default_permissions(manage_roles=True)
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.guild_only()
async def create_subjects_slash(interaction: discord.Interaction) -> None:
    await _run_slash_guild_task(
        interaction=interaction,
        task=lambda guild: create_subject_roles(guild, interaction.user),
        forbidden_message="No tengo permisos suficientes (**Gestionar roles**).",
    )


@bot.tree.command(
    name="borrar_roles_materias",
    description="Lee MATERIAS.txt y elimina los roles de las materias.",
)
@app_commands.default_permissions(manage_roles=True)
@app_commands.checks.has_permissions(manage_roles=True)
@app_commands.guild_only()
async def delete_subjects_slash(interaction: discord.Interaction) -> None:
    guild = _get_guild(interaction)
    await ask_confirmation_and_run(
        interaction=interaction,
        prompt_message=(
            "¿Estás seguro de que querés **eliminar los roles** de las materias "
            "listadas en `MATERIAS.txt`? Esta acción no se puede deshacer."
        ),
        task=lambda: delete_subject_roles(guild, interaction.user),
        confirm_label="Eliminar roles",
        progress_message="Eliminando roles, por favor esperá...",
        cancel_message="Operación cancelada. No se eliminó ningún rol.",
        forbidden_message="No tengo permisos suficientes (**Gestionar roles**).",
    )


# ------------- Subject Channels -------------


@bot.tree.command(
    name="crear_canales",
    description="Lee MATERIAS.txt y configura categorías y canales por materia.",
)
@app_commands.default_permissions(manage_channels=True)
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.guild_only()
async def create_channels_slash(interaction: discord.Interaction) -> None:
    await _run_slash_guild_task(
        interaction=interaction,
        task=create_subject_channels,
        forbidden_message=(
            "No tengo permisos suficientes "
            "(**Gestionar canales** y **Gestionar roles**)."
        ),
    )


@bot.tree.command(
    name="borrar_canales",
    description="Lee MATERIAS.txt y elimina las categorías y canales de las materias.",
)
@app_commands.default_permissions(manage_channels=True)
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.guild_only()
async def delete_channels_slash(interaction: discord.Interaction) -> None:
    guild = _get_guild(interaction)
    await ask_confirmation_and_run(
        interaction=interaction,
        prompt_message=(
            "¿Estás seguro de que querés **eliminar los canales** de las materias "
            "listadas en `MATERIAS.txt`? Esta acción no se puede deshacer."
        ),
        task=lambda: delete_subject_channels(guild),
        confirm_label="Eliminar canales",
        progress_message="Eliminando canales, por favor esperá...",
        cancel_message="Operación cancelada. No se eliminó ningún canal.",
        forbidden_message="No tengo permisos suficientes (**Gestionar canales**).",
    )


# ------------- Subject Notices -------------


@bot.tree.command(
    name="aviso_apuntes",
    description="Envía y fija el aviso estándar en los canales de apuntes.",
)
@app_commands.describe(forzar="Reenviar el aviso aunque ya exista en el canal")
@app_commands.default_permissions(manage_channels=True)
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.guild_only()
async def send_notes_notice_slash(
    interaction: discord.Interaction,
    forzar: bool = False,
) -> None:
    await _run_slash_guild_task(
        interaction=interaction,
        task=lambda guild: send_notes_notices(
            guild=guild,
            bot_user=bot.user,
            force=forzar,
        ),
        forbidden_message="No tengo permisos suficientes en alguno de los canales.",
    )


@bot.tree.command(
    name="borrar_aviso_apuntes",
    description="Desfija y elimina los avisos de apuntes y sus notificaciones.",
)
@app_commands.default_permissions(manage_channels=True)
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.guild_only()
async def delete_notes_notice_slash(interaction: discord.Interaction) -> None:
    guild = _get_guild(interaction)
    await ask_confirmation_and_run(
        interaction=interaction,
        prompt_message=(
            "¿Estás seguro de que querés **desfijar y eliminar los avisos de apuntes** "
            "en todos los canales listados en `MATERIAS.txt`?"
        ),
        task=lambda: delete_notes_notices(
            guild=guild,
            bot_user=bot.user,
        ),
        confirm_label="Eliminar avisos",
        progress_message="Eliminando avisos, por favor esperá...",
        cancel_message="Operación cancelada. No se eliminó ningún aviso.",
        forbidden_message="No tengo permisos suficientes en alguno de los canales.",
    )


# ------------- Metrics -------------


@bot.tree.command(
    name="actualizar_metricas",
    description="Crea o actualiza el mensaje fijado en el canal de métricas.",
)
@app_commands.default_permissions(manage_channels=True)
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.guild_only()
async def update_metrics_slash(interaction: discord.Interaction) -> None:
    await _run_slash_guild_task(
        interaction=interaction,
        task=lambda guild: update_metrics_board(
            guild=guild,
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
    except (FileNotFoundError, ValueError):
        logger.exception("Error de configuración al crear OpinionTagsView")
        await interaction.response.send_message(
            "Error de configuración. Avisá a moderación.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        content="Seleccioná las etiquetas de la materia para continuar:",
        view=view,
        ephemeral=True,
    )
    view.message = await interaction.original_response()


# ------------- Token Validation and Startup -------------

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Falta DISCORD_TOKEN en el archivo .env o en las variables de entorno.")
    bot.run(token, log_handler=None)
