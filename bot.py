import os
import discord
from discord.ext import commands

# =========================
# INTENTS
# =========================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# =========================
# CONFIGURACIÓN
# =========================

WELCOME_CHANNEL_ID = 1548521317295198258
TICKET_CATEGORY_ID = 1548528404649873438

POSTULACIONES_EMOJI = discord.PartialEmoji(
    name="573567deadhamster",
    id=1549076149399715840
)


# =========================
# BOT LISTO
# =========================

@bot.event
async def on_ready():
    print(f"InfernMc conectado como {bot.user}")

    bot.add_view(TicketPanelView())
    bot.add_view(TicketControlView())


# =========================
# BIENVENIDAS
# =========================

@bot.event
async def on_member_join(member):

    channel = bot.get_channel(WELCOME_CHANNEL_ID)

    if channel:
        await channel.send(
            f"¡Bienvenido/a al servidor, {member.mention}! 🎉"
        )


# =========================
# PRUEBA DE BIENVENIDA
# =========================

@bot.command()
@commands.has_permissions(administrator=True)
async def testbienvenida(ctx):

    channel = bot.get_channel(WELCOME_CHANNEL_ID)

    if channel is None:
        await ctx.send(
            "No se encontró el canal de bienvenidas."
        )
        return

    await channel.send(
        f"¡Bienvenido/a al servidor, {ctx.author.mention}! 🎉"
    )

    await ctx.send(
        f"Bienvenida de prueba enviada en {channel.mention}."
    )


# =========================
# MENÚ DE TICKETS
# =========================

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
                description="Postulaciones al Staff-Team de InfernMC.",
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

    async def callback(self, interaction: discord.Interaction):

        guild = interaction.guild
        member = interaction.user

        category = guild.get_channel(TICKET_CATEGORY_ID)

        if category is None:
            await interaction.response.send_message(
                "La categoría de tickets no está configurada.",
                ephemeral=True
            )
            return

        # =========================
        # COMPROBAR TICKET EXISTENTE
        # =========================

        for channel in category.channels:

            if channel.name == f"ticket-{member.id}":

                await interaction.response.send_message(
                    f"Ya tienes un ticket abierto: {channel.mention}",
                    ephemeral=True
                )

                return

        # =========================
        # INFORMACIÓN DE CATEGORÍAS
        # =========================

        categorias = {

            "ayuda_general": {
                "nombre": "🎲 Ayuda General",
                "descripcion": (
                    "¿Necesitas ayuda en algo en general? "
                    "Esta categoría sirve para los usuarios "
                    "que tengan este tipo de dudas, ya sea en "
                    "Discord o en Minecraft."
                )
            },

            "bugs": {
                "nombre": "🎗️ Bugs",
                "descripcion": (
                    "¿Has encontrado un bug en nuestro servidor "
                    "o ya sea en el Discord del servidor? "
                    "Abre ticket en nuestra categoría específica."
                )
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
                )
            },

            "tienda": {
                "nombre": "📯 Tienda",
                "descripcion": (
                    "Si tienes una duda o problema con la tienda "
                    "del servidor, en esta categoría se resuelve "
                    "todo lo que implica acerca de la tienda."
                )
            },

            "sanciones": {
                "nombre": "🗂️ Sanciones",
                "descripcion": (
                    "Has sido sancionado en el servidor de InfernMC "
                    "o tienes alguna duda sobre tu sanción y quieres "
                    "protestar en contra de esta."
                )
            }

        }

        datos = categorias[self.values[0]]

        # =========================
        # PERMISOS DEL TICKET
        # =========================

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

        # Dar acceso a administradores

        for role in guild.roles:

            if role.permissions.administrator:

                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )

        # =========================
        # CREAR CANAL
        # =========================

        channel = await guild.create_text_channel(
            f"ticket-{member.id}",
            category=category,
            overwrites=overwrites
        )

        # =========================
        # MENSAJE DEL TICKET
        # =========================

        embed = discord.Embed(
            title=datos["nombre"],
            description=(
                f"{datos['descripcion']}\n\n"
                "Un miembro del staff te atenderá lo antes posible.\n\n"
                "**Recuerda:**\n"
                "• No abras demasiados tickets simultáneamente.\n"
                "• No insultes al staff.\n"
                "• Sé claro y directo a la hora de hacer un ticket."
            ),
            color=discord.Color.blurple()
        )

        await channel.send(
            content=member.mention,
            embed=embed,
            view=TicketControlView()
        )

        await interaction.response.send_message(
            f"Ticket creado: {channel.mention}",
            ephemeral=True
        )


# =========================
# PANEL DE TICKETS
# =========================

class TicketPanelView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

        self.add_item(TicketSelect())


# =========================
# CONTROL DE TICKETS
# =========================

class TicketControlView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

    # =========================
    # RECLAMAR
    # =========================

    @discord.ui.button(
        label="Reclamar",
        style=discord.ButtonStyle.blurple,
        custom_id="infernmc_claim_ticket"
    )
    async def claim_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not interaction.user.guild_permissions.administrator:

            await interaction.response.send_message(
                "Solo el staff puede reclamar tickets.",
                ephemeral=True
            )

            return

        await interaction.response.send_message(
            f"Ticket reclamado por {interaction.user.mention}."
        )

    # =========================
    # CERRAR
    # =========================

    @discord.ui.button(
        label="Cerrar",
        style=discord.ButtonStyle.red,
        custom_id="infernmc_close_ticket"
    )
    async def close_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not interaction.user.guild_permissions.administrator:

            await interaction.response.send_message(
                "Solo el staff puede cerrar tickets.",
                ephemeral=True
            )

            return

        await interaction.response.send_message(
            "Cerrando ticket..."
        )

        await interaction.channel.delete()


# =========================
# COMANDO DEL PANEL
# =========================

@bot.command()
@commands.has_permissions(administrator=True)
async def ticketpanel(ctx):

    # =========================
    # BORRAR PANELES ANTERIORES
    # =========================

    async for message in ctx.channel.history(limit=50):

        if message.author == bot.user:

            try:
                await message.delete()
            except:
                pass

    # =========================
    # CREAR EMBED
    # =========================

    embed = discord.Embed(
        title="¿Necesitas ayuda?",
        description=(
            "No dudes en abrir ticket para una atención mediante "
            "el staff del servidor.\n\n"

            "**Ten en cuenta que:**\n"
            "• No abras demasiados tickets simultáneamente.\n"
            "• No insultes al staff, podrías ser sancionado si lo haces.\n"
            "• Recuerda ser claro y directo a la hora de hacer un ticket.\n\n"

            "Los tickets se dividen en diferentes categorías, "
            "las cuales incluyen el 50% de las situaciones que "
            "pueden pasar en el servidor."
        ),
        color=discord.Color.blurple()
    )

    # =========================
    # AYUDA GENERAL
    # =========================

    embed.add_field(
        name="🎲 Ayuda General",
        value=(
            "¿Necesitas ayuda en algo en general? "
            "Esta categoría sirve para los usuarios que "
            "tengan este tipo de dudas, ya sea en Discord "
            "o en Minecraft."
        ),
        inline=False
    )

    # =========================
    # BUGS
    # =========================

    embed.add_field(
        name="🎗️ Bugs",
        value=(
            "¿Has encontrado un bug en nuestro servidor "
            "o ya sea en el Discord del servidor? "
            "Abre ticket en nuestra categoría específica."
        ),
        inline=False
    )

    # =========================
    # POSTULACIONES
    # =========================

    embed.add_field(
        name="<:573567deadhamster:1549076149399715840> Postulaciones",
        value=(
            "¿Has sido aceptado en el staff-team de InfernMC? "
            "Si estás abriendo en esta categoría, enhorabuena, "
            "felicidades por pasar la primera fase del staff-team."
        ),
        inline=False
    )

    # =========================
    # TIENDA
    # =========================

    embed.add_field(
        name="📯 Tienda",
        value=(
            "Si tienes una duda o problema con la tienda "
            "del servidor, en esta categoría se resuelve "
            "todo lo que implica acerca de la tienda."
        ),
        inline=False
    )

    # =========================
    # SANCIONES
    # =========================

    embed.add_field(
        name="🗂️ Sanciones",
        value=(
            "Has sido sancionado en el servidor de InfernMC "
            "o tienes alguna duda sobre tu sanción y quieres "
            "protestar en contra de esta."
        ),
        inline=False
    )

    # =========================
    # FOOTER
    # =========================

    embed.set_footer(
        text="Selecciona una categoría en el menú desplegable."
    )

    # =========================
    # ENVIAR PANEL
    # =========================

    await ctx.send(
        embed=embed,
        view=TicketPanelView()
    )


# =========================
# INICIAR BOT
# =========================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("Falta DISCORD_TOKEN")

bot.run(TOKEN)
