import os
import discord
from discord.ext import commands

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
# MENÚ DE CATEGORÍAS
# =========================

class TicketSelect(discord.ui.Select):

    def __init__(self):

        options = [

            discord.SelectOption(
                label="Ayuda General",
                description="Dudas generales sobre Discord o Minecraft.",
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
                description="Postulaciones para el Staff-Team de InfernMC.",
                emoji="📋",
                value="postulaciones"
            ),

            discord.SelectOption(
                label="Tienda",
                description="Dudas o problemas con la tienda del servidor.",
                emoji="📯",
                value="tienda"
            ),

            discord.SelectOption(
                label="Sanciones",
                description="Dudas o protestas relacionadas con sanciones.",
                emoji="🗂️",
                value="sanciones"
            )

        ]

        super().__init__(
            placeholder="Selecciona una categoría...",
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

        # Comprobar si ya tiene un ticket

        for channel in category.channels:

            if channel.name == f"ticket-{member.id}":

                await interaction.response.send_message(
                    f"Ya tienes un ticket abierto: {channel.mention}",
                    ephemeral=True
                )

                return

        # Datos de la categoría

        categorias = {

            "ayuda_general": {
                "nombre": "Ayuda General",
                "emoji": "🎲",
                "descripcion":
                    "¿Necesitas ayuda en algo en general? "
                    "Esta categoría sirve para dudas relacionadas "
                    "con Discord o Minecraft."
            },

            "bugs": {
                "nombre": "Bugs",
                "emoji": "🎗️",
                "descripcion":
                    "¿Has encontrado un bug en nuestro servidor "
                    "o en el Discord? Abre ticket en esta categoría."
            },

            "postulaciones": {
                "nombre": "Postulaciones",
                "emoji": "📋",
                "descripcion":
                    "¿Has sido aceptado en el Staff-Team de InfernMC? "
                    "Enhorabuena por pasar la primera fase."
            },

            "tienda": {
                "nombre": "Tienda",
                "emoji": "📯",
                "descripcion":
                    "Si tienes una duda o problema con la tienda "
                    "del servidor, aquí se resolverá todo lo relacionado "
                    "con ella."
            },

            "sanciones": {
                "nombre": "Sanciones",
                "emoji": "🗂️",
                "descripcion":
                    "¿Has sido sancionado en el servidor de InfernMC "
                    "o tienes alguna duda sobre tu sanción y quieres "
                    "protestar contra ella?"
            }

        }

        datos = categorias[self.values[0]]

        # Permisos

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

        # Crear canal

        channel = await guild.create_text_channel(
            f"ticket-{member.id}",
            category=category,
            overwrites=overwrites
        )

        # Mensaje del ticket

        await channel.send(

            f"{member.mention}\n\n"

            f"{datos['emoji']} **{datos['nombre']}**\n\n"

            f"{datos['descripcion']}\n\n"

            "Un miembro del staff te atenderá lo antes posible.\n\n"

            "**Recuerda:**\n"
            "• Sé claro y directo.\n"
            "• No insultes al staff.\n"
            "• No abras demasiados tickets simultáneamente.",

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
# CONTROL DEL TICKET
# =========================

class TicketControlView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

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

    await ctx.send(

        "# ¿Necesitas ayuda?\n\n"

        "No dudes en abrir ticket para una atención mediante "
        "el staff del servidor.\n\n"

        "**Ten en cuenta:**\n"
        "• No abras demasiados tickets simultáneamente.\n"
        "• No insultes al staff, podrías ser sancionado.\n"
        "• Recuerda ser claro y directo a la hora de hacer un ticket.\n\n"

        "Los tickets se dividen en diferentes categorías, "
        "las cuales incluyen diferentes situaciones que pueden "
        "pasar en el servidor.\n\n"

        "Selecciona una categoría en el menú desplegable:",

        view=TicketPanelView()
    )


# =========================
# INICIAR BOT
# =========================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("Falta DISCORD_TOKEN")

bot.run(TOKEN)
