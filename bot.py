import discord
from discord.ext import commands
from discord.ui import View, Button, Select, Modal, TextInput

import sqlite3
import os
import re
import io
import asyncio
from datetime import datetime, timezone


# ============================================================
# CONFIGURACIÓN
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")

WELCOME_CHANNEL_ID = 1548521317295198258
TICKET_CATEGORY_ID = 1548528404649873438
VALORACIONES_CHANNEL_ID = 1550534072449900684
TRANSCRIPTS_CHANNEL_ID = 1548694373875585125

POSTULACIONES_EMOJI = "<:573567deadhamster:1549076149399715840>"

DB_NAME = "infernmc.db"


# ============================================================
# INTENTS
# ============================================================

intents = discord.Intents.default()

intents.members = True
intents.message_content = True
intents.presences = True


# ============================================================
# BOT
# ============================================================

class InfernMCBot(commands.Bot):

    async def setup_hook(self):

        # Views persistentes
        self.add_view(TicketPanelView())
        self.add_view(TicketControlView())

        print("Views persistentes cargadas.")


bot = InfernMCBot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# BASE DE DATOS
# ============================================================

db = sqlite3.connect(DB_NAME)

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


# ============================================================
# FUNCIONES DE BASE DE DATOS
# ============================================================

def asegurar_staff(user_id):

    cursor.execute(
        """
        INSERT OR IGNORE INTO staff
        (user_id)
        VALUES (?)
        """,
        (user_id,)
    )

    db.commit()


def sumar_puntos(user_id, puntos, tipo):

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

    if tipo == "claim":

        cursor.execute(
            """
            UPDATE staff

            SET tickets_claimed =
                tickets_claimed + 1

            WHERE user_id = ?
            """,
            (user_id,)
        )

    elif tipo == "rating":

        cursor.execute(
            """
            UPDATE staff

            SET ratings_received =
                ratings_received + 1

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


def semana_actual():

    ahora = datetime.now(timezone.utc)

    return ahora.isocalendar().week


def revisar_reset_semanal():

    semana = str(semana_actual())

    cursor.execute(
        """
        SELECT value
        FROM config
        WHERE key = 'staff_week'
        """
    )

    resultado = cursor.fetchone()

    if resultado is None:

        cursor.execute(
            """
            INSERT INTO config
            (key, value)

            VALUES
            ('staff_week', ?)
            """,
            (semana,)
        )

        db.commit()

        return

    if resultado[0] != semana:

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

            WHERE key = 'staff_week'
            """,
            (semana,)
        )

        db.commit()


def es_admin(member):

    return member.guild_permissions.administrator


# ============================================================
# CATEGORÍAS
# ============================================================

CATEGORIAS = {

    "general": {
        "label": "Ayuda General",
        "emoji": "🎲",
        "descripcion":
            "Necesitas ayuda con cualquier problema general.",
        "pregunta":
            "¿En qué necesitas ayuda?"
    },

    "bugs": {
        "label": "Bugs",
        "emoji": "🎗️",
        "descripcion":
            "Reporta errores o problemas del servidor.",
        "pregunta":
            "¿Qué bug encontraste?"
    },

    "postulaciones": {
        "label": "Postulaciones",
        "emoji": POSTULACIONES_EMOJI,
        "descripcion":
            "Postúlate para formar parte del Staff-Team.",
        "pregunta":
            "¿Por qué quieres formar parte del Staff-Team?"
    },

    "tienda": {
        "label": "Tienda",
        "emoji": "📯",
        "descripcion":
            "Problemas relacionados con la tienda.",
        "pregunta":
            "¿Cuál es tu problema con la tienda?"
    },

    "sanciones": {
        "label": "Sanciones",
        "emoji": "🗂️",
        "descripcion":
            "Apela una sanción aplicada en el servidor.",
        "pregunta":
            "¿Por qué motivo quieres apelar tu sanción?"
    }
}


# ============================================================
# FUNCIONES DE TICKETS
# ============================================================

def obtener_datos_ticket(channel):

    topic = channel.topic or ""

    datos = {}

    for parte in topic.split("|"):

        if ":" not in parte:
            continue

        clave, valor = parte.split(":", 1)

        datos[clave.lower()] = valor

    return datos


def buscar_ticket_usuario(guild, user_id):

    categoria = guild.get_channel(
        TICKET_CATEGORY_ID
    )

    if categoria is None:
        return None

    for canal in categoria.channels:

        if canal.name == f"ticket-{user_id}":
            return canal

    return None


# ============================================================
# MODAL
# ============================================================

class TicketModal(Modal):

    def __init__(self, categoria):

        self.categoria = categoria

        info = CATEGORIAS[categoria]

        super().__init__(
            title=f"Ticket • {info['label']}"
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

    async def on_submit(self, interaction):

        guild = interaction.guild

        if guild is None:

            await interaction.response.send_message(
                "No se pudo detectar el servidor.",
                ephemeral=True
            )

            return

        # ----------------------------------------------------
        # COMPROBAR CATEGORÍA
        # ----------------------------------------------------

        categoria_discord = guild.get_channel(
            TICKET_CATEGORY_ID
        )

        if categoria_discord is None:

            await interaction.response.send_message(
                "La categoría de tickets no existe. "
                "Revisa TICKET_CATEGORY_ID en el código.",
                ephemeral=True
            )

            return

        if not isinstance(
            categoria_discord,
            discord.CategoryChannel
        ):

            await interaction.response.send_message(
                "El ID configurado no corresponde a una categoría.",
                ephemeral=True
            )

            return

        # ----------------------------------------------------
        # COMPROBAR TICKET EXISTENTE
        # ----------------------------------------------------

        ticket_existente = buscar_ticket_usuario(
            guild,
            interaction.user.id
        )

        if ticket_existente:

            await interaction.response.send_message(
                f"Ya tienes un ticket abierto: "
                f"{ticket_existente.mention}",
                ephemeral=True
            )

            return

        # ----------------------------------------------------
        # PERMISOS
        # ----------------------------------------------------

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

                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_channels=True,
                    attach_files=True,
                    embed_links=True
                )

        # ----------------------------------------------------
        # CREAR CANAL
        # ----------------------------------------------------

        try:

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

        except discord.Forbidden:

            await interaction.response.send_message(
                "El bot no tiene permisos para crear canales.",
                ephemeral=True
            )

            return

        except Exception as e:

            print(
                "ERROR CREANDO TICKET:",
                repr(e)
            )

            await interaction.response.send_message(
                "Ocurrió un error al crear el ticket.",
                ephemeral=True
            )

            return

        # ----------------------------------------------------
        # EMBED
        # ----------------------------------------------------

        info = CATEGORIAS[self.categoria]

        embed = discord.Embed(
            title=f"🎫 Ticket • {info['label']}",
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

        try:

            await canal.send(
                content=interaction.user.mention,
                embed=embed,
                view=TicketControlView()
            )

        except Exception as e:

            print(
                "ERROR ENVIANDO MENSAJE DEL TICKET:",
                repr(e)
            )

            try:
                await canal.delete()
            except:
                pass

            await interaction.response.send_message(
                "El canal fue creado pero no pude enviar "
                "el mensaje del ticket. Revisa los permisos del bot.",
                ephemeral=True
            )

            return

        # ----------------------------------------------------
        # RESPUESTA
        # ----------------------------------------------------

        await interaction.response.send_message(
            f"Ticket creado correctamente: {canal.mention}",
            ephemeral=True
        )


# ============================================================
# SELECTOR DE TICKETS
# ============================================================

class TicketSelect(Select):

    def __init__(self):

        opciones = []

        for key, info in CATEGORIAS.items():

            opciones.append(
                discord.SelectOption(
                    label=info["label"],
                    description=info["descripcion"][:100],
                    emoji=info["emoji"],
                    value=key
                )
            )

        super().__init__(
            placeholder="Selecciona una categoría...",
            min_values=1,
            max_values=1,
            options=opciones,
            custom_id="infernmc_ticket_category_select"
        )

    async def callback(self, interaction):

        try:

            categoria = self.values[0]

            if categoria not in CATEGORIAS:

                await interaction.response.send_message(
                    "Categoría inválida.",
                    ephemeral=True
                )

                return

            # IMPORTANTE:
            # El Modal se abre desde la interacción
            await interaction.response.send_modal(
                TicketModal(categoria)
            )

        except Exception as e:

            print(
                "ERROR EN SELECT DE TICKET:",
                repr(e)
            )

            if not interaction.response.is_done():

                await interaction.response.send_message(
                    "No se pudo abrir el formulario.",
                    ephemeral=True
                )


class TicketPanelView(View):

    def __init__(self):

        super().__init__(
            timeout=None
        )

        self.add_item(
            TicketSelect()
        )


# ============================================================
# BOTONES DE TICKET
# ============================================================

class ClaimButton(Button):

    def __init__(self):

        super().__init__(
            label="Reclamar",
            emoji="🙋",
            style=discord.ButtonStyle.primary,
            custom_id="infernmc_ticket_claim"
        )

    async def callback(self, interaction):

        if not es_admin(interaction.user):

            await interaction.response.send_message(
                "Solo el Staff autorizado puede reclamar tickets.",
                ephemeral=True
            )

            return

        datos = obtener_datos_ticket(
            interaction.channel
        )

        staff_actual = datos.get(
            "staff",
            "Sin reclamar"
        )

        if staff_actual != "Sin reclamar":

            await interaction.response.send_message(
                f"Este ticket ya fue reclamado por "
                f"<@{staff_actual}>.",
                ephemeral=True
            )

            return

        topic = interaction.channel.topic or ""

        nuevo_topic = re.sub(
            r"Staff:[^|]+",
            f"Staff:{interaction.user.id}",
            topic
        )

        await interaction.channel.edit(
            topic=nuevo_topic
        )

        sumar_puntos(
            interaction.user.id,
            3,
            "claim"
        )

        await interaction.response.send_message(
            f"{interaction.user.mention} reclamó este ticket.\n\n"
            "**+3 puntos**"
        )

        await actualizar_top_staff()


class CloseButton(Button):

    def __init__(self):

        super().__init__(
            label="Cerrar",
            emoji="🔒",
            style=discord.ButtonStyle.danger,
            custom_id="infernmc_ticket_close"
        )

    async def callback(self, interaction):

        if not es_admin(interaction.user):

            await interaction.response.send_message(
                "Solo el Staff autorizado puede cerrar tickets.",
                ephemeral=True
            )

            return

        await interaction.response.defer()

        canal = interaction.channel

        datos = obtener_datos_ticket(canal)

        owner_id = datos.get("owner")
        staff_id = datos.get("staff")

        if not owner_id:

            await interaction.followup.send(
                "No se encontró el propietario del ticket."
            )

            return

        # ====================================================
        # TRANSCRIPT
        # ====================================================

        transcript_text, mensajes = await crear_transcript(
            canal
        )

        transcript_channel = canal.guild.get_channel(
            TRANSCRIPTS_CHANNEL_ID
        )

        if transcript_channel:

            archivo = discord.File(
                io.BytesIO(
                    transcript_text.encode("utf-8")
                ),
                filename=f"{canal.name}.txt"
            )

            try:

                await transcript_channel.send(
                    content=(
                        f"**Transcript:** `{canal.name}`\n"
                        f"**Cerrado por:** "
                        f"{interaction.user.mention}"
                    ),
                    file=archivo
                )

            except Exception as e:

                print(
                    "ERROR ENVIANDO TRANSCRIPT:",
                    repr(e)
                )

        # ====================================================
        # IA PROPIA
        # ====================================================

        ai_score = 0

        ai_reason = (
            "El ticket no fue reclamado por un miembro del staff."
        )

        if staff_id and staff_id != "Sin reclamar":

            try:

                staff_id_int = int(staff_id)

                resultado = evaluar_ticket_local(
                    mensajes,
                    staff_id_int
                )

                ai_score = resultado["score"]

                ai_reason = resultado["reason"]

                sumar_puntos(
                    staff_id_int,
                    ai_score,
                    "ai"
                )

                cursor.execute(
                    """
                    INSERT INTO ai_reviews
                    (
                        staff_id,
                        ticket,
                        score,
                        reason,
                        created_at
                    )

                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        staff_id_int,
                        canal.name,
                        ai_score,
                        ai_reason,
                        datetime.now(
                            timezone.utc
                        ).isoformat()
                    )
                )

                db.commit()

            except Exception as e:

                print(
                    "ERROR IA:",
                    repr(e)
                )

        # ====================================================
        # VALORACIÓN
        # ====================================================

        try:

            owner = await bot.fetch_user(
                int(owner_id)
            )

            rating_embed = discord.Embed(
                title="⭐ Valora la atención recibida",
                description=(
                    f"Tu ticket `{canal.name}` fue cerrado.\n\n"
                    "Selecciona una valoración del **1 al 5**.\n\n"
                    "Tu valoración influirá en el ranking del Staff."
                ),
                color=discord.Color.gold()
            )

            await owner.send(
                embed=rating_embed,
                view=RatingView(
                    owner_id=int(owner_id),
                    staff_id=(
                        int(staff_id)
                        if staff_id and staff_id != "Sin reclamar"
                        else None
                    ),
                    ticket_name=canal.name
                )
            )

        except Exception as e:

            print(
                "ERROR ENVIANDO VALORACIÓN:",
                repr(e)
            )

        # ====================================================
        # RESULTADO IA
        # ====================================================

        valoraciones = canal.guild.get_channel(
            VALORACIONES_CHANNEL_ID
        )

        if valoraciones:

            embed = discord.Embed(
                title="🤖 Evaluación automática",
                color=discord.Color.red()
            )

            embed.add_field(
                name="Ticket",
                value=canal.name,
                inline=True
            )

            if staff_id and staff_id != "Sin reclamar":

                embed.add_field(
                    name="Staff",
                    value=f"<@{staff_id}>",
                    inline=True
                )

                embed.add_field(
                    name="Puntuación",
                    value=f"**{ai_score}/10**",
                    inline=True
                )

                embed.add_field(
                    name="Análisis",
                    value=ai_reason[:1024],
                    inline=False
                )

            else:

                embed.add_field(
                    name="Resultado",
                    value=(
                        "No hubo un Staff reclamando el ticket."
                    ),
                    inline=False
                )

            embed.set_footer(
                text="InfernMC • IA automática"
            )

            try:

                await valoraciones.send(
                    embed=embed
                )

            except Exception as e:

                print(
                    "ERROR ENVIANDO EVALUACIÓN:",
                    repr(e)
                )

        await actualizar_top_staff()

        # ====================================================
        # CERRAR
        # ====================================================

        await interaction.followup.send(
            "Ticket cerrado. El canal será eliminado en 3 segundos."
        )

        await asyncio.sleep(3)

        try:

            await canal.delete(
                reason="Ticket cerrado"
            )

        except Exception as e:

            print(
                "ERROR ELIMINANDO TICKET:",
                repr(e)
            )


class TicketControlView(View):

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


# ============================================================
# TRANSCRIPT
# ============================================================

async def crear_transcript(channel):

    mensajes_db = []

    async for mensaje in channel.history(
        limit=None,
        oldest_first=True
    ):

        contenido = mensaje.content

        if not contenido:

            contenido = "[Sin contenido]"

        attachments = []

        for archivo in mensaje.attachments:

            attachments.append(
                archivo.url
            )

        mensajes_db.append({

            "author":
                mensaje.author.name,

            "author_id":
                mensaje.author.id,

            "content":
                contenido,

            "created_at":
                mensaje.created_at,

            "attachments":
                attachments
        })

    lineas = []

    lineas.append(
        f"TRANSCRIPT - {channel.name}"
    )

    lineas.append(
        f"CANAL ID: {channel.id}"
    )

    lineas.append(
        "GENERADO: "
        + datetime.now(
            timezone.utc
        ).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    )

    lineas.append(
        "=" * 70
    )

    for mensaje in mensajes_db:

        fecha = mensaje["created_at"].strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        lineas.append(
            f"[{fecha}] "
            f"{mensaje['author']} "
            f"({mensaje['author_id']}):"
        )

        lineas.append(
            mensaje["content"]
        )

        if mensaje["attachments"]:

            lineas.append(
                "ARCHIVOS:"
            )

            for url in mensaje["attachments"]:

                lineas.append(
                    url
                )

        lineas.append(
            "-" * 70
        )

    return (
        "\n".join(lineas),
        mensajes_db
    )


# ============================================================
# IA PROPIA
# ============================================================

def limpiar_texto(texto):

    texto = texto.lower()

    texto = re.sub(
        r"https?://\S+",
        " ",
        texto
    )

    texto = re.sub(
        r"<a?:\w+:\d+>",
        " ",
        texto
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


def contar_palabras(texto, palabras):

    texto = limpiar_texto(texto)

    cantidad = 0

    for palabra in palabras:

        if palabra in texto:

            cantidad += 1

    return cantidad


def evaluar_ticket_local(
    mensajes,
    staff_id
):

    """
    IA LOCAL DE INFERNMC.

    No utiliza APIs.

    Devuelve:
        score = 0 - 10
        reason = explicación
    """

    if not mensajes:

        return {
            "score": 0,
            "reason":
                "No se encontraron mensajes."
        }

    staff_messages = []
    user_messages = []

    for mensaje in mensajes:

        if mensaje["author_id"] == staff_id:

            staff_messages.append(
                mensaje
            )

        else:

            user_messages.append(
                mensaje
            )

    if not staff_messages:

        return {
            "score": 0,
            "reason":
                "No hubo mensajes del Staff."
        }

    texto_staff = " ".join(
        mensaje["content"]
        for mensaje in staff_messages
    )

    texto_usuario = " ".join(
        mensaje["content"]
        for mensaje in user_messages
    )

    staff_limpio = limpiar_texto(
        texto_staff
    )

    usuario_limpio = limpiar_texto(
        texto_usuario
    )

    score = 5

    razones = []

    # --------------------------------------------------------
    # PARTICIPACIÓN
    # --------------------------------------------------------

    cantidad = len(
        staff_messages
    )

    if cantidad >= 2:

        score += 1

        razones.append(
            "hubo participación suficiente"
        )

    if cantidad >= 5:

        score += 1

        razones.append(
            "hubo una participación alta"
        )

    # --------------------------------------------------------
    # RESPUESTAS CORTAS
    # --------------------------------------------------------

    cortos = 0

    for mensaje in staff_messages:

        contenido = limpiar_texto(
            mensaje["content"]
        )

        if len(contenido) <= 4:

            cortos += 1

    if cortos >= 3:

        score -= 2

        razones.append(
            "hubo varias respuestas demasiado cortas"
        )

    # --------------------------------------------------------
    # AYUDA
    # --------------------------------------------------------

    palabras_ayuda = [

        "ayuda",
        "puedes",
        "puedo",
        "vamos",
        "revisar",
        "revisaré",
        "revisamos",
        "solucion",
        "solución",
        "resolver",
        "resuelto",
        "problema",
        "explicar",
        "explico",
        "comprobar",
        "verificar",
        "verifico",
        "revisando"

    ]

    ayuda = contar_palabras(
        staff_limpio,
        palabras_ayuda
    )

    if ayuda >= 2:

        score += 1

        razones.append(
            "se detectaron respuestas orientadas a ayudar"
        )

    if ayuda >= 5:

        score += 1

        razones.append(
            "hubo varias acciones de solución"
        )

    # --------------------------------------------------------
    # RESOLUCIÓN
    # --------------------------------------------------------

    resolucion = [

        "solucionado",
        "solucioné",
        "solucione",
        "resuelto",
        "resolví",
        "resolvi",
        "arreglado",
        "arreglé",
        "arregle",
        "hecho",
        "listo",
        "corregido",
        "funciona",
        "funcionando",
        "prueba ahora"

    ]

    cantidad_resolucion = contar_palabras(
        staff_limpio,
        resolucion
    )

    if cantidad_resolucion >= 1:

        score += 1

        razones.append(
            "hay señales de resolución"
        )

    # --------------------------------------------------------
    # EXPLICACIÓN
    # --------------------------------------------------------

    explicacion = [

        "porque",
        "debido",
        "significa",
        "funciona",
        "motivo",
        "razón",
        "razon",
        "explicación",
        "explicacion",
        "para que",
        "esto ocurre"

    ]

    cantidad_explicacion = contar_palabras(
        staff_limpio,
        explicacion
    )

    if cantidad_explicacion >= 2:

        score += 1

        razones.append(
            "el Staff proporcionó explicaciones"
        )

    # --------------------------------------------------------
    # BUEN TRATO
    # --------------------------------------------------------

    buen_trato = [

        "hola",
        "buenas",
        "gracias",
        "por favor",
        "disculpa",
        "disculpe",
        "entiendo",
        "claro",
        "perfecto",
        "con gusto",
        "de nada"

    ]

    cantidad_trato = contar_palabras(
        staff_limpio,
        buen_trato
    )

    if cantidad_trato >= 2:

        score += 1

        razones.append(
            "se detectó un trato adecuado"
        )

    # --------------------------------------------------------
    # CIERRE
    # --------------------------------------------------------

    cierres = [

        "alguna otra duda",
        "alguna otra pregunta",
        "puedo ayudarte",
        "necesitas algo más",
        "necesitas algo mas",
        "si necesitas",
        "que tengas",
        "buen día",
        "buen dia"

    ]

    if contar_palabras(
        staff_limpio,
        cierres
    ) >= 1:

        score += 1

        razones.append(
            "el cierre fue adecuado"
        )

    # --------------------------------------------------------
    # MAL TRATO
    # --------------------------------------------------------

    negativas = [

        "cállate",
        "callate",
        "idiota",
        "imbecil",
        "imbécil",
        "estúpido",
        "estupido",
        "no me importa",
        "problema tuyo",
        "vete",
        "largate",
        "lárgate"

    ]

    if contar_palabras(
        staff_limpio,
        negativas
    ) >= 1:

        score -= 3

        razones.append(
            "se detectaron expresiones poco profesionales"
        )

    # --------------------------------------------------------
    # REPETICIONES
    # --------------------------------------------------------

    contenidos = []

    for mensaje in staff_messages:

        texto = limpiar_texto(
            mensaje["content"]
        )

        if len(texto) > 8:

            contenidos.append(
                texto
            )

    repetidos = 0

    for i in range(
        len(contenidos)
    ):

        for j in range(
            i + 1,
            len(contenidos)
        ):

            if contenidos[i] == contenidos[j]:

                repetidos += 1

    if repetidos >= 2:

        score -= 2

        razones.append(
            "se detectaron respuestas repetitivas"
        )

    # --------------------------------------------------------
    # CANTIDAD DE INFORMACIÓN
    # --------------------------------------------------------

    cantidad_palabras = len(
        staff_limpio.split()
    )

    if cantidad_palabras >= 40:

        score += 1

        razones.append(
            "se proporcionó suficiente información"
        )

    if cantidad_palabras <= 8:

        score -= 1

        razones.append(
            "la información fue limitada"
        )

    # --------------------------------------------------------
    # USUARIO CONFORME
    # --------------------------------------------------------

    conformidad = [

        "gracias",
        "muchas gracias",
        "perfecto",
        "funciona",
        "ya funciona",
        "listo",
        "solucionado",
        "todo bien"

    ]

    if contar_palabras(
        usuario_limpio,
        conformidad
    ) >= 1:

        score += 1

        razones.append(
            "el usuario dejó señales de conformidad"
        )

    # --------------------------------------------------------
    # USUARIO INCONFORME
    # --------------------------------------------------------

    inconformidad = [

        "no funciona",
        "sigue sin funcionar",
        "no sirve",
        "no me ayudaste",
        "sigo igual",
        "nadie me ayuda",
        "llevo mucho esperando",
        "esto no sirve"

    ]

    if contar_palabras(
        usuario_limpio,
        inconformidad
    ) >= 1:

        score -= 2

        razones.append(
            "el usuario dejó señales de inconformidad"
        )

    # --------------------------------------------------------
    # LIMITAR
    # --------------------------------------------------------

    score = max(
        0,
        min(
            10,
            score
        )
    )

    if not razones:

        razones.append(
            "evaluación basada en la actividad del ticket"
        )

    razones = list(
        dict.fromkeys(
            razones
        )
    )

    return {

        "score":
            score,

        "reason":
            "; ".join(
                razones
            )
    }


# ============================================================
# VALORACIONES
# ============================================================

class RatingButton(Button):

    def __init__(
        self,
        stars,
        owner_id,
        staff_id,
        ticket_name
    ):

        estilos = {

            1:
                discord.ButtonStyle.danger,

            2:
                discord.ButtonStyle.danger,

            3:
                discord.ButtonStyle.primary,

            4:
                discord.ButtonStyle.success,

            5:
                discord.ButtonStyle.success
        }

        super().__init__(
            label=f"{stars} ⭐",
            style=estilos[stars],
            custom_id=f"infernmc_rating_{stars}_{ticket_name}"
        )

        self.stars = stars
        self.owner_id = owner_id
        self.staff_id = staff_id
        self.ticket_name = ticket_name

    async def callback(self, interaction):

        if interaction.user.id != self.owner_id:

            await interaction.response.send_message(
                "Esta valoración no te pertenece.",
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
                self.owner_id,
                self.ticket_name
            )
        )

        if cursor.fetchone():

            await interaction.response.send_message(
                "Ya has valorado este ticket.",
                ephemeral=True
            )

            return

        cursor.execute(
            """
            INSERT INTO ratings
            (
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
                self.owner_id,
                self.stars,
                self.ticket_name,
                datetime.now(
                    timezone.utc
                ).isoformat()
            )
        )

        db.commit()

        if self.staff_id:

            sumar_puntos(
                self.staff_id,
                self.stars,
                "rating"
            )

        canal_valoraciones = bot.get_channel(
            VALORACIONES_CHANNEL_ID
        )

        if canal_valoraciones:

            embed = discord.Embed(
                title="⭐ Nueva valoración",
                color=discord.Color.gold()
            )

            embed.add_field(
                name="Usuario",
                value=f"<@{self.owner_id}>",
                inline=True
            )

            if self.staff_id:

                embed.add_field(
                    name="Staff",
                    value=f"<@{self.staff_id}>",
                    inline=True
                )

            embed.add_field(
                name="Valoración",
                value="⭐" * self.stars,
                inline=False
            )

            embed.add_field(
                name="Puntos",
                value=f"**+{self.stars}**",
                inline=False
            )

            embed.set_footer(
                text=f"Ticket: {self.ticket_name}"
            )

            await canal_valoraciones.send(
                embed=embed
            )

        await interaction.response.edit_message(
            content=(
                f"Valoración registrada: "
                f"{'⭐' * self.stars}\n\n"
                f"**+{self.stars} puntos** para el Staff."
            ),
            embed=None,
            view=None
        )

        await actualizar_top_staff()


class RatingView(View):

    def __init__(
        self,
        owner_id,
        staff_id,
        ticket_name
    ):

        # La valoración dura 24 horas
        super().__init__(
            timeout=86400
        )

        for stars in range(
            1,
            6
        ):

            self.add_item(
                RatingButton(
                    stars,
                    owner_id,
                    staff_id,
                    ticket_name
                )
            )


# ============================================================
# TOP STAFF
# ============================================================

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
            ai_reviews,
            ai_points

        FROM staff

        WHERE weekly_points > 0

        ORDER BY
            weekly_points DESC,
            total_points DESC

        LIMIT 10
        """
    )

    return cursor.fetchall()


async def actualizar_top_staff():

    cursor.execute(
        """
        SELECT value

        FROM config

        WHERE key = 'top_channel'
        """
    )

    channel_result = cursor.fetchone()

    cursor.execute(
        """
        SELECT value

        FROM config

        WHERE key = 'top_message'
        """
    )

    message_result = cursor.fetchone()

    if not channel_result:
        return

    if not message_result:
        return

    try:

        channel = bot.get_channel(
            int(channel_result[0])
        )

        if channel is None:
            return

        message = await channel.fetch_message(
            int(message_result[0])
        )

        top = obtener_top_staff()

        embed = discord.Embed(
            title="🏆 TOP 10 STAFF",
            description=(
                "**Clasificación semanal**\n\n"

                "El ranking se actualiza automáticamente.\n\n"

                "**Sistema de puntos**\n"
                "🎫 Ticket reclamado → **+3**\n"
                "⭐ Valoración → **+1 a +5**\n"
                "🤖 IA → **+0 a +10**"
            ),
            color=discord.Color.red()
        )

        if not top:

            embed.add_field(
                name="Ranking",
                value=(
                    "Todavía no hay puntos registrados."
                ),
                inline=False
            )

        else:

            texto = ""

            for posicion, datos in enumerate(
                top,
                start=1
            ):

                user_id = datos[0]
                weekly = datos[1]
                total = datos[2]
                tickets = datos[3]
                ratings = datos[4]
                ai_points = datos[6]

                miembro = channel.guild.get_member(
                    user_id
                )

                if miembro:

                    nombre = miembro.mention

                else:

                    nombre = f"<@{user_id}>"

                texto += (
                    f"**#{posicion} {nombre}**\n"
                    f"└ Semanal: **{weekly}**\n"
                    f"└ Total: **{total}**\n"
                    f"└ Tickets: **{tickets}** | "
                    f"Valoraciones: **{ratings}** | "
                    f"IA: **{ai_points}**\n\n"
                )

            embed.add_field(
                name="Clasificación",
                value=texto[:1024],
                inline=False
            )

        embed.set_footer(
            text=(
                f"InfernMC • Semana "
                f"{semana_actual()}"
            )
        )

        await message.edit(
            embed=embed
        )

    except discord.NotFound:

        print(
            "El mensaje del Top Staff ya no existe."
        )

    except Exception as e:

        print(
            "ERROR ACTUALIZANDO TOP:",
            repr(e)
        )


# ============================================================
# BIENVENIDA
# ============================================================

async def enviar_bienvenida(member):

    channel = bot.get_channel(
        WELCOME_CHANNEL_ID
    )

    if channel is None:
        return

    embed = discord.Embed(
        title="🔥 ¡Bienvenido/a a InfernMC!",
        description=(
            f"¡Bienvenido/a {member.mention}!\n\n"
            "Esperamos que disfrutes de tu estancia "
            "en **InfernMC**.\n\n"
            "Recuerda leer las reglas, respetar a "
            "los demás miembros y utilizar los tickets "
            "si necesitas ayuda."
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
        inline=True
    )

    embed.set_footer(
        text="InfernMC • Sistema de bienvenidas"
    )

    await channel.send(
        embed=embed
    )


@bot.event
async def on_member_join(member):

    await enviar_bienvenida(
        member
    )


# ============================================================
# READY
# ============================================================

@bot.event
async def on_ready():

    revisar_reset_semanal()

    print("=" * 50)

    print(
        f"Bot conectado: {bot.user}"
    )

    print(
        f"ID: {bot.user.id}"
    )

    print(
        f"Servidor(es): {len(bot.guilds)}"
    )

    print("=" * 50)

    await actualizar_top_staff()


# ============================================================
# !TICKETPANEL
# ============================================================

@bot.command()
async def ticketpanel(ctx):

    if not es_admin(ctx.author):

        await ctx.send(
            "No tienes permisos para usar este comando."
        )

        return

    # Borrar paneles anteriores del bot
    try:

        mensajes = []

        async for mensaje in ctx.channel.history(
            limit=50
        ):

            if mensaje.author.id == bot.user.id:

                mensajes.append(
                    mensaje
                )

        for mensaje in mensajes:

            try:

                await mensaje.delete()

            except:

                pass

    except Exception as e:

        print(
            "ERROR LIMPIANDO PANEL:",
            repr(e)
        )

    embed = discord.Embed(
        title="🎫 ¿Necesitas ayuda?",
        description=(

            "No dudes en abrir un ticket si necesitas "
            "ayuda con cualquier situación relacionada "
            "con **InfernMC**.\n\n"

            "## Ten en cuenta que\n"

            "• No abras demasiados tickets.\n"
            "• No insultes ni faltes el respeto al Staff-Team.\n"
            "• Explica tu problema de forma clara y directa.\n\n"

            "## Categorías disponibles\n\n"

            "🎲 **Ayuda General**\n"
            "Para cualquier problema o duda general.\n\n"

            "🎗️ **Bugs**\n"
            "Para reportar errores o problemas del servidor.\n\n"

            f"{POSTULACIONES_EMOJI} **Postulaciones**\n"
            "Para postularte al Staff-Team.\n\n"

            "📯 **Tienda**\n"
            "Para problemas relacionados con la tienda.\n\n"

            "🗂️ **Sanciones**\n"
            "Para apelar una sanción.\n\n"

            "**Selecciona una categoría en el menú "
            "desplegable.**"
        ),
        color=discord.Color.red()
    )

    embed.set_footer(
        text="InfernMC • Sistema de tickets"
    )

    await ctx.send(
        embed=embed,
        view=TicketPanelView()
    )


# ============================================================
# !TOPSTAFFPANEL
# ============================================================

@bot.command()
async def topstaffpanel(ctx):

    if not es_admin(ctx.author):

        await ctx.send(
            "No tienes permisos para usar este comando."
        )

        return

    embed = discord.Embed(
        title="🏆 TOP 10 STAFF",
        description=(
            "**Clasificación semanal**\n\n"

            "El ranking se actualiza automáticamente.\n\n"

            "**Sistema de puntos**\n"
            "🎫 Ticket reclamado → **+3**\n"
            "⭐ Valoración → **+1 a +5**\n"
            "🤖 IA → **+0 a +10**"
        ),
        color=discord.Color.red()
    )

    embed.add_field(
        name="Ranking",
        value=(
            "Todavía no hay puntos registrados."
        ),
        inline=False
    )

    embed.set_footer(
        text=f"InfernMC • Semana {semana_actual()}"
    )

    mensaje = await ctx.send(
        embed=embed
    )

    cursor.execute(
        """
        INSERT OR REPLACE INTO config
        (key, value)

        VALUES
        ('top_channel', ?)
        """,
        (
            str(ctx.channel.id),
        )
    )

    cursor.execute(
        """
        INSERT OR REPLACE INTO config
        (key, value)

        VALUES
        ('top_message', ?)
        """,
        (
            str(mensaje.id),
        )
    )

    db.commit()

    await ctx.send(
        "Panel de Top Staff configurado."
    )


# ============================================================
# !TOPSTAFF
# ============================================================

@bot.command()
async def topstaff(ctx):

    top = obtener_top_staff()

    embed = discord.Embed(
        title="🏆 TOP 10 STAFF",
        color=discord.Color.red()
    )

    if not top:

        embed.description = (
            "Todavía no hay puntos registrados."
        )

    else:

        texto = ""

        for posicion, datos in enumerate(
            top,
            start=1
        ):

            user_id = datos[0]
            weekly = datos[1]
            total = datos[2]

            texto += (
                f"**#{posicion} <@{user_id}>**\n"
                f"└ Semanal: **{weekly}**\n"
                f"└ Total: **{total}**\n\n"
            )

        embed.description = texto

    embed.set_footer(
        text=f"InfernMC • Semana {semana_actual()}"
    )

    await ctx.send(
        embed=embed
    )


# ============================================================
# !STAFF
# ============================================================

@bot.command()
async def staff(
    ctx,
    miembro: discord.Member = None
):

    if miembro is None:

        miembro = ctx.author

    asegurar_staff(
        miembro.id
    )

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

    if not datos:
        return

    embed = discord.Embed(
        title="📊 Estadísticas Staff",
        color=discord.Color.red()
    )

    embed.set_thumbnail(
        url=miembro.display_avatar.url
    )

    embed.add_field(
        name="Staff",
        value=miembro.mention,
        inline=False
    )

    embed.add_field(
        name="Puntos semanales",
        value=f"**{datos[1]}**",
        inline=True
    )

    embed.add_field(
        name="Puntos totales",
        value=f"**{datos[0]}**",
        inline=True
    )

    embed.add_field(
        name="Tickets reclamados",
        value=str(datos[2]),
        inline=True
    )

    embed.add_field(
        name="Valoraciones",
        value=str(datos[3]),
        inline=True
    )

    embed.add_field(
        name="Evaluaciones IA",
        value=str(datos[4]),
        inline=True
    )

    embed.add_field(
        name="Puntos IA",
        value=f"**{datos[5]}**",
        inline=True
    )

    embed.set_footer(
        text="InfernMC • Estadísticas Staff"
    )

    await ctx.send(
        embed=embed
    )


# ============================================================
# !TESTBIENVENIDA
# ============================================================

@bot.command()
async def testbienvenida(ctx):

    if not es_admin(ctx.author):

        await ctx.send(
            "No tienes permisos para usar este comando."
        )

        return

    await enviar_bienvenida(
        ctx.author
    )

    await ctx.send(
        "Bienvenida de prueba enviada."
    )


# ============================================================
# !MENSAJE
# ============================================================

@bot.command()
async def mensaje(
    ctx,
    canal: discord.TextChannel,
    *,
    texto
):

    if not es_admin(ctx.author):

        await ctx.send(
            "No tienes permisos para usar este comando."
        )

        return

    await canal.send(
        texto
    )

    await ctx.send(
        "Mensaje enviado."
    )


# ============================================================
# ERRORES DE COMANDOS
# ============================================================

@bot.event
async def on_command_error(
    ctx,
    error
):

    if isinstance(
        error,
        commands.CommandNotFound
    ):

        return

    if isinstance(
        error,
        commands.MissingRequiredArgument
    ):

        await ctx.send(
            "Faltan argumentos para usar este comando."
        )

        return

    print(
        f"ERROR COMANDO {ctx.command}:",
        repr(error)
    )


# ============================================================
# INICIAR
# ============================================================

if not TOKEN:

    raise RuntimeError(
        "Falta DISCORD_TOKEN en Railway."
    )


bot.run(TOKEN)
