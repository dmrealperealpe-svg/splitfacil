"""Envío de correos (opcional). Si no configuras MAIL_SERVER, la app sigue funcionando."""
import smtplib
from email.message import EmailMessage

from flask import current_app


def configurado():
    return bool(current_app.config.get("MAIL_SERVER"))


def enviar(destino, asunto, cuerpo):
    cfg = current_app.config
    mensaje = EmailMessage()
    mensaje["Subject"] = asunto
    mensaje["From"] = cfg["MAIL_FROM"] or cfg["MAIL_USER"]
    mensaje["To"] = destino
    mensaje.set_content(cuerpo)
    with smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=10) as servidor:
        servidor.starttls()
        if cfg["MAIL_USER"]:
            servidor.login(cfg["MAIL_USER"], cfg["MAIL_PASSWORD"])
        servidor.send_message(mensaje)
