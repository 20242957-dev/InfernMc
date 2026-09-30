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

    # Registrar las vistas para que los botones sigan funcionando
    # después de reiniciar el bot.
    bot.add_view(TicketView())
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
                value="ayuda"
            ),

            discord.SelectOption(
                label="Bugs",
                description="Reporta un bug del servidor o Discord.",
                emoji="🎗️",
                value="bugs"
            ),

            discord.SelectOption(
                label="Postulaciones",
                description="Postulaciones relacionadas con el Staff-Team.",
                emoji="📋",
                value="postulaciones"
            ),

            discord.SelectOption(
                label="Tienda",
                description="Dudas o problemas relacionados con la tienda.",
                emoji="📯",
                value="tienda"
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

        # Obtener categoría seleccionada

        categoria = self.values[0]

        nombres = {
            "ayuda": "Ayuda General",
            "bugs": "Bugs",
            "postulaciones": "Postulaciones",
            "tienda": "Tienda"
        }

        nombre_categoria = nombres[categoria]

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

        # Crear ticket

        channel = await guild.create_text_channel(
            f"ticket-{member.id}",
            category=category,
            overwrites=overwrites
        )

        # Mensaje dentro del ticket

        await channel.send(
            f"{member.mention}\n\n"
            f"**Categoría:** {nombre_categoria}\n\n"
            "Tu ticket ha sido creado correctamente.\n"
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
# VIEW DEL MENÚ
# =========================

class TicketCategoryView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

        self.add_item(TicketSelect())


# =========================
# PANEL PRINCIPAL
# =========================

class TicketView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)


    @discord.ui.button(
        label="Crear ticket",
        style=discord.ButtonStyle.green,
        custom_id="infernmc_create_ticket"
    )
    async def create_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_message(
            "**Selecciona una categoría para tu ticket:**\n\n"
            "🎲 **Ayuda General** — Dudas generales sobre Discord o Minecraft.\n"
            "🎗️ **Bugs** — Reporta errores del servidor o Discord.\n"
            "📋 **Postulaciones** — Postulaciones para el Staff-Team.\n"
            "📯 **Tienda** — Dudas o problemas relacionados con la tienda.",
            view=TicketCategoryView(),
            ephemeral=True
        )


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
        "# Soporte InfernMc\n\n"
        "¿Necesitas ayuda? No dudes en abrir ticket para "
        "una atención mediante el staff del servidor.\n\n"

        "**Ten en cuenta:**\n"
        "• No abras demasiados tickets simultáneamente.\n"
        "• No insultes al staff, podrías ser sancionado.\n"
        "• Sé claro y directo al crear tu ticket.\n\n"

        "Los tickets se dividen en diferentes categorías "
        "para atender cada situación.",
        view=TicketView()
    )


# =========================
# INICIAR BOT
# =========================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("Falta DISCORD_TOKEN")

bot.run(TOKEN)
