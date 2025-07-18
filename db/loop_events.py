import asyncio
import datetime
from db.connection import get_pool

EJECUCION_HORA_UTC = 5  # 05:00 UTC
GRACE_DAYS = 3  # días de tolerancia para ejecución tardía

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
            frecuencia_minutos = 10  # puedes ajustarlo a lo que necesites
            fecha_programada = last_applied + datetime.timedelta(minutes=frecuencia_minutos)

        if fecha_programada is None:
            return

        # Ejecutar si corresponde hoy, o si se pasó más de X días desde la última ejecución válida
        diferencia = now - fecha_programada
        tolerancia_superada = diferencia.days >= GRACE_DAYS
        no_ejecutado_aun = last_applied < fecha_programada

        if (now >= fecha_programada and no_ejecutado_aun) or (tolerancia_superada and no_ejecutado_aun):
            await funcion_callback()
            await conn.execute("""
                UPDATE loop_events SET last_applied = $1 WHERE event = $2;
            """, now, nombre_evento)

async def events_loop():
    while True:
        await ejecutar_evento_si_corresponde("reset_fcr", reset_fcr_func)
        await ejecutar_evento_si_corresponde("reduce_popularity", reducir_popularidad_func)
        await ejecutar_evento_si_corresponde("reduce_influence", reducir_influencia_func)
        await ejecutar_evento_si_corresponde("change_limited_set", cambiar_limited_set_func)
        await ejecutar_evento_si_corresponde("cancel_presentation", cancel_presentation_func)
        await ejecutar_evento_si_corresponde("increase_payment", increase_payment)

        await asyncio.sleep(300)  # revisa cada 5 minutos

# FUNCIONES CALLBACK

async def reset_fcr_func():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET can_fcr = True")
    print("FCR reseteados")

async def reducir_popularidad_func():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE groups SET popularity = popularity * 0.9")
    print("Popularidad reducida")

async def reducir_influencia_func():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET influence_temp = influence_temp * 0.9")
    print("Influencia reducida")

async def cambiar_limited_set_func():
    pool = get_pool()
    
    print("Limited set cambiado")
    
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
                SET status = 'cancelled'
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
            print(f"Presentaciones canceladas: {len(presentaciones)}")

async def increase_payment():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE groups SET unpaid_weeks = unpaid_weeks + 1 WHERE status = 'active'")
    print("Pago semanal de grupos agregado")