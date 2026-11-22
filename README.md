# 🤖 UNAHUR Discord Bot

Bot de administración automatizada para el servidor comunitario de estudiantes de la **Universidad Nacional de Hurlingham (UNAHUR)**[cite: 1]. Permite gestionar de forma masiva roles, categorías, canales y avisos fijados por materia a partir de un archivo de configuración (`MATERIAS.txt`).

---

## ✨ Características principales

* **Gestión masiva de roles:** Crea o elimina roles individuales para cada materia evitando duplicados.
* **Estructura automática de canales:** Genera una categoría privada por materia con acceso exclusivo para el rol correspondiente y moderación, incluyendo:
  * `#general-<materia>`: Canal de consultas y chat con *slowmode* de 15 segundos.
  * `#apuntes-<materia>`: Canal de solo lectura para alumnos destinado a material de estudio y resúmenes[cite: 2, 3].
* **Avisos fijados automáticos:** Publica y fija un mensaje informativo en cada canal de apuntes (evitando duplicados) y permite desfijarlos y limpiar notificaciones del sistema.
* **Slash Commands (`/`) nativos:** Integración con `discord.app_commands`, permisos nativos de Discord y respuestas efímeras divididas automáticamente para respetar el límite de caracteres.
* **Tablero dinámico de métricas (`#📊・metricas`):** Genera y actualiza automáticamente en tiempo real (con *cooldown* anti rate-limit) un mensaje fijado con el conteo de estudiantes inscriptos por carrera y materia.
* **Opiniones anónimas de comisiones (`/opinar_comision`):** Permite a los estudiantes enviar reseñas anónimas sobre materias y docentes mediante un flujo guiado (selección de etiquetas de carrera/año desde `TAGS_OPINIONES.txt` + formulario emergente). Publica en el canal de Foro agrupando opiniones por materia.
* **Calidad y CI/CD:** Código bajo estándar PEP 8 (`flake8` a 100 caracteres), tests unitarios con `pytest`, contenedorización con Docker y flujo automatizado en GitHub Actions.

---

## 📁 Estructura del proyecto

```text
unibot/
├── .github/
│   └── workflows/
│       └── ci-cd.yml         # Pipeline de linting (flake8), tests (pytest) y deploy
├── services/                 # Lógica de negocio modularizada
│   ├── __init__.py
│   ├── channels.py           # Creación y borrado de categorías y canales
│   ├── metrics.py            # Tablero dinámico de métricas
│   ├── notices.py            # Gestión de avisos fijados
│   ├── opinions.py           # Flujo de opiniones anónimas y logs de moderación
│   ├── roles.py              # Creación y borrado de roles
│   └── utils.py              # Lectura y normalización de archivos .txt
├── tests/
│   └── test_utils.py         # Tests unitarios con pytest
├── .env                      # Variables de entorno reales (ignorado en Git)
├── .env.example              # Plantilla de variables de entorno
├── .gitignore
├── Dockerfile                # Imagen Docker para producción
├── MATERIAS.txt              # Listado de materias (una por línea)
├── TAGS_OPINIONES.txt        # Etiquetas de carreras y años para el foro de opiniones
├── main.py                   # Punto de entrada, eventos y slash commands
├── pyproject.toml            # Configuración de pytest (pythonpath)
├── requirements.txt          # Dependencias del proyecto
└── ui.py                     # Vistas interactivas, botones y menús desplegables

COMANDOS DISPONIBLES
====================

Todos los comandos se ejecutan dentro de un servidor usando barra (/) y requieren permisos administrativos específicos:

- /crear_roles_materias
  Permiso requerido: Gestionar roles (manage_roles)
  Descripción: Lee MATERIAS.txt y crea un rol sin permisos globales por cada materia que aún no exista.

- /borrar_roles_materias
  Permiso requerido: Gestionar roles (manage_roles)
  Descripción: Solicita confirmación interactiva y elimina del servidor todos los roles que coincidan con el listado de MATERIAS.txt.

- /crear_canales
  Permiso requerido: Gestionar canales (manage_channels)
  Descripción: Crea o actualiza la categoría de cada materia y sus canales general-<materia> y apuntes-<materia> con los permisos correspondientes.

- /borrar_canales
  Permiso requerido: Gestionar canales (manage_channels)
  Descripción: Solicita confirmación interactiva y elimina las categorías y canales internos (general-<materia> y apuntes-<materia>) que coincidan con MATERIAS.txt.

- /aviso_apuntes [forzar: True/False]
  Permiso requerido: Gestionar canales (manage_channels)
  Descripción: Envía y fija el mensaje estándar en todos los canales apuntes-<materia>. Si el parámetro opcional "forzar" es False (por defecto), omite los canales que ya tienen el aviso.

- /borrar_aviso_apuntes
  Permiso requerido: Gestionar canales (manage_channels)
  Descripción: Solicita confirmación interactiva para desfijar y eliminar los avisos enviados por el bot en apuntes-<materia>, junto con las notificaciones del sistema de mensajes fijados.

- /opinar_comision
  Permiso requerido: Ninguno (disponible para todos los usuarios del servidor)
  Descripción: Abre un selector efímero de etiquetas obligatorias (Carrera y Año desde TAGS_OPINIONES.txt) y un formulario para publicar una opinión anónima sobre una materia, comisión y docente en el canal de Foro configurado (agrupando comentarios si la materia ya tiene un post), con un aviso informando del respeto requerido aunque la publicacion sea anonima. 


FLUJO DE TRABAJO RECOMENDADO
============================

Para configurar materias nuevas en el servidor desde cero, ejecuta los comandos en este orden:

1. Agregar las materias nuevas en el archivo MATERIAS.txt (una materia por línea).
2. Ejecutar /crear_roles_materias para generar los roles de cada materia.
3. Ejecutar /crear_canales para crear las categorías y vincular los permisos a los roles recién creados.
4. Ejecutar /aviso_apuntes para publicar y fijar la guía inicial en cada canal de apuntes.

Nota: El rol del bot debe ubicarse por encima de los roles de materias en Ajustes del Servidor -> Roles, y contar con permisos para gestionar roles, canales y mensajes.