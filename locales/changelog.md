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

## Versión 1.2 - ¡Llegan las misiones diarias y semanales! (2025-08-11)

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

## 📢 Versión 1.2.1 - Pequeño parche con mejoras (2025-08-12)

🕒 Ahora las misiones muestran un **timestamp** que indica cuánto falta para el próximo reinicio y la posible generación de nuevas misiones. **Importante:** solo se asignarán misiones nuevas si **has completado ✅** o **cancelado ❌** las misiones que tenías en ese momento. Si una misión sigue activa durante el reinicio, **se conservará su progreso** y no será reemplazada — en ese caso **no** se generarán nuevas recompensas hasta que completes o canceles esa misión.

- 📈 Las misiones de nivel **medio** y **difícil** (slots 4 y 5) ahora piden más acciones, pero también aumentaron ligeramente las recompensas en 💵 y XP. 
- ➕ Se arreglaron los timestamp de `/presentation list` para que muestre correctamente la fecha y hora de creación y último movimiento, de acuerdo al horario de cada jugador. 
- 🛠️ Se corrigieron varios bugs y errores menores en distintos comandos.

### 🎵 Nueva canción añadida para presentaciones
- **Sweet Juice** — *Purple Kiss*

_Sigo en proceso de agregar aún más, principalmente de los sets o albums agregados de cada grupo._

----------------------------------

## 📢 Versión 1.2.2 - Colecciones con recompensas + nuevo grupo (2025-08-19)

### 🗂️ Recompensas por colecciones  
Al revisar tus colecciones con `/collections`, ahora tendrás la posibilidad de recibir **recompensas** automáticamente cuando completes una colección de un **set** o un **set + idol**.  
- 🔑 Solo las colecciones que incluyen cartas de tipo **POB** o **FCR** entregan recompensas en esta primera implementación. Posteriormente se agregarán las cartas restantes de los sets ya integrados para su entrega de recompensas. 
- 💡 El sistema verifica en el momento de la consulta si tu colección está completa y, de ser así, entrega la recompensa una sola vez.

> Esto busca dar más valor a completar los sets, fomentar la colección y abrir la puerta a un sistema más amplio de logros y recompensas en el futuro.

### 🌟 Nuevas cartas disponibles: ARTMS y Yves  
Se añadió al juego el grupo **ARTMS** y a la solista **Yves**.

### ⚙️ Mejoras y correcciones  
- ⚡ Se optimizó la respuesta del bot para reducir la latencia que venía afectando algunos comandos en la última semana.  
- 🛠️ Correcciones menores de bugs y ajustes internos para mayor estabilidad.  

----------------------------------

## 📢 Versión 1.2.3 - Cupones canjeables (2025-08-22)

### 🎟️ Funciones y nuevos cupones  
Se ha agregado e implementado el funcionamiento de varios cupones en el juego:  

- **Training** → Ahora puedes canjear **Performance Cards** con el comando `/redeem p_card`, eligiendo la que desees.  
- **🆕 Reroll Skills** → Usado con `/redeem skill_reroll`, permite regenerar las habilidades de una carta ingresando su `card_id`.  
- **🆕 Upgrade Card** → Usado con `/redeem upgrade`, permite subir de nivel las cartas **Regular** hasta un máximo de nivel 3, ingresando su `card_id`.  

_Todos los cupones pueden obtenerse (con baja probabilidad) en cualquier Pack (a menos que sea solo de cartas idol garantizadas, como Individual Pack, POB Pack, Star Pack o MiniStar Pack)_

### ⚙️ Mejoras y correcciones  
- 🖼️ Corregido un problema en `/cards view` que permitía mostrar la imagen de cualquier carta si se usaba un `unique_id` válido con un `card_id` de la carta que se quisiera ver. Aunque no afectaba el progreso ni se podía aprovechar en la práctica, se consideró un bug visual y fue arreglado.
- 🌐 Ajustados errores en varios textos.  
- 🛠️ Ahora los cupones que no se usan directamente desde el inventario incluyen en su descripción el comando con el que deben ser utilizados.  

----------------------------------

## 📢 Versión 1.2.4 - Nuevo contenido y mejoras (2025-08-25)

### 🎶 Nuevas canciones disponibles  
- Agregada **Into the New World** para usarse en presentaciones.  

### 🃏 Nuevas cartas  
- Se añadieron cartas **FCR** y **POB** de **Chuu**.  
- Se añadieron cartas **FCR** y **POB** de todas las integrantes de **Loossemble**.  

### ⚙️ Mejoras y correcciones  
- 🎼 Ahora, al terminar una presentación, se muestra también el **nombre de la canción presentada**, junto con la **puntuación obtenida** y la **puntuación promedio esperada**.  

----------------------------------

## 📢 Versión 1.2.5 - Transferencias y cumpleaños (2025-08-26)

### 💸 Nuevas funciones bancarias  
Se agregó el comando **`/bank send_credits`** para enviar créditos a otros jugadores.  
- Incluye una comisión del **5% FAME** (Fee for Artistic Monetary Exchange).  
- Cada transacción aplica un **mínimo de 💵50 en FAME**, incluso si el monto enviado es menor.  
- Si el jugador receptor tiene notificaciones activadas, recibirá un **DM automático** informándole del dinero recibido.  

### 🎂 Función especial de cumpleaños  
- Se añadió el comando **`/mod birthday`** para registrar cumpleaños.  
- Durante agosto, quienes cumplan años favor de mencionarlo, pues podrán recibir **recompensas especiales** 👀.

### ⚙️ Otros ajustes
- Mejoras internas menores para asegurar un correcto funcionamiento de las nuevas funciones.  

----------------------------------

## 📢 Versión 1.2.6 - Sorteos y bonificación semanal (2025-08-27)

### :tickets: Nuevo comando de sorteos
Se agregó el comando **`/giveaways`**, inicialmente disponible solo para **moderadores y administradores**.  
- Permite organizar **sorteos de cartas** en el servidor.  
- Los jugadores podrán **unirse con un botón** y recibir la carta cuando termine el sorteo.  
> :warning: Más adelante se abrirá para todos los jugadores, junto con otras opciones.

### :sparkles: Bonificación semanal en presentaciones
Al realizar una presentación con un **grupo por primera vez en la semana**, se obtiene **+30% de popularidad extra**.  
- Cada grupo tiene disponible este **bono una vez por semana**.  
- Incentiva a que los jugadores con varios grupos los usen activamente, en lugar de que solo generen gastos adicionales.

### :gear: Otros cambios
- Mejoras internas y ajustes de balance menores.

----------------------------------

## 📢 Parche 1.2.6.1 - Pequeñas mejoras y proyección semanal (2025-09-01)

### 🎟️ Ticker de _Exclusive Content_
Ahora es posible usar estos tickets para obtener dinero. Al usarlo, deberás elegir un grupo. La cantidad de dinero obtenida depende de la popularidad actual de ese grupo, _contando como 24h de sponsor únicamente con ese grupo._

### ⚙️ Otros ajustes
- Mejoras internas menores para asegurar un correcto funcionamiento de las nuevas funciones.  

### Proyección a futuro
De acuerdo a los resultados **preliminares** de la **encuesta** actual, durante la semana estaré enfocado en **agregar más grupos y canciones** nuevos. Por ello, es posible que no se agreguen nuevas mecánicas al juego en este tiempo. Sin embargo, todo lo planeado llegará eventualmente. Les agradezco muchísimo su participación durante este primer mes de juego, espero que poco a poco seamos más en esta comunidad. Sigo atento a sus comentarios, feedback, sugerencias, entre otras cosas.

_Probablemente en este tiempo esté subiendo algunas imagenes de cartas a la cuenta de Insta  también jsjs_
