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

---

## 📁 Estructura del proyecto

```text
unahur-bot/
├── .env                    # Variables de entorno (ignorado en Git)
├── .env.example            # Plantilla de variables de entorno
├── .gitignore              # Archivos excluidos del control de versiones
├── MATERIAS.txt            # Listado de materias (una por línea)
├── main.py                 # Punto de entrada del bot y definición de /comandos
├── README.md               # Documentación del proyecto
└── services/               # Lógica de negocio modularizada
    ├── __init__.py         # Interfaz pública del paquete services
    ├── utils.py            # Normalización de texto/canales y lectura de MATERIAS.txt
    ├── roles.py            # Creación y eliminación de roles por materia
    ├── channels.py         # Configuración de categorías, canales y permisos
    └── notices.py          # Envío, fijado y limpieza de avisos de apuntes


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
  Descripción: Abre un selector efímero de etiquetas obligatorias (Carrera y Año desde TAGS_OPINIONES.txt) y un formulario para publicar una opinión anónima sobre una materia, comisión y docente en el canal de Foro configurado (agrupando comentarios si la materia ya tiene un post), registrando la autoría real únicamente en el canal privado de moderación. Contiene un aviso informando del respeto requerido aunque la publicacion sea anonima. 


FLUJO DE TRABAJO RECOMENDADO
============================

Para configurar materias nuevas en el servidor desde cero, ejecuta los comandos en este orden:

1. Agregar las materias nuevas en el archivo MATERIAS.txt (una materia por línea).
2. Ejecutar /crear_roles_materias para generar los roles de cada materia.
3. Ejecutar /crear_canales para crear las categorías y vincular los permisos a los roles recién creados.
4. Ejecutar /aviso_apuntes para publicar y fijar la guía inicial en cada canal de apuntes.

Nota: El rol del bot debe ubicarse por encima de los roles de materias en Ajustes del Servidor -> Roles, y contar con permisos para gestionar roles, canales y mensajes.