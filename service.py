"""
Servicio en segundo plano de SmartExpiry Pro.

Corre de forma independiente a la pantalla principal. Revisa el inventario
una vez al día y manda la alerta de WhatsApp aunque la app esté cerrada.

Android exige que un servicio que corre de forma continua muestre una
notificación permanente mientras está activo (no es un error, es un
requisito del sistema para que el usuario sepa que algo sigue corriendo).
"""
import json
import os
import ssl
import time
import urllib.parse
import urllib.request
from datetime import date

try:
    import certifi
    _CONTEXTO_SSL = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _CONTEXTO_SSL = ssl.create_default_context()

DIAS_ALERTA = 7
SEGUNDOS_ENTRE_REVISIONES = 3600  # cada hora, para detectar el cambio de día


def _ruta_base_de_datos():
    """Usa la misma carpeta privada que la app principal, para leer el
    mismo archivo smart_expiry_db.json."""
    try:
        from android.storage import app_storage_path
        return os.path.join(app_storage_path(), "smart_expiry_db.json")
    except Exception:
        # Si esto falla, el servicio no puede encontrar los datos; se
        # detiene solo en vez de fallar de forma ruidosa.
        return None


def dias_para_vencer(fecha_texto):
    return (date.fromisoformat(fecha_texto) - date.today()).days


def cargar_db(ruta):
    if not ruta or not os.path.exists(ruta):
        return None
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

