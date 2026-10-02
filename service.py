"""
Servicio en segundo plano de SmartExpiry Pro.
"""
import json
import os
import ssl
import time
from datetime import date

try:
    from jnius import autoclass
    ANDROID_AVAILABLE = True
except Exception:
    ANDROID_AVAILABLE = False

try:
    import certifi
    _CONTEXTO_SSL = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _CONTEXTO_SSL = ssl.create_default_context()

DIAS_ALERTA = 7
SEGUNDOS_ENTRE_REVISIONES = 3600


def iniciar_notificacion_foreground():
    """Registra la notificación permanente para evitar que Android API 33 mate el proceso."""
    if not ANDROID_AVAILABLE:
        return

    try:
        PythonService = autoclass('org.kivy.android.PythonService')
        service = PythonService.mService

        String = autoclass('java.lang.String')
        NotificationManager = autoclass('android.app.NotificationManager')
        NotificationChannel = autoclass('android.app.NotificationChannel')
        NotificationBuilder = autoclass('android.app.Notification$Builder')
        Context = autoclass('android.content.Context')

        channel_id = 'smartexpiry_foreground_channel'
        channel_name = String('SmartExpiry Servicio de Alertas')

        notification_service = service.getSystemService(Context.NOTIFICATION_SERVICE)

        importance = NotificationManager.IMPORTANCE_LOW
        channel = NotificationChannel(channel_id, channel_name, importance)
        notification_service.createNotificationChannel(channel)

        builder = NotificationBuilder(service, channel_id)
        builder.setContentTitle(String('SmartExpiry Pro'))
        builder.setContentText(String('Monitoreo de vencimientos activo'))
        builder.setSmallIcon(service.getApplicationInfo().icon)

        notification = builder.build()
        service.startForeground(1001, notification)
    except Exception as e:
        print(f"[SmartExpiry Service] Error startForeground: {e}")


def _ruta_base_de_datos():
    private_dir = os.environ.get("ANDROID_PRIVATE_DIR")
    if private_dir:
        return os.path.join(private_dir, "smart_expiry_db.json")

    try:
        from android.storage import app_storage_path
        return os.path.join(app_storage_path(), "smart_expiry_db.json")
    except Exception:
        return "smart_expiry_db.json"


def dias_para_vencer(fecha_texto):
    try:
        return (date.fromisoformat(str(fecha_texto).strip()) - date.today()).days
    except Exception:
        return 9999


def cargar_db(ruta):
    if not ruta or not os.path.exists(ruta):
        return None
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def revisar_inventario_y_notificar(ruta_db):
    db = cargar_db(ruta_db)
    if not db:
        return

    productos = db.get("productos", []) if isinstance(db, dict) else db
    por_vencer = []

    for item in productos:
        fecha_exp = item.get("fecha_expiracion") or item.get("fecha")
        if fecha_exp:
            dias = dias_para_vencer(fecha_exp)
            if 0 <= dias <= DIAS_ALERTA:
                por_vencer.append((item.get("nombre", "Producto"), dias))

    if por_vencer:
        print(f"[SmartExpiry Service] Se encontraron {len(por_vencer)} productos por vencer.")


if __name__ == "__main__":
    iniciar_notificacion_foreground()
    ruta_db = _ruta_base_de_datos()
    ultima_fecha_revision = None

    while True:
        hoy = date.today()
        if ultima_fecha_revision != hoy:
            revisar_inventario_y_notificar(ruta_db)
            ultima_fecha_revision = hoy

        time.sleep(SEGUNDOS_ENTRE_REVISIONES)
