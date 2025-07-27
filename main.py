import discord
import logging
import os
from discord.ext import commands
from datetime import datetime
from config import TOKEN
from db.connection import create_pool
from db.schema import create_all_tables
from db.loop_events import events_loop
from keep_alive import keep_alive

keep_alive()

logging.basicConfig(level=logging.INFO)

class LudiBot(commands.Bot):
    async def setup_hook(self):
        asyncio.create_task(events_loop())


intents = discord.Intents.default()
intents.message_content = True
bot = LudiBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"🟢 Bot conectado como {bot.user}")
    await bot.tree.sync()

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    logging.warning(f"[Error en comando] Usuario: {interaction.user} ({interaction.user.id}) - Error: {error}")
    if isinstance(error, discord.app_commands.CheckFailure):
        # Ya diste feedback al usuario en interaction_check, así que silenciamos la excepción
        return
    # Para otros errores, sí queremos ver el traceback
    raise error

@bot.event
async def on_interaction(interaction: discord.Interaction):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user = interaction.user

    if interaction.type.name == "component":
        comp = interaction.data
        custom_id = comp.get("custom_id")
        label = getattr(interaction.component, "label", None)
        if label:
            logging.info(f"[{now}] [Botón presionado] Usuario: {user} ({user.id}) – Custom ID: {custom_id} – Label: {label}")
        else:
            logging.info(f"[{now}] [Componente activado] Usuario: {user} ({user.id}) – Custom ID: {custom_id}")

    elif interaction.type.name == "application_command":
        full_cmd = interaction.command.qualified_name
        logging.info(f"[{now}] [Comando usado] Usuario: {user} ({user.id}) – Comando: /{full_cmd}")


# 🔁 Carga todas las extensiones de la carpeta commands/
async def load_extensions():
    for filename in os.listdir("./commands"):
        if filename.endswith(".py") and not filename.startswith("_"):
            await bot.load_extension(f"commands.{filename[:-3]}")
    print("📦 Comandos cargados.")
    

async def main():
    await create_pool()
    await create_all_tables()
    print("Base de datos inicializada.")

    await load_extensions()
    await bot.start(TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
