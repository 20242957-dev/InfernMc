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

WELCOME_CHANNEL_ID = 0
GOODBYE_CHANNEL_ID = 0
TICKET_CATEGORY_ID = 0
STAFF_ROLE_ID = 0


# =========================
# BOT LISTO
# =========================

@bot.event
async def on_ready():
    print(f"InfernMc conectado como {bot.user}")


# =========================
# BIENVENIDAS
# =========================

@bot.event
async def on_member_join(member):

    if WELCOME_CHANNEL_ID == 0:
        return

    channel = bot.get_channel(WELCOME_CHANNEL_ID)

    if channel:
        await channel.send(
            f"Bienvenido/a {member.mention} a **InfernMc**."
        )


# =========================
# DESPEDIDAS
# =========================

@bot.event
async def on_member_remove(member):

    if GOODBYE_CHANNEL_ID == 0:
        return

    channel = bot.get_channel(GOODBYE_CHANNEL_ID)

    if channel:
        await channel.send(
            f"**{member.name}** ha salido de InfernMc."
        )


# =========================
# TICKETS
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

        guild = interaction.guild
        member = interaction.user

        category = guild.get_channel(TICKET_CATEGORY_ID)

        if category is None:
            await interaction.response.send_message(
                "La categoría de tickets no está configurada.",
                ephemeral=True
            )
            return

        # Comprobar si ya tiene ticket
        for channel in category.channels:

            if channel.name == f"ticket-{member.id}":

                await interaction.response.send_message(
                    f"Ya tienes un ticket abierto: {channel.mention}",
                    ephemeral=True
                )

                return

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

        staff_role = guild.get_role(STAFF_ROLE_ID)

        if staff_role:

            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

        channel = await guild.create_text_channel(
            f"ticket-{member.id}",
            category=category,
            overwrites=overwrites
        )

        await channel.send(
            f"{member.mention} tu ticket ha sido creado.\n\n"
            "Un miembro del staff te atenderá lo antes posible.",
            view=TicketControlView()
        )

        await interaction.response.send_message(
            f"Ticket creado: {channel.mention}",
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

        staff_role = interaction.guild.get_role(STAFF_ROLE_ID)

        if staff_role is None or staff_role not in interaction.user.roles:

            await interaction.response.send_message(
                "Solo el staff puede reclamar tickets.",
                ephemeral=True
            )

            return

        await interaction.channel.send(
            f"Este ticket ha sido reclamado por {interaction.user.mention}."
        )

        await interaction.response.defer()


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

        staff_role = interaction.guild.get_role(STAFF_ROLE_ID)

        if staff_role is None or staff_role not in interaction.user.roles:

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
# COMANDO PANEL
# =========================

@bot.command()
@commands.has_permissions(administrator=True)
async def ticketpanel(ctx):

    await ctx.send(
        "**Soporte InfernMc**\n\n"
        "Si necesitas ayuda, abre un ticket utilizando "
        "el botón de abajo.",
        view=TicketView()
    )


# =========================
# INICIAR BOT
# =========================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("Falta DISCORD_TOKEN")

bot.run(TOKEN)
