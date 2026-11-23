import logging
from collections.abc import Awaitable, Callable

import discord

logger = logging.getLogger("unibot")

DISCORD_MESSAGE_CHUNK_SIZE: int = 1900
GENERIC_ERROR_MESSAGE = "Ocurrió un error inesperado. Avisá a moderación si se repite."

# Single source of truth for response visibility. Used by every admin command and
# confirmation prompt so results are consistently private to whoever ran the command.
DEFAULT_EPHEMERAL: bool = True

# ------------ Helper Functions -------------


def split_text(text: str, limit: int = DISCORD_MESSAGE_CHUNK_SIZE) -> list[str]:
    """Split text into chunks of at most `limit` characters, preferring line breaks."""
    chunks: list[str] = []
    current = ""

    for line in text.splitlines(keepends=True):
        # A single line longer than the limit has to be cut.
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]

        if len(current) + len(line) > limit:
            chunks.append(current)
            current = ""
        current += line

    if current:
        chunks.append(current)

    # Discord rejects empty / whitespace-only messages.
    return [chunk for chunk in chunks if chunk.strip()]


async def send_followup_chunks(
    interaction: discord.Interaction,
    text: str,
    ephemeral: bool = DEFAULT_EPHEMERAL,
) -> None:
    """Send a long response as several followups, respecting Discord's 2000-char limit."""
    output = text if text and text.strip() else "No se realizaron cambios."
    for chunk in split_text(output):
        await interaction.followup.send(chunk, ephemeral=ephemeral)


# //////////////// Interactive Views ////////////////


# ------------- Confirmation View -------------


class ConfirmActionView(discord.ui.View):
    """Interactive confirmation view with Confirm and Cancel buttons."""

    def __init__(
        self,
        author_id: int,
        task: Callable[[], Awaitable[str]],
        forbidden_message: str = "No tengo permisos suficientes para completar la operación.",
        ephemeral: bool = DEFAULT_EPHEMERAL,
        timeout: float = 30.0,
        confirm_label: str = "Confirmar",
        cancel_label: str = "Cancelar",
        progress_message: str = "Ejecutando la operación, por favor esperá...",
        cancel_message: str = "Operación cancelada. No se realizaron cambios.",
    ) -> None:
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.task = task
        self.forbidden_message = forbidden_message
        self.ephemeral = ephemeral
        self.progress_message = progress_message
        self.cancel_message = cancel_message
        self.message: discord.InteractionMessage | None = None

        # Button labels are set here so the view can be reused for any action.
        self.confirm.label = confirm_label
        self.cancel.label = cancel_label

    # Ensure only the command author can click the buttons
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Solo quien ejecutó el comando puede confirmar o cancelar esta acción.",
                ephemeral=True,
            )
            return False
        return True

    # Disable all action buttons once a choice is made or on timeout
    def _disable_buttons(self) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

    # Confirm button handler
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.danger)
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        self._disable_buttons()
        await interaction.response.edit_message(
            content=self.progress_message,
            view=self,
        )
        # Stop the view *before* running the task. Otherwise, if the task takes longer
        # than the view timeout, on_timeout would fire and overwrite the message with
        # "Operación cancelada" while the task is still running.
        self.stop()

        try:
            result = await self.task()
        except FileNotFoundError:
            logger.exception("Archivo de configuración faltante durante una confirmación")
            await interaction.followup.send(
                "Falta un archivo de configuración (por ejemplo, `MATERIAS.txt`). "
                "Avisá a moderación.",
                ephemeral=self.ephemeral,
            )
            return
        except discord.Forbidden:
            await interaction.followup.send(self.forbidden_message, ephemeral=self.ephemeral)
            return
        except discord.HTTPException:
            logger.exception("Error HTTP de Discord durante una confirmación")
            await interaction.followup.send(
                "Discord devolvió un error. Intentá de nuevo en unos minutos.",
                ephemeral=self.ephemeral,
            )
            return
        except Exception:
            logger.exception("Error inesperado durante una confirmación")
            await interaction.followup.send(GENERIC_ERROR_MESSAGE, ephemeral=self.ephemeral)
            return

        await send_followup_chunks(interaction, result, ephemeral=self.ephemeral)

    # Cancel button handler
    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        self._disable_buttons()
        await interaction.response.edit_message(
            content=self.cancel_message,
            view=self,
        )
        self.stop()

    async def on_timeout(self) -> None:
        self._disable_buttons()
        if self.message is not None:
            try:
                await self.message.edit(
                    content="Tiempo de confirmación agotado. Operación cancelada.",
                    view=self,
                )
            except discord.HTTPException:
                logger.warning("No se pudo editar el mensaje de confirmación tras el timeout")


# ------------- Confirmation Entrypoint -------------


async def ask_confirmation_and_run(
    interaction: discord.Interaction,
    prompt_message: str,
    task: Callable[[], Awaitable[str]],
    forbidden_message: str = "No tengo permisos suficientes para completar la operación.",
    ephemeral: bool = DEFAULT_EPHEMERAL,
    confirm_label: str = "Confirmar",
    progress_message: str = "Ejecutando la operación, por favor esperá...",
    cancel_message: str = "Operación cancelada. No se realizaron cambios.",
) -> None:
    """Validate guild context and prompt for confirmation before running a task."""
    if interaction.guild is None:
        await interaction.response.send_message(
            "Este comando solo funciona dentro de un servidor.",
            ephemeral=True,
        )
        return

    view = ConfirmActionView(
        author_id=interaction.user.id,
        task=task,
        forbidden_message=forbidden_message,
        ephemeral=ephemeral,
        confirm_label=confirm_label,
        progress_message=progress_message,
        cancel_message=cancel_message,
    )
    await interaction.response.send_message(
        content=prompt_message,
        view=view,
        ephemeral=ephemeral,
    )
    view.message = await interaction.original_response()
