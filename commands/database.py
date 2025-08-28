import discord
import csv
import io
from discord import app_commands
from discord.ext import commands
from db.connection import get_pool

class DatabaseCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Creamos el grupo principal /database
    @app_commands.guild_only()
    class DatabaseGroup(app_commands.Group):
        def __init__(self):
            super().__init__(name="database", description="Comandos relacionados con la base de datos.")

        async def table_autocomplete(self, interaction: discord.Interaction, current: str):
            pool = await get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public';
                """)
            return [
                app_commands.Choice(name=row["table_name"], value=row["table_name"])
                for row in rows if current.lower() in row["table_name"].lower()
            ][:25]  # Discord limita a 25 resultados
        
        @app_commands.command(name="delete-table", description="Eliminar una tabla de la base de datos (solo desarrollador)")
        @app_commands.describe(table="Nombre de la tabla a eliminar")
        @app_commands.autocomplete(table=table_autocomplete)
        async def delete_table(self, interaction: discord.Interaction, table: str):
            if interaction.guild is None:
                return await interaction.response.send_message(
                    "❌ Este comando solo está disponible en servidores.", 
                    ephemeral=True
                )
            # Reemplaza ID-DISCORD por tu ID real
            if interaction.user.id != 206937569307525122:
                await interaction.response.send_message("❌ No tienes permiso para usar este comando.", ephemeral=True)
                return

            pool = await get_pool()
            async with pool.acquire() as conn:
                try:
                    await conn.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE;')
                    await interaction.response.send_message(f"💥 Tabla `{table}` eliminada exitosamente.", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"❌ Error al eliminar la tabla: `{e}`", ephemeral=True)
        
        @app_commands.command(name="export", description="Exportar una tabla como archivo CSV")
        @app_commands.describe(table="Tabla a exportar")
        @app_commands.autocomplete(table=table_autocomplete)
        async def export(self, interaction: discord.Interaction, table: str):
            if interaction.guild is None:
                return await interaction.response.send_message(
                    "❌ Este comando solo está disponible en servidores.", 
                    ephemeral=True
                )
            import csv
            import io

            pool = await get_pool()
            async with pool.acquire() as conn:
                try:
                    rows = await conn.fetch(f'SELECT * FROM "{table}"')  # Protege contra mayúsculas

                    if not rows:
                        await interaction.response.send_message(f"La tabla `{table}` está vacía.", ephemeral=True)
                        return

                    # Preparamos archivo en memoria
                    output = io.StringIO()
                    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
                    writer.writeheader()

                    for row in rows:
                        writer.writerow(dict(row))

                    csv_data = output.getvalue()
                    csv_bytes = csv_data.encode("utf-8")
                    file = discord.File(fp=io.BytesIO(csv_bytes), filename=f"{table}.csv")

                    await interaction.response.send_message(
                        f"📤 Tabla `{table}` exportada con éxito:",
                        file=file
                    )

                except Exception as e:
                    await interaction.response.send_message(f"❌ Error al exportar la tabla: `{e}`", ephemeral=True)

    async def cog_load(self):
        self.bot.tree.add_command(self.DatabaseGroup())

async def setup(bot: commands.Bot):
    await bot.add_cog(DatabaseCommands(bot))