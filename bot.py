import os
import io
import asyncio
import discord
from discord.ext import commands


# =========================================================
# INTENTS
# =========================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# CONFIGURACIÓN
# =========================================================

WELCOME_CHANNEL_ID = 1548521317295198258
TICKET_CATEGORY_ID = 1548528404649873438

VALORACIONES_CHANNEL_ID = 1550534072449900684
TRANSCRIPTS_CHANNEL_ID = 1548694373875585125

POSTULACIONES_EMOJI = discord.PartialEmoji(
    name="573567deadhamster",
    id=1549076149399715840
)


# =========================================================
# CATEGORÍAS DE TICKETS
# =========================================================

CATEGORIAS = {

    "ayuda_general": {
        "nombre": "🎲 Ayuda General",
        "descripcion": (
            "¿Necesitas ayuda en algo en general? "
            "Esta categoría sirve para los usuarios que "
            "tengan este tipo de dudas, ya sea en Discord "
            "o en Minecraft."
        ),
        "pregunta": "¿En qué necesitas ayuda?"
    },

    "bugs": {
        "nombre": "🎗️ Bugs",
        "descripcion": (
            "¿Has encontrado un bug en nuestro servidor "
            "o ya sea en el Discord del servidor? "
            "Abre ticket en nuestra categoría específica."
        ),
        "pregunta": "¿Qué bug encontraste?"
    },

    "postulaciones": {
        "nombre": (
            "<:573567deadhamster:1549076149399715840> "
            "Postulaciones"
        ),
        "descripcion": (
            "¿Has sido aceptado en el staff-team de InfernMC? "
            "Si estás abriendo en esta categoría, enhorabuena, "
            "felicidades por pasar la primera fase del staff-team."
        ),
        "pregunta": "¿Por qué quieres formar parte del Staff-Team?"
    },

    "tienda": {
        "nombre": "📯 Tienda",
        "descripcion": (
            "Si tienes una duda o problema con la tienda "
            "del servidor, en esta categoría se resuelve "
            "todo lo que implica acerca de la tienda."
        ),
        "pregunta": "¿Cuál es tu problema con la tienda?"
    },

    "sanciones": {
        "nombre": "🗂️ Sanciones",
        "descripcion": (
            "Has sido sancionado en el servidor de InfernMC "
            "o tienes alguna duda sobre tu sanción y quieres "
            "protestar en contra de esta."
        ),
        "pregunta": "¿Por qué motivo quieres apelar tu sanción?"
    }

}


# =========================================================
# FUNCIÓN DE BIENVENIDA
# =========================================================

def crear_embed_bienvenida(member):

    embed = discord.Embed(
        title="¡Bienvenido/a a InfernMC!",
        description=(
            f"¡Bienvenido/a {member.mention}!\n\n"
            "Esperamos que disfrutes tu estancia en el servidor.\n"
            "No olvides leer las normas y disfrutar de InfernMC."
        ),
        color=discord.Color.blurple()
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

    embed.set_footer(
        text="InfernMC • Sistema de bienvenidas"
    )

    return embed


# =========================================================
# BOT LISTO
# =========================================================

@bot.event
async def on_ready():

    print(f"InfernMC conectado como {bot.user}")

    bot.add_view(
        TicketPanelView()
    )

    bot.add_view(
        TicketControlView()
    )


# =========================================================
# BIENVENIDA
# =========================================================

@bot.event
async def on_member_join(member):

    channel = bot.get_channel(
        WELCOME_CHANNEL_ID
    )

    if channel is None:
        return

    embed = crear_embed_bienvenida(
        member
    )

    await channel.send(
        embed=embed
    )


# =========================================================
# TEST DE BIENVENIDA
# =========================================================

@bot.command()
@commands.has_permissions(administrator=True)
async def testbienvenida(ctx):

    channel = bot.get_channel(
        WELCOME_CHANNEL_ID
    )

    if channel is None:

        await ctx.send(
            "No se encontró el canal de bienvenidas."
        )

        return

    embed = crear_embed_bienvenida(
        ctx.author
    )

    await channel.send(
        embed=embed
    )

    await ctx.send(
        f"Bienvenida de prueba enviada en {channel.mention}."
    )


# =========================================================
# MODAL DE TICKETS
# =========================================================

class TicketModal(discord.ui.Modal):

    def __init__(self, categoria):

        self.categoria = categoria

        datos = CATEGORIAS[categoria]

        super().__init__(
            title=f"Abrir ticket • {datos['nombre']}"
        )

        # -------------------------------------------------
        # NICK
        # -------------------------------------------------

        self.nick = discord.ui.TextInput(
            label="¿Nick?",
            placeholder="Escribe tu nick de Minecraft...",
            required=True,
            min_length=1,
            max_length=32
        )

        self.add_item(
            self.nick
        )

        # -------------------------------------------------
        # PREGUNTA ESPECÍFICA
        # -------------------------------------------------

        self.problema = discord.ui.TextInput(
            label=datos["pregunta"],
            placeholder="Escribe tu respuesta...",
            style=discord.TextStyle.paragraph,
            required=True,
            min_length=1,
            max_length=1000
        )

        self.add_item(
            self.problema
        )


    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        guild = interaction.guild
        member = interaction.user

        category = guild.get_channel(
            TICKET_CATEGORY_ID
        )

        if category is None:

            await interaction.response.send_message(
                "La categoría de tickets no está configurada.",
                ephemeral=True
            )

            return

        # -------------------------------------------------
        # COMPROBAR SI YA TIENE TICKET
        # -------------------------------------------------

        for channel in category.channels:

            if channel.name == f"ticket-{member.id}":

                await interaction.response.send_message(
                    f"Ya tienes un ticket abierto: {channel.mention}",
                    ephemeral=True
                )

                return

        nick = self.nick.value
        respuesta = self.problema.value

        datos = CATEGORIAS[
            self.categoria
        ]

        # -------------------------------------------------
        # PERMISOS
        # -------------------------------------------------

        overwrites = {

            guild.default_role:
                discord.PermissionOverwrite(
                    view_channel=False
                ),

            member:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )
        }

        # Administradores

        for role in guild.roles:

            if role.permissions.administrator:

                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )

        # -------------------------------------------------
        # CREAR CANAL
        # -------------------------------------------------

        channel = await guild.create_text_channel(
            f"ticket-{member.id}",
            category=category,
            overwrites=overwrites
        )

        # -------------------------------------------------
        # TOPIC
        # -------------------------------------------------

        await channel.edit(
            topic=(
                f"Owner:{member.id}|"
                f"Staff:Sin reclamar|"
                f"Categoria:{self.categoria}"
            )
        )

        # -------------------------------------------------
        # EMBED DEL TICKET
        # -------------------------------------------------

        embed = discord.Embed(
            title=datos["nombre"],
            description=(
                f"Bienvenido/a {member.mention}.\n\n"
                "Tu ticket ha sido creado correctamente.\n\n"
                "Un miembro del staff te atenderá lo antes posible."
            ),
            color=discord.Color.blurple()
        )

        embed.add_field(
            name="¿Nick?",
            value=nick,
            inline=False
        )

        embed.add_field(
            name=datos["pregunta"],
            value=respuesta,
            inline=False
        )

        embed.add_field(
            name="Categoría",
            value=datos["nombre"],
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

        await channel.send(
            content=member.mention,
            embed=embed,
            view=TicketControlView()
        )

        await interaction.response.send_message(
            f"Ticket creado correctamente: {channel.mention}",
            ephemeral=True
        )


# =========================================================
# SELECTOR DE CATEGORÍAS
# =========================================================

class TicketSelect(discord.ui.Select):

    def __init__(self):

        options = [

            discord.SelectOption(
                label="Ayuda General",
                description="Dudas sobre Discord o Minecraft.",
                emoji="🎲",
                value="ayuda_general"
            ),

            discord.SelectOption(
                label="Bugs",
                description="Reporta un bug del servidor o Discord.",
                emoji="🎗️",
                value="bugs"
            ),

            discord.SelectOption(
                label="Postulaciones",
                description="Postulaciones al Staff-Team.",
                emoji=POSTULACIONES_EMOJI,
                value="postulaciones"
            ),

            discord.SelectOption(
                label="Tienda",
                description="Dudas o problemas con la tienda.",
                emoji="📯",
                value="tienda"
            ),

            discord.SelectOption(
                label="Sanciones",
                description="Dudas o protestas sobre una sanción.",
                emoji="🗂️",
                value="sanciones"
            )

        ]

        super().__init__(
            placeholder="Selecciona una categoría...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="infernmc_ticket_category"
        )


    async def callback(
        self,
        interaction: discord.Interaction
    ):

        categoria = self.values[0]

        await interaction.response.send_modal(
            TicketModal(categoria)
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
# VALORACIONES
# =========================================================

class RatingView(discord.ui.View):

    def __init__(
        self,
        ticket_user_id,
        ticket_name,
        staff_name
    ):

        super().__init__(
            timeout=86400
        )

        self.ticket_user_id = ticket_user_id
        self.ticket_name = ticket_name
        self.staff_name = staff_name


    async def send_rating(
        self,
        interaction,
        stars
    ):

        if interaction.user.id != self.ticket_user_id:

            await interaction.response.send_message(
                "Solo el usuario que abrió el ticket puede valorarlo.",
                ephemeral=True
            )

            return

        channel = bot.get_channel(
            VALORACIONES_CHANNEL_ID
        )

        if channel is None:

            await interaction.response.send_message(
                "No se encontró el canal de valoraciones.",
                ephemeral=True
            )

            return

        estrellas = "⭐" * stars

        embed = discord.Embed(
            title="Nueva valoración",
            color=discord.Color.gold()
        )

        embed.add_field(
            name="Usuario",
            value=interaction.user.mention,
            inline=True
        )

        embed.add_field(
            name="Valoración",
            value=f"{estrellas} ({stars}/5)",
            inline=True
        )

        embed.add_field(
            name="Ticket",
            value=self.ticket_name,
            inline=False
        )

        embed.add_field(
            name="Staff",
            value=self.staff_name,
            inline=False
        )

        embed.set_footer(
            text="InfernMC • Sistema de valoraciones"
        )

        await channel.send(
            embed=embed
        )

        await interaction.response.edit_message(
            content="Gracias por valorar la atención recibida.",
            embed=None,
            view=None
        )


    @discord.ui.button(
        label="⭐ 1",
        style=discord.ButtonStyle.red,
        custom_id="infernmc_rating_1"
    )
    async def rating_1(
        self,
        interaction,
        button
    ):

        await self.send_rating(
            interaction,
            1
        )


    @discord.ui.button(
        label="⭐ 2",
        style=discord.ButtonStyle.red,
        custom_id="infernmc_rating_2"
    )
    async def rating_2(
        self,
        interaction,
        button
    ):

        await self.send_rating(
            interaction,
            2
        )


    @discord.ui.button(
        label="⭐ 3",
        style=discord.ButtonStyle.blurple,
        custom_id="infernmc_rating_3"
    )
    async def rating_3(
        self,
        interaction,
        button
    ):

        await self.send_rating(
            interaction,
            3
        )


    @discord.ui.button(
        label="⭐ 4",
        style=discord.ButtonStyle.green,
        custom_id="infernmc_rating_4"
    )
    async def rating_4(
        self,
        interaction,
        button
    ):

        await self.send_rating(
            interaction,
            4
        )


    @discord.ui.button(
        label="⭐ 5",
        style=discord.ButtonStyle.green,
        custom_id="infernmc_rating_5"
    )
    async def rating_5(
        self,
        interaction,
        button
    ):

        await self.send_rating(
            interaction,
            5
        )


# =========================================================
# TRANSCRIPT
# =========================================================

async def crear_transcript(channel):

    mensajes = []

    async for message in channel.history(
        limit=None,
        oldest_first=True
    ):

        fecha = message.created_at.strftime(
            "%d/%m/%Y %H:%M:%S"
        )

        contenido = message.content

        if not contenido:
            contenido = "[Sin contenido de texto]"

        mensajes.append(
            f"[{fecha}] "
            f"{message.author} "
            f"({message.author.id}):\n"
            f"{contenido}\n"
        )

        if message.attachments:

            for attachment in message.attachments:

                mensajes.append(
                    f"Archivo adjunto: {attachment.url}\n"
                )

        mensajes.append(
            "-" * 70
        )

    texto = (
        f"TRANSCRIPT - {channel.name}\n"
        f"ID DEL CANAL: {channel.id}\n"
        f"FECHA: "
        f"{discord.utils.utcnow().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
        + "\n".join(mensajes)
    )

    return texto


# =========================================================
# BOTONES DEL TICKET
# =========================================================

class TicketControlView(discord.ui.View):

    def __init__(self):

        super().__init__(
            timeout=None
        )


    # =====================================================
    # RECLAMAR
    # =====================================================

    @discord.ui.button(
        label="Reclamar",
        style=discord.ButtonStyle.blurple,
        custom_id="infernmc_claim_ticket"
    )
    async def claim_ticket(
        self,
        interaction,
        button
    ):

        if not interaction.user.guild_permissions.administrator:

            await interaction.response.send_message(
                "Solo el staff puede reclamar tickets.",
                ephemeral=True
            )

            return

        channel = interaction.channel
        topic = channel.topic or ""

        if (
            "Staff:" in topic
            and "Staff:Sin reclamar" not in topic
        ):

            await interaction.response.send_message(
                "Este ticket ya fue reclamado.",
                ephemeral=True
            )

            return

        owner_id = "Desconocido"

        if "Owner:" in topic:

            try:

                owner_id = (
                    topic
                    .split("Owner:")[1]
                    .split("|")[0]
                )

            except:
                pass

        categoria = "desconocida"

        if "Categoria:" in topic:

            categoria = topic.split(
                "Categoria:"
            )[-1]

        await channel.edit(
            topic=(
                f"Owner:{owner_id}|"
                f"Staff:{interaction.user.id}|"
                f"Categoria:{categoria}"
            )
        )

        await interaction.response.send_message(
            f"Ticket reclamado por {interaction.user.mention}."
        )


    # =====================================================
    # CERRAR
    # =====================================================

    @discord.ui.button(
        label="Cerrar",
        style=discord.ButtonStyle.red,
        custom_id="infernmc_close_ticket"
    )
    async def close_ticket(
        self,
        interaction,
        button
    ):

        if not interaction.user.guild_permissions.administrator:

            await interaction.response.send_message(
                "Solo el staff puede cerrar tickets.",
                ephemeral=True
            )

            return

        channel = interaction.channel
        topic = channel.topic or ""

        owner_id = None
        staff_id = None

        # -------------------------------------------------
        # OWNER
        # -------------------------------------------------

        if "Owner:" in topic:

            try:

                owner_id = int(
                    topic
                    .split("Owner:")[1]
                    .split("|")[0]
                )

            except:
                pass

        # -------------------------------------------------
        # STAFF
        # -------------------------------------------------

        if "Staff:" in topic:

            try:

                staff_text = (
                    topic
                    .split("Staff:")[1]
                    .split("|")[0]
                )

                if staff_text != "Sin reclamar":

                    staff_id = int(
                        staff_text
                    )

            except:
                pass

        await interaction.response.send_message(
            "Generando transcript y cerrando ticket..."
        )

        # -------------------------------------------------
        # TRANSCRIPT
        # -------------------------------------------------

        transcript = await crear_transcript(
            channel
        )

        transcript_channel = bot.get_channel(
            TRANSCRIPTS_CHANNEL_ID
        )

        if transcript_channel:

            archivo = discord.File(
                io.BytesIO(
                    transcript.encode("utf-8")
                ),
                filename=f"{channel.name}.txt"
            )

            transcript_embed = discord.Embed(
                title="Transcript de ticket",
                color=discord.Color.red()
            )

            transcript_embed.add_field(
                name="Ticket",
                value=channel.name,
                inline=True
            )

            transcript_embed.add_field(
                name="Cerrado por",
                value=interaction.user.mention,
                inline=True
            )

            if owner_id:

                transcript_embed.add_field(
                    name="Usuario",
                    value=f"<@{owner_id}>",
                    inline=True
                )

            if staff_id:

                transcript_embed.add_field(
                    name="Staff",
                    value=f"<@{staff_id}>",
                    inline=True
                )

            else:

                transcript_embed.add_field(
                    name="Staff",
                    value="Sin reclamar",
                    inline=True
                )

            await transcript_channel.send(
                embed=transcript_embed,
                file=archivo
            )

        # -------------------------------------------------
        # VALORACIÓN
        # -------------------------------------------------

        if owner_id:

            try:

                user = await bot.fetch_user(
                    owner_id
                )

                if staff_id:

                    staff_user = await bot.fetch_user(
                        staff_id
                    )

                    staff_name = (
                        f"{staff_user} "
                        f"(<@{staff_id}>)"
                    )

                else:

                    staff_name = "Sin reclamar"

                rating_embed = discord.Embed(
                    title="Valora la atención recibida",
                    description=(
                        "Tu ticket ha sido cerrado.\n\n"
                        "¿Qué valoración le das a la atención "
                        "recibida por nuestro staff?"
                    ),
                    color=discord.Color.gold()
                )

                rating_embed.set_footer(
                    text="InfernMC • Valoraciones"
                )

                await user.send(
                    embed=rating_embed,
                    view=RatingView(
                        owner_id,
                        channel.name,
                        staff_name
                    )
                )

            except discord.Forbidden:
                pass

            except Exception as error:

                print(
                    f"Error enviando valoración: {error}"
                )

        # -------------------------------------------------
        # ELIMINAR
        # -------------------------------------------------

        await asyncio.sleep(3)

        await channel.delete()


# =========================================================
# COMANDO PARA CREAR PANEL
# =========================================================

@bot.command()
@commands.has_permissions(administrator=True)
async def ticketpanel(ctx):

    # -----------------------------------------------------
    # BORRAR MENSAJES ANTERIORES DEL BOT
    # -----------------------------------------------------

    async for message in ctx.channel.history(
        limit=50
    ):

        if message.author == bot.user:

            try:
                await message.delete()
            except:
                pass

    # -----------------------------------------------------
    # EMBED
    # -----------------------------------------------------

    embed = discord.Embed(
        title="¿Necesitas ayuda?",
        description=(

            "No dudes en abrir ticket para una atención mediante "
            "el staff del servidor.\n\n"

            "## Ten en cuenta que\n"

            "• No abras demasiados tickets simultáneamente.\n"
            "• No insultes al staff, podrías ser sancionado si lo haces.\n"
            "• Recuerda ser claro y directo a la hora de hacer un ticket.\n\n"

            "Los tickets se dividen en diferentes categorías, "
            "las cuales incluyen el 50% de las situaciones que "
            "pueden pasar en el servidor.\n\n"

            "# 🎲 Ayuda General\n"

            "¿Necesitas ayuda en algo en general? Esta categoría "
            "sirve para los usuarios que tengan este tipo de dudas, "
            "ya sea en Discord o en Minecraft.\n\n"

            "# 🎗️ Bugs\n"

            "¿Has encontrado un bug en nuestro servidor o ya sea "
            "en el Discord del servidor? Abre ticket en nuestra "
            "categoría específica.\n\n"

            "# <:573567deadhamster:1549076149399715840> Postulaciones\n"

            "¿Has sido aceptado en el staff-team de InfernMC? "
            "Si estás abriendo en esta categoría, enhorabuena, "
            "felicidades por pasar la primera fase del staff-team.\n\n"

            "# 📯 Tienda\n"

            "Si tienes una duda o problema con la tienda del servidor, "
            "en esta categoría se resuelve todo lo que implica acerca "
            "de la tienda.\n\n"

            "# 🗂️ Sanciones\n"

            "Has sido sancionado en el servidor de InfernMC o tienes "
            "alguna duda sobre tu sanción y quieres protestar en contra "
            "de esta."
        ),
        color=discord.Color.blurple()
    )

    embed.set_footer(
        text="Selecciona una categoría en el menú desplegable."
    )

    await ctx.send(
        embed=embed,
        view=TicketPanelView()
    )


# =========================================================
# TOKEN
# =========================================================

TOKEN = os.getenv(
    "DISCORD_TOKEN"
)

if not TOKEN:

    raise RuntimeError(
        "Falta DISCORD_TOKEN"
    )

bot.run(TOKEN)
