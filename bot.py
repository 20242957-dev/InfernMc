import discord
from discord.ext import commands
from discord.ui import View, Button, Select, Modal, TextInput
import sqlite3
import os
import re
import asyncio
from datetime import datetime, timezone


# =========================================================
# CONFIGURACIÓN
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

WELCOME_CHANNEL_ID = 1548521317295198258
TICKET_CATEGORY_ID = 1548528404649873438
VALORACIONES_CHANNEL_ID = 1550534072449900684
TRANSCRIPTS_CHANNEL_ID = 1548694373875585125

POSTULACIONES_EMOJI = "<:573567deadhamster:1549076149399715840>"

# Base de datos
DB_NAME = "infernmc.db"


# =========================================================
# BOT
# =========================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.presences = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# BASE DE DATOS
# =========================================================

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


# =========================================================
# FUNCIONES GENERALES
# =========================================================

def asegurar_staff(user_id):
    cursor.execute(
        "INSERT OR IGNORE INTO staff (user_id) VALUES (?)",
        (user_id,)
    )
    db.commit()


def sumar_puntos(user_id, puntos, tipo):
    asegurar_staff(user_id)

    cursor.execute("""
        UPDATE staff
        SET total_points = total_points + ?,
            weekly_points = weekly_points + ?
        WHERE user_id = ?
    """, (puntos, puntos, user_id))

    if tipo == "claim":
        cursor.execute("""
            UPDATE staff
            SET tickets_claimed = tickets_claimed + 1
            WHERE user_id = ?
        """, (user_id,))

    elif tipo == "rating":
        cursor.execute("""
            UPDATE staff
            SET ratings_received = ratings_received + 1
            WHERE user_id = ?
        """, (user_id,))

    elif tipo == "ai":
        cursor.execute("""
            UPDATE staff
            SET ai_reviews = ai_reviews + 1,
                ai_points = ai_points + ?
            WHERE user_id = ?
        """, (puntos, user_id))

    db.commit()


def semana_actual():
    ahora = datetime.now(timezone.utc)
    return ahora.isocalendar().week


def revisar_reset_semanal():
    semana = str(semana_actual())

    cursor.execute(
        "SELECT value FROM config WHERE key='staff_week'"
    )

    resultado = cursor.fetchone()

    if resultado is None:
        cursor.execute("""
            INSERT INTO config (key, value)
            VALUES ('staff_week', ?)
        """, (semana,))
        db.commit()
        return

    semana_guardada = resultado[0]

    if semana_guardada != semana:

        cursor.execute("""
            UPDATE staff
            SET weekly_points = 0
        """)

        cursor.execute("""
            UPDATE config
            SET value = ?
            WHERE key = 'staff_week'
        """, (semana,))

        db.commit()


def es_admin(member):
    return member.guild_permissions.administrator


# =========================================================
# TOP STAFF
# =========================================================

def obtener_top_staff():
    revisar_reset_semanal()

    cursor.execute("""
        SELECT user_id, weekly_points, total_points,
               tickets_claimed, ratings_received,
               ai_reviews, ai_points
        FROM staff
        WHERE weekly_points > 0
        ORDER BY weekly_points DESC, total_points DESC
        LIMIT 10
    """)

    return cursor.fetchall()


async def actualizar_top_staff():

    cursor.execute("""
        SELECT value FROM config
        WHERE key='top_channel'
    """)

    channel_result = cursor.fetchone()

    cursor.execute("""
        SELECT value FROM config
        WHERE key='top_message'
    """)

    message_result = cursor.fetchone()

    if not channel_result or not message_result:
        return

    try:
        channel = bot.get_channel(int(channel_result[0]))

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
                "🤖 Evaluación IA → **+0 a +10**"
            ),
            color=discord.Color.red()
        )

        if not top:
            embed.add_field(
                name="Ranking",
                value="Todavía no hay puntos registrados.",
                inline=False
            )

        else:
            texto = ""

            for posicion, datos in enumerate(top, start=1):

                user_id = datos[0]
                weekly = datos[1]
                total = datos[2]
                tickets = datos[3]
                ratings = datos[4]
                ai_reviews = datos[5]
                ai_points = datos[6]

                member = channel.guild.get_member(user_id)

                if member:
                    nombre = member.mention
                else:
                    nombre = f"<@{user_id}>"

                texto += (
                    f"**#{posicion} {nombre}**\n"
                    f"└ Puntos semanales: **{weekly}**\n"
                    f"└ Puntos totales: **{total}**\n"
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
            text=f"InfernMC • Semana {semana_actual()}"
        )

        await message.edit(embed=embed)

    except Exception as e:
        print("Error actualizando Top Staff:", e)


# =========================================================
# IA PROPIA
# =========================================================

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


def evaluar_ticket_local(mensajes, staff_id):

    """
    IA PROPIA DE INFERNMC

    No utiliza ninguna API externa.

    Analiza:
    - Cantidad de mensajes
    - Participación del staff
    - Respuestas útiles
    - Resolución
    - Claridad
    - Trato
    - Señales negativas
    - Despedida/cierre
    - Tiempo aproximado
    """

    if not mensajes:
        return {
            "score": 0,
            "reason": "No se encontraron mensajes suficientes."
        }

    staff_messages = []
    user_messages = []

    for mensaje in mensajes:

        if mensaje["author_id"] == staff_id:
            staff_messages.append(mensaje)
        else:
            user_messages.append(mensaje)

    if not staff_messages:
        return {
            "score": 0,
            "reason": "El ticket fue cerrado sin participación registrada del staff."
        }

    # -----------------------------------------------------
    # Texto del staff
    # -----------------------------------------------------

    texto_staff = " ".join(
        m["content"]
        for m in staff_messages
    )

    texto_usuario = " ".join(
        m["content"]
        for m in user_messages
    )

    texto_total = texto_staff + " " + texto_usuario

    staff_limpio = limpiar_texto(texto_staff)
    total_limpio = limpiar_texto(texto_total)

    # -----------------------------------------------------
    # PUNTUACIÓN BASE
    # -----------------------------------------------------

    score = 5

    razones = []

    # -----------------------------------------------------
    # PARTICIPACIÓN
    # -----------------------------------------------------

    cantidad_staff = len(staff_messages)

    if cantidad_staff >= 2:
        score += 1
        razones.append("hubo participación suficiente del staff")

    if cantidad_staff >= 5:
        score += 1
        razones.append("el staff tuvo una participación alta")

    # -----------------------------------------------------
    # MENSAJES MUY CORTOS
    # -----------------------------------------------------

    mensajes_cortos = 0

    for mensaje in staff_messages:

        contenido = limpiar_texto(
            mensaje["content"]
        )

        if len(contenido) <= 4:
            mensajes_cortos += 1

    if mensajes_cortos >= 3:
        score -= 2
        razones.append("varias respuestas del staff fueron demasiado cortas")

    # -----------------------------------------------------
    # PALABRAS DE AYUDA
    # -----------------------------------------------------

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
        razones.append("se detectaron respuestas orientadas a ayudar")

    if ayuda >= 5:
        score += 1
        razones.append("hubo varias acciones relacionadas con la solución")

    # -----------------------------------------------------
    # PALABRAS DE RESOLUCIÓN
    # -----------------------------------------------------

    palabras_resolucion = [
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
        "puedes probar",
        "prueba ahora"
    ]

    resolucion = contar_palabras(
        staff_limpio,
        palabras_resolucion
    )

    if resolucion >= 1:
        score += 1
        razones.append("hay señales de resolución del problema")

    # -----------------------------------------------------
    # PALABRAS DE EXPLICACIÓN
    # -----------------------------------------------------

    palabras_explicacion = [
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

    explicacion = contar_palabras(
        staff_limpio,
        palabras_explicacion
    )

    if explicacion >= 2:
        score += 1
        razones.append("el staff proporcionó explicaciones")

    # -----------------------------------------------------
    # TRATO AL USUARIO
    # -----------------------------------------------------

    palabras_buen_trato = [
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

    buen_trato = contar_palabras(
        staff_limpio,
        palabras_buen_trato
    )

    if buen_trato >= 2:
        score += 1
        razones.append("se detectó un trato adecuado al usuario")

    # -----------------------------------------------------
    # CIERRE PROFESIONAL
    # -----------------------------------------------------

    palabras_cierre = [
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

    cierre = contar_palabras(
        staff_limpio,
        palabras_cierre
    )

    if cierre >= 1:
        score += 1
        razones.append("el cierre de la atención fue adecuado")

    # -----------------------------------------------------
    # RESPUESTAS NEGATIVAS
    # -----------------------------------------------------

    palabras_negativas = [
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

    negativas = contar_palabras(
        staff_limpio,
        palabras_negativas
    )

    if negativas >= 1:
        score -= 3
        razones.append("se detectaron expresiones poco profesionales")

    # -----------------------------------------------------
    # SPAM / REPETICIÓN
    # -----------------------------------------------------

    mensajes_repetidos = 0

    contenidos = []

    for mensaje in staff_messages:

        contenido = limpiar_texto(
            mensaje["content"]
        )

        if len(contenido) > 8:
            contenidos.append(contenido)

    for i in range(len(contenidos)):

        for j in range(i + 1, len(contenidos)):

            if contenidos[i] == contenidos[j]:
                mensajes_repetidos += 1

    if mensajes_repetidos >= 2:
        score -= 2
        razones.append("se detectaron respuestas repetitivas")

    # -----------------------------------------------------
    # RELACIÓN STAFF / USUARIO
    # -----------------------------------------------------

    if len(user_messages) > 0:

        relacion = cantidad_staff / len(user_messages)

        if relacion >= 0.3 and relacion <= 5:
            score += 1
            razones.append("la conversación tuvo una participación equilibrada")

    # -----------------------------------------------------
    # LONGITUD
    # -----------------------------------------------------

    palabras_staff = len(
        staff_limpio.split()
    )

    if palabras_staff >= 40:
        score += 1
        razones.append("el staff proporcionó suficiente información")

    if palabras_staff <= 8:
        score -= 1
        razones.append("la información proporcionada fue limitada")

    # -----------------------------------------------------
    # SEÑALES DE QUE EL USUARIO QUEDÓ CONFORME
    # -----------------------------------------------------

    conformidad = [
        "gracias",
        "muchas gracias",
        "perfecto",
        "funciona",
        "ya funciona",
        "listo",
        "solucionado",
        "solucionado gracias",
        "todo bien"
    ]

    conformidad_detectada = contar_palabras(
        texto_usuario,
        conformidad
    )

    if conformidad_detectada >= 1:
        score += 1
        razones.append("el usuario dejó señales de conformidad")

    # -----------------------------------------------------
    # SEÑALES DE QUE EL USUARIO SIGUE MOLESTO
    # -----------------------------------------------------

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

    inconformidad_detectada = contar_palabras(
        texto_usuario,
        inconformidad
    )

    if inconformidad_detectada >= 1:
        score -= 2
        razones.append("el usuario dejó señales de inconformidad")

    # -----------------------------------------------------
    # LIMITAR RESULTADO
    # -----------------------------------------------------

    score = max(0, min(10, score))

    if not razones:
        razones.append(
            "la evaluación se basó en la actividad registrada del ticket"
        )

    # Quitar duplicados
    razones = list(dict.fromkeys(razones))

    return {
        "score": score,
        "reason": "; ".join(razones)
    }


# =========================================================
# TRANSCRIPT
# =========================================================

async def crear_transcript(channel):

    mensajes = []

    async for mensaje in channel.history(
        limit=None,
        oldest_first=True
    ):

        contenido = mensaje.content

        if not contenido:
            contenido = "[Sin contenido]"

        archivos = ""

        if mensaje.attachments:

            archivos = "\n".join(
                attachment.url
                for attachment in mensaje.attachments
            )

        mensajes.append({
            "author": mensaje.author.name,
            "author_id": mensaje.author.id,
            "content": contenido,
            "created_at": mensaje.created_at,
            "attachments": archivos
        })

    lineas = []

    lineas.append(
        f"TRANSCRIPT - {channel.name}"
    )

    lineas.append(
        f"ID DEL CANAL: {channel.id}"
    )

    lineas.append(
        f"GENERADO: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )

    lineas.append("=" * 70)

    for mensaje in mensajes:

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
            lineas.append(
                mensaje["attachments"]
            )

        lineas.append("-" * 70)

    contenido = "\n".join(lineas)

    return contenido, mensajes


# =========================================================
# TOPIC DEL TICKET
# =========================================================

def obtener_datos_ticket(channel):

    topic = channel.topic or ""

    datos = {}

    partes = topic.split("|")

    for parte in partes:

        if ":" not in parte:
            continue

        clave, valor = parte.split(":", 1)

        datos[clave.lower()] = valor

    return datos


# =========================================================
# CATEGORÍAS
# =========================================================

CATEGORIAS = {
    "general": {
        "label": "Ayuda General",
        "emoji": "🎲",
        "descripcion": "Necesitas ayuda con cualquier problema general.",
        "pregunta": "¿En qué necesitas ayuda?"
    },

    "bugs": {
        "label": "Bugs",
        "emoji": "🎗️",
        "descripcion": "Reporta errores o problemas del servidor.",
        "pregunta": "¿Qué bug encontraste?"
    },

    "postulaciones": {
        "label": "Postulaciones",
        "emoji": POSTULACIONES_EMOJI,
        "descripcion": "Postúlate para formar parte del Staff-Team.",
        "pregunta": "¿Por qué quieres formar parte del Staff-Team?"
    },

    "tienda": {
        "label": "Tienda",
        "emoji": "📯",
        "descripcion": "Problemas relacionados con la tienda.",
        "pregunta": "¿Cuál es tu problema con la tienda?"
    },

    "sanciones": {
        "label": "Sanciones",
        "emoji": "🗂️",
        "descripcion": "Apela una sanción aplicada en el servidor.",
        "pregunta": "¿Por qué motivo quieres apelar tu sanción?"
    }
}


# =========================================================
# MODAL DE TICKET
# =========================================================

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
            required=True,
            max_length=32,
            style=discord.TextStyle.short
        )

        self.motivo = TextInput(
            label=info["pregunta"],
            placeholder="Explica tu situación con claridad",
            required=True,
            max_length=1000,
            style=discord.TextStyle.paragraph
        )

        self.add_item(self.nick)
        self.add_item(self.motivo)

    async def on_submit(self, interaction):

        guild = interaction.guild

        if guild is None:
            return

        categoria_discord = guild.get_channel(
            TICKET_CATEGORY_ID
        )

        if categoria_discord is None:
            await interaction.response.send_message(
                "La categoría de tickets no existe.",
                ephemeral=True
            )
            return

        # Comprobar si ya tiene ticket
        for canal in categoria_discord.channels:

            if canal.name == f"ticket-{interaction.user.id}":

                await interaction.response.send_message(
                    f"Ya tienes un ticket abierto: {canal.mention}",
                    ephemeral=True
                )

                return

        await interaction.response.defer(
            ephemeral=True
        )

        overwrites = {

            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),

            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True
            )
        }

        # Administradores
        for role in guild.roles:

            if role.permissions.administrator:

                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_channels=True
                )

        canal = await guild.create_text_channel(
            name=f"ticket-{interaction.user.id}",
            category=categoria_discord,
            overwrites=overwrites,
            topic=(
                f"Owner:{interaction.user.id}"
                f"|Staff:Sin reclamar"
                f"|Categoria:{self.categoria}"
            )
        )

        info = CATEGORIAS[self.categoria]

        embed = discord.Embed(
            title=f"🎫 Ticket • {info['label']}",
            description=(
                f"Hola {interaction.user.mention}.\n\n"
                "Un miembro del Staff-Team atenderá tu ticket "
                "lo antes posible.\n\n"
                "**Información proporcionada**"
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
            f"Tu ticket ha sido creado: {canal.mention}",
            ephemeral=True
        )


# =========================================================
# SELECT DE TICKETS
# =========================================================

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
            options=opciones
        )

    async def callback(self, interaction):

        categoria = self.values[0]

        await interaction.response.send_modal(
            TicketModal(categoria)
        )


class TicketPanelView(View):

    def __init__(self):

        super().__init__(timeout=None)

        self.add_item(
            TicketSelect()
        )


# =========================================================
# RECLAMAR TICKET
# =========================================================

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
                "Solo el Staff con permisos de administrador puede reclamar tickets.",
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
                f"Este ticket ya fue reclamado por <@{staff_actual}>.",
                ephemeral=True
            )

            return

        topic = interaction.channel.topic or ""

        topic = re.sub(
            r"Staff:[^|]+",
            f"Staff:{interaction.user.id}",
            topic
        )

        await interaction.channel.edit(
            topic=topic
        )

        sumar_puntos(
            interaction.user.id,
            3,
            "claim"
        )

        await interaction.response.send_message(
            f"{interaction.user.mention} ha reclamado este ticket.\n"
            "**+3 puntos**",
        )

        await actualizar_top_staff()


# =========================================================
# CERRAR TICKET
# =========================================================

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
                "Solo el Staff con permisos de administrador puede cerrar tickets.",
                ephemeral=True
            )

            return

        await interaction.response.defer()

        canal = interaction.channel

        datos = obtener_datos_ticket(
            canal
        )

        owner_id = datos.get("owner")
        staff_id = datos.get("staff")

        if not owner_id:

            await interaction.followup.send(
                "No se pudo encontrar al propietario del ticket."
            )

            return

        # -------------------------------------------------
        # TRANSCRIPT
        # -------------------------------------------------

        transcript_text, mensajes = await crear_transcript(
            canal
        )

        # -------------------------------------------------
        # ENVIAR TRANSCRIPT
        # -------------------------------------------------

        transcript_channel = canal.guild.get_channel(
            TRANSCRIPTS_CHANNEL_ID
        )

        if transcript_channel:

            archivo = discord.File(
                fp=__import__("io").BytesIO(
                    transcript_text.encode("utf-8")
                ),
                filename=f"{canal.name}.txt"
            )

            await transcript_channel.send(
                content=(
                    f"Transcript de **{canal.name}**\n"
                    f"Ticket cerrado por {interaction.user.mention}"
                ),
                file=archivo
            )

        # -------------------------------------------------
        # IA PROPIA
        # -------------------------------------------------

        ai_score = None
        ai_reason = "No se pudo realizar la evaluación."

        if staff_id and staff_id != "Sin reclamar":

            try:

                staff_id_int = int(staff_id)

                resultado_ia = evaluar_ticket_local(
                    mensajes,
                    staff_id_int
                )

                ai_score = resultado_ia["score"]
                ai_reason = resultado_ia["reason"]

                sumar_puntos(
                    staff_id_int,
                    ai_score,
                    "ai"
                )

                cursor.execute("""
                    INSERT INTO ai_reviews
                    (staff_id, ticket, score, reason, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    staff_id_int,
                    canal.name,
                    ai_score,
                    ai_reason,
                    datetime.now(timezone.utc).isoformat()
                ))

                db.commit()

            except Exception as e:

                print(
                    "Error en IA propia:",
                    e
                )

        # -------------------------------------------------
        # EMBED DE VALORACIÓN
        # -------------------------------------------------

        try:

            owner = await bot.fetch_user(
                int(owner_id)
            )

            rating_embed = discord.Embed(
                title="⭐ Valora la atención recibida",
                description=(
                    f"Tu ticket **{canal.name}** ha sido cerrado.\n\n"
                    "Puedes valorar la atención del Staff-Team "
                    "del **1 al 5**.\n\n"
                    "Tu valoración influirá en el ranking."
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
                "No se pudo enviar la valoración:",
                e
            )

        # -------------------------------------------------
        # VALORACIÓN EN CANAL
        # -------------------------------------------------

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
                    name="Puntuación IA",
                    value=f"**{ai_score or 0}/10**",
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
                        "El ticket no fue reclamado por ningún miembro "
                        "del Staff-Team."
                    ),
                    inline=False
                )

            embed.set_footer(
                text="InfernMC • IA automática"
            )

            await valoraciones.send(
                embed=embed
            )

        await actualizar_top_staff()

        # -------------------------------------------------
        # BORRAR TICKET
        # -------------------------------------------------

        await interaction.followup.send(
            "El ticket será cerrado y eliminado."
        )

        await asyncio.sleep(3)

        await canal.delete(
            reason="Ticket cerrado"
        )


class TicketControlView(View):

    def __init__(self):

        super().__init__(timeout=None)

        self.add_item(
            ClaimButton()
        )

        self.add_item(
            CloseButton()
        )


# =========================================================
# VALORACIONES
# =========================================================

class RatingButton(Button):

    def __init__(
        self,
        stars,
        owner_id,
        staff_id,
        ticket_name
    ):

        colores = {
            1: discord.ButtonStyle.danger,
            2: discord.ButtonStyle.danger,
            3: discord.ButtonStyle.primary,
            4: discord.ButtonStyle.success,
            5: discord.ButtonStyle.success
        }

        super().__init__(
            label=f"{stars} ⭐",
            style=colores[stars],
            custom_id=f"infernmc_rating_{stars}"
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

        # Evitar doble valoración
        cursor.execute("""
            SELECT id
            FROM ratings
            WHERE user_id = ?
            AND ticket = ?
        """, (
            self.owner_id,
            self.ticket_name
        ))

        if cursor.fetchone():

            await interaction.response.send_message(
                "Ya has valorado este ticket.",
                ephemeral=True
            )

            return

        # Guardar valoración
        cursor.execute("""
            INSERT INTO ratings
            (staff_id, user_id, stars, ticket, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            self.staff_id,
            self.owner_id,
            self.stars,
            self.ticket_name,
            datetime.now(timezone.utc).isoformat()
        ))

        db.commit()

        # Dar puntos al staff
        if self.staff_id:

            sumar_puntos(
                self.staff_id,
                self.stars,
                "rating"
            )

        # Canal de valoraciones
        channel = bot.get_channel(
            VALORACIONES_CHANNEL_ID
        )

        if channel:

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
                name="Puntos obtenidos",
                value=f"**+{self.stars}**",
                inline=False
            )

            embed.set_footer(
                text=f"Ticket: {self.ticket_name}"
            )

            await channel.send(
                embed=embed
            )

        await interaction.response.edit_message(
            content=(
                f"Valoración registrada: "
                f"{'⭐' * self.stars}\n\n"
                f"Has dado **+{self.stars} puntos** al Staff."
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

        super().__init__(
            timeout=86400
        )

        for stars in range(1, 6):

            self.add_item(
                RatingButton(
                    stars,
                    owner_id,
                    staff_id,
                    ticket_name
                )
            )


# =========================================================
# BIENVENIDA
# =========================================================

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
            "Esperamos que disfrutes de tu estancia en "
            "**InfernMC**.\n\n"
            "Antes de comenzar, recuerda leer las reglas, "
            "respetar a los demás miembros y utilizar los "
            "tickets si necesitas ayuda."
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
        value=str(member.guild.member_count),
        inline=True
    )

    embed.add_field(
        name="🆔 Cuenta",
        value=str(member.id),
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
    await enviar_bienvenida(member)


# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    revisar_reset_semanal()

    print(
        f"Conectado como {bot.user}"
    )

    print(
        f"ID: {bot.user.id}"
    )

    await actualizar_top_staff()

    # Views persistentes
    bot.add_view(
        TicketPanelView()
    )

    bot.add_view(
        TicketControlView()
    )


# =========================================================
# !TESTBIENVENIDA
# =========================================================

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


# =========================================================
# !TICKETPANEL
# =========================================================

@bot.command()
async def ticketpanel(ctx):

    if not es_admin(ctx.author):

        await ctx.send(
            "No tienes permisos para usar este comando."
        )

        return

    # Borrar mensajes anteriores del bot
    try:

        async for mensaje in ctx.channel.history(
            limit=50
        ):

            if mensaje.author == bot.user:

                try:
                    await mensaje.delete()
                except:
                    pass

    except Exception as e:

        print(
            "Error limpiando panel:",
            e
        )

    embed = discord.Embed(
        title="🎫 ¿Necesitas ayuda?",
        description=(
            "No dudes en abrir un ticket si necesitas ayuda "
            "con cualquier situación relacionada con InfernMC.\n\n"

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

            "Selecciona una categoría en el menú desplegable."
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


# =========================================================
# !TOPSTAFFPANEL
# =========================================================

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
        value="Todavía no hay puntos registrados.",
        inline=False
    )

    embed.set_footer(
        text=f"InfernMC • Semana {semana_actual()}"
    )

    mensaje = await ctx.send(
        embed=embed
    )

    cursor.execute("""
        INSERT OR REPLACE INTO config
        (key, value)
        VALUES ('top_channel', ?)
    """, (
        str(ctx.channel.id),
    ))

    cursor.execute("""
        INSERT OR REPLACE INTO config
        (key, value)
        VALUES ('top_message', ?)
    """, (
        str(mensaje.id),
    ))

    db.commit()

    await ctx.send(
        "Panel de Top Staff configurado."
    )


# =========================================================
# !TOPSTAFF
# =========================================================

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


# =========================================================
# !STAFF
# =========================================================

@bot.command()
async def staff(ctx, miembro: discord.Member = None):

    if miembro is None:
        miembro = ctx.author

    asegurar_staff(
        miembro.id
    )

    cursor.execute("""
        SELECT total_points,
               weekly_points,
               tickets_claimed,
               ratings_received,
               ai_reviews,
               ai_points
        FROM staff
        WHERE user_id = ?
    """, (
        miembro.id,
    ))

    datos = cursor.fetchone()

    if not datos:
        return

    total = datos[0]
    weekly = datos[1]
    tickets = datos[2]
    ratings = datos[3]
    ai_reviews = datos[4]
    ai_points = datos[5]

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
        value=f"**{weekly}**",
        inline=True
    )

    embed.add_field(
        name="Puntos totales",
        value=f"**{total}**",
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
        value=f"**{ai_points}**",
        inline=True
    )

    embed.set_footer(
        text="InfernMC • Estadísticas Staff"
    )

    await ctx.send(
        embed=embed
    )


# =========================================================
# !MENSAJE
# =========================================================

@bot.command()
async def mensaje(ctx, canal: discord.TextChannel, *, texto):

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


# =========================================================
# ERRORES
# =========================================================

@bot.event
async def on_command_error(ctx, error):

    if isinstance(
        error,
        commands.MissingPermissions
    ):
        return

    if isinstance(
        error,
        commands.CommandNotFound
    ):
        return

    print(
        f"Error en comando {ctx.command}:",
        error
    )


# =========================================================
# INICIAR
# =========================================================

if not TOKEN:

    raise RuntimeError(
        "Falta DISCORD_TOKEN en las variables de Railway."
    )


bot.run(TOKEN)
