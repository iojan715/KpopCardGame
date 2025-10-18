import asyncio, discord
import datetime, random, string
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
        await conn.execute("UPDATE groups SET first_presentation = True")
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

            if presentation_type == "live" and song_id and group_id:
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
            
            # Marcar como cancelada
            await conn.execute("""
                UPDATE presentations
                SET status = 'expired'
                WHERE presentation_id = $1
            """, presentation_id)
            
        if presentaciones:
            logging.info(f"Presentaciones canceladas: {len(presentaciones)}")
            
        active_event = await conn.fetchrow("SELECT * FROM event_instances WHERE status = 'active'")
        
        if active_event:
            if active_event['set_id']:
                await conn.execute(
                    "UPDATE packs SET price = 10000, set_id = $1 WHERE pack_id = 'LMT'",
                    active_event['set_id']
                )
                
            else:
                await conn.execute(
                    "UPDATE packs SET price = 0, set_id = $1 WHERE pack_id = 'LMT'",
                    None
                )

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
                if g['type'] == 'idol':
                    await conn.execute(
                        "UPDATE user_idol_cards SET user_id=$1, status='available', date_obtained=now() WHERE unique_id=$2",
                        g['host_id'], prize_card
                    )
                elif g['type'] == 'item':
                    await conn.execute(
                        "UPDATE user_item_cards SET user_id=$1, status='available', date_obtained=now() WHERE unique_id=$2",
                        g['host_id'], prize_card
                    )

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
                        
                        if g['type'] == 'idol':
                            card_id = await conn.fetchval("SELECT card_id FROM user_idol_cards WHERE unique_id = $1", unique_id)
                            embed = discord.Embed(
                                title="🎊 ¡Felicidades!",
                                description=f"Has ganado la carta `{card_id}.{prize_card}` en un sorteo 🎁",
                                color=discord.Color.gold()
                            )
                            embed.set_footer(text=f"{giveaway_id}")
                            image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{card_id}.webp{version}"
                            embed.set_image(url=image_url)
                            
                        elif g['type'] == 'item':
                            card_id = await conn.fetchval("SELECT item_id FROM user_item_cards WHERE unique_id = $1", unique_id)
                            item_name = await conn.fetchval("SELECT name FROM cards_item WHERE item_id = $1", card_id)
                            embed = discord.Embed(
                                title="🎊 ¡Felicidades!",
                                description=f"Has ganado el objeto **{item_name}** (ID: `{card_id}.{prize_card}`) en un sorteo 🎁",
                                color=discord.Color.gold()
                            )
                            embed.set_footer(text=f"{giveaway_id}")

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
            if g['type'] == 'idol':
                await conn.execute(
                    "UPDATE user_idol_cards SET user_id=$1, status='available', date_obtained=now() WHERE unique_id=$2",
                    winner, prize_card
                )
            elif g['type'] == 'item':
                await conn.execute(
                    "UPDATE user_item_cards SET user_id=$1, status='available', date_obtained=now() WHERE unique_id=$2",
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

async def change_event():
    pool = get_pool()
    async with pool.acquire() as conn:
        event_exists = await conn.fetch("SELECT 1 FROM events")
        if not event_exists:
            print("no hay eventos")
            return
        
        today = datetime.datetime.now(datetime.timezone.utc)
        current_event_row = await conn.fetchrow("SELECT * FROM event_instances WHERE status = 'active' ORDER BY start_date DESC")
        
        last_winner = ""
            
        if current_event_row:
            if today < current_event_row['end_date']:
                print("El evento aun no termina")
                return
            
            await conn.execute("UPDATE event_instances SET status = 'finished' WHERE instance_id = $1",
                               current_event_row['instance_id'])
            
            statuses = ["completed", "expired", "canceled"]
            presentaciones = await conn.fetch("""
                SELECT * FROM presentations
                WHERE status <> ALL($1::text[])
                AND presentation_type = 'event'
            """, statuses)

            if presentaciones:
                for p in presentaciones:
                    if p['status'] == 'preparation':
                        await conn.execute("UPDATE presentations SET status = 'expired' WHERE presentation_id = $1",
                                        p['presentation_id'])
                    elif p['status'] == 'active':
                        await conn.execute("UPDATE presentations SET status = 'expired' WHERE presentation_id = $1",
                                        p['presentation_id'])
                        
                        average_score = await conn.fetchval("""
                            SELECT average_score FROM songs WHERE song_id = $1
                        """, p['song_id'])

                        if average_score and average_score > 0:
                            final_score = p['total_score']
                            popularity = int(500 * (final_score / average_score))

                            # Actualizar popularidad en la presentación
                            await conn.execute("""
                                UPDATE presentations
                                SET total_popularity = $1
                                WHERE presentation_id = $2
                            """, popularity, p['presentation_id'])

                            # Sumar popularidad al grupo
                            await conn.execute("""
                                UPDATE event_participation
                                SET normal_score = $1
                                WHERE performance_id = $2
                            """, popularity, p['presentation_id'])
                    else:
                        await conn.execute("UPDATE presentations SET status = 'completed' WHERE presentation_id = $1",
                                        p['presentation_id'])
                
            participations = await conn.fetch("""
                SELECT * FROM event_participation
                WHERE instance_id = $1 AND normal_score > 0 ORDER BY normal_score DESC
            """, current_event_row['instance_id'])
            
            event_type = await conn.fetchval("SELECT event_type FROM events WHERE event_id = $1",
                                             current_event_row['event_id'])
            
            
            rank = 1
            if participations:
                for pa in participations:
                    if event_type in ['live_showcase', 'comeback_show', 'star_hunt']:
                        rewards = await conn.fetch("SELECT * FROM event_rewards WHERE rank_min <= $1 AND rank_max >= $1 AND event_id = $2",
                                                rank, current_event_row['event_id'])
                    
                    await conn.execute("UPDATE event_participation SET ranking = $1 WHERE participation_id = $2",
                                    rank, pa['participation_id'])
                    group_id = ""
                    normal_score = pa['normal_score']
                    
                    reward_desc = ""
                    reward_credits = 0
                    for r in rewards:
                        # Credits
                        await conn.execute(
                            "UPDATE users SET credits = credits + $1 WHERE user_id = $2",
                        r['credits'], pa['user_id'])
                        reward_credits += r['credits']
                        
                        # Packs
                        while True:
                            new_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
                            exists = await conn.fetchval("SELECT 1 FROM players_packs WHERE unique_id = $1", new_id)
                            if not exists:
                                break
                        now = datetime.datetime.now(datetime.timezone.utc)
                        await conn.execute("""
                            INSERT INTO players_packs (
                                unique_id, user_id, pack_id, buy_date,
                                set_id, theme
                            ) VALUES ($1, $2, $3, $4, $5, $6)
                        """, new_id, pa['user_id'], r['pack_id'], now,
                            current_event_row['set_id'], current_event_row['theme'])
                        
                        pack_name = await conn.fetchval("SELECT name FROM packs WHERE pack_id = $1", r['pack_id'])
                        reward_desc += f"> 📦 {pack_name}\n"
                        
                        # Badges
                        if r['badge_id']:
                            await conn.execute("""
                                INSERT INTO user_badges (
                                    badge_id, user_id, date_obtained, event_number
                                ) VALUES ($1, $2, $3, $4)
                            """, r['badge_id'], pa['user_id'], now, current_event_row['event_number'])
                            
                            badge_name = await conn.fetchval("SELECT name FROM badges WHERE badge_id = $1", r['badge_id'])
                            reward_desc += f"> 🏅 {badge_name} #{current_event_row['event_number']}\n"
                        
                        # Redeemable
                        
                        # Popularity
                        normal_score *= r['boost']
                    
                    normal_score = int(normal_score)
                    
                    group_id = await conn.fetchval(
                        "SELECT group_id FROM presentations WHERE presentation_id = $1",
                        pa['performance_id'])
                    
                    if group_id:
                        group_row = await conn.fetchrow(
                            "SELECT * FROM groups WHERE group_id = $1", group_id)

                        group_popularity = group_row['popularity'] + group_row['permanent_popularity']
                        merch_credits = int(50 * (group_popularity ** 0.5))
                        await conn.execute(
                                "UPDATE users SET credits = credits + $1 WHERE user_id = $2",
                            merch_credits, pa['user_id'])
                        
                        
                        
                        await conn.execute("""
                            UPDATE groups
                            SET popularity = popularity + $1
                            WHERE group_id = $2
                        """, normal_score, group_id)
                        
                        reward_desc += f"> **Venta de mercancía:** 💵{format(merch_credits,',')}\n"
                        
                        reward_desc += f"> **⭐ Popularidad para `{group_row['name']}`**: {format(normal_score,',')}\n"
                       
                    
                        perm = 0
                        if event_type == 'comeback_show':
                            perm = 100
                            await conn.execute("""
                                UPDATE groups
                                SET permanent_popularity = permanent_popularity + $1
                                WHERE group_id = $2
                            """, perm, group_id)
                        
                        elif event_type == 'live_showcase' and rank == 1:
                            perm = 50
                            await conn.execute("""
                                UPDATE groups
                                SET permanent_popularity = permanent_popularity + $1
                                WHERE group_id = $2
                            """, perm, group_id)
                        
                        reward_desc += f"> **🏆 Popularidad permanente para `{group_row['name']}`**: {perm}\n"
                    
                    if reward_credits > 0:
                        reward_desc += f"> **Créditos:** 💵{format(reward_credits,',')}\n"
                    
                    
                    
                    
                    try:
                        row = await conn.fetchrow(
                            "SELECT notifications FROM users WHERE user_id=$1",
                            pa['user_id'])
                        
                        if row and row["notifications"]:
                            user = BOT.get_user(pa['user_id'])
                            if user is None:
                                user = await BOT.fetch_user(pa['user_id'])  # fallback si no está en caché
                            if user:
                                embed = discord.Embed(
                                    title=f"✨ El evento semanal ha finalizado y has logrado el puesto `{rank}`",
                                    description=f"**Recompensas:**\n{reward_desc}",
                                    color=discord.Color.gold()
                                )
                                try:
                                    await user.send(embed=embed)
                                    await asyncio.sleep(5)
                                except discord.Forbidden:
                                    logging.warning(f"No pude enviar DM a {pa['user_id']}, tiene bloqueados los mensajes.")
                    except Exception as e:
                        logging.error(f"Error al intentar notificar al ganador {pa['user_id']}: {e}")
                    
                    
                    if rank == 1:
                        agency_name = await conn.fetchval("SELECT agency_name FROM users WHERE user_id = $1",
                                                          pa['user_id'])
                        last_winner += f"\n🏆 Grupo ganador del evento anterior: 🥇**{group_row['name']}** de la Agencia `{agency_name}` _(CEO: <@{pa['user_id']}>)_\n"
                    
                    rank += 1
            
            else:
                logging.info(f"No hubo participaciones en el evento anterior.")


        start_of_week = today - datetime.timedelta(days=today.weekday())
        start_of_event = start_of_week.replace(hour=5, minute=0, second=0, microsecond=0)

        end_of_event = (start_of_event + datetime.timedelta(days=6)).replace(hour=20, minute=0, second=0, microsecond=0)


        scheduled = await conn.fetchrow("""
            SELECT * FROM event_instances
            WHERE status = 'scheduled'
              AND DATE(start_date) = DATE($1)
            ORDER BY start_date ASC
            LIMIT 1
        """, start_of_event)

        new_desc = ""
        
        new_type_desc = new_song = new_set = ""
        if scheduled:
            if scheduled['song_id']:
                new_song = await conn.fetchval("SELECT name FROM songs WHERE song_id = $1", scheduled['song_id'])
                
            if scheduled['set_id']:
                new_set = await conn.fetchval("SELECT set_name FROM cards_idol WHERE set_id = $1 LIMIT 1", scheduled['set_id'])
            
            # ACTIVAR LIMITED PACKS Y OTRAS CONFIGURACIONES SI APLICA
            await conn.execute("""
                UPDATE event_instances
                SET status='active'
                WHERE instance_id=$1
            """, scheduled["instance_id"])
            
            # set_id y price en Limited Packs
            if scheduled['set_id']:
                await conn.execute("""UPDATE packs SET
                    set_id = $1, price = 10000 WHERE pack_id = 'LMT'
                    """, scheduled['set_id'])
            else:
                await conn.execute("UPDATE packs SET price = 0 WHERE pack_id = 'LMT'")
            
            event_name = await conn.fetchval("SELECT base_name FROM events WHERE event_id = $1", scheduled['event_id'])
            new_desc += f"# 📢 Ya comenzó el nuevo evento semanal: {event_name} #{scheduled['event_number']}"
            logging.info(f"Evento programado {scheduled['instance_id']} activado.")
            
        else:

            events = await conn.fetch("""
                SELECT * FROM events WHERE weight > 0
            """)
            if not events:
                logging.warning("No hay eventos disponibles en la tabla events con weight > 0.")
                return

            chosen_event = random.choices(events, weights=[e["weight"] for e in events])[0]

            # Obtener siguiente event_number para ese event_id
            next_number = await conn.fetchval("""
                SELECT COALESCE(MAX(event_number), 0) + 1
                FROM event_instances
                WHERE event_id=$1
            """, chosen_event["event_id"])
            
            song = set_id = None
            if chosen_event['can_song']:
                song = await conn.fetchval("SELECT song_id FROM songs ORDER BY RANDOM() LIMIT 1")
            
            if chosen_event['can_set']:
                set_id = await conn.fetchval("""
                            SELECT set_id
                            FROM (
                                SELECT DISTINCT set_id
                                FROM cards_idol
                            ) AS sub
                            ORDER BY RANDOM()
                            LIMIT 1
                        """)
                
            if song:
                new_song = await conn.fetchval("SELECT name FROM songs WHERE song_id = $1", song)
                
                if not set_id:
                    set_id = await conn.fetchval("SELECT set_id FROM songs WHERE song_id = $1", song)
                
            if set_id:
                new_set = await conn.fetchval("SELECT set_name FROM cards_idol WHERE set_id = $1 LIMIT 1", set_id)

            # Insertar nuevo evento activo
            await conn.execute("""
                INSERT INTO event_instances (event_id, event_number, start_date, end_date, status, song_id, set_id)
                VALUES ($1, $2, $3, $4, 'active', $5, $6)
            """, chosen_event["event_id"], next_number, start_of_event, end_of_event, song, set_id)
            
            if set_id:
                await conn.execute("""UPDATE packs SET
                    set_id = $1, price = 10000 WHERE pack_id = 'LMT'
                    """, set_id)
            else:
                await conn.execute("UPDATE packs SET price = 0 WHERE pack_id = 'LMT'")

            new_desc += f"# 📢 Ya comenzó el nuevo evento semanal: {chosen_event['base_name']} #{next_number}"
            logging.info(f"Nuevo evento creado: {chosen_event['event_id']} #{next_number}")
        
        if new_song:
            new_type_desc += f"🎶 La canción designada para este evento es: **{new_song}**\n"
            
        if new_set:
            new_type_desc += f"📦 Durante este evento estará activo para su compra el **Limited Pack** del set `{new_set}`. Podrás comprarlo por 💵10,000\n"
        
        try:
            if BOT.user.id == 1311183246431752224:
                CHANNEL_ID = 1395557400521474108
            else:
                CHANNEL_ID = 1421367405149552670

            channel = BOT.get_channel(CHANNEL_ID)
            if channel is None:
                channel = await BOT.fetch_channel(CHANNEL_ID)  # fallback si no está en caché
            
            if channel:
                new_desc += f"{last_winner}"
                new_desc += f"\n### Participa en el nuevo evento durante la semana para clasificar y obtener recompensas\nCrea tu presentación con `/presentation create` eligiendo el tipo `Event` para participar\n"
                new_desc += f"{new_type_desc}\n"
                new_desc += f"_Recuerda revisar tus misiones semanales, tu sponsor y unirte a un FanClub esta semana_\n"
                new_desc += f"@everyone"
                await channel.send(content=new_desc)
            else:
                logging.error(f"No pude encontrar el canal con ID {CHANNEL_ID}")
                
        except Exception as e:
            logging.error(f"Error al intentar notificar el nuevo evento: {e}")
        
    logging.info("Se han entregado recompensas del evento y configurado uno nuevo")

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
        await ejecutar_evento_si_corresponde('change_event', change_event)

        await asyncio.sleep(300)  # revisa cada 5 minutos

# FUNCIONES CALLBACK

