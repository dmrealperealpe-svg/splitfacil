# SplitFácil

Aplicación web para dividir gastos entre amigos, familia o compañeros de casa. Proyecto final del curso de Flask (7 temas).

**Cuentas claras, amistades largas.**

## Qué puede hacer
- Crear cuenta, iniciar y cerrar sesión, recuperar contraseña y editar el perfil (nombre, foto-emoji, bio).
- Crear grupos, agregar gastos (partes iguales o montos exactos), registrar pagos y ver quién le debe a quién.
- Invitar a otras personas por correo o por enlace; ellas aceptan o rechazan desde su bandeja.
- Chat del grupo y comentarios en cada gasto (ej.: "yo no tomé licor"), con opción de borrar tus mensajes.
- Agregar personas que no tienen cuenta, solo con su nombre.
- Elegir tema (claro, oscuro, automático) y color de acento.
- Exportar los gastos a CSV (se abre en Excel).
- Zona de administración (solo rol administrador): usuarios, grupos y mensajes de contacto.
- API REST con token personal.

## Cómo correrla en VS Code (Windows)
```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python run.py
```
Abre http://127.0.0.1:5000

Datos de ejemplo: crea tu cuenta y pulsa **Cargar grupos de ejemplo** en el panel.

Administrador: pon `ADMIN_EMAIL` en `.env` y regístrate con ese correo, o ejecuta
`flask --app wsgi crear-admin tucorreo@ejemplo.com`.

Pruebas: `pip install -r requirements-dev.txt` y luego `python -m pytest`.

## Dónde está cada tema del curso
| Tema | Dónde verlo |
|---|---|
| 1. Flask y plantillas | `app/templates/` con Jinja (filtros `cop`, `fecha`, `hace`) |
| 2. Estructura profesional | `create_app`, blueprints en `app/routes/`, `base.html`, `parciales/`, `static/` |
| 3. Base de datos y CRUD | `app/db.py`, `app/datos.py`; grupos, gastos, pagos |
| 4. Formularios, flash y validación | `servicios.validar_*`, `parciales/_avisos.html` |
| 5. Usuarios y seguridad | `routes/auth.py`, hash de contraseñas, sesiones, CSRF, roles, `/admin` da 403 a usuarios normales |
| 6. API REST | `routes/api.py`, documentación en `/desarrolladores` |
| 7. Producción | `wsgi.py`, `Procfile`, `render.yaml`, variables de entorno, PostgreSQL con `DATABASE_URL` |

## Producción
Define `APP_ENV=production`, `SECRET_KEY` (larga y aleatoria) y `DATABASE_URL`. Inicio: `gunicorn wsgi:app`.
Hay un `render.yaml` listo para Render.

## Nota sobre las fuentes
Se usan las fuentes del sistema, así que la app funciona sin conexión y no carga recursos externos.
