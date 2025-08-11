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

## v0.1.5 - 2025-07-08 / 2025-07-28
Terminado el sistema de presentaciones con todos los botones necesarios:
- Acción Básica
- Switch: para cambiar de Active idol
- P.cards: para usar Performance Cards
- Active, Support y Ultimate: para usar skills
Creación de los subcomandos `level_up`, `/fusion` y `refund` dentro de `/cards`. Adición de diseños finales de cartas de Kiiikiii y Nmixx, además de iniciados para tripleS y Purple Kiss.

## v0.2 - 2025-07-28 / 2025-08-04
Solución de errores generales. Adición de los sistemas completos de `redeemables`. Soporte para colecciones de menor cantidad de cartas. Adición de emojis para los tipos de habilidades. Creación de la guia mediante `/help`.

## Cambios previos a la versión 1.0

Durante los últimos meses se fueron agregando:

- Sistema de cartas, grupos, popularidad y skills
- Tipos de presentaciones: Live, Practice
- Packs, ítems, XP, badges y más
- Soporte multilenguaje (para futuras traducciones)
- Colecciones por idol o set
- Más de 60 habilidades distintas implementadas
- Primeras cartas oficiales: datos y diseño visual

_¡Gracias a quienes participaron en la etapa de desarrollo y pruebas!_

## Versión 1.0 - Lanzamiento oficial (2025-08-04)
¡El juego ya está disponible para todos los jugadores!
Esta primera versión incluye todas las funciones esenciales para comenzar tu aventura como manager K-pop:

- Comienza con `/start` y crea tu agencia
- Colecciona cartas idol y objetos especiales
- Forma tus propios grupos de idols
- Participa en presentaciones con recompensas de popularidad
- Sube de nivel, equipa cartas, fusiona y mejora tu equipo
- Canjea cupones y objetos con `/redeem`
- Explora y consulta tus progresos con `/inventory`, `/groups`, `/collections` y más
- Consulta la guía básica con `/help tutorial`

Últimas correcciones y mejoras:
- Balance y ajustes en habilidades, stats y tipos de presentación
- Mejor detección de errores y mensajes informativos
- Diseño visual de cartas actualizado

----------------------------------

## Versión 1.1 - Primer paso hacia el intercambio (2025-08-06)

Esta actualización introduce nuevas formas de interacción entre jugadores, además de expandir el contenido coleccionable del juego.

### 🆕 Nuevas funciones
- ✉️ **Nuevo comando**: `/gift card`  
  Ahora puedes regalar cartas idol o cartas item a otros jugadores.  
  El envío tiene un costo dependiendo del tipo y rareza de la carta.

### 🧩 Cambios y mejoras
- ✅ Se agregó en `/sponsor` la visualización de **créditos obtenidos por hora**.
- 🐞 Correcciones en traducciones y textos de algunas habilidades que mostraban descripciones erróneas o datos vacíos.
- 🔧 Pequeños ajustes de funcionamiento interno y estabilidad.

### 🎶 Nuevos grupos y artistas disponibles
- **IVE**  
- **Loossemble**  
- **Chuu**

----------------------------------

## Versión 1.2 - ¡Llegan las misiones diarias y semanales! (2025-08-10)

Esta actualización introduce un sistema completamente nuevo de **misiones** que permitirá a los jugadores obtener recompensas adicionales cada día y semana.  
Además, incluye diversas mejoras técnicas y ajustes internos para optimizar la experiencia de juego.

### 🆕 Nuevas funciones
- 🎯 **Sistema de misiones diarias y semanales**
  - Ahora cada jugador recibirá 5 misiones automáticamente:
    - **Misiones diarias** *fáciles* (2) y *exploratorias* (1).
    - **Misiones semanales** de dificultad *media* (1) y *difícil* (1).
  - Las misiones ofrecen recompensas en XP, además de poder otorgar algunos *Packs*, *Cupones* o *Dinero*.
  - Se pueden **cancelar** manualmente con un botón de confirmación, para recibir una nueva en su lugar en el siguiente periodo
  - Si no se completa ni se cancela una misión, no se genera una nueva, sino que **el progreso se mantiene** para el siguiente día o la siguiente semana (según sea el caso).
- 🔍 **Visualización de misiones**
  - Nuevo comando `/missions list` para ver tus misiones activas, su progreso y botones para reclamar o cancelar.

### 🧩 Cambios y mejoras
- 📊 **Sistema interno de asignación de misiones**
  - Lógica optimizada para evitar que se repitan misiones del mismo tipo en un mismo ciclo.
  - Control independiente entre diarias y semanales para mayor variedad.
- 🖱️ **Interfaz más reactiva**
  - Todas las interacciones de misiones (reclamar, cancelar) se realizan en el mismo mensaje, sin mensajes adicionales.
- 🐞 Correcciones menores en traducciones y en la lógica de asignación de misiones al reset diario/semanal.

----------------------------------


## ¡Llegan las misiones diarias y semanales! 🎯 (Versión 1.2)

A partir de esta actualización, los jugadores podrán disfrutar de un nuevo sistema de **misiones** que ofrece recompensas adicionales todos los días y semanas.  

- Recibe hasta 5 misiones automáticamente:  
  • 3 misiones diarias (fáciles y exploratorias)  
  • 2 misiones semanales (de dificultad media y difícil)  

- Completa tus misiones para ganar XP, créditos, packs y cupones.  

- Usa el nuevo comando `/missions list` para ver tus misiones activas, su progreso y para reclamar o cancelar misiones fácilmente.  

¡Podrás avanzar más rápido y obtener mejores recompensas con este sistema!  
Sigue jugando, cumpliendo retos y disfrutando del juego.  

Gracias por tu apoyo continuo y sigue atento a las novedades.