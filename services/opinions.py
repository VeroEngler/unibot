import asyncio
import logging
import os
from pathlib import Path

import discord

from .utils import (
    DEFAULT_OPINION_TAGS_PATH,
    load_opinion_tags,
    normalize_text,
)

logger = logging.getLogger("unibot")

MENSAJE_CONFIRMACION_ANONIMA: str = (
    "⚠️ **Recordatorio antes de publicar:**\n"
    "Tu opinión se publicará de forma anónima, pero **el respeto es obligatorio**. "
    "Solo críticas constructivas, sin agresiones ni ataques personales. "
    "Cualquier post o mensaje que rompa las reglas será eliminado."
)

GENERIC_ERROR_MESSAGE = "Ocurrió un error inesperado. Avisá a moderación si se repite."
MAX_FORUM_TAGS_PER_THREAD = 5
MAX_SELECT_OPTIONS = 25

# Serializes "find thread -> create/append" so two simultaneous reviews of the same
# subject don't end up creating duplicate forum posts.
_publish_lock = asyncio.Lock()


# ------------ Helper Functions -------------


def _parse_channel_id(env_var: str) -> int | None:
    """Parse a positive integer channel ID from an environment variable."""
    raw = os.getenv(env_var, "").strip()
    return int(raw) if raw.isdigit() else None


def _capitalize_first(text: str) -> str:
    """Capitalize only the first character while preserving remaining casing."""
    cleaned = text.strip()
    return f"{cleaned[0].upper()}{cleaned[1:]}" if cleaned else ""


def _build_public_message(comision: str, profesor: str, opinion: str) -> str:
    """Build the text that gets published in the forum (max ~1904 chars with modal limits)."""
    return f"{comision}\n\n{profesor}\n\n{opinion}"


async def _send_generic_error(interaction: discord.Interaction) -> None:
    """Best-effort generic error reply that works whether or not we already responded."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(GENERIC_ERROR_MESSAGE, ephemeral=True)
        else:
            await interaction.response.send_message(GENERIC_ERROR_MESSAGE, ephemeral=True)
    except discord.HTTPException:
        logger.warning("No se pudo enviar el mensaje de error al usuario")


async def _find_existing_subject_thread(
    forum_channel: discord.ForumChannel,
    subject_name: str,
) -> discord.Thread | None:
    """Find an existing forum thread for the given subject (accent/case-insensitive)."""
    target_key = normalize_text(subject_name)

    for thread in forum_channel.threads:
        if normalize_text(thread.name) == target_key:
            return thread

    async for thread in forum_channel.archived_threads(limit=None):
        if normalize_text(thread.name) == target_key:
            return thread

    return None


# //////////////// Interactive Views & Modals ////////////////


class _AuthorOnlyView(discord.ui.View):
    """Base view: restricted to one user, disables itself on timeout, logs errors."""

    # Text shown when the view times out. If None, the message content is left untouched.
    timeout_message: str | None = None

    def __init__(self, author_id: int, timeout: float = 180.0) -> None:
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.message: discord.InteractionMessage | None = None
        self._busy = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    def _set_disabled(self, disabled: bool) -> None:
        for child in self.children:
            if isinstance(child, (discord.ui.Button, discord.ui.Select)):
                child.disabled = disabled

    async def on_timeout(self) -> None:
        if self._busy or self.message is None:
            return
        self._set_disabled(True)
        edit_kwargs: dict = {"view": self}
        if self.timeout_message:
            edit_kwargs["content"] = self.timeout_message
        try:
            await self.message.edit(**edit_kwargs)
        except discord.HTTPException:
            logger.warning("No se pudo deshabilitar la vista tras el timeout")

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item,
    ) -> None:
        logger.error("Error en una vista de opiniones", exc_info=error)
        await _send_generic_error(interaction)


# ------------- Step 3: Confirmation View -------------


class OpinionConfirmView(_AuthorOnlyView):
    """Final confirmation prompt before publishing the anonymous review."""

    timeout_message = "⌛ Se agotó el tiempo de confirmación. Tu opinión no fue publicada."

    def __init__(
        self,
        author_id: int,
        carrera_tag_name: str,
        anio_tag_name: str,
        titulo_materia: str,
        comision_txt: str,
        profesor_txt: str,
        opinion_txt: str,
    ) -> None:
        super().__init__(author_id, timeout=180.0)
        self.carrera_tag_name = carrera_tag_name
        self.anio_tag_name = anio_tag_name
        self.titulo_materia = titulo_materia
        self.comision_txt = comision_txt
        self.profesor_txt = profesor_txt
        self.opinion_txt = opinion_txt

    async def _publish(self, forum: discord.ForumChannel) -> tuple[str, str]:
        """Publish the review in the forum. Returns (jump_url, log_action)."""
        selected_keys = {
            normalize_text(self.carrera_tag_name),
            normalize_text(self.anio_tag_name),
        }
        applied_tags = [
            tag for tag in forum.available_tags if normalize_text(tag.name) in selected_keys
        ]
        missing = selected_keys - {normalize_text(tag.name) for tag in applied_tags}
        if missing:
            logger.warning(
                "Etiquetas seleccionadas que no existen en el foro: %s", ", ".join(sorted(missing))
            )

        public_message = _build_public_message(
            self.comision_txt, self.profesor_txt, self.opinion_txt
        )
        no_mentions = discord.AllowedMentions.none()

        async with _publish_lock:
            thread = await _find_existing_subject_thread(forum, self.titulo_materia)

            if thread is not None:
                if thread.archived:
                    await thread.edit(archived=False)

                current_ids = {t.id for t in thread.applied_tags}
                merged_tags = list(thread.applied_tags)
                for tag in applied_tags:
                    if tag.id not in current_ids and len(merged_tags) < MAX_FORUM_TAGS_PER_THREAD:
                        merged_tags.append(tag)
                if len(merged_tags) > len(thread.applied_tags):
                    await thread.edit(applied_tags=merged_tags)

                sent_msg = await thread.send(content=public_message, allowed_mentions=no_mentions)
                return sent_msg.jump_url, "Comentario agregado a post existente"

            created = await forum.create_thread(
                name=self.titulo_materia[:100],
                content=public_message,
                applied_tags=applied_tags,
                allowed_mentions=no_mentions,
            )
            return created.message.jump_url, "Nuevo post creado en el foro"

    async def _send_audit_log(
        self,
        interaction: discord.Interaction,
        logs_channel: discord.abc.GuildChannel | None,
        action: str,
        jump_url: str,
    ) -> None:
        """Send the moderation log. Failures here must never undo a successful publication."""
        if not isinstance(logs_channel, discord.TextChannel):
            return

        log_embed = discord.Embed(
            title=f"🕵️ Registro de opinión anónima ({action})",
            description=self.opinion_txt,
            color=discord.Color.orange(),
        )
        log_embed.add_field(
            name="Autor real",
            value=(
                f"{interaction.user.mention} "
                f"(`{interaction.user}` | ID: `{interaction.user.id}`)"
            ),
            inline=False,
        )
        log_embed.add_field(
            name="Materia / Tags",
            value=f"**{self.titulo_materia}** ({self.anio_tag_name} • {self.carrera_tag_name})",
            inline=False,
        )
        log_embed.add_field(
            name="Comisión / Docente",
            value=f"{self.comision_txt} — {self.profesor_txt}",
            inline=False,
        )
        log_embed.add_field(
            name="Enlace al post",
            value=f"[Ir al mensaje en el foro]({jump_url})",
            inline=False,
        )
        try:
            await logs_channel.send(embed=log_embed,
                                    allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            logger.exception("No se pudo enviar el registro de opinión al canal de logs")

    async def _fail(self, interaction: discord.Interaction, text: str, retry: bool) -> None:
        """Report a publishing failure, optionally keeping the buttons for a retry."""
        self._busy = False
        if retry:
            self._set_disabled(False)
            await interaction.edit_original_response(
                content=f"❌ {text}\nPodés volver a intentar.", view=self
            )
        else:
            await interaction.edit_original_response(content=f"❌ {text}", embed=None, view=None)
            self.stop()

    @discord.ui.button(label="Acepto y publicar", style=discord.ButtonStyle.success)
    async def confirm_publish(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if self._busy:
            await interaction.response.send_message(
                "Tu opinión ya se está publicando, esperá un momento.",
                ephemeral=True,
            )
            return

        if interaction.guild is None:
            await interaction.response.send_message(
                "Este formulario solo funciona dentro del servidor.",
                ephemeral=True,
            )
            return

        public_id = _parse_channel_id("OPINIONES_CHANNEL_ID")
        logs_id = _parse_channel_id("LOGS_OPINIONES_CHANNEL_ID")

        public_channel = interaction.guild.get_channel(public_id) if public_id else None
        logs_channel = interaction.guild.get_channel(logs_id) if logs_id else None

        if not isinstance(public_channel, discord.ForumChannel):
            await interaction.response.edit_message(
                content="No está configurado el canal de Foro de opiniones. Avisá a moderación.",
                embed=None,
                view=None,
            )
            self.stop()
            return

        self._busy = True
        self._set_disabled(True)
        await interaction.response.edit_message(
            content="Publicando tu opinión de forma anónima...",
            view=self,
        )

        try:
            jump_url, action = await self._publish(public_channel)
        except discord.Forbidden:
            logger.exception("Sin permisos para publicar en el foro de opiniones")
            await self._fail(
                interaction,
                "No tengo permisos para publicar en el foro. Avisá a moderación.",
                retry=False,
            )
            return
        except discord.HTTPException:
            logger.exception("Error HTTP de Discord al publicar una opinión")
            await self._fail(interaction, "Discord devolvió un error al publicar.", retry=True)
            return
        except Exception:
            logger.exception("Error inesperado al publicar una opinión")
            await self._fail(interaction, GENERIC_ERROR_MESSAGE, retry=True)
            return

        await self._send_audit_log(interaction, logs_channel, action, jump_url)

        await interaction.edit_original_response(
            content="✅ Tu opinión fue publicada de forma anónima.",
            embed=None,
            view=None,
        )
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel_publish(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if self._busy:
            await interaction.response.send_message(
                "Ya no se puede cancelar: la opinión se está publicando.",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            content="❌ Publicación cancelada. No se envió ningún mensaje.",
            embed=None,
            view=None,
        )
        self.stop()


# ------------- Step 2: Review Input Modal -------------


class OpinionModal(discord.ui.Modal, title="Opinión anónima de cátedra"):
    materia = discord.ui.TextInput(
        label="Materia",
        placeholder="Ej: Redes de Computadoras",
        max_length=100,
        required=True,
    )
    comision = discord.ui.TextInput(
        label="Comisión / Horario",
        placeholder="Ej: Miércoles Noche - Virtual",
        max_length=150,
        required=True,
    )
    profesor = discord.ui.TextInput(
        label="Profesor/a",
        placeholder="Ej: Xoana Prior (2C 2026)",
        max_length=150,
        required=True,
    )
    opinion = discord.ui.TextInput(
        label="Opinión",
        style=discord.TextStyle.paragraph,
        placeholder="Contá cómo explica, cómo son los parciales/TPs, consejos, etc.",
        max_length=1600,
        required=True,
    )

    def __init__(self, carrera_tag_name: str, anio_tag_name: str) -> None:
        super().__init__()
        self.carrera_tag_name = carrera_tag_name
        self.anio_tag_name = anio_tag_name

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este formulario solo funciona dentro del servidor.",
                ephemeral=True,
            )
            return

        titulo_materia = _capitalize_first(self.materia.value)
        comision_txt = self.comision.value.strip()
        profesor_txt = self.profesor.value.strip()
        opinion_txt = self.opinion.value.strip()

        # `required=True` still lets whitespace-only values through.
        if not all((titulo_materia, comision_txt, profesor_txt, opinion_txt)):
            await interaction.response.send_message(
                "⚠️ Todos los campos son obligatorios y no pueden quedar vacíos. "
                "Volvé a usar `/opinar_comision`.",
                ephemeral=True,
            )
            return

        confirm_view = OpinionConfirmView(
            author_id=interaction.user.id,
            carrera_tag_name=self.carrera_tag_name,
            anio_tag_name=self.anio_tag_name,
            titulo_materia=titulo_materia,
            comision_txt=comision_txt,
            profesor_txt=profesor_txt,
            opinion_txt=opinion_txt,
        )

        # The preview goes in an embed (4096 chars) so it is never cut off, unlike
        # message content (2000 chars) once the reminder text is included.
        preview = discord.Embed(
            title=f"📌 {titulo_materia}",
            description=_build_public_message(comision_txt, profesor_txt, opinion_txt),
            color=discord.Color.blurple(),
        )
        preview.set_footer(text=f"{self.carrera_tag_name} • {self.anio_tag_name}")

        await interaction.response.send_message(
            content=f"{MENSAJE_CONFIRMACION_ANONIMA}\n\n**Vista previa de tu publicación:**",
            embed=preview,
            view=confirm_view,
            ephemeral=True,
        )
        confirm_view.message = await interaction.original_response()

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logger.error("Error en el formulario de opinión", exc_info=error)
        await _send_generic_error(interaction)


# ------------- Step 1: Mandatory Tags Selector View -------------


class OpinionTagsView(_AuthorOnlyView):
    """Initial view forcing selection of Career and Year tags from TAGS_OPINIONS.txt."""

    def __init__(
        self,
        author_id: int,
        tags_file: str | Path = DEFAULT_OPINION_TAGS_PATH,
    ) -> None:
        super().__init__(author_id, timeout=180.0)
        self.selected_carrera: str | None = None
        self.selected_anio: str | None = None

        carreras, anios = load_opinion_tags(tags_file)
        if not carreras or not anios:
            raise ValueError(
                "El archivo `TAGS_OPINIONS.txt` debe tener al"
                " menos una opción en `[CARRERAS]` y `[ANIOS]`."
            )
        if len(carreras) > MAX_SELECT_OPTIONS or len(anios) > MAX_SELECT_OPTIONS:
            logger.warning(
                "TAGS_OPINIONS.txt tiene más de %d opciones; se ignoran las sobrantes.",
                MAX_SELECT_OPTIONS,
            )

        self.carrera_select.options = [
            discord.SelectOption(label=c[:100], value=c[:100])
            for c in carreras[:MAX_SELECT_OPTIONS]
        ]
        self.anio_select.options = [
            discord.SelectOption(label=a[:100], value=a[:100])
            for a in anios[:MAX_SELECT_OPTIONS]
        ]

    @discord.ui.select(
        placeholder="1. Seleccioná la carrera (obligatorio)",
        min_values=1,
        max_values=1,
        row=0,
    )
    async def carrera_select(
        self,
        interaction: discord.Interaction,
        select: discord.ui.Select,
    ) -> None:
        self.selected_carrera = select.values[0]
        for opt in select.options:
            opt.default = opt.value == self.selected_carrera
        await interaction.response.edit_message(view=self)

    @discord.ui.select(
        placeholder="2. Seleccioná el año de la materia (obligatorio)",
        min_values=1,
        max_values=1,
        row=1,
    )
    async def anio_select(
        self,
        interaction: discord.Interaction,
        select: discord.ui.Select,
    ) -> None:
        self.selected_anio = select.values[0]
        for opt in select.options:
            opt.default = opt.value == self.selected_anio
        await interaction.response.edit_message(view=self)

    @discord.ui.button(
        label="Escribir opinión",
        style=discord.ButtonStyle.primary,
        row=2,
    )
    async def open_modal_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not self.selected_carrera or not self.selected_anio:
            await interaction.response.send_message(
                "⚠️ Tenés que seleccionar **ambas etiquetas** (Carrera y Año) antes de continuar.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            OpinionModal(
                carrera_tag_name=self.selected_carrera,
                anio_tag_name=self.selected_anio,
            )
        )
