import os
from pathlib import Path
import discord

from .utils import (
    DEFAULT_OPINION_TAGS_PATH,
    load_opinion_tags,
    normalize_text,
)

MENSAJE_CONFIRMACION_ANONIMA: str = (
    "⚠️ **Antes de publicar, confirmá las normas de convivencia:**\n\n"
    "> *\"Entiendo que no quiero compartirlo públicamente, pero mantengo el respeto en mi post. "
    "De otra manera entiendo que será borrado y puedo recibir baneo por mal comportamiento en la comunidad.\"*"
)


# ------------ Helper Functions -------------


def _parse_channel_id(env_var: str) -> int | None:
    """Parse a positive integer channel ID from an environment variable."""
    raw = os.getenv(env_var, "").strip()
    return int(raw) if raw.isdigit() else None


def _capitalize_first(text: str) -> str:
    """Capitalize only the first character while preserving remaining casing."""
    cleaned = text.strip()
    return f"{cleaned[0].upper()}{cleaned[1:]}" if cleaned else ""


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


# ------------- Step 3: Confirmation View -------------


class OpinionConfirmView(discord.ui.View):
    """Final confirmation prompt before publishing the anonymous review."""

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
        super().__init__(timeout=180.0)
        self.author_id = author_id
        self.carrera_tag_name = carrera_tag_name
        self.anio_tag_name = anio_tag_name
        self.titulo_materia = titulo_materia
        self.comision_txt = comision_txt
        self.profesor_txt = profesor_txt
        self.opinion_txt = opinion_txt

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    def _disable_buttons(self) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

    @discord.ui.button(label="Acepto y publicar", style=discord.ButtonStyle.success)
    async def confirm_publish(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.guild is None:
            return

        public_id = _parse_channel_id("OPINIONES_CHANNEL_ID")
        logs_id = _parse_channel_id("LOGS_OPINIONES_CHANNEL_ID")

        public_channel = interaction.guild.get_channel(public_id) if public_id else None
        logs_channel = interaction.guild.get_channel(logs_id) if logs_id else None

        if not isinstance(public_channel, discord.ForumChannel):
            await interaction.response.edit_message(
                content="No está configurado el canal de Foro de opiniones. Avisá a moderación.",
                view=None,
            )
            self.stop()
            return

        self._disable_buttons()
        await interaction.response.edit_message(
            content="Publicando tu opinión de forma anónima...",
            view=self,
        )

        selected_keys = {
            normalize_text(self.carrera_tag_name),
            normalize_text(self.anio_tag_name),
        }
        applied_tags = [
            tag for tag in public_channel.available_tags
            if normalize_text(tag.name) in selected_keys
        ]

        mensaje_publico = (
            f"{self.comision_txt}\n\n"
            f"{self.profesor_txt}\n\n"
            f"{self.opinion_txt}"
        )

        existing_thread = await _find_existing_subject_thread(
            public_channel, self.titulo_materia
        )

        if existing_thread is not None:
            if existing_thread.archived:
                await existing_thread.edit(archived=False)

            current_tag_ids = {t.id for t in existing_thread.applied_tags}
            merged_tags = list(existing_thread.applied_tags)
            for tag in applied_tags:
                if tag.id not in current_tag_ids and len(merged_tags) < 5:
                    merged_tags.append(tag)
            if len(merged_tags) > len(existing_thread.applied_tags):
                await existing_thread.edit(applied_tags=merged_tags)

            sent_msg = await existing_thread.send(content=mensaje_publico)
            jump_url = sent_msg.jump_url
            accion_log = "Comentario agregado a post existente"
        else:
            created = await public_channel.create_thread(
                name=self.titulo_materia[:100],
                content=mensaje_publico,
                applied_tags=applied_tags,
            )
            jump_url = created.message.jump_url
            accion_log = "Nuevo post creado en el foro"

        if isinstance(logs_channel, discord.TextChannel):
            log_embed = discord.Embed(
                title=f"🕵️ Registro de opinión anónima ({accion_log})",
                description=self.opinion_txt,
                color=discord.Color.orange(),
            )
            log_embed.add_field(
                name="Autor real",
                value=f"{interaction.user.mention} (`{interaction.user}` | ID: `{interaction.user.id}`)",
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
            await logs_channel.send(embed=log_embed)

        await interaction.edit_original_response(
            content="✅ Tu opinión fue publicada de forma anónima.",
            view=None,
        )
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel_publish(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        self._disable_buttons()
        await interaction.response.edit_message(
            content="❌ Publicación cancelada. No se envió ningún mensaje.",
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

        confirm_view = OpinionConfirmView(
            author_id=interaction.user.id,
            carrera_tag_name=self.carrera_tag_name,
            anio_tag_name=self.anio_tag_name,
            titulo_materia=titulo_materia,
            comision_txt=comision_txt,
            profesor_txt=profesor_txt,
            opinion_txt=opinion_txt,
        )

        vista_previa = (
            f"{MENSAJE_CONFIRMACION_ANONIMA}\n\n"
            f"**Vista previa de tu publicación:**\n"
            f"📌 **{titulo_materia}** (`{self.carrera_tag_name}` • `{self.anio_tag_name}`)\n"
            f"• {comision_txt} — {profesor_txt}\n"
            f"• {opinion_txt}"
        )

        await interaction.response.send_message(
            content=vista_previa[:2000],
            view=confirm_view,
            ephemeral=True,
        )


# ------------- Step 1: Mandatory Tags Selector View -------------


class OpinionTagsView(discord.ui.View):
    """Initial view forcing selection of Career and Year tags from TAGS_OPINIONES.txt."""

    def __init__(
        self,
        author_id: int,
        tags_file: str | Path = DEFAULT_OPINION_TAGS_PATH,
    ) -> None:
        super().__init__(timeout=180.0)
        self.author_id = author_id
        self.selected_carrera: str | None = None
        self.selected_anio: str | None = None

        carreras, anios = load_opinion_tags(tags_file)
        if not carreras or not anios:
            raise ValueError(
                "El archivo `TAGS_OPINIONES.txt` debe tener al menos una opción en `[CARRERAS]` y `[ANIOS]`."
            )

        self.carrera_select.options = [
            discord.SelectOption(label=c[:100], value=c[:100]) for c in carreras[:25]
        ]
        self.anio_select.options = [
            discord.SelectOption(label=a[:100], value=a[:100]) for a in anios[:25]
        ]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

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