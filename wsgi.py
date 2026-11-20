"""Punto de entrada para producción (Tema 7).   gunicorn wsgi:app

El servidor importa `app` desde aquí. Antes de arrancar define APP_ENV=production
y SECRET_KEY como variables de entorno (ver .env.example).
"""
from app import create_app

app = create_app()
