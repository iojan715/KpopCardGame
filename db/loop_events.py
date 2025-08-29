import asyncio, discord
import datetime, random
from db.connection import get_pool
import logging
from commands.starter import version

EJECUCION_HORA_UTC = 5  # 05:00 UTC
GRACE_DAYS = 50  # días de tolerancia para ejecución tardía

BOT = None

async def ejecutar_evento_si_corresponde(nombre_evento, funcion_callback):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT last_applied, frecuencia_tipo, dia_semana, dia_mes
            FROM loop_events
            WHERE event = $1;
        """, nombre_evento)

        if not row:
            return  # Evento no registrado

        last_applied = row['last_applied']
        tipo = row['frecuencia_tipo']
        dia_semana = row['dia_semana']
        dia_mes = row['dia_mes']

        now = datetime.datetime.now(datetime.timezone.utc)

        # Fecha objetivo del evento (cuando se supone que debió ejecutarse)
        fecha_programada = None

        if tipo == 'diaria':
            fecha_programada = datetime.datetime(
                year=now.year, month=now.month, day=now.day,
                hour=EJECUCION_HORA_UTC, tzinfo=datetime.timezone.utc
            )

        elif tipo == 'semanal':
            # Buscar el lunes de esta semana a las 05:00 UTC
            dias_desde_lunes = (now.weekday() - dia_semana) % 7
            fecha_programada = datetime.datetime(
                year=now.year, month=now.month, day=now.day,
                hour=EJECUCION_HORA_UTC, tzinfo=datetime.timezone.utc
            ) - datetime.timedelta(days=dias_desde_lunes)

        elif tipo == 'mensual':
            try:
                fecha_programada = datetime.datetime(
                    year=now.year, month=now.month, day=dia_mes,
                    hour=EJECUCION_HORA_UTC, tzinfo=datetime.timezone.utc
                )
            except ValueError:
                return  # Día inválido para este mes (por ejemplo, 31 de febrero)

        elif tipo == 'frecuente':
            frecuencia_minutos = 5  # puedes ajustarlo a lo que necesites
            fecha_programada = last_applied + datetime.timedelta(minutes=frecuencia_minutos)

        if fecha_programada is None:
            return
        # Ejecutar si corresponde hoy, o si se pasó más de X días desde la última ejecución válida
        diferencia = now - last_applied
        tolerancia_superada = diferencia.days >= GRACE_DAYS
        no_ejecutado_aun = last_applied < fecha_programada

        if (now >= fecha_programada and no_ejecutado_aun) or (tolerancia_superada and no_ejecutado_aun):
            await funcion_callback()
            await conn.execute("""
                UPDATE loop_events SET last_applied = $1 WHERE event = $2;
            """, now, nombre_evento)


async def reset_fcr_func():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET can_fcr = True")
    logging.info("FCR reseteados")

async def reducir_popularidad_func():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE groups SET popularity = popularity * 0.9")
    logging.info("Popularidad reducida")

async def reducir_influencia_func():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET influence_temp = influence_temp * 0.9")
    logging.info("Influencia reducida")

async def cambiar_limited_set_func():
    pool = get_pool()
    
    logging.info("Limited set cambiado")
    
async def cancel_presentation_func():
    pool = get_pool()
    async with pool.acquire() as conn:
        limite_tiempo = datetime.timedelta(hours=168)  # 7 días

        now = datetime.datetime.now(datetime.timezone.utc)

        # Buscar presentaciones activas o en preparación que hayan excedido el límite
        presentaciones = await conn.fetch("""
            SELECT * FROM presentations
            WHERE status IN ('preparation', 'active')
            AND $1 - presentation_date > INTERVAL '168 hours'
        """, now)

        for presentation in presentaciones:
            presentation_id = presentation['presentation_id']
            presentation_type = presentation['presentation_type']
            song_id = presentation['song_id']
            group_id = presentation['group_id']
            total_score = presentation['total_score']

            # Marcar como cancelada
            await conn.execute("""
                UPDATE presentations
                SET status = 'expired'
                WHERE presentation_id = $1
            """, presentation_id)

            if presentation_type == 'live' and song_id and group_id:
                # Obtener average_score
                average_score = await conn.fetchval("""
                    SELECT average_score FROM songs WHERE song_id = $1
                """, song_id)

                if average_score and average_score > 0:
                    final_score = total_score  # Ya viene acumulado
                    popularity = int(500 * (final_score / average_score))

                    # Actualizar popularidad en la presentación
                    await conn.execute("""
                        UPDATE presentations
                        SET total_popularity = $1
                        WHERE presentation_id = $2
                    """, popularity, presentation_id)

                    # Sumar popularidad al grupo
                    await conn.execute("""
                        UPDATE groups
                        SET popularity = popularity + $1
                        WHERE group_id = $2
                    """, popularity, group_id)
        if presentaciones:
            logging.info(f"Presentaciones canceladas: {len(presentaciones)}")

async def increase_payment():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE groups SET unpaid_weeks = unpaid_weeks + 1 WHERE status = 'active'")
    logging.info("Pago semanal de grupos agregado")

async def add_daily_missions():
    pool = get_pool()
    async with pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id FROM users")

        exploratories = await conn.fetch("""
            SELECT mission_id, mission_type, needed, pack_id, redeemable_id, credits, xp
            FROM missions_base
            WHERE difficulty = 'exploratory'
        """)
        easy_missions = await conn.fetch("""
            SELECT mission_id, mission_type, needed, pack_id, redeemable_id, credits, xp
            FROM missions_base
            WHERE difficulty = 'easy'
        """)

        if not exploratories and not easy_missions:
            return

        for u in users:
            user_id = u["user_id"]

            active_rows = await conn.fetch(
                """
                SELECT um.mission_number, um.mission_id, mb.mission_type
                FROM user_missions um
                LEFT JOIN missions_base mb ON um.mission_id = mb.mission_id
                WHERE um.user_id = $1 AND um.status = 'active'
                """,
                user_id
            )

            active_ids = {r["mission_id"] for r in active_rows if r["mission_id"]}
            
            active_types = {r["mission_type"] for r in active_rows if r["mission_type"]}
            active_by_number = {r["mission_number"]: r["mission_id"] for r in active_rows if r["mission_id"]}

            if 1 not in active_by_number:
                candidates = [m for m in exploratories if m["mission_id"] not in active_ids]
                if candidates:
                    m = random.choice(candidates)
                    await conn.execute(
                        """
                        INSERT INTO user_missions (
                            user_id, mission_number, mission_id, needed, obtained,
                            pack_id, redeemable_id, credits, xp, status, assigned_at, last_updated
                        ) VALUES (
                            $1, $2, $3, $4, $5,
                            $6, $7, $8, $9, 'active', now(), now()
                        )
                        ON CONFLICT DO NOTHING
                        """,
                        user_id,
                        1,
                        m["mission_id"],
                        int(m["needed"] or 1),
                        0,
                        m["pack_id"] or None,
                        m["redeemable_id"] or None,
                        int(m["credits"] or 0),
                        int(m["xp"] or 1)
                    )
                    active_ids.add(m["mission_id"])
                    active_by_number[1] = m["mission_id"]
                    
                    if m.get("mission_type"):
                        active_types.add(m["mission_type"])

            if 2 not in active_by_number:
                candidates = [
                    m for m in easy_missions
                    if m["mission_id"] not in active_ids and (m.get("mission_type") not in active_types)
                ]
                if candidates:
                    m = random.choice(candidates)
                    await conn.execute(
                        """
                        INSERT INTO user_missions (
                            user_id, mission_number, mission_id, needed, obtained,
                            pack_id, redeemable_id, credits, xp, status, assigned_at, last_updated
                        ) VALUES (
                            $1, $2, $3, $4, $5,
                            $6, $7, $8, $9, 'active', now(), now()
                        )
                        ON CONFLICT DO NOTHING
                        """,
                        user_id,
                        2,
                        m["mission_id"],
                        int(m["needed"] or 1),
                        0,
                        m["pack_id"] or None,
                        m["redeemable_id"] or None,
                        int(m["credits"] or 0),
                        int(m["xp"] or 1)
                    )
                    active_ids.add(m["mission_id"])
                    active_by_number[2] = m["mission_id"]
                    if m.get("mission_type"):
                        active_types.add(m["mission_type"])

            if 3 not in active_by_number:
                candidates = [
                    m for m in easy_missions
                    if m["mission_id"] not in active_ids and (m.get("mission_type") not in active_types)
                ]
                if candidates:
                    m = random.choice(candidates)
                    await conn.execute(
                        """
                        INSERT INTO user_missions (
                            user_id, mission_number, mission_id, needed, obtained,
                            pack_id, redeemable_id, credits, xp, status, assigned_at, last_updated
                        ) VALUES (
                            $1, $2, $3, $4, $5,
                            $6, $7, $8, $9, 'active', now(), now()
                        )
                        ON CONFLICT DO NOTHING
                        """,
                        user_id,
                        3,
                        m["mission_id"],
                        int(m["needed"] or 1),
                        0,
                        m["pack_id"] or None,
                        m["redeemable_id"] or None,
                        int(m["credits"] or 0),
                        int(m["xp"] or 1)
                    )
                    active_ids.add(m["mission_id"])
                    active_by_number[3] = m["mission_id"]
                    if m.get("mission_type"):
                        active_types.add(m["mission_type"])
    logging.info("Misiones diarias agregadas correctamente.")

async def add_weekly_missions():
    pool = get_pool()
    async with pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id FROM users")

        medium_missions = await conn.fetch("""
            SELECT mission_id, mission_type, needed, pack_id, redeemable_id, credits, xp
            FROM missions_base
            WHERE difficulty = 'medium'
        """)
        hard_missions = await conn.fetch("""
            SELECT mission_id, mission_type, needed, pack_id, redeemable_id, credits, xp
            FROM missions_base
            WHERE difficulty = 'hard'
        """)

        if not medium_missions and not hard_missions:
            return

        for u in users:
            user_id = u["user_id"]

            active_rows = await conn.fetch(
                """
                SELECT um.mission_number, um.mission_id, mb.mission_type
                FROM user_missions um
                LEFT JOIN missions_base mb ON um.mission_id = mb.mission_id
                WHERE um.user_id = $1 AND um.status = 'active' AND um.mission_number IN (4,5)
                """,
                user_id
            )

            active_by_number = {r["mission_number"]: r["mission_id"] for r in active_rows if r["mission_id"]}
            active_types = {r["mission_type"] for r in active_rows if r["mission_type"]}

            if 4 not in active_by_number and medium_missions:
                forbidden_type_for_4 = None
                if 5 in active_by_number:
                    for r in active_rows:
                        if r["mission_number"] == 5:
                            forbidden_type_for_4 = r.get("mission_type")
                            break

                candidates = [
                    m for m in medium_missions
                    if (forbidden_type_for_4 is None or (m.get("mission_type") != forbidden_type_for_4))
                ]

                if not candidates:
                    candidates = list(medium_missions)

                if candidates:
                    m = random.choice(candidates)
                    await conn.execute(
                        """
                        INSERT INTO user_missions (
                            user_id, mission_number, mission_id, needed, obtained,
                            pack_id, redeemable_id, credits, xp, status, assigned_at, last_updated
                        ) VALUES (
                            $1, $2, $3, $4, $5,
                            $6, $7, $8, $9, 'active', now(), now()
                        )
                        ON CONFLICT DO NOTHING
                        """,
                        user_id,
                        4,
                        m["mission_id"],
                        int(m["needed"] or 1),
                        0,
                        m["pack_id"] or None,
                        m["redeemable_id"] or None,
                        int(m["credits"] or 0),
                        int(m["xp"] or 1)
                    )
                    
                    if m.get("mission_type"):
                        active_types.add(m["mission_type"])
                        active_by_number[4] = m["mission_id"]

            if 5 not in active_by_number and hard_missions:
                
                forbidden_type_for_5 = None
                if 4 in active_by_number:
                    
                    for r in active_rows:
                        if r["mission_number"] == 4:
                            forbidden_type_for_5 = r.get("mission_type")
                            break
                    
                    if forbidden_type_for_5 is None and active_types:
                        pass

                candidates = [
                    m for m in hard_missions
                    if (m.get("mission_type") not in active_types)
                ]

                if not candidates:
                    candidates = list(hard_missions)

                if candidates:
                    m = random.choice(candidates)
                    await conn.execute(
                        """
                        INSERT INTO user_missions (
                            user_id, mission_number, mission_id, needed, obtained,
                            pack_id, redeemable_id, credits, xp, status, assigned_at, last_updated
                        ) VALUES (
                            $1, $2, $3, $4, $5,
                            $6, $7, $8, $9, 'active', now(), now()
                        )
                        ON CONFLICT DO NOTHING
                        """,
                        user_id,
                        5,
                        m["mission_id"],
                        int(m["needed"] or 1),
                        0,
                        m["pack_id"] or None,
                        m["redeemable_id"] or None,
                        int(m["credits"] or 0),
                        int(m["xp"] or 1)
                    )
                    
                    active_by_number[5] = m["mission_id"]
                    if m.get("mission_type"):
                        active_types.add(m["mission_type"])

    logging.info("Misiones semanales agregadas correctamente.")

async def giveaway_winner():
    pool = get_pool()
    now = datetime.datetime.now(datetime.timezone.utc)

    async with pool.acquire() as conn:
        # Buscar sorteos activos que ya vencieron
        giveaways = await conn.fetch("""
            SELECT * FROM giveaways
            WHERE active = TRUE AND end_time <= $1
        """, now)
        
        if not giveaways:
            return

        for g in giveaways:
            giveaway_id = g["giveaway_id"]
            guild_id = g["guild_id"]
            channel_id = g["channel_id"]
            message_id = g["message_id"]
            prize_card = g["card_id"]

            # Buscar participantes
            participants = await conn.fetch("""
                SELECT user_id FROM giveaway_entries
                WHERE giveaway_id = $1
            """, giveaway_id)

            if not participants:
                # No hubo participantes
                await conn.execute(
                    "UPDATE giveaways SET active = FALSE WHERE giveaway_id=$1",
                    giveaway_id)

                try:
                    channel = BOT.get_channel(channel_id)
                    if channel:
                        msg = await channel.fetch_message(message_id)
                        embed = msg.embeds[0] if msg.embeds else discord.Embed(title="🎉 Sorteo finalizado")
                        embed.color = discord.Color.red()
                        embed.add_field(name="Resultado", value="⚠️ Nadie participó en este sorteo.")
                        await msg.edit(embed=embed, view=None)
                except Exception as e:
                    logging.error(f"No se pudo editar mensaje de sorteo vacío {giveaway_id}: {e}")

                continue

            # Elegir ganador
            winner = random.choice(participants)["user_id"]
            try:
                row = await conn.fetchrow(
                    "SELECT notifications FROM users WHERE user_id=$1",
                    winner
                )
                if row and row["notifications"]:
                    user = BOT.get_user(winner)
                    if user is None:
                        user = await BOT.fetch_user(winner)  # fallback si no está en caché
                    if user:
                        unique_id = prize_card
                        card_id = await conn.fetchval("SELECT card_id FROM user_idol_cards WHERE unique_id = $1", unique_id)
                        embed = discord.Embed(
                            title="🎊 ¡Felicidades!",
                            description=f"Has ganado la carta `{card_id}.{prize_card}` en un sorteo 🎁",
                            color=discord.Color.gold()
                        )
                        embed.set_footer(text=f"{giveaway_id}")

                        # Opcional: mostrar imagen de la carta
                        image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{card_id}.webp{version}"
                        embed.set_image(url=image_url)
                        try:
                            await user.send(embed=embed)
                        except discord.Forbidden:
                            logging.warning(f"No pude enviar DM a {winner}, tiene bloqueados los mensajes.")
            except Exception as e:
                logging.error(f"Error al intentar notificar al ganador {winner}: {e}")
                

            # Marcar en DB
            await conn.execute(
                "UPDATE giveaway_entries SET winner=TRUE WHERE giveaway_id=$1 AND user_id=$2",
                giveaway_id, winner
            )
            await conn.execute(
                "UPDATE giveaways SET active=FALSE WHERE giveaway_id=$1",
                giveaway_id
            )

            # Transferir la carta
            await conn.execute(
                "UPDATE user_idol_cards SET user_id=$1, status='available', date_obtained=now() WHERE unique_id=$2",
                winner, prize_card
            )

            # Editar mensaje original
            try:
                channel = BOT.get_channel(channel_id)
                if channel:
                    msg = await channel.fetch_message(message_id)
                    embed = msg.embeds[0] if msg.embeds else discord.Embed(title="🎉 Sorteo finalizado")
                    embed.color = discord.Color.gold()
                    embed.add_field(name="Ganador", value=f"<@{winner}> 🎊", inline=False)
                    embed.set_footer(text=f"{giveaway_id}")
                    await msg.edit(embed=embed, view=None)
            except Exception as e:
                logging.error(f"No se pudo editar mensaje del sorteo {giveaway_id}: {e}")

        if giveaways:
            logging.info(f"Sorteos finalizados: {len(giveaways)}")
    
async def remove_roles():
    guild_ids = [1395514643283443742, 1311186435054764032]
    for gid in guild_ids:
        guild = BOT.get_guild(gid)
        if not guild:
            print(f"⚠️ Guild {gid} no está cacheada aún.")
            continue

        # Filtramos los roles que contienen "FanClub"
        fanclub_roles = [r for r in guild.roles if "FanClub" in r.name]
        if not fanclub_roles:
            print(f"✅ No hay roles FanClub en guild {gid}.")
            continue

        print(f"🔄 Limpiando {len(fanclub_roles)} roles FanClub en {guild.name}")
        # Recorremos cada miembro
        async for member in guild.fetch_members(limit=None):
            to_remove = [r for r in member.roles if r in fanclub_roles]
            if to_remove:
                try:
                    await member.remove_roles(*to_remove, reason="Reset semanal de FanClub roles")
                    logging.info(f"Rol FanClub quitado a {member.display_name}")
                except Exception as e:
                    print(f"❌ No pude quitar roles a {member.display_name}: {e}")
        print(f"✅ Limpieza completada en {guild.name}")
    pass
  

async def events_loop(bot):
    global BOT
    BOT = bot
    
    await BOT.wait_until_ready()
    
    while True:
        await ejecutar_evento_si_corresponde("reset_fcr", reset_fcr_func)
        await ejecutar_evento_si_corresponde("reduce_popularity", reducir_popularidad_func)
        await ejecutar_evento_si_corresponde("reduce_influence", reducir_influencia_func)
        await ejecutar_evento_si_corresponde("change_limited_set", cambiar_limited_set_func)
        await ejecutar_evento_si_corresponde("cancel_presentation", cancel_presentation_func)
        await ejecutar_evento_si_corresponde("increase_payment", increase_payment)
        await ejecutar_evento_si_corresponde("remove_roles", remove_roles)
        await ejecutar_evento_si_corresponde("add_daily_mission", add_daily_missions)
        await ejecutar_evento_si_corresponde("add_weekly_mission", add_weekly_missions)
        await ejecutar_evento_si_corresponde('giveaway_winner', giveaway_winner)

        await asyncio.sleep(300)  # revisa cada 5 minutos

# FUNCIONES CALLBACK

