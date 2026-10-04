import discord
from discord.ext import commands
from discord.ui import View, Button, Select, Modal, TextInput
import sqlite3
import os
import asyncio
import re
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

DATABASE = "infernmc.db"


# =========================================================
# INTENTS
# =========================================================

intents = discord.Intents.default()

intents.members = True
intents.message_content = True
intents.presences = True


# =========================================================
# BOT
# =========================================================

class InfernMCBot(commands.Bot):

    async def setup_hook(self):

        print("[BOT] Registrando vistas permanentes...")

        self.add_view(TicketPanelView())
        self.add_view(TicketControlView())

        print("[BOT] Vistas registradas.")


bot = InfernMCBot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# BASE DE DATOS
# =========================================================

db = sqlite3.connect(
    DATABASE,
    check_same_thread=False
)

cursor = db.cursor()


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


db.commit()


# =========================================================
# CATEGORÍAS
# =========================================================

CATEGORIAS = {

    "general": {
        "label": "🎲 Ayuda General",
        "pregunta": "¿En qué necesitas ayuda?"
    },

    "bugs": {
        "label": "🎗️ Bugs",
        "pregunta": "¿Qué bug encontraste?"
    },

    "postulaciones": {
        "label": "Postulaciones",
        "pregunta": "¿Por qué quieres formar parte del Staff-Team?"
    },

    "tienda": {
        "label": "📯 Tienda",
        "pregunta": "¿Cuál es tu problema con la tienda?"
    },

    "sanciones": {
        "label": "🗂️ Sanciones",
        "pregunta": "¿Por qué motivo quieres apelar tu sanción?"
    }

}


# =========================================================
# FUNCIONES GENERALES
# =========================================================

def es_admin(member):

    if not isinstance(member, discord.Member):
        return False

    return member.guild_permissions.administrator


def asegurar_staff(user_id):

    cursor.execute(
        "SELECT user_id FROM staff WHERE user_id = ?",
        (user_id,)
    )

    resultado = cursor.fetchone()

    if resultado is None:

        cursor.execute(
            """
            INSERT INTO staff (
                user_id,
                total_points,
                weekly_points,
                tickets_claimed,
                ratings_received,
                ai_reviews,
                ai_points
            )
            VALUES (?, 0, 0, 0, 0, 0, 0)
            """,
            (user_id,)
        )

        db.commit()


def semana_actual():

    return datetime.now(
        timezone.utc
    ).isocalendar().week


def revisar_reset_semanal():

    semana = str(semana_actual())

    cursor.execute(
        "SELECT value FROM config WHERE key = 'week'",
    )

    resultado = cursor.fetchone()

    if resultado is None:

        cursor.execute(
            """
            INSERT INTO config (key, value)
            VALUES ('week', ?)
            """,
            (semana,)
        )

        db.commit()

        return

    semana_guardada = resultado[0]

    if semana_guardada != semana:

        cursor.execute(
            """
            UPDATE staff
            SET weekly_points = 0
            """
        )

        cursor.execute(
            """
            UPDATE config
            SET value = ?
            WHERE key = 'week'
            """,
            (semana,)
        )

        db.commit()

        print("[STAFF] Ranking semanal reiniciado.")


def sumar_puntos(
    user_id,
    puntos,
    tipo=None
):

    asegurar_staff(user_id)

    cursor.execute(
        """
        UPDATE staff
        SET total_points = total_points + ?,
            weekly_points = weekly_points + ?
        WHERE user_id = ?
        """,
        (
            puntos,
            puntos,
            user_id
        )
    )

    if tipo == "ticket":

        cursor.execute(
            """
            UPDATE staff
            SET tickets_claimed = tickets_claimed + 1
            WHERE user_id = ?
            """,
            (user_id,)
        )

    elif tipo == "rating":

        cursor.execute(
            """
            UPDATE staff
            SET ratings_received = ratings_received + 1
            WHERE user_id = ?
            """,
            (user_id,)
        )

    elif tipo == "ai":

        cursor.execute(
            """
            UPDATE staff
            SET ai_reviews = ai_reviews + 1,
                ai_points = ai_points + ?
            WHERE user_id = ?
            """,
            (
                puntos,
                user_id
            )
        )

    db.commit()


def obtener_datos_ticket(channel):

    topic = channel.topic or ""

    owner = None
    staff = None
    categoria = None

    for parte in topic.split("|"):

        if parte.startswith("Owner:"):
            owner = parte.replace(
                "Owner:",
                ""
            )

        elif parte.startswith("Staff:"):
            staff = parte.replace(
                "Staff:",
                ""
            )

        elif parte.startswith("Categoria:"):
            categoria = parte.replace(
                "Categoria:",
                ""
            )

    return owner, staff, categoria


def buscar_ticket_usuario(
    guild,
    user_id
):

    for channel in guild.text_channels:

        if not channel.name.startswith("ticket-"):
            continue

        owner, staff, categoria = obtener_datos_ticket(
            channel
        )

        if owner == str(user_id):

            return channel

    return None


# =========================================================
# TICKET MODAL
# =========================================================

class TicketModal(discord.ui.Modal):

    def __init__(self, categoria):

        self.categoria = categoria

        info = CATEGORIAS[categoria]

        super().__init__(
            title=f"Ticket - {info['label']}"
        )

        self.nick = TextInput(
            label="¿Nick?",
            placeholder="Escribe tu nick de Minecraft",
            style=discord.TextStyle.short,
            required=True,
            min_length=1,
            max_length=32
        )

        self.motivo = TextInput(
            label=info["pregunta"],
            placeholder="Explica tu situación con claridad.",
            style=discord.TextStyle.paragraph,
            required=True,
            min_length=3,
            max_length=1000
        )

        self.add_item(self.nick)
        self.add_item(self.motivo)


    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        try:

            print(
                f"[TICKETS] Creando ticket para "
                f"{interaction.user}"
            )

            guild = interaction.guild

            if guild is None:

                await interaction.response.send_message(
                    "No se pudo detectar el servidor.",
                    ephemeral=True
                )

                return


            # Respondemos inmediatamente
            await interaction.response.defer(
                ephemeral=True
            )


            categoria_discord = guild.get_channel(
                TICKET_CATEGORY_ID
            )


            if categoria_discord is None:

                await interaction.followup.send(
                    "No encuentro la categoría de tickets.",
                    ephemeral=True
                )

                return


            if not isinstance(
                categoria_discord,
                discord.CategoryChannel
            ):

                await interaction.followup.send(
                    "El ID configurado no corresponde "
                    "a una categoría de Discord.",
                    ephemeral=True
                )

                return


            # Comprobar ticket existente

            ticket_existente = buscar_ticket_usuario(
                guild,
                interaction.user.id
            )


            if ticket_existente:

                await interaction.followup.send(
                    f"Ya tienes un ticket abierto: "
                    f"{ticket_existente.mention}",
                    ephemeral=True
                )

                return


            # Permisos

            overwrites = {

                guild.default_role:
                    discord.PermissionOverwrite(
                        view_channel=False
                    ),

                interaction.user:
                    discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        attach_files=True,
                        embed_links=True
                    )

            }


            # Administradores

            for role in guild.roles:

                if role.permissions.administrator:

                    overwrites[role] = (
                        discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=True,
                            read_message_history=True,
                            manage_channels=True,
                            attach_files=True,
                            embed_links=True
                        )
                    )


            # Crear canal

            canal = await guild.create_text_channel(

                name=f"ticket-{interaction.user.id}",

                category=categoria_discord,

                overwrites=overwrites,

                topic=(
                    f"Owner:{interaction.user.id}"
                    f"|Staff:Sin reclamar"
                    f"|Categoria:{self.categoria}"
                ),

                reason="Creación de ticket InfernMC"

            )


            info = CATEGORIAS[
                self.categoria
            ]


            # Embed

            embed = discord.Embed(

                title=f"🎫 Ticket - {info['label']}",

                description=(
                    f"Hola {interaction.user.mention}.\n\n"
                    "Un miembro del Staff-Team atenderá "
                    "tu ticket lo antes posible.\n\n"
                    "**Información proporcionada:**"
                ),

                color=discord.Color.red()

            )


            embed.add_field(
                name="Nick",
                value=self.nick.value,
                inline=False
            )


            embed.add_field(
                name="Motivo",
                value=self.motivo.value,
                inline=False
            )


            embed.add_field(
                name="Categoría",
                value=info["label"],
                inline=True
            )


            embed.add_field(
                name="Estado",
                value="Sin reclamar",
                inline=True
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


        except Exception as error:

            print(
                "======================================"
            )

            print(
                "[TICKETS] ERROR CREANDO TICKET"
            )

            print(
                repr(error)
            )

            print(
                "======================================"
            )


            try:

                if interaction.response.is_done():

                    await interaction.followup.send(

                        "Ocurrió un error creando el ticket. "
                        "Revisa los logs de Railway.",

                        ephemeral=True

                    )

                else:

                    await interaction.response.send_message(

                        "Ocurrió un error creando el ticket. "
                        "Revisa los logs de Railway.",

                        ephemeral=True

                    )


            except Exception as response_error:

                print(
                    "[TICKETS] ERROR RESPONDIENDO:"
                )

                print(
                    repr(response_error)
                )


# =========================================================
# SELECTOR DE TICKETS
# =========================================================

class TicketSelect(discord.ui.Select):

    def __init__(self):

        opciones = [

            discord.SelectOption(
                label="Ayuda General",
                description="Necesitas ayuda con un problema general.",
                emoji="🎲",
                value="general"
            ),

            discord.SelectOption(
                label="Bugs",
                description="Reporta errores o problemas del servidor.",
                emoji="🎗️",
                value="bugs"
            ),

            discord.SelectOption(
                label="Postulaciones",
                description="Postúlate para formar parte del Staff-Team.",
                emoji=discord.PartialEmoji(
                    name=POSTULACIONES_EMOJI_NAME,
                    id=POSTULACIONES_EMOJI_ID
                ),
                value="postulaciones"
            ),

            discord.SelectOption(
                label="Tienda",
                description="Problemas relacionados con la tienda.",
                emoji="📯",
                value="tienda"
            ),

            discord.SelectOption(
                label="Sanciones",
                description="Apela una sanción.",
                emoji="🗂️",
                value="sanciones"
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

        try:

            categoria = self.values[0]

            print(
                f"[TICKETS] {interaction.user} "
                f"seleccionó: {categoria}"
            )


            if categoria not in CATEGORIAS:

                await interaction.response.send_message(

                    "Categoría inválida.",

                    ephemeral=True

                )

                return


            await interaction.response.send_modal(

                TicketModal(categoria)

            )


            print(
                f"[TICKETS] Modal enviado a "
                f"{interaction.user}"
            )


        except Exception as error:

            print(
                "[TICKETS] ERROR EN SELECT:"
            )

            print(
                repr(error)
            )


            try:

                if not interaction.response.is_done():

                    await interaction.response.send_message(

                        "Ocurrió un error al abrir "
                        "el formulario. Revisa los logs "
                        "de Railway.",

                        ephemeral=True

                    )


            except Exception as error2:

                print(
                    "[TICKETS] ERROR RESPONDIENDO:"
                )

                print(
                    repr(error2)
                )


# =========================================================
# PANEL DE TICKETS
# =========================================================

class TicketPanelView(discord.ui.View):

    def __init__(self):

        super().__init__(
            timeout=None
        )

        self.add_item(
            TicketSelect()
        )


# =========================================================
# RECLAMAR TICKET
# =========================================================

class ClaimButton(
    discord.ui.Button
):

    def __init__(self):

        super().__init__(
            label="Reclamar",
            style=discord.ButtonStyle.primary,
            emoji="📌",
            custom_id="infernmc_ticket_claim"
        )


    async def callback(
        self,
        interaction: discord.Interaction
    ):

        try:

            if not es_admin(
                interaction.user
            ):

                await interaction.response.send_message(

                    "Solo el Staff puede reclamar tickets.",

                    ephemeral=True

                )

                return


            channel = interaction.channel


            if channel is None:

                return


            owner, staff, categoria = (
                obtener_datos_ticket(channel)
            )


            if staff and staff != "Sin reclamar":

                await interaction.response.send_message(

                    "Este ticket ya fue reclamado.",

                    ephemeral=True

                )

                return


            nuevo_topic = (

                f"Owner:{owner}"
                f"|Staff:{interaction.user.id}"
                f"|Categoria:{categoria}"

            )


            await channel.edit(
                topic=nuevo_topic
            )


            sumar_puntos(
                interaction.user.id,
                3,
                "ticket"
            )


            embed = discord.Embed(

                title="📌 Ticket reclamado",

                description=(

                    f"El ticket fue reclamado por "
                    f"{interaction.user.mention}.\n\n"
                    "**+3 puntos para el Staff.**"

                ),

                color=discord.Color.blue()

            )


            await interaction.response.send_message(
                embed=embed
            )


            await actualizar_top_staff(
                interaction.guild
            )


        except Exception as error:

            print(
                "[STAFF] ERROR RECLAMANDO:"
            )

            print(
                repr(error)
            )


# =========================================================
# CERRAR TICKET
# =========================================================

class CloseButton(
    discord.ui.Button
):

    def __init__(self):

        super().__init__(
            label="Cerrar",
            style=discord.ButtonStyle.danger,
            emoji="🔒",
            custom_id="infernmc_ticket_close"
        )


    async def callback(
        self,
        interaction: discord.Interaction
    ):

        try:

            if not es_admin(
                interaction.user
            ):

                await interaction.response.send_message(

                    "Solo el Staff puede cerrar tickets.",

                    ephemeral=True

                )

                return


            channel = interaction.channel


            if channel is None:

                return


            await interaction.response.send_message(

                "Cerrando ticket y generando transcript...",

                ephemeral=True

            )


            owner, staff, categoria = (
                obtener_datos_ticket(channel)
            )


            # Transcript

            archivo = await crear_transcript(
                channel
            )


            # Enviar transcript

            transcripts = (
                interaction.guild.get_channel(
                    TRANSCRIPTS_CHANNEL_ID
                )
            )


            if transcripts:

                await transcripts.send(

                    content=(
                        f"Transcript de `{channel.name}`"
                    ),

                    file=discord.File(
                        archivo
                    )

                )


            # IA local

            if (
                staff
                and staff != "Sin reclamar"
            ):

                try:

                    staff_id = int(staff)

                    score, razon = (
                        await evaluar_ticket_local(
                            channel
                        )
                    )


                    cursor.execute(

                        """
                        INSERT INTO ai_reviews (
                            staff_id,
                            ticket,
                            score,
                            reason,
                            created_at
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,

                        (
                            staff_id,
                            channel.name,
                            score,
                            razon,
                            datetime.now(
                                timezone.utc
                            ).isoformat()
                        )

                    )


                    db.commit()


                    sumar_puntos(
                        staff_id,
                        score,
                        "ai"
                    )


                    print(
                        f"[IA] {channel.name}: "
                        f"{score}/10"
                    )


                except Exception as ai_error:

                    print(
                        "[IA] ERROR:"
                    )

                    print(
                        repr(ai_error)
                    )


            # Rating

            if owner:

                try:

                    owner_id = int(owner)

                    usuario = interaction.guild.get_member(
                        owner_id
                    )


                    if usuario:

                        await usuario.send(

                            embed=discord.Embed(

                                title="⭐ Valora tu ticket",

                                description=(

                                    "Tu ticket en InfernMC "
                                    "ha sido cerrado.\n\n"
                                    "Selecciona cuántas estrellas "
                                    "quieres darle al Staff que "
                                    "atendió tu ticket."

                                ),

                                color=discord.Color.gold()

                            ),

                            view=RatingView(

                                staff_id=(
                                    int(staff)
                                    if staff
                                    and staff != "Sin reclamar"
                                    else None
                                ),

                                ticket_name=channel.name

                            )

                        )

                except Exception as dm_error:

                    print(
                        "[RATING] No se pudo enviar DM:"
                    )

                    print(
                        repr(dm_error)
                    )


            await actualizar_top_staff(
                interaction.guild
            )


            await asyncio.sleep(3)


            await channel.delete(
                reason="Ticket cerrado"
            )


        except Exception as error:

            print(
                "[TICKETS] ERROR CERRANDO:"
            )

            print(
                repr(error)
            )


# =========================================================
# VISTA CONTROL TICKET
# =========================================================

class TicketControlView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=None
        )

        self.add_item(
            ClaimButton()
        )

        self.add_item(
            CloseButton()
        )


# =========================================================
# TRANSCRIPT
# =========================================================

async def crear_transcript(
    channel
):

    nombre = (
        f"transcript-{channel.name}.txt"
    )

    ruta = os.path.join(
        "/tmp",
        nombre
    )


    mensajes = []


    async for mensaje in channel.history(
        limit=None,
        oldest_first=True
    ):

        fecha = mensaje.created_at.strftime(
            "%Y-%m-%d %H:%M:%S"
        )


        contenido = mensaje.content


        if not contenido:

            contenido = "[Sin contenido]"


        mensajes.append(

            f"[{fecha}] "
            f"{mensaje.author} "
            f"(ID: {mensaje.author.id})\n"
            f"{contenido}\n"

        )


        for archivo in mensaje.attachments:

            mensajes.append(
                f"Adjunto: {archivo.url}\n"
            )


        mensajes.append(
            "\n"
        )


    with open(
        ruta,
        "w",
        encoding="utf-8"
    ) as archivo:

        archivo.write(
            f"INFERNMC TRANSCRIPT\n"
            f"Canal: {channel.name}\n"
            f"ID: {channel.id}\n"
            f"Generado: "
            f"{datetime.now(timezone.utc).isoformat()}\n"
            f"{'=' * 60}\n\n"
        )


        archivo.writelines(
            mensajes
        )


    return ruta


# =========================================================
# IA LOCAL GRATUITA
# =========================================================

async def evaluar_ticket_local(
    channel
):

    mensajes = []


    async for mensaje in channel.history(
        limit=200,
        oldest_first=True
    ):

        if mensaje.author.bot:
            continue

        if mensaje.content:

            mensajes.append(
                mensaje.content.lower()
            )


    if not mensajes:

        return 0, "No hubo suficiente información."


    texto = " ".join(
        mensajes
    )


    score = 0
    razones = []


    # Participación

    cantidad = len(
        mensajes
    )


    if cantidad >= 10:

        score += 2
        razones.append(
            "Buena participación."
        )

    elif cantidad >= 5:

        score += 1
        razones.append(
            "Participación aceptable."
        )


    # Mensajes cortos

    cortos = sum(
        1
        for m in mensajes
        if len(m.split()) <= 3
    )


    if cortos > cantidad * 0.5:

        score -= 2

        razones.append(
            "Demasiadas respuestas cortas."
        )


    # Ayuda

    palabras_ayuda = [
        "ayuda",
        "solución",
        "solucion",
        "puedes",
        "debes",
        "tienes que",
        "revisa",
        "explico",
        "explicarte",
        "resuelto",
        "arreglado"
    ]


    ayuda = sum(
        1
        for palabra in palabras_ayuda
        if palabra in texto
    )


    if ayuda >= 3:

        score += 2

        razones.append(
            "El Staff proporcionó ayuda."
        )

    elif ayuda >= 1:

        score += 1


    # Trato

    buenas = [
        "gracias",
        "por favor",
        "disculpa",
        "perdón",
        "bienvenido",
        "claro",
        "perfecto",
        "con gusto"
    ]


    buenas_count = sum(
        1
        for palabra in buenas
        if palabra in texto
    )


    if buenas_count >= 2:

        score += 1

        razones.append(
            "Buen trato."
        )


    malas = [
        "idiota",
        "estupido",
        "estúpido",
        "imbecil",
        "imbécil",
        "cállate",
        "callate",
        "no sirves",
        "mierda"
    ]


    malas_count = sum(
        1
        for palabra in malas
        if palabra in texto
    )


    if malas_count > 0:

        score -= 3

        razones.append(
            "Se detectó lenguaje inapropiado."
        )


    # Resolución

    resolucion = [
        "resuelto",
        "solucionado",
        "solucioné",
        "solucione",
        "arreglado",
        "ya está",
        "ya esta",
        "funciona"
    ]


    if any(
        palabra in texto
        for palabra in resolucion
    ):

        score += 2

        razones.append(
            "El problema parece haber sido resuelto."
        )


    # Explicación

    largos = sum(
        1
        for m in mensajes
        if len(m.split()) >= 15
    )


    if largos >= 2:

        score += 1

        razones.append(
            "Se proporcionaron explicaciones."
        )


    # Repetición

    repetidos = (
        len(mensajes)
        - len(set(mensajes))
    )


    if repetidos >= 3:

        score -= 1

        razones.append(
            "Se detectaron respuestas repetitivas."
        )


    # Satisfacción

    positivos = [
        "gracias por la ayuda",
        "muchas gracias",
        "perfecto",
        "excelente",
        "funcionó",
        "funciono"
    ]


    if any(
        palabra in texto
        for palabra in positivos
    ):

        score += 1

        razones.append(
            "El usuario mostró satisfacción."
        )


    negativos = [
        "no ayudó",
        "no ayudo",
        "sigo igual",
        "no funciona",
        "nadie me ayuda"
    ]


    if any(
        palabra in texto
        for palabra in negativos
    ):

        score -= 1

        razones.append(
            "Se detectó insatisfacción."
        )


    score = max(
        0,
        min(
            10,
            score
        )
    )


    if not razones:

        razones.append(
            "Interacción normal."
        )


    razon = " ".join(
        razones
    )


    return score, razon


# =========================================================
# RATING
# =========================================================

class RatingButton(
    discord.ui.Button
):

    def __init__(
        self,
        estrellas,
        staff_id,
        ticket_name
    ):

        if estrellas <= 2:

            estilo = discord.ButtonStyle.danger

        elif estrellas == 3:

            estilo = discord.ButtonStyle.primary

        else:

            estilo = discord.ButtonStyle.success


        super().__init__(

            label=f"{estrellas} ⭐",

            style=estilo,

            custom_id=(
                f"infernmc_rating_"
                f"{estrellas}_"
                f"{ticket_name}"
            )

        )


        self.estrellas = estrellas
        self.staff_id = staff_id
        self.ticket_name = ticket_name


    async def callback(
        self,
        interaction: discord.Interaction
    ):

        try:

            if self.staff_id is None:

                await interaction.response.send_message(

                    "El ticket no tenía un Staff asignado.",

                    ephemeral=True

                )

                return


            cursor.execute(

                """
                SELECT id
                FROM ratings
                WHERE user_id = ?
                AND ticket = ?
                """,

                (
                    interaction.user.id,
                    self.ticket_name
                )

            )


            existente = cursor.fetchone()


            if existente:

                await interaction.response.send_message(

                    "Ya has valorado este ticket.",

                    ephemeral=True

                )

                return


            cursor.execute(

                """
                INSERT INTO ratings (
                    staff_id,
                    user_id,
                    stars,
                    ticket,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,

                (
                    self.staff_id,
                    interaction.user.id,
                    self.estrellas,
                    self.ticket_name,
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                )

            )


            db.commit()


            sumar_puntos(

                self.staff_id,

                self.estrellas,

                "rating"

            )


            await interaction.response.send_message(

                f"Gracias por tu valoración de "
                f"{self.estrellas} estrellas.",

                ephemeral=True

            )


            canal = (
                interaction.client.get_channel(
                    VALORACIONES_CHANNEL_ID
                )
            )


            if canal:

                embed = discord.Embed(

                    title="⭐ Nueva valoración",

                    color=discord.Color.gold()

                )


                embed.add_field(

                    name="Usuario",

                    value=interaction.user.mention,

                    inline=True

                )


                embed.add_field(

                    name="Staff",

                    value=f"<@{self.staff_id}>",

                    inline=True

                )


                embed.add_field(

                    name="Valoración",

                    value=(
                        "⭐" * self.estrellas
                    ),

                    inline=False

                )


                embed.add_field(

                    name="Puntos",

                    value=f"+{self.estrellas}",

                    inline=True

                )


                embed.set_footer(

                    text="InfernMC • Valoraciones"

                )


                await canal.send(
                    embed=embed
                )


            await actualizar_top_staff(
                interaction.guild
            )


            for item in self.view.children:

                item.disabled = True


            await interaction.message.edit(
                view=self.view
            )


        except Exception as error:

            print(
                "[RATING] ERROR:"
            )

            print(
                repr(error)
            )


class RatingView(
    discord.ui.View
):

    def __init__(
        self,
        staff_id,
        ticket_name
    ):

        super().__init__(
            timeout=86400
        )


        for estrellas in range(
            1,
            6
        ):

            self.add_item(

                RatingButton(

                    estrellas,

                    staff_id,

                    ticket_name

                )

            )


# =========================================================
# TOP STAFF
# =========================================================

def obtener_top_staff():

    revisar_reset_semanal()


    cursor.execute(

        """
        SELECT
            user_id,
            weekly_points,
            total_points,
            tickets_claimed,
            ratings_received,
            ai_points
        FROM staff
        ORDER BY weekly_points DESC
        LIMIT 10
        """

    )


    return cursor.fetchall()


async def actualizar_top_staff(
    guild
):

    revisar_reset_semanal()


    cursor.execute(

        """
        SELECT value
        FROM config
        WHERE key = 'top_channel'
        """

    )


    canal_resultado = cursor.fetchone()


    cursor.execute(

        """
        SELECT value
        FROM config
        WHERE key = 'top_message'
        """

    )


    mensaje_resultado = cursor.fetchone()


    if not canal_resultado or not mensaje_resultado:

        return


    canal = guild.get_channel(
        int(canal_resultado[0])
    )


    if canal is None:

        return


    try:

        mensaje = await canal.fetch_message(
            int(mensaje_resultado[0])
        )

    except Exception:

        return


    top = obtener_top_staff()


    embed = discord.Embed(

        title="🏆 TOP 10 STAFF",

        description=(

            "Clasificación semanal del Staff.\n\n"

            "**Sistema de puntos**\n"
            "📌 Reclamar ticket → **+3**\n"
            "⭐ Valoración → **+1 a +5**\n"
            "🤖 Evaluación IA → **+0 a +10**\n\n"

        ),

        color=discord.Color.red()

    )


    if not top:

        embed.add_field(

            name="Ranking",

            value="Todavía no hay Staff con puntos.",

            inline=False

        )

    else:

        lineas = []


        for posicion, datos in enumerate(
            top,
            start=1
        ):

            (
                user_id,
                weekly,
                total,
                tickets,
                ratings,
                ai_points
            ) = datos


            miembro = guild.get_member(
                user_id
            )


            nombre = (
                miembro.mention
                if miembro
                else f"<@{user_id}>"
            )


            lineas.append(

                f"**#{posicion}** {nombre} "
                f"→ **{weekly} puntos**"

            )


        embed.add_field(

            name="Ranking semanal",

            value="\n".join(
                lineas
            ),

            inline=False

        )


    semana = semana_actual()


    embed.set_footer(

        text=(
            f"InfernMC • Semana {semana}"
        )

    )


    await mensaje.edit(
        embed=embed
    )


# =========================================================
# BIENVENIDA
# =========================================================

async def enviar_bienvenida(
    member
):

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
            "Recuerda leer las reglas, utilizar los "
            "tickets cuando necesites ayuda y respetar "
            "a toda la comunidad."

        ),

        color=discord.Color.red()

    )


    embed.set_thumbnail(
        url=member.display_avatar.url
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

        value=str(
            member.id
        ),

        inline=False

    )


    embed.set_footer(

        text=(
            "InfernMC • Sistema de bienvenidas"
        )

    )


    await canal.send(
        embed=embed
    )


@bot.event
async def on_member_join(
    member
):

    await enviar_bienvenida(
        member
    )


# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    revisar_reset_semanal()


    print(
        "======================================"
    )

    print(
        f"InfernMC conectado como "
        f"{bot.user}"
    )

    print(
        f"ID: {bot.user.id}"
    )

    print(
        f"Servidores: {len(bot.guilds)}"
    )

    print(
        "======================================"
    )


    for guild in bot.guilds:

        try:

            await actualizar_top_staff(
                guild
            )

        except Exception as error:

            print(
                "[TOP] Error actualizando:"
            )

            print(
                repr(error)
            )


# =========================================================
# !TICKETPANEL
# =========================================================

@bot.command()
@commands.has_permissions(
    administrator=True
)
async def ticketpanel(
    ctx
):

    # Borrar paneles anteriores

    try:

        mensajes = []

        async for mensaje in ctx.channel.history(
            limit=50
        ):

            if mensaje.author == bot.user:

                mensajes.append(
                    mensaje
                )


        for mensaje in mensajes:

            try:

                await mensaje.delete()

            except:

                pass


    except Exception as error:

        print(
            "[PANEL] Error limpiando:"
        )

        print(
            repr(error)
        )


    embed = discord.Embed(

        title="🎫 Soporte InfernMC",

        description=(

            "**¿Necesitas ayuda?**\n\n"

            "No dudes en abrir un ticket para "
            "contactar con el Staff-Team.\n\n"

            "**Ten en cuenta que:**\n"
            "• No abras demasiados tickets.\n"
            "• No insultes al Staff.\n"
            "• Sé claro y directo con tu problema.\n\n"

            "**Categorías disponibles:**\n\n"

            "🎲 **Ayuda General**\n"
            "Problemas o dudas generales.\n\n"

            "🎗️ **Bugs**\n"
            "Reporta errores o problemas del servidor.\n\n"

            f"<:{POSTULACIONES_EMOJI_NAME}:"
            f"{POSTULACIONES_EMOJI_ID}> "
            "**Postulaciones**\n"
            "Postúlate para formar parte del Staff-Team.\n\n"

            "📯 **Tienda**\n"
            "Problemas relacionados con la tienda.\n\n"

            "🗂️ **Sanciones**\n"
            "Apela una sanción recibida."

        ),

        color=discord.Color.red()

    )


    embed.set_footer(

        text=(
            "Selecciona una categoría en el menú desplegable."
        )

    )


    await ctx.send(

        embed=embed,

        view=TicketPanelView()

    )


# =========================================================
# !TOPSTAFFPANEL
# =========================================================

@bot.command()
@commands.has_permissions(
    administrator=True
)
async def topstaffpanel(
    ctx
):

    embed = discord.Embed(

        title="🏆 TOP 10 STAFF",

        description=(

            "Clasificación semanal del Staff.\n\n"

            "**Sistema de puntos**\n"
            "📌 Reclamar ticket → **+3**\n"
            "⭐ Valoración → **+1 a +5**\n"
            "🤖 Evaluación IA → **+0 a +10**"

        ),

        color=discord.Color.red()

    )


    embed.add_field(

        name="Ranking",

        value="Cargando ranking...",

        inline=False

    )


    mensaje = await ctx.send(
        embed=embed
    )


    cursor.execute(

        """
        INSERT OR REPLACE INTO config (
            key,
            value
        )
        VALUES (
            'top_channel',
            ?
        )
        """,

        (
            str(ctx.channel.id),
        )

    )


    cursor.execute(

        """
        INSERT OR REPLACE INTO config (
            key,
            value
        )
        VALUES (
            'top_message',
            ?
        )
        """,

        (
            str(mensaje.id),
        )

    )


    db.commit()


    await actualizar_top_staff(
        ctx.guild
    )


# =========================================================
# !TOPSTAFF
# =========================================================

@bot.command()
async def topstaff(
    ctx
):

    top = obtener_top_staff()


    embed = discord.Embed(

        title="🏆 TOP 10 STAFF",

        color=discord.Color.red()

    )


    if not top:

        embed.description = (
            "Todavía no hay Staff con puntos."
        )

    else:

        lineas = []


        for posicion, datos in enumerate(
            top,
            start=1
        ):

            (
                user_id,
                weekly,
                total,
                tickets,
                ratings,
                ai_points
            ) = datos


            miembro = ctx.guild.get_member(
                user_id
            )


            nombre = (
                miembro.mention
                if miembro
                else f"<@{user_id}>"
            )


            lineas.append(

                f"**#{posicion}** {nombre} "
                f"→ **{weekly} puntos**"

            )


        embed.description = "\n".join(
            lineas
        )


    await ctx.send(
        embed=embed
    )


# =========================================================
# !STAFF
# =========================================================

@bot.command()
async def staff(
    ctx,
    miembro: discord.Member = None
):

    if miembro is None:

        miembro = ctx.author


    cursor.execute(

        """
        SELECT
            total_points,
            weekly_points,
            tickets_claimed,
            ratings_received,
            ai_reviews,
            ai_points
        FROM staff
        WHERE user_id = ?
        """,

        (
            miembro.id,
        )

    )


    datos = cursor.fetchone()


    if datos is None:

        await ctx.send(
            "Este Staff todavía no tiene estadísticas."
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

        title=f"📊 Estadísticas de {miembro.display_name}",

        color=discord.Color.red()

    )


    embed.add_field(

        name="Puntos semanales",

        value=str(weekly),

        inline=True

    )


    embed.add_field(

        name="Puntos totales",

        value=str(total),

        inline=True

    )


    embed.add_field(

        name="Tickets reclamados",

        value=str(tickets),

        inline=True

    )


    embed.add_field(

        name="Valoraciones",

        value=str(ratings),

        inline=True

    )


    embed.add_field(

        name="Evaluaciones IA",

        value=str(ai_reviews),

        inline=True

    )


    embed.add_field(

        name="Puntos IA",

        value=str(ai_points),

        inline=True

    )


    await ctx.send(
        embed=embed
    )


# =========================================================
# !TESTBIENVENIDA
# =========================================================

@bot.command()
@commands.has_permissions(
    administrator=True
)
async def testbienvenida(
    ctx
):

    await enviar_bienvenida(
        ctx.author
    )


# =========================================================
# !MENSAJE
# =========================================================

@bot.command()
@commands.has_permissions(
    administrator=True
)
async def mensaje(
    ctx,
    canal: discord.TextChannel,
    *,
    contenido: str
):

    await canal.send(
        contenido
    )


    await ctx.send(
        f"Mensaje enviado a {canal.mention}.",
        delete_after=5
    )


# =========================================================
# ERRORES DE COMANDOS
# =========================================================

@bot.event
async def on_command_error(
    ctx,
    error
):

    if isinstance(
        error,
        commands.MissingPermissions
    ):

        await ctx.send(
            "No tienes permisos para utilizar este comando.",
            delete_after=5
        )

        return


    if isinstance(
        error,
        commands.MemberNotFound
    ):

        await ctx.send(
            "No encontré ese usuario.",
            delete_after=5
        )

        return


    print(
        "[COMMAND ERROR]"
    )

    print(
        repr(error)
    )


# =========================================================
# INICIAR
# =========================================================

if not TOKEN:

    raise RuntimeError(
        "Falta DISCORD_TOKEN en Railway."
    )


bot.run(
    TOKEN
)
