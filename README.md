# 🤖 UNAHUR Discord Bot

Bot de administración para el servidor comunitario de estudiantes de la **Universidad Nacional de Hurlingham (UNAHUR)**. Automatiza la creación y limpieza de roles, categorías, canales, avisos fijados y métricas a partir de archivos de texto simples (`MATERIAS.txt` y `TAGS_OPINIONES.txt`).

---

## ✨ Funcionalidades

- **Roles por materia:** Crea o elimina roles individuales según `MATERIAS.txt`, evitando duplicados.
- **Canales por materia:** Genera una categoría privada por materia accesible solo para el rol correspondiente y moderación, con dos canales internos:
  - `#general-<materia>`: Chat de consultas con *slowmode* de 15 segundos.
  - `#apuntes-<materia>`: Canal de solo lectura para material de estudio y resúmenes.
- **Avisos fijados:** Publica y fija la guía estándar en cada canal de apuntes (sin duplicar si ya existe) y permite borrarlos junto con las notificaciones de sistema de Discord.
- **Tablero de métricas:** Mantiene un mensaje fijado en el canal configurado en `METRICS_CHANNEL_ID` con el conteo de inscriptos por carrera y materia. Se actualiza automáticamente (agrupando cambios cada 30 segundos) o de forma manual.
- **Opiniones anónimas (`/opinar_comision`):** Flujo guiado con selección de etiquetas (Carrera y Año desde `TAGS_OPINIONES.txt`) y formulario emergente. Publica en el Foro agrupando las reseñas bajo un mismo post por materia y guarda un registro privado para moderación.

---

## 📁 Estructura del proyecto

```text
unibot/
├── .github/workflows/
│   └── ci-cd.yml         # Linting (flake8), tests (pytest) y deploy
├── services/
│   ├── __init__.py
│   ├── channels.py       # Categorías y canales por materia
│   ├── metrics.py        # Tablero de métricas por carrera y materia
│   ├── notices.py        # Avisos fijados en canales de apuntes
│   ├── opinions.py       # Opiniones anónimas y log de moderación
│   ├── roles.py          # Roles por materia
│   └── utils.py          # Lectura y normalización de archivos .txt
├── tests/
│   └── test_utils.py     # Tests unitarios
├── .env                  # Variables de entorno reales (ignorado en Git)
├── .env.example          # Plantilla de configuración
├── Dockerfile
├── MATERIAS.txt          # Listado de materias (una por línea)
├── TAGS_OPINIONES.txt    # Etiquetas [CARRERAS] y [ANIOS] para opiniones
├── main.py               # Entrada principal, eventos y slash commands
├── pyproject.toml        # Configuración de pytest
├── requirements.txt
└── ui.py                 # Vistas interactivas, confirmaciones y paginado



## ⚙️ Variables de entorno (`.env`)

Tomá `.env.example` como base:

- `DISCORD_TOKEN`: Token del bot[cite: 1].
- `METRICS_CHANNEL_ID`: ID del canal de texto donde se fija el tablero de métricas.
- `OPINIONES_CHANNEL_ID`: ID del canal de Foro para opiniones anónimas.
- `LOGS_OPINIONES_CHANNEL_ID`: ID del canal privado de auditoría para moderación.
- `ROLE_MODERADOR_ID`: ID del rol de moderación.
- `ROLE_CAREER_*_ID`: IDs de los roles de cada carrera.


## 🛠️ Comandos disponibles

Todos los comandos se usan con `/` dentro del servidor. Salvo `/opinar_comision`, son exclusivos para moderación:

- **`/crear_roles_materias`** *(Permiso: Gestionar roles)*
  Crea un rol sin permisos globales por cada materia de `MATERIAS.txt` que aún no exista.

- **`/borrar_roles_materias`** *(Permiso: Gestionar roles)*
  Pide confirmación y elimina del servidor todos los roles que coincidan con `MATERIAS.txt`.

- **`/crear_canales`** *(Permiso: Gestionar canales)*
  Crea o actualiza la categoría de cada materia junto con `general-<materia>` y `apuntes-<materia>`.

- **`/borrar_canales`** *(Permiso: Gestionar canales)* 
  Pide confirmación y elimina las categorías y canales de las materias listadas en `MATERIAS.txt`.

- **`/aviso_apuntes [forzar: True/False]`** *(Permiso: Gestionar canales)*
  Envía y fija el aviso estándar en cada `apuntes-<materia>`. Si `forzar` es `False` (por defecto), saltea los canales que ya lo tienen.

- **`/borrar_aviso_apuntes`** *(Permiso: Gestionar canales)*
  Pide confirmación para desfijar y borrar los avisos del bot en `apuntes-<materia>` y limpiar los mensajes de sistema.

- **`/actualizar_metricas`** *(Permiso: Gestionar canales)*  
  Crea o actualiza manualmente el mensaje fijado con el conteo de inscriptos en el canal configurado en `METRICS_CHANNEL_ID`.

- **`/opinar_comision`** *(Disponible para todos)*
  Abre un selector de etiquetas (Carrera y Año) y un formulario para publicar una reseña anónima en el Foro, previa confirmación de las reglas de respeto.


## 📋 Flujo recomendado para materias nuevas

1. Agregar las materias en `MATERIAS.txt` (una por línea)[cite: 2].
2. Ejecutar `/crear_roles_materias`[cite: 2].
3. Ejecutar `/crear_canales`[cite: 2].
4. Ejecutar `/aviso_apuntes`[cite: 2].
5. Ejecutar `/actualizar_metricas` (o esperar la actualización automática).

> **Importante:** En *Ajustes del Servidor → Roles*, el rol del bot debe estar **por encima** de los roles de materias y tener permisos para gestionar roles, canales y mensajes. Además, debe tener activado el **Server Members Intent** en el Discord Developer Portal.

