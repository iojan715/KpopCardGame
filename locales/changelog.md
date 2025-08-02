# Changelog

## v.0.0.1 - 2025-03-01

Inicio de la ideación general del juego.
Definición conceptual de:
- Tipos de cartas y características
- Packs de cartas
- Sistema de creación de grupos
- Presentaciones y características principales
- Sistema de economía, popularidad y patrocinios

## v.0.0.2 - 2025-04-01
Adición conceptual de:
- Sistema de trade y mercado
- Sistema de XP y quema económica
- Nuevos tipos de presentaciones

## v0.0.3 - 2025-05-01
Creación estructural de:
- Lista de comandos
- Estructura de tablas para la base de datos
- Distintos tipos de habilidades
- Creación de un RoadMap formal

## v0.1.0 - 2025-06-01 / 2025-06-07
Comienzo del desarrollo de **codigo** y **base de datos**. Configuración del servidor de discord y el bot. Adición de los **primeros comandos** para prueba: `/database`, `/start`, `/admin` y `/sponsor`. Se estableció un **valor base** para cada idol en cada estadística.

Se establecieron los códigos únicos para:
- 98 posibles idols
- 32 posibles sets
- 13 rarezas de Idol Card (contando niveles y modelos de regulares)

Se estableció el valor estadístico promedio de cada rareza de Idol Card:
- Regular nivel 1: 300 (1 habilidad)
- Regular nivel 2: 340 (1 habilidad)
- Regular nivel 3: 380 (1 habilidad)
- Special: 400 (2 habilidades)
- Limited: 400 (2 habilidades)
- FCR: 400 (3 habilidades)
- POB: 420 (3 habilidades)

## v0.1.1 - 2025-06-07 / 2025-06-16
Llenado de tablas:
- Idol Cards (1 set, 5 idols, 65 cartas en total)
- Item Cards (25 cartas en total)
- Packs (12 Packs)
- Recompensas y xp requerida por nivel (hasta nivel 30)
- Redeemables (13 cupones)
- Habilidades (30 activas, 75 pasivas, 23 de soporte y 9 ultimates)

## v0.1.2 - 2025-06-16 / 2025-06-23
Creacion de los comandos:
- `/inventory`: subcomandos para ver cada tipo de carta u objeto en posesión.
- `/packs`: subcomandos para: ver packs existentes, comprar packs disponibles y abrir packs (con animación y efecto final).
Llenado de tablas:
- Performance cards

## v0.1.3 - 2025-06-23 / 2025-06-27
Ajustes menores a comandos ya existentes. Se agregó autocompletado para diversas opciones, ademas de traducciones a la mayoria de  casos en los que se retorna un mensaje.

Creacion de los comandos:
- `/groups`: Incluye subcomandos para crear grupos nuevos, vista de grupos creados y gestion de grupos.
- `/cards`: Incluye subcomandos para equipar y desequipar cartas idol y cartas item.

Llenado de tablas:
- Badges
- Level rewards

## v0.1.4 - 2025-06-27 / 2025-07-08
Adición de soporte para imagenes, y creación de cuenta en plataforma tipo CDN para su almacenamiento y ruta.

Creación y llenado de tablas:
- Songs
- Songs sections

Creacion del comando `/presentation`, con soporte para crear presentaciones tipo `Live`, agregar un grupo y canción a la presentación y ejecutarla, con acciones basicas como pasar a la siguiente sección y cambiar de idol activa. Finalizado el sistema de recompensas de popularidad para el grupo, gasto y desequipamiento de items agotados, cálculo de stats por items equipados, y soporte para Passive Skills (PS). 

## v0.1.5 - 2025-07-08 / 
Terminado el sistema de presentaciones con todos los botones necesarios:
- Acción Básica
- Switch: para cambiar de Active idol
- P.cards: para usar Performance Cards
- Active, Support y Ultimate: para usar skills
Creación de los subcomandos `level_up`, `/fusion` y `refund` dentro de `/cards`. Adición de diseños finales de cartas de Kiiikiii y Nmixx, además de iniciados para tripleS y Purple Kiss.
