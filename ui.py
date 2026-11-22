from collections.abc import Awaitable, Callable
import discord

DISCORD_MESSAGE_CHUNK_SIZE: int = 1900

# ------------ Helper Functions -------------

# Split long responses into Discord-safe character chunks


async def send_followup_chunks(
    interaction: discord.Interaction,
    text: str,
    ephemeral: bool = True,
) -> None:
    # Split long responses to comply with Discord's 2000-character limit.
    output = text if text and text.strip() else "No se realizaron cambios."
    for start in range(0, len(output), DISCORD_MESSAGE_CHUNK_SIZE):
        chunk = output[start:start + DISCORD_MESSAGE_CHUNK_SIZE]
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
        ephemeral: bool = True,
        timeout: float = 30.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.task = task
        self.forbidden_message = forbidden_message
        self.ephemeral = ephemeral
        self.message: discord.InteractionMessage | None = None

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
    @discord.ui.button(label="Confirmar borrado", style=discord.ButtonStyle.danger)
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        self._disable_buttons()
        await interaction.response.edit_message(
            content="Ejecutando borrado, por favor esperá...",
            view=self,
        )

        try:
            result = await self.task()
        except FileNotFoundError as exc:
            await interaction.followup.send(f"Error: {exc}", ephemeral=self.ephemeral)
            self.stop()
            return
        except discord.Forbidden:
            await interaction.followup.send(self.forbidden_message, ephemeral=self.ephemeral)
            self.stop()
            return

        await send_followup_chunks(interaction, result, ephemeral=self.ephemeral)
        self.stop()

    # Cancel button handler
    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        self._disable_buttons()
        await interaction.response.edit_message(
            content="Operación cancelada. No se borró nada.",
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
                pass


# ------------- Confirmation Entrypoint -------------

# Validate guild context and display the confirmation prompt


async def ask_confirmation_and_run(
    interaction: discord.Interaction,
    prompt_message: str,
    task: Callable[[], Awaitable[str]],
    forbidden_message: str = "No tengo permisos suficientes para completar la operación.",
    ephemeral: bool = True,
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
    )
    await interaction.response.send_message(
        content=prompt_message,
        view=view,
        ephemeral=ephemeral,
    )
    view.message = await interaction.original_response()
