import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import asyncio
import os
from datetime import datetime, timezone


# =========================================================
# CONFIGURACIÓN
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

WELCOME_CHANNEL_ID = 1548521317295198258
TICKET_CATEGORY_ID = 1548528404649873438
VALORACIONES_CHANNEL_ID = 1550534072449900684
TRANSCRIPTS_CHANNEL_ID = 1548694373875585125

POSTULACIONES_EMOJI_ID = 1549076149399715840
POSTULACIONES_EMOJI_NAME = "573567deadhamster"

WELCOME_IMAGE_URL = (
    "https://assets.grok.com/users/8c348165-c392-4407-b2d9-45e29530f48d/"
    "generated/eb35ba2f-e63e-408c-9c2e-2cef76141c5b/image.jpg"
)

DATABASE = "infernmc.db"


# =========================================================
# CATEGORÍAS
# =========================================================

CATEGORIAS = {
    "general": {
        "nombre": "🎲 Ayuda General",
        "pregunta": "¿En qué necesitas ayuda?"
    },
    "bugs": {
        "nombre": "🎗️ Bugs",
        "pregunta": "¿Qué bug encontraste?"
    },
    "postulaciones": {
        "nombre": "Postulaciones",
        "pregunta": "¿Por qué quieres formar parte del Staff-Team?"
    },
    "tienda": {
        "nombre": "📯 Tienda",
        "pregunta": "¿Cuál es tu problema con la tienda?"
    },
    "sanciones": {
        "nombre": "🗂️ Sanciones",
        "pregunta": "¿Por qué motivo quieres apelar tu sanción?"
    }
}


# =========================================================
# INTENTS
# =========================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.presences = True


# =========================================================
# DATABASE
# =========================================================

def conectar_db():
    return sqlite3.connect(DATABASE)


def preparar_database():
    conn = conectar_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS staff (
            user_id INTEGER PRIMARY KEY,
            total_points INTEGER DEFAULT 0,
            weekly_points INTEGER DEFAULT 0,
            tickets_claimed INTEGER DEFAULT 0,
            ratings_received INTEGER DEFAULT 0,
            ai_reviews INTEGER DEFAULT 0,
            ai_points INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER,
            user_id INTEGER,
            stars INTEGER,
            ticket TEXT,
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER,
            ticket TEXT,
            score INTEGER,
            reason TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def obtener_config(key):
    conn = conectar_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT value FROM config WHERE key = ?",
        (key,)
    )

    resultado = cursor.fetchone()
    conn.close()

    return resultado[0] if resultado else None


def guardar_config(key, value):
    conn = conectar_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO config(key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, str(value)))

    conn.commit()
    conn.close()


def comprobar_semana():
    semana_actual = datetime.now(timezone.utc).strftime("%Y-W%W")
    semana_guardada = obtener_config("ultima_semana")

    if semana_guardada != semana_actual:

        conn = conectar_db()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE staff
            SET weekly_points = 0
        """)

        conn.commit()
        conn.close()

        guardar_config(
            "ultima_semana",
            semana_actual
        )

        print("[STAFF] Ranking semanal reiniciado.")


# =========================================================
# BOT
# =========================================================

class InfernMCBot(commands.Bot):

    async def setup_hook(self):

        preparar_database()
        comprobar_semana()

        print("[BOT] Registrando vistas permanentes...")

        self.add_view(TicketPanelView())
        self.add_view(TicketControlView())

        print("[BOT] Vistas registradas.")

        try:

            synced = await self.tree.sync()

            print(
                f"[BOT] {len(synced)} comandos slash sincronizados."
            )

        except Exception as e:

            print(
                f"[BOT] Error sincronizando comandos: {e}"
            )


bot = InfernMCBot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# UTILIDADES
# =========================================================

def es_admin(member):

    return member.guild_permissions.administrator


def obtener_ticket_usuario(guild, user_id):

    categoria = guild.get_channel(
        TICKET_CATEGORY_ID
    )

    if categoria is None:
        return None

    for canal in categoria.text_channels:

        if canal.name == f"ticket-{user_id}":
            return canal

    return None


# =========================================================
# SISTEMA DE PUNTOS
# =========================================================

async def sumar_puntos(
    staff_id,
    puntos,
    tickets=0,
    ratings=0,
    ai_reviews=0,
    ai_points=0
):

    comprobar_semana()

    conn = conectar_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO staff (
            user_id,
            total_points,
            weekly_points,
            tickets_claimed,
            ratings_received,
            ai_reviews,
            ai_points
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(user_id) DO UPDATE SET
            total_points = total_points + excluded.total_points,
            weekly_points = weekly_points + excluded.weekly_points,
            tickets_claimed =
                tickets_claimed + excluded.tickets_claimed,
            ratings_received =
                ratings_received + excluded.ratings_received,
            ai_reviews =
                ai_reviews + excluded.ai_reviews,
            ai_points =
                ai_points + excluded.ai_points
    """, (
        staff_id,
        puntos,
        puntos,
        tickets,
        ratings,
        ai_reviews,
        ai_points
    ))

    conn.commit()
    conn.close()

    print(
        f"[STAFF] {staff_id} recibió +{puntos} puntos."
    )

    await actualizar_topstaff_panel()


# =========================================================
# TOP STAFF AUTOMÁTICO
# =========================================================

async def actualizar_topstaff_panel():

    comprobar_semana()

    channel_id = obtener_config(
        "topstaff_channel_id"
    )

    message_id = obtener_config(
        "topstaff_message_id"
    )

    if not channel_id or not message_id:
        return

    channel = bot.get_channel(
        int(channel_id)
    )

    if channel is None:
        return

    try:

        message = await channel.fetch_message(
            int(message_id)
        )

    except discord.NotFound:

        return

    except discord.HTTPException:

        return

    conn = conectar_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            user_id,
            total_points,
            weekly_points,
            tickets_claimed,
            ratings_received,
            ai_reviews
        FROM staff
        ORDER BY total_points DESC
        LIMIT 10
    """)

    resultados = cursor.fetchall()

    conn.close()

    embed = discord.Embed(
        title="🏆 Top 10 Staff",
        description="Ranking actualizado automáticamente.",
        color=discord.Color.red(),
        timestamp=datetime.now(timezone.utc)
    )

    if not resultados:

        embed.description = (
            "Todavía no hay miembros con puntos."
        )

    else:

        texto = ""

        medallas = {
            1: "🥇",
            2: "🥈",
            3: "🥉"
        }

        for posicion, datos in enumerate(
            resultados,
            1
        ):

            (
                user_id,
                total,
                weekly,
                tickets,
                ratings,
                ai_reviews
            ) = datos

            miembro = bot.get_user(
                user_id
            )

            nombre = (
                miembro.mention
                if miembro
                else f"<@{user_id}>"
            )

            icono = medallas.get(
                posicion,
                f"**#{posicion}**"
            )

            texto += (
                f"{icono} {nombre}\n"
                f"**{total} puntos** "
                f"• Semana: **{weekly}**\n"
                f"Tickets: `{tickets}` "
                f"• Valoraciones: `{ratings}` "
                f"• IA: `{ai_reviews}`\n\n"
            )

        embed.description = texto

    embed.set_footer(
        text="InfernMC • Ranking automático"
    )

    try:

        await message.edit(
            embed=embed
        )

    except discord.HTTPException as e:

        print(
            f"[STAFF] Error actualizando Top: {e}"
        )


# =========================================================
# TRANSCRIPT
# =========================================================

async def crear_transcript(channel):

    archivo = f"transcript-{channel.name}.txt"

    mensajes = []

    try:

        async for mensaje in channel.history(
            limit=None,
            oldest_first=True
        ):

            mensajes.append(
                mensaje
            )

    except Exception as e:

        print(
            f"[TRANSCRIPT] Error: {e}"
        )

    with open(
        archivo,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "=" * 60 + "\n"
        )

        f.write(
            "INFERNMC - TRANSCRIPT\n"
        )

        f.write(
            "=" * 60 + "\n\n"
        )

        f.write(
            f"Canal: {channel.name}\n"
        )

        f.write(
            f"ID: {channel.id}\n"
        )

        f.write(
            "Fecha: "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        )

        f.write(
            "\n" + "=" * 60 + "\n\n"
        )

        for mensaje in mensajes:

            fecha = mensaje.created_at.strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            f.write(
                f"[{fecha}] "
                f"{mensaje.author} "
                f"({mensaje.author.id})\n"
            )

            if mensaje.content:

                f.write(
                    f"{mensaje.content}\n"
                )

            for adjunto in mensaje.attachments:

                f.write(
                    f"Archivo: {adjunto.url}\n"
                )

            f.write("\n")

    return archivo


# =========================================================
# IA LOCAL
# =========================================================

async def evaluar_ticket_local(channel):

    mensajes = []

    try:

        async for mensaje in channel.history(
            limit=200,
            oldest_first=True
        ):

            if (
                not mensaje.author.bot
                and mensaje.content
            ):

                mensajes.append(
                    mensaje.content.lower()
                )

    except Exception as e:

        print(
            f"[IA] Error leyendo ticket: {e}"
        )

        return (
            0,
            "No se pudo analizar el ticket."
        )

    if not mensajes:

        return (
            0,
            "No hubo suficientes mensajes para analizar."
        )

    texto = " ".join(
        mensajes
    )

    score = 5

    razones = []

    if len(mensajes) >= 8:

        score += 1

        razones.append(
            "hubo buena participación"
        )

    if len(mensajes) >= 20:

        score += 1

        razones.append(
            "hubo bastante interacción"
        )

    respuestas_cortas = sum(
        1
        for x in mensajes
        if len(x.strip()) <= 8
    )

    if respuestas_cortas >= 5:

        score -= 1

        razones.append(
            "hubo varias respuestas demasiado cortas"
        )

    palabras_buen_trato = [
        "gracias",
        "por favor",
        "perfecto",
        "ayuda",
        "solucionado",
        "muchas gracias",
        "entiendo"
    ]

    if any(
        p in texto
        for p in palabras_buen_trato
    ):

        score += 1

        razones.append(
            "se detectó buen trato"
        )

    malas_palabras = [
        "idiota",
        "imbecil",
        "estupido",
        "puta",
        "mierda",
        "cabron"
    ]

    if any(
        p in texto
        for p in malas_palabras
    ):

        score -= 2

        razones.append(
            "se detectó lenguaje inapropiado"
        )

    resolucion = [
        "solucionado",
        "resuelto",
        "ya funciona",
        "gracias por ayudar",
        "problema resuelto"
    ]

    if any(
        p in texto
        for p in resolucion
    ):

        score += 2

        razones.append(
            "el ticket parece haber sido solucionado"
        )

    if len(texto) > 1000:

        score += 1

        razones.append(
            "hubo explicaciones detalladas"
        )

    score = max(
        0,
        min(10, score)
    )

    if not razones:

        razones.append(
            "actividad normal en el ticket"
        )

    return (
        score,
        ", ".join(razones) + "."
    )


# =========================================================
# MODAL
# =========================================================

class TicketModal(discord.ui.Modal):

    def __init__(self, categoria):

        self.categoria = categoria

        datos = CATEGORIAS[
            categoria
        ]

        super().__init__(
            title=datos["nombre"][:45]
        )

        self.nick = discord.ui.TextInput(
            label="¿Nick?",
            placeholder="Escribe tu nick de Minecraft",
            required=True,
            max_length=32
        )

        self.motivo = discord.ui.TextInput(
            label="Motivo",
            placeholder=datos["pregunta"],
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=1000
        )

        self.add_item(
            self.nick
        )

        self.add_item(
            self.motivo
        )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        await interaction.response.defer(
            ephemeral=True
        )

        guild = interaction.guild

        if guild is None:

            await interaction.followup.send(
                "No se pudo encontrar el servidor.",
                ephemeral=True
            )

            return

        existente = obtener_ticket_usuario(
            guild,
            interaction.user.id
        )

        if existente:

            await interaction.followup.send(
                f"Ya tienes un ticket abierto: "
                f"{existente.mention}",
                ephemeral=True
            )

            return

        categoria = guild.get_channel(
            TICKET_CATEGORY_ID
        )

        if categoria is None:

            await interaction.followup.send(
                "La categoría de tickets no existe.",
                ephemeral=True
            )

            return

        nombre = (
            f"ticket-{interaction.user.id}"
        )

        overwrites = {

            guild.default_role:
                discord.PermissionOverwrite(
                    view_channel=False
                ),

            interaction.user:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )
        }

        for miembro in guild.members:

            if miembro.guild_permissions.administrator:

                overwrites[miembro] = (
                    discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True
                    )
                )

        try:

            canal = await guild.create_text_channel(
                name=nombre,
                category=categoria,
                overwrites=overwrites,
                topic=(
                    f"Owner:{interaction.user.id}"
                    f"|Staff:Sin reclamar"
                    f"|Categoria:{self.categoria}"
                )
            )

            datos = CATEGORIAS[
                self.categoria
            ]

            embed = discord.Embed(
                title="🎫 Ticket creado",
                color=discord.Color.red()
            )

            embed.add_field(
                name="Usuario",
                value=interaction.user.mention,
                inline=False
            )

            embed.add_field(
                name="Nick",
                value=self.nick.value,
                inline=False
            )

            embed.add_field(
                name="Categoría",
                value=datos["nombre"],
                inline=False
            )

            embed.add_field(
                name="Motivo",
                value=self.motivo.value,
                inline=False
            )

            embed.add_field(
                name="Estado",
                value="Sin reclamar",
                inline=False
            )

            embed.set_footer(
                text="InfernMC • Sistema de tickets"
            )

            await canal.send(
                content=interaction.user.mention,
                embed=embed,
                view=TicketControlView()
            )

            await interaction.followup.send(
                f"Ticket creado correctamente: "
                f"{canal.mention}",
                ephemeral=True
            )

            print(
                f"[TICKETS] Ticket creado: {canal.name}"
            )

        except Exception as e:

            print(
                f"[TICKETS] ERROR CREANDO TICKET: {e}"
            )

            await interaction.followup.send(
                "Ocurrió un error creando el ticket.",
                ephemeral=True
            )


# =========================================================
# SELECTOR
# =========================================================

class TicketSelect(discord.ui.Select):

    def __init__(self):

        opciones = [

            discord.SelectOption(
                label="Ayuda General",
                value="general",
                emoji="🎲",
                description="Necesitas ayuda con el servidor."
            ),

            discord.SelectOption(
                label="Bugs",
                value="bugs",
                emoji="🎗️",
                description="Reporta un error o bug."
            ),

            discord.SelectOption(
                label="Postulaciones",
                value="postulaciones",
                emoji=discord.PartialEmoji(
                    name=POSTULACIONES_EMOJI_NAME,
                    id=POSTULACIONES_EMOJI_ID
                ),
                description="Postúlate para Staff-Team."
            ),

            discord.SelectOption(
                label="Tienda",
                value="tienda",
                emoji="📯",
                description="Problemas con la tienda."
            ),

            discord.SelectOption(
                label="Sanciones",
                value="sanciones",
                emoji="🗂️",
                description="Apela una sanción."
            )
        ]

        super().__init__(
            placeholder="Selecciona una categoría...",
            min_values=1,
            max_values=1,
            options=opciones,
            custom_id="infernmc_ticket_category_select"
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        categoria = self.values[0]

        try:

            await interaction.response.send_modal(
                TicketModal(categoria)
            )

            print(
                f"[TICKETS] Modal enviado: "
                f"{interaction.user} -> {categoria}"
            )

        except Exception as e:

            print(
                f"[TICKETS] ERROR EN SELECT: {e}"
            )

            if not interaction.response.is_done():

                await interaction.response.send_message(
                    "No se pudo abrir el formulario.",
                    ephemeral=True
                )


class TicketPanelView(discord.ui.View):

    def __init__(self):

        super().__init__(
            timeout=None
        )

        self.add_item(
            TicketSelect()
        )


# =========================================================
# CONTROL DE TICKETS
# =========================================================

class TicketControlView(discord.ui.View):

    def __init__(self):

        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="Reclamar",
        style=discord.ButtonStyle.primary,
        custom_id="infernmc_ticket_claim"
    )
    async def reclamar(
        self,
        interaction,
        button
    ):

        if not es_admin(
            interaction.user
        ):

            await interaction.response.send_message(
                "Solo el Staff puede reclamar tickets.",
                ephemeral=True
            )

            return

        canal = interaction.channel

        if not isinstance(
            canal,
            discord.TextChannel
        ):

            return

        topic = canal.topic or ""

        if "Staff:Sin reclamar" not in topic:

            await interaction.response.send_message(
                "Este ticket ya fue reclamado.",
                ephemeral=True
            )

            return

        nuevo_topic = topic.replace(
            "Staff:Sin reclamar",
            f"Staff:{interaction.user.id}"
        )

        try:

            await canal.edit(
                topic=nuevo_topic
            )

            await sumar_puntos(
                interaction.user.id,
                3,
                tickets=1
            )

            await interaction.response.send_message(
                f"{interaction.user.mention} "
                "ha reclamado este ticket."
            )

        except Exception as e:

            print(
                f"[TICKETS] ERROR RECLAMANDO: {e}"
            )

            if not interaction.response.is_done():

                await interaction.response.send_message(
                    "No se pudo reclamar el ticket.",
                    ephemeral=True
                )

    @discord.ui.button(
        label="Cerrar",
        style=discord.ButtonStyle.danger,
        custom_id="infernmc_ticket_close"
    )
    async def cerrar(
        self,
        interaction,
        button
    ):

        if not es_admin(
            interaction.user
        ):

            await interaction.response.send_message(
                "Solo el Staff puede cerrar tickets.",
                ephemeral=True
            )

            return

        canal = interaction.channel

        if not isinstance(
            canal,
            discord.TextChannel
        ):

            return

        await interaction.response.defer(
            ephemeral=True
        )

        topic = canal.topic or ""

        owner_id = None
        staff_id = None

        for parte in topic.split("|"):

            if parte.startswith("Owner:"):

                try:

                    owner_id = int(
                        parte.replace(
                            "Owner:",
                            ""
                        )
                    )

                except:
                    pass

            if parte.startswith("Staff:"):

                valor = parte.replace(
                    "Staff:",
                    ""
                )

                if valor != "Sin reclamar":

                    try:

                        staff_id = int(
                            valor
                        )

                    except:
                        pass

        archivo = None

        try:

            archivo = await crear_transcript(
                canal
            )

            transcript_channel = bot.get_channel(
                TRANSCRIPTS_CHANNEL_ID
            )

            if (
                transcript_channel
                and archivo
            ):

                await transcript_channel.send(
                    content=(
                        f"Transcript de `{canal.name}`\n"
                        f"Staff: "
                        f"{f'<@{staff_id}>' if staff_id else 'Sin reclamar'}"
                    ),
                    file=discord.File(
                        archivo
                    )
                )

        except Exception as e:

            print(
                f"[TRANSCRIPT] ERROR: {e}"
            )

        if staff_id:

            try:

                score, reason = (
                    await evaluar_ticket_local(
                        canal
                    )
                )

                conn = conectar_db()
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO ai_reviews (
                        staff_id,
                        ticket,
                        score,
                        reason,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    staff_id,
                    canal.name,
                    score,
                    reason,
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ))

                conn.commit()
                conn.close()

                await sumar_puntos(
                    staff_id,
                    score,
                    ai_reviews=1,
                    ai_points=score
                )

                print(
                    f"[IA] {staff_id} recibió "
                    f"{score} puntos."
                )

            except Exception as e:

                print(
                    f"[IA] ERROR: {e}"
                )

        if (
            owner_id
            and staff_id
        ):

            try:

                usuario = bot.get_user(
                    owner_id
                )

                if usuario:

                    await usuario.send(
                        embed=discord.Embed(
                            title="⭐ Valora tu ticket",
                            description=(
                                "Tu ticket de InfernMC "
                                "ha sido cerrado.\n\n"
                                "Selecciona una valoración "
                                "del 1 al 5."
                            ),
                            color=discord.Color.gold()
                        ),
                        view=RatingView(
                            owner_id,
                            staff_id,
                            canal.name
                        )
                    )

            except discord.Forbidden:

                print(
                    "[RATING] No se pudo enviar DM."
                )

        if archivo:

            try:
                os.remove(
                    archivo
                )
            except:
                pass

        await interaction.followup.send(
            "Ticket cerrado correctamente.",
            ephemeral=True
        )

        await asyncio.sleep(3)

        try:

            await canal.delete(
                reason="Ticket cerrado"
            )

        except Exception as e:

            print(
                f"[TICKETS] ERROR ELIMINANDO: {e}"
            )


# =========================================================
# RATING
# =========================================================

class RatingView(discord.ui.View):

    def __init__(
        self,
        owner_id,
        staff_id,
        ticket_name
    ):

        super().__init__(
            timeout=86400
        )

        self.owner_id = owner_id
        self.staff_id = staff_id
        self.ticket_name = ticket_name
        self.respondido = False

    async def registrar_rating(
        self,
        interaction,
        estrellas
    ):

        if interaction.user.id != self.owner_id:

            await interaction.response.send_message(
                "Esta valoración no te pertenece.",
                ephemeral=True
            )

            return

        if self.respondido:

            await interaction.response.send_message(
                "Ya has enviado una valoración.",
                ephemeral=True
            )

            return

        self.respondido = True

        conn = conectar_db()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO ratings (
                staff_id,
                user_id,
                stars,
                ticket,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            self.staff_id,
            self.owner_id,
            estrellas,
            self.ticket_name,
            datetime.now(
                timezone.utc
            ).isoformat()
        ))

        conn.commit()
        conn.close()

        await sumar_puntos(
            self.staff_id,
            estrellas,
            ratings=1
        )

        canal = bot.get_channel(
            VALORACIONES_CHANNEL_ID
        )

        if canal:

            embed = discord.Embed(
                title="⭐ Nueva valoración",
                color=discord.Color.gold()
            )

            embed.add_field(
                name="Staff",
                value=f"<@{self.staff_id}>",
                inline=False
            )

            embed.add_field(
                name="Usuario",
                value=f"<@{self.owner_id}>",
                inline=False
            )

            embed.add_field(
                name="Valoración",
                value="⭐" * estrellas,
                inline=False
            )

            embed.add_field(
                name="Puntos",
                value=f"+{estrellas}",
                inline=False
            )

            await canal.send(
                embed=embed
            )

        await interaction.response.edit_message(
            content="Gracias por tu valoración.",
            embed=None,
            view=None
        )

    @discord.ui.button(
        label="1 ⭐",
        style=discord.ButtonStyle.danger
    )
    async def uno(
        self,
        interaction,
        button
    ):

        await self.registrar_rating(
            interaction,
            1
        )

    @discord.ui.button(
        label="2 ⭐",
        style=discord.ButtonStyle.danger
    )
    async def dos(
        self,
        interaction,
        button
    ):

        await self.registrar_rating(
            interaction,
            2
        )

    @discord.ui.button(
        label="3 ⭐",
        style=discord.ButtonStyle.primary
    )
    async def tres(
        self,
        interaction,
        button
    ):

        await self.registrar_rating(
            interaction,
            3
        )

    @discord.ui.button(
        label="4 ⭐",
        style=discord.ButtonStyle.success
    )
    async def cuatro(
        self,
        interaction,
        button
    ):

        await self.registrar_rating(
            interaction,
            4
        )

    @discord.ui.button(
        label="5 ⭐",
        style=discord.ButtonStyle.success
    )
    async def cinco(
        self,
        interaction,
        button
    ):

        await self.registrar_rating(
            interaction,
            5
        )


# =========================================================
# BIENVENIDA
# =========================================================

async def enviar_bienvenida(member):

    canal = bot.get_channel(
        WELCOME_CHANNEL_ID
    )

    if canal is None:
        return

    embed = discord.Embed(
        title="🔥 ¡Bienvenido/a a InfernMC!",
        description=(
            f"¡Bienvenido/a {member.mention}!\n\n"
            "Esperamos que disfrutes de InfernMC.\n"
            "Recuerda leer las reglas, respetar a la comunidad "
            "y abrir un ticket si necesitas ayuda."
        ),
        color=discord.Color.red()
    )

    embed.set_thumbnail(
        url=member.display_avatar.url
    )

    embed.set_image(
        url=WELCOME_IMAGE_URL
    )

    embed.add_field(
        name="👤 Usuario",
        value=member.mention,
        inline=True
    )

    embed.add_field(
        name="📊 Miembros",
        value=str(
            member.guild.member_count
        ),
        inline=True
    )

    embed.add_field(
        name="🆔 Cuenta",
        value=f"`{member.id}`",
        inline=True
    )

    embed.set_footer(
        text="InfernMC • Sistema de bienvenidas"
    )

    await canal.send(
        embed=embed
    )


@bot.event
async def on_member_join(member):

    try:

        await enviar_bienvenida(
            member
        )

    except Exception as e:

        print(
            f"[WELCOME] ERROR: {e}"
        )


# =========================================================
# /TICKETPANEL
# =========================================================

@bot.tree.command(
    name="ticketpanel",
    description="Crea o actualiza el panel de tickets."
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def ticketpanel(
    interaction: discord.Interaction
):

    await interaction.response.defer(
        ephemeral=True
    )

    canal = interaction.channel

    if canal is None:
        return

    try:

        async for mensaje in canal.history(
            limit=100
        ):

            if mensaje.author.id == bot.user.id:

                try:
                    await mensaje.delete()
                except:
                    pass

    except Exception as e:

        print(
            f"[PANEL] Error limpiando: {e}"
        )

    embed = discord.Embed(
        title="🎫 Soporte InfernMC",
        description=(
            "¿Necesitas ayuda?\n\n"
            "No dudes en abrir un ticket para recibir "
            "asistencia por parte del Staff.\n\n"

            "**Ten en cuenta que:**\n"
            "• No abras demasiados tickets.\n"
            "• No insultes al Staff.\n"
            "• Sé claro y directo con tu problema.\n\n"

            "**Categorías disponibles:**\n\n"

            "🎲 **Ayuda General**\n"
            "Necesitas ayuda con el servidor.\n\n"

            "🎗️ **Bugs**\n"
            "Reporta un error o bug.\n\n"

            f"<:{POSTULACIONES_EMOJI_NAME}:{POSTULACIONES_EMOJI_ID}> "
            "**Postulaciones**\n"
            "Postúlate para formar parte del Staff-Team.\n\n"

            "📯 **Tienda**\n"
            "Problemas relacionados con la tienda.\n\n"

            "🗂️ **Sanciones**\n"
            "Apela una sanción."
        ),
        color=discord.Color.red()
    )

    embed.set_footer(
        text="InfernMC • Selecciona una categoría en el menú"
    )

    await canal.send(
        embed=embed,
        view=TicketPanelView()
    )

    await interaction.followup.send(
        "Panel de tickets creado correctamente.",
        ephemeral=True
    )


# =========================================================
# /TOPSTAFFPANEL
# =========================================================

@bot.tree.command(
    name="topstaffpanel",
    description="Crea el panel automático del Top Staff."
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def topstaffpanel(
    interaction: discord.Interaction
):

    await interaction.response.defer(
        ephemeral=True
    )

    canal = interaction.channel

    if canal is None:
        return

    embed = discord.Embed(
        title="🏆 Top 10 Staff",
        description="Cargando ranking...",
        color=discord.Color.red()
    )

    mensaje = await canal.send(
        embed=embed
    )

    guardar_config(
        "topstaff_channel_id",
        canal.id
    )

    guardar_config(
        "topstaff_message_id",
        mensaje.id
    )

    await actualizar_topstaff_panel()

    await interaction.followup.send(
        "Panel de Top Staff creado. "
        "Se actualizará automáticamente.",
        ephemeral=True
    )


# =========================================================
# /TOPSTAFF
# =========================================================

@bot.tree.command(
    name="topstaff",
    description="Muestra el Top 10 del Staff."
)
async def topstaff(
    interaction: discord.Interaction
):

    comprobar_semana()

    conn = conectar_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            user_id,
            total_points,
            weekly_points
        FROM staff
        ORDER BY total_points DESC
        LIMIT 10
    """)

    resultados = cursor.fetchall()

    conn.close()

    embed = discord.Embed(
        title="🏆 Top 10 Staff",
        color=discord.Color.red()
    )

    if not resultados:

        embed.description = (
            "Todavía no hay miembros con puntos."
        )

    else:

        texto = ""

        for posicion, (
            user_id,
            total,
            weekly
        ) in enumerate(
            resultados,
            1
        ):

            texto += (
                f"**#{posicion}** <@{user_id}>\n"
                f"Total: **{total}** "
                f"• Semana: **{weekly}**\n\n"
            )

        embed.description = texto

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# /STAFF
# =========================================================

@bot.tree.command(
    name="staff",
    description="Muestra las estadísticas de un miembro del Staff."
)
@app_commands.describe(
    miembro="Miembro del Staff"
)
async def staff(
    interaction: discord.Interaction,
    miembro: discord.Member = None
):

    objetivo = (
        miembro
        or interaction.user
    )

    conn = conectar_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            total_points,
            weekly_points,
            tickets_claimed,
            ratings_received,
            ai_reviews,
            ai_points
        FROM staff
        WHERE user_id = ?
    """, (
        objetivo.id,
    ))

    datos = cursor.fetchone()

    conn.close()

    if not datos:

        await interaction.response.send_message(
            f"{objetivo.mention} "
            "todavía no tiene estadísticas.",
            ephemeral=True
        )

        return

    (
        total,
        weekly,
        tickets,
        ratings,
        ai_reviews,
        ai_points
    ) = datos

    embed = discord.Embed(
        title=(
            f"Estadísticas de "
            f"{objetivo.display_name}"
        ),
        color=discord.Color.red()
    )

    embed.set_thumbnail(
        url=objetivo.display_avatar.url
    )

    embed.add_field(
        name="Puntos totales",
        value=f"**{total}**",
        inline=True
    )

    embed.add_field(
        name="Puntos semanales",
        value=f"**{weekly}**",
        inline=True
    )

    embed.add_field(
        name="Tickets reclamados",
        value=f"**{tickets}**",
        inline=True
    )

    embed.add_field(
        name="Valoraciones",
        value=f"**{ratings}**",
        inline=True
    )

    embed.add_field(
        name="Revisiones IA",
        value=f"**{ai_reviews}**",
        inline=True
    )

    embed.add_field(
        name="Puntos IA",
        value=f"**{ai_points}**",
        inline=True
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# /TESTBIENVENIDA
# =========================================================

@bot.tree.command(
    name="testbienvenida",
    description="Prueba el sistema de bienvenida."
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def testbienvenida(
    interaction: discord.Interaction
):

    await interaction.response.defer(
        ephemeral=True
    )

    try:

        await enviar_bienvenida(
            interaction.user
        )

        await interaction.followup.send(
            "Bienvenida de prueba enviada.",
            ephemeral=True
        )

    except Exception as e:

        print(
            f"[WELCOME] ERROR TEST: {e}"
        )

        await interaction.followup.send(
            "No se pudo enviar la bienvenida.",
            ephemeral=True
        )


# =========================================================
# /MENSAJE
# =========================================================

@bot.tree.command(
    name="mensaje",
    description="Envía un mensaje a un canal."
)
@app_commands.checks.has_permissions(
    administrator=True
)
@app_commands.describe(
    canal="Canal donde enviar el mensaje",
    mensaje="Mensaje que quieres enviar"
)
async def mensaje(
    interaction: discord.Interaction,
    canal: discord.TextChannel,
    mensaje: str
):

    try:

        await canal.send(
            mensaje
        )

        await interaction.response.send_message(
            f"Mensaje enviado en {canal.mention}.",
            ephemeral=True
        )

    except Exception as e:

        print(
            f"[MENSAJE] ERROR: {e}"
        )

        await interaction.response.send_message(
            "No se pudo enviar el mensaje.",
            ephemeral=True
        )


# =========================================================
# ERRORES
# =========================================================

@ticketpanel.error
async def ticketpanel_error(
    interaction,
    error
):

    if isinstance(
        error,
        app_commands.errors.MissingPermissions
    ):

        if not interaction.response.is_done():

            await interaction.response.send_message(
                "No tienes permisos para usar este comando.",
                ephemeral=True
            )


@topstaffpanel.error
async def topstaffpanel_error(
    interaction,
    error
):

    if isinstance(
        error,
        app_commands.errors.MissingPermissions
    ):

        if not interaction.response.is_done():

            await interaction.response.send_message(
                "No tienes permisos para usar este comando.",
                ephemeral=True
            )


@testbienvenida.error
async def testbienvenida_error(
    interaction,
    error
):

    if isinstance(
        error,
        app_commands.errors.MissingPermissions
    ):

        if not interaction.response.is_done():

            await interaction.response.send_message(
                "No tienes permisos para usar este comando.",
                ephemeral=True
            )


@mensaje.error
async def mensaje_error(
    interaction,
    error
):

    if isinstance(
        error,
        app_commands.errors.MissingPermissions
    ):

        if not interaction.response.is_done():

            await interaction.response.send_message(
                "No tienes permisos para usar este comando.",
                ephemeral=True
            )


# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    comprobar_semana()

    print("=" * 50)
    print(
        f"[BOT] Conectado como {bot.user}"
    )
    print(
        f"[BOT] ID: {bot.user.id}"
    )
    print(
        "[BOT] InfernMC listo."
    )
    print("=" * 50)

    await actualizar_topstaff_panel()


# =========================================================
# INICIO
# =========================================================

if not TOKEN:

    raise RuntimeError(
        "Falta DISCORD_TOKEN en las variables de Railway."
    )

bot.run(TOKEN)
