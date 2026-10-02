# SmartExpiry Pro - Fase 2: interfaz Kivy
# Misma lógica de la Fase 1, ahora con pantalla táctil.
# Este archivo se llama main.py porque Buildozer lo necesitará así.

import json
import os
import ssl
import threading
import time
import urllib.parse
import urllib.request
from calendar import monthrange
from datetime import date, timedelta

try:
    import certifi
    _CONTEXTO_SSL = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _CONTEXTO_SSL = ssl.create_default_context()

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import ListProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scatter import Scatter
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import escape_markup, platform

UNIDADES = ["Unidad", "Litro", "Mililitro (ml)", "Onza (oz)", "Paquete", "Caja"]
NOMBRES_MES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
               "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

# ---------- Tema visual: una sola paleta de colores para toda la app ----------
COLOR_FONDO = (0.06, 0.07, 0.09, 1)
COLOR_PANEL = (0.12, 0.14, 0.17, 1)
COLOR_CAMPO = (0.18, 0.20, 0.24, 1)
COLOR_ACENTO = (0.30, 0.48, 0.68, 1)
COLOR_ACENTO_OSCURO = (0.20, 0.33, 0.48, 1)
COLOR_NEUTRO = (0.27, 0.29, 0.33, 1)
COLOR_PELIGRO = (0.75, 0.20, 0.19, 1)
COLOR_TEXTO = (0.96, 0.97, 0.99, 1)
COLOR_TEXTO_TENUE = (0.63, 0.67, 0.73, 1)
COLOR_TARJETA_OK = (0.14, 0.30, 0.38, 1)
COLOR_TARJETA_WARN = (0.46, 0.35, 0.12, 1)
COLOR_TARJETA_DANGER = (0.46, 0.20, 0.19, 1)

Window.clearcolor = COLOR_FONDO
Window.softinput_mode = "below_target"  # Mantiene visible el campo donde escribes

# Permisos en tiempo de ejecución para Android
if platform == "android":
    from android.permissions import Permission, check_permission, request_permissions
else:
    Permission = check_permission = request_permissions = None

CAMARA_DISPONIBLE = True
_error_camara = ""

try:
    if platform == "android":
        import ctypes
        from jnius import autoclass
        _actividad = autoclass("org.kivy.android.PythonActivity").mActivity
        _carpeta_libs = _actividad.getApplicationInfo().nativeLibraryDir
        try:
            ctypes.CDLL(os.path.join(_carpeta_libs, "libzbar.so"))
        except OSError:
            pass

    from pyzbar.pyzbar import decode as zbar_decode
    from PIL import Image as PILImage
    from kivy.uix.camera import Camera
except Exception as _e:
    CAMARA_DISPONIBLE = False
    _error_camara = str(_e)
    zbar_decode = None
    PILImage = None
    Camera = None

def _rotacion_pantalla_actual():
    """Grados que la pantalla está rotada ahora mismo (0/90/180/270). Solo Android."""
    if platform != "android":
        return 0
    try:
        from jnius import autoclass
        actividad = autoclass("org.kivy.android.PythonActivity").mActivity
        codigo = actividad.getWindowManager().getDefaultDisplay().getRotation()
        return {0: 0, 1: 90, 2: 180, 3: 270}.get(codigo, 0)
    except Exception:
        return 0


DIAS_ALERTA = 7


# ---------- Lógica ----------

def dias_para_vencer(fecha_texto):
    try:
        return (date.fromisoformat(fecha_texto) - date.today()).days
    except (ValueError, TypeError):
        return 0


def estado(dias):
    """Devuelve el texto de estado y el color de tarjeta correspondiente."""
    if dias < 0:
        return "VENCIDO", COLOR_TARJETA_DANGER
    if dias <= DIAS_ALERTA:
        return f"POR VENCER ({dias}d)", COLOR_TARJETA_WARN
    return f"OK ({dias}d)", COLOR_TARJETA_OK


def lotes_ordenados(db, filtro=""):
    filtro = filtro.lower().strip()
    resultado = []
    for lote in db.get("inventario", []):
        prod_info = db.get("catalogo", {}).get(lote.get("codigo_upc", "")) or {}
        nombre = prod_info.get("nombre") or ""
        codigo = lote.get("codigo_upc", "")
        if filtro in nombre.lower() or filtro in codigo.lower():
            resultado.append(lote)
    return sorted(resultado, key=lambda l: l.get("fecha_vencimiento", ""))


# ---------- Diseño de la pantalla (lenguaje KV) ----------

KV = """
#:import Clock kivy.clock.Clock
#:import COLOR_ACENTO __main__.COLOR_ACENTO
#:import COLOR_ACENTO_OSCURO __main__.COLOR_ACENTO_OSCURO
#:import COLOR_CAMPO __main__.COLOR_CAMPO
#:import COLOR_NEUTRO __main__.COLOR_NEUTRO
#:import COLOR_PANEL __main__.COLOR_PANEL
#:import COLOR_TEXTO __main__.COLOR_TEXTO
#:import COLOR_TEXTO_TENUE __main__.COLOR_TEXTO_TENUE

<Button>:
    background_normal: ''
    background_down: ''
    background_color: COLOR_ACENTO if self.state == 'normal' else COLOR_ACENTO_OSCURO
    color: COLOR_TEXTO
    on_release: Clock.schedule_once(lambda dt: setattr(self, 'state', 'normal'), 0)

<TextInput>:
    background_color: COLOR_CAMPO
    foreground_color: COLOR_TEXTO
    hint_text_color: COLOR_TEXTO_TENUE
    cursor_color: COLOR_ACENTO
    padding: [dp(10), dp(10), dp(10), dp(10)]

<Label>:
    color: COLOR_TEXTO

<SpinnerOption>:
    background_normal: ''
    background_down: ''
    background_color: COLOR_CAMPO
    color: COLOR_TEXTO
    size_hint_y: None
    height: dp(46)
    padding: [dp(12), dp(4)]
    on_release: Clock.schedule_once(lambda dt: setattr(self, 'state', 'normal'), 0)

<Popup>:
    title_color: COLOR_TEXTO
    title_size: '17sp'
    separator_color: COLOR_ACENTO
    background_color: (0.22, 0.30, 0.25, 1)

<FilaLote>:
    background_normal: ''
    background_down: ''
    background_color: 0, 0, 0, 0
    color: COLOR_TEXTO
    markup: True
    halign: 'left'
    valign: 'middle'
    text_size: self.width - dp(28), self.height
    font_size: '15sp'
    on_release: Clock.schedule_once(lambda dt: setattr(self, 'state', 'normal'), 0)
    canvas.before:
        Color:
            rgba: self.color_estado
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]

<BotonFAB>:
    background_normal: ''
    background_down: ''
    background_color: 0, 0, 0, 0
    color: COLOR_TEXTO
    on_release: Clock.schedule_once(lambda dt: setattr(self, 'state', 'normal'), 0)
    canvas.before:
        Color:
            rgba: 0.04, 0.10, 0.07, 0.55
        Ellipse:
            pos: self.x - dp(2), self.y - dp(5)
            size: self.width + dp(4), self.height + dp(4)
        Color:
            rgba: COLOR_ACENTO if self.state == 'normal' else COLOR_ACENTO_OSCURO
        Ellipse:
            pos: self.pos
            size: self.size

<BotonRedondeado>:
    background_normal: ''
    background_down: ''
    background_color: COLOR_ACENTO
    color: COLOR_TEXTO
    on_release: Clock.schedule_once(lambda dt: setattr(self, 'state', 'normal'), 0)
    canvas.before:
        Color:
            rgba: self.background_color if self.state == 'normal' else COLOR_ACENTO_OSCURO
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(14)]

FloatLayout:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(12)
        spacing: dp(10)
        canvas.before:
            Color:
                rgba: COLOR_PANEL
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [dp(16)]
        Label:
            id: titulo
            size_hint_y: None
            height: dp(40)
            font_size: '18sp'
            bold: True
            color: COLOR_ACENTO
            halign: 'left'
            text_size: self.size
        BoxLayout:
            size_hint_y: None
            height: dp(46)
            spacing: dp(8)
            TextInput:
                id: buscar
                hint_text: 'Buscar producto o UPC...'
                multiline: False
                on_text: app.refrescar()
            BotonRedondeado:
                text: 'Ajustes'
                size_hint_x: None
                width: dp(100)
                background_color: COLOR_NEUTRO
                on_release: app.abrir_configuracion()
            BotonRedondeado:
                text: 'Escanear'
                size_hint_x: None
                width: dp(110)
                on_release: app.abrir_escaneo('filtro')
        RecycleView:
            id: rv
            viewclass: 'FilaLote'
            RecycleBoxLayout:
                default_size: None, dp(76)
                default_size_hint: 1, None
                size_hint_y: None
                height: self.minimum_height
                orientation: 'vertical'
                spacing: dp(8)
    BotonFAB:
        text: '+'
        font_size: '32sp'
        size_hint: None, None
        size: dp(64), dp(64)
        pos_hint: {'right': 0.97, 'y': 0.03}
        on_release: app.abrir_escaneo('nuevo')
"""


class FilaLote(Button):
    id_lote = StringProperty("")
    color_estado = ListProperty(COLOR_TARJETA_OK)

    def on_release(self):
        App.get_running_app().abrir_detalle(self.id_lote)


class BotonFAB(Button):
    pass


class BotonRedondeado(Button):
    pass


class SmartExpiryApp(App):

    # ----- Inicio y datos -----

    def build(self):
        self.archivo = os.path.join(self.user_data_dir, "smart_expiry_db.json")
        self.db = self.cargar_db()
        return Builder.load_string(KV)

    def on_start(self):
        self.refrescar()
        self._revisar_alerta_diaria()
        self._arrancar_servicio_de_fondo()

    def _arrancar_servicio_de_fondo(self):
        if platform != "android":
            return
        try:
            from jnius import autoclass
            nombre_paquete = "org.smartexpiry.smartexpiry"
            ServicioAlertas = autoclass(f"{nombre_paquete}.ServiceAlertas")
            actividad = autoclass("org.kivy.android.PythonActivity").mActivity
            ServicioAlertas.start(actividad, "")
        except Exception:
            pass

    def _db_defecto(self):
        return {
            "catalogo": {},
            "inventario": [],
            "config": {
                "rotacion_camara": 0,
                "rotacion_pantalla_base": 0,
                "whatsapp_telefono": "",
                "whatsapp_apikey": "",
                "whatsapp_ultima_alerta": ""
            }
        }

    def cargar_db(self):
        if not os.path.exists(self.archivo):
            return self._db_defecto()
        try:
            with open(self.archivo, "r", encoding="utf-8") as f:
                datos = json.load(f)
        except Exception:
            return self._db_defecto()

        config = datos.setdefault("config", {})
        config.setdefault("rotacion_camara", 0)
        config.setdefault("rotacion_pantalla_base", 0)
        config.setdefault("whatsapp_telefono", "")
        config.setdefault("whatsapp_apikey", "")
        config.setdefault("whatsapp_ultima_alerta", "")
        datos.setdefault("catalogo", {})
        datos.setdefault("inventario", [])
        return datos

    def guardar_db(self):
        try:
            with open(self.archivo, "w", encoding="utf-8") as f:
                json.dump(self.db, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error guardando DB: {e}")

    # ----- Lista principal -----

    def refrescar(self):
        ids = self.root.ids
        lotes = lotes_ordenados(self.db, ids.buscar.text)
        datos = []
        for lote in lotes:
            producto = self.db.get("catalogo", {}).get(lote.get("codigo_upc", "")) or {}
            nombre_raw = producto.get("nombre") or "Sin nombre"
            nombre = escape_markup(nombre_raw)
            unidad_raw = producto.get("unidad") or ""
            unidad = escape_markup(unidad_raw)

            detalle = f"UPC {lote.get('codigo_upc', '')}"
            if unidad and unidad != "Unidad":
                detalle = f"{detalle} · {unidad}"

            dias = dias_para_vencer(lote.get("fecha_vencimiento", ""))
            texto_estado, color = estado(dias)
            datos.append({
                "text": (f"[b]{nombre}[/b] {detalle}\n"
                         f"Cant: {lote.get('cantidad', 0)} | Vence: {lote.get('fecha_vencimiento', '')} | {texto_estado}"),
                "color_estado": color,
                "id_lote": lote.get("id_lote", ""),
            })
        ids.rv.data = datos

        por_vencer = sum(1 for l in self.db.get("inventario", [])
                         if dias_para_vencer(l.get("fecha_vencimiento", "")) <= DIAS_ALERTA)
        ids.titulo.text = (f"SmartExpiry Pro | {len(self.db.get('inventario', []))} lotes | "
                           f"{por_vencer} por vencer")

    # ----- Ayudas para armar diálogos -----

    def _fila_botones(self, *pares):
        fila = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(10))
        for texto, accion in pares:
            boton = BotonRedondeado(text=texto)
            t_lower = texto.strip().lower()
            if t_lower in ("cancelar", "cerrar", "entendido"):
                boton.background_color = COLOR_NEUTRO
            elif t_lower in ("eliminar lote", "dar de baja"):
                boton.background_color = COLOR_PELIGRO

            def envoltura(instancia, accion=accion):
                instancia.state = "normal"
                accion(instancia)

            boton.bind(on_release=envoltura)
            fila.add_widget(boton)
        return fila

    def _campo(self, contenido, etiqueta, texto="", solo_numeros=False):
        contenido.add_widget(Label(text=etiqueta, size_hint_y=None, height=dp(24),
                                   halign="left", text_size=(dp(300), None)))
        campo = TextInput(text=str(texto) if texto is not None else "", multiline=False, size_hint_y=None, height=dp(46),
                          input_filter="int" if solo_numeros else None)
        contenido.add_widget(campo)
        return campo

    def _mensaje(self, contenido):
        msg = Label(text="", color=(1, 0.5, 0.45, 1), size_hint_y=None, height=dp(28))
        contenido.add_widget(msg)
        return msg

    # ----- Punto de entrada: elegir cámara o escritura manual -----

    def abrir_escaneo(self, modo):
        contenido = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(10))
        contenido.add_widget(Label(text="Elige cómo quieres registrar el código",
                                   size_hint_y=None, height=dp(30)))

        def usar_camara(*_):
            popup.dismiss()
            self.abrir_camara(modo)

        def usar_manual(*_):
            popup.dismiss()
            self.abrir_manual(modo)

        contenido.add_widget(self._fila_botones(
            ("Cámara", usar_camara),
            ("Escribir a mano", usar_manual)))
        contenido.add_widget(self._fila_botones(
            ("Cancelar", lambda *_: popup.dismiss()),))
        popup = Popup(title="Registrar producto", content=contenido,
                      size_hint=(0.85, None), height=dp(220), auto_dismiss=False)
        popup.open()

    def _procesar_codigo(self, upc, modo):
        if modo == "filtro":
            self.root.ids.buscar.text = upc
            return
        if upc in self.db.get("catalogo", {}):
            self.abrir_lote(upc, es_nuevo=False)
            return

        self._mostrar_buscando()

        def al_terminar(nombre, cantidad_texto, error_texto):
            self._cerrar_buscando()
            aviso = ""
            if error_texto:
                aviso = self._mensaje_amigable_red(error_texto)

            self.abrir_lote(upc, es_nuevo=True, prellenado={
                "nombre": nombre or "",
                "descripcion": cantidad_texto or "",
                "encontrado": bool(nombre),
                "aviso_error": aviso
            })

        self._consultar_openfoodfacts(upc, al_terminar)

    def _consultar_openfoodfacts(self, upc, on_listo, intento=1):
        def tarea():
            nombre = None
            cantidad_texto = ""
            error_texto = ""
            try:
                url = f"https://world.openfoodfacts.org/api/v2/product/{upc}.json"
                peticion = urllib.request.Request(
                    url, headers={"User-Agent": "SmartExpiryPro/1.0"})
                with urllib.request.urlopen(peticion, timeout=8,
                                            context=_CONTEXTO_SSL) as resp:
                    datos = json.loads(resp.read().decode("utf-8"))
                if datos.get("status") == 1:
                    producto = datos.get("product", {})
                    nombre = (producto.get("product_name_es")
                              or producto.get("product_name") or None)
                    cantidad_texto = producto.get("quantity", "") or ""
            except Exception as e:
                error_texto = f"{type(e).__name__}: {e}"

            if error_texto and intento < 2:
                time.sleep(1.5)
                Clock.schedule_once(
                    lambda dt: self._consultar_openfoodfacts(upc, on_listo, intento + 1), 0)
                return

            Clock.schedule_once(lambda dt: on_listo(nombre, cantidad_texto, error_texto), 0)

        threading.Thread(target=tarea, daemon=True).start()

    @staticmethod
    def _mensaje_amigable_red(error_texto):
        minuscula = error_texto.lower()
        if "timed out" in minuscula or "timeout" in minuscula:
            return "La conexión está muy lenta."
        if ("gaierror" in minuscula or "name or service not known" in minuscula
                or "network is unreachable" in minuscula or "nodename" in minuscula):
            return "Sin conexión a internet."
        if "certificate" in minuscula or "ssl" in minuscula:
            return "Error de certificado SSL."
        return "No se pudo consultar Open Food Facts."

    def _mostrar_buscando(self):
        contenido = BoxLayout(orientation="vertical", padding=dp(20))
        contenido.add_widget(Label(text="Buscando en Open Food Facts..."))
        self._popup_buscando = Popup(title="Un momento", content=contenido,
                                     size_hint=(0.8, None), height=dp(140),
                                     auto_dismiss=False)
        self._popup_buscando.open()

    def _cerrar_buscando(self):
        if getattr(self, "_popup_buscando", None):
            self._popup_buscando.dismiss()
            self._popup_buscando = None

    # ----- Escritura manual -----

    def abrir_manual(self, modo):
        contenido = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        campo = self._campo(contenido, "Escribe el código UPC", solo_numeros=True)
        contenido.add_widget(Label())

        def aceptar(*_):
            upc = campo.text.strip()
            if not upc:
                return
            popup.dismiss()
            self._procesar_codigo(upc, modo)

        contenido.add_widget(self._fila_botones(
            ("Cancelar", lambda *_: popup.dismiss()),
            ("Aceptar", aceptar)))
        popup = Popup(title="Escribir código", content=contenido,
                      size_hint=(0.9, None), height=dp(260), auto_dismiss=False)
        popup.open()

    def _angulo_camara_actual(self):
        config = self.db.get("config", {})
        pantalla_ahora = _rotacion_pantalla_actual()
        diferencia = (pantalla_ahora - config.get("rotacion_pantalla_base", 0)) % 360
        return (config.get("rotacion_camara", 0) + diferencia) % 360

    # ----- Escaneo con la cámara -----

    def abrir_camara(self, modo):
        if not CAMARA_DISPONIBLE:
            self._mostrar_aviso(
                "El escaneo con cámara no está disponible.\n"
                "Usa 'Escribir a mano' por ahora.\n\n"
                f"Detalle: {_error_camara[:120]}")
            return

        if platform == "android" and check_permission is not None:
            if not check_permission(Permission.CAMERA):
                request_permissions([Permission.CAMERA])
                self._mostrar_aviso("Concede el permiso de cámara y vuelve a intentar.")
                return

        contenido = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        try:
            camara = Camera(play=True, resolution=(640, 480))
        except Exception:
            contenido.add_widget(Label(
                text="No se pudo abrir la cámara en este dispositivo.\n"
                     "Usa la opción de escribir a mano."))
            contenido.add_widget(self._fila_botones(
                ("Cerrar", lambda *_: popup.dismiss())))
            popup = Popup(title="Cámara no disponible", content=contenido,
                          size_hint=(0.9, None), height=dp(220), auto_dismiss=False)
            popup.open()
            return

        contenedor = Scatter(do_rotation=False, do_scale=False, do_translation=False,
                             size_hint=(None, None), size=(dp(320), dp(320)),
                             pos_hint={"center_x": 0.5})
        camara.size_hint = (None, None)
        camara.size = (dp(320), dp(320))
        contenedor.rotation = self._angulo_camara_actual()
        contenedor.add_widget(camara)

        envoltorio = BoxLayout(size_hint_y=None, height=dp(320))
        envoltorio.add_widget(Widget())
        envoltorio.add_widget(contenedor)
        envoltorio.add_widget(Widget())
        contenido.add_widget(envoltorio)

        estado_txt = Label(text="Preparando cámara...", size_hint_y=None, height=dp(30))
        contenido.add_widget(estado_txt)

        def girar(*_):
            nueva = (contenedor.rotation + 90) % 360
            contenedor.rotation = nueva
            contenedor.center = (dp(160), dp(160))
            self.db["config"]["rotacion_camara"] = nueva
            self.db["config"]["rotacion_pantalla_base"] = _rotacion_pantalla_actual()
            self.guardar_db()

        contenido.add_widget(self._fila_botones(
            ("Girar imagen", girar),
            ("Cancelar", lambda *_: cerrar())))

        popup = Popup(title="Escaneando", content=contenido,
                      size_hint=(0.95, None), height=dp(520), auto_dismiss=False)

        tarea = None
        fotogramas_a_descartar = [6]
        analizando = [False]
        activo = [True]

        def intentar_leer(dt):
            if not activo[0]:
                return
            if fotogramas_a_descartar[0] > 0:
                fotogramas_a_descartar[0] -= 1
                if fotogramas_a_descartar[0] == 0:
                    estado_txt.text = "Apunta al código de barras..."
                return
            if analizando[0]:
                return
            textura = camara.texture
            if textura is None:
                return
            ancho, alto = textura.size
            datos = textura.pixels
            fmt_str = (textura.colorfmt or "RGBA").upper()
            analizando[0] = True

            def analizar_en_segundo_plano():
                codigo = None
                try:
                    if fmt_str in ("RGBA", "RGB", "BGRA", "BGR"):
                        imagen = PILImage.frombytes(fmt_str, (ancho, alto), datos).convert("L")
                    else:
                        imagen = PILImage.frombytes("RGBA", (ancho, alto), datos).convert("L")

                    resultados = zbar_decode(imagen)
                    if resultados:
                        codigo = resultados[0].data.decode("utf-8", errors="ignore").strip()
                except Exception:
                    codigo = None

                def terminar(dt2):
                    analizando[0] = False
                    if codigo and activo[0]:
                        cerrar()
                        self._procesar_codigo(codigo, modo)
                Clock.schedule_once(terminar, 0)

            threading.Thread(target=analizar_en_segundo_plano, daemon=True).start()

        def cerrar(*_):
            activo[0] = False
            if tarea:
                tarea.cancel()
            camara.play = False
            if camara in contenedor.children:
                contenedor.remove_widget(camara)
            popup.dismiss()

        tarea = Clock.schedule_interval(intentar_leer, 0.3)
        popup.open()

    def _mostrar_aviso(self, texto):
        contenido = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        contenido.add_widget(Label(text=texto))
        contenido.add_widget(self._fila_botones(
            ("Entendido", lambda *_: aviso.dismiss())))
        aviso = Popup(title="Aviso", content=contenido,
                     size_hint=(0.85, None), height=dp(200), auto_dismiss=False)
        aviso.open()

    # ----- Alertas por WhatsApp (CallMeBot) -----

    def _enviar_whatsapp(self, mensaje, al_terminar=None):
        telefono = self.db.get("config", {}).get("whatsapp_telefono", "").strip()
        apikey = self.db.get("config", {}).get("whatsapp_apikey", "").strip()
        if not telefono or not apikey:
            if al_terminar:
                Clock.schedule_once(
                    lambda dt: al_terminar(False, "Falta configurar teléfono o API Key."), 0)
            return

        def tarea():
            ok, error_texto = True, ""
            try:
                url = ("https://api.callmebot.com/whatsapp.php"
                       f"?phone={urllib.parse.quote(telefono)}"
                       f"&text={urllib.parse.quote(mensaje)}"
                       f"&apikey={urllib.parse.quote(apikey)}")
                with urllib.request.urlopen(url, timeout=10, context=_CONTEXTO_SSL):
                    pass
            except Exception as e:
                ok = False
                error_texto = f"{type(e).__name__}: {e}"
            if al_terminar:
                Clock.schedule_once(lambda dt: al_terminar(ok, error_texto), 0)

        threading.Thread(target=tarea, daemon=True).start()

    def _revisar_alerta_diaria(self, forzado=False):
        hoy = date.today().isoformat()
        if not forzado and self.db.get("config", {}).get("whatsapp_ultima_alerta") == hoy:
            return
        if not self.db.get("config", {}).get("whatsapp_telefono") or \
           not self.db.get("config", {}).get("whatsapp_apikey"):
            return

        urgentes = [l for l in self.db.get("inventario", [])
                    if dias_para_vencer(l.get("fecha_vencimiento", "")) <= DIAS_ALERTA]
        if not urgentes:
            if forzado:
                self._mostrar_aviso("No hay productos por vencer ahora mismo.")
            return

        urgentes.sort(key=lambda l: l.get("fecha_vencimiento", ""))
        lineas = []
        for lote in urgentes:
            prod = self.db.get("catalogo", {}).get(lote.get("codigo_upc", "")) or {}
            nombre = prod.get("nombre") or "Producto"
            dias = dias_para_vencer(lote.get("fecha_vencimiento", ""))
            texto_estado = "VENCIDO" if dias < 0 else f"vence en {dias}d"
            lineas.append(f"- {nombre}: {lote.get('cantidad', 1)} u. ({texto_estado})")
        mensaje = "SmartExpiry Pro - Productos por revisar:\n" + "\n".join(lineas)

        def al_terminar(ok, error_texto):
            if ok:
                self.db["config"]["whatsapp_ultima_alerta"] = hoy
                self.guardar_db()
                if forzado:
                    self._mostrar_aviso(f"Alerta enviada por WhatsApp ({len(urgentes)} producto(s)).")
            elif forzado:
                self._mostrar_aviso(f"No se pudo enviar el mensaje.\n\nDetalle: {error_texto[:160]}")

        self._enviar_whatsapp(mensaje, al_terminar)

    def abrir_configuracion(self):
        contenido = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(10),
                              size_hint_y=None)
        contenido.bind(minimum_height=contenido.setter("height"))
        contenido.add_widget(Label(
            text="Alertas automáticas por WhatsApp (CallMeBot, gratis)",
            size_hint_y=None, height=dp(26), bold=True))

        f_tel = self._campo(contenido, "Tu número con código de país (ej. +50688887777)",
                            self.db.get("config", {}).get("whatsapp_telefono", ""))
        f_key = self._campo(contenido, "Tu API Key de CallMeBot",
                            self.db.get("config", {}).get("whatsapp_apikey", ""))

        instrucciones = Label(
            text="Para conseguir tu API Key (una sola vez):\n"
                 "1. Agrega +34 644 59 71 68 a tus contactos\n"
                 "2. Envíale por WhatsApp: \"I allow callmebot to send me messages\"\n"
                 "3. En unos minutos te contesta con tu API Key",
            size_hint_y=None, halign="left", valign="top")
        instrucciones.bind(width=lambda inst, w: setattr(inst, "text_size", (w, None)))
        instrucciones.bind(texture_size=lambda inst, val: setattr(inst, "height", val[1]))
        contenido.add_widget(instrucciones)

        msg = self._mensaje(contenido)

        def guardar_datos():
            self.db["config"]["whatsapp_telefono"] = f_tel.text.strip()
            self.db["config"]["whatsapp_apikey"] = f_key.text.strip()
            self.guardar_db()

        def guardar(*_):
            guardar_datos()
            popup.dismiss()

        def probar(*_):
            guardar_datos()
            msg.color = (0.6, 0.6, 0.6, 1)
            msg.text = "Enviando mensaje de prueba..."

            def al_terminar(ok, error_texto):
                if ok:
                    msg.color = (0.35, 0.75, 0.45, 1)
                    msg.text = "Enviado. Revisa tu WhatsApp en unos segundos."
                else:
                    msg.color = (1, 0.5, 0.45, 1)
                    msg.text = f"No se pudo enviar: {error_texto[:100]}"

            self._enviar_whatsapp("SmartExpiry Pro: mensaje de prueba ✅", al_terminar)

        def enviar_ahora(*_):
            guardar_datos()
            popup.dismiss()
            self._revisar_alerta_diaria(forzado=True)

        contenido.add_widget(self._fila_botones(
            ("Cancelar", lambda *_: popup.dismiss()),
            ("Probar", probar)))
        contenido.add_widget(self._fila_botones(
            ("Guardar", guardar),
            ("Enviar alerta ahora", enviar_ahora)))

        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(contenido)
        popup = Popup(title="Alertas por WhatsApp", content=scroll,
                      size_hint=(0.92, None), height=dp(560), auto_dismiss=False)
        popup.open()

    # ----- Calendario para elegir fechas -----

    def abrir_calendario(self, fecha_inicial_iso, al_elegir):
        try:
            base = date.fromisoformat(fecha_inicial_iso)
        except Exception:
            base = date.today()
        estado_mes = {"anio": base.year, "mes": base.month}

        contenido = BoxLayout(orientation="vertical", spacing=dp(8),
                              padding=[dp(10), dp(18), dp(10), dp(10)])

        cabecera_anio = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        btn_prev_anio = BotonRedondeado(text="<< Año", size_hint_x=None, width=dp(80))
        lbl_anio = Label(text="")
        btn_next_anio = BotonRedondeado(text="Año >>", size_hint_x=None, width=dp(80))
        cabecera_anio.add_widget(btn_prev_anio)
        cabecera_anio.add_widget(lbl_anio)
        cabecera_anio.add_widget(btn_next_anio)
        contenido.add_widget(cabecera_anio)

        cabecera = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        btn_prev = BotonRedondeado(text="< Mes", size_hint_x=None, width=dp(80))
        lbl_mes = Label(text="")
        btn_next = BotonRedondeado(text="Mes >", size_hint_x=None, width=dp(80))
        cabecera.add_widget(btn_prev)
        cabecera.add_widget(lbl_mes)
        cabecera.add_widget(btn_next)
        contenido.add_widget(cabecera)

        grilla = GridLayout(cols=7, size_hint_y=None, height=dp(260), spacing=dp(3))
        contenido.add_widget(grilla)

        def pintar():
            lbl_anio.text = str(estado_mes["anio"])
            lbl_mes.text = f"{NOMBRES_MES[estado_mes['mes'] - 1].capitalize()} {estado_mes['anio']}"
            grilla.clear_widgets()
            for inicial in ["L", "M", "M", "J", "V", "S", "D"]:
                grilla.add_widget(Label(text=inicial, size_hint_y=None, height=dp(34)))
            primer_dia, dias_en_mes = monthrange(estado_mes["anio"], estado_mes["mes"])
            for _ in range(primer_dia):
                grilla.add_widget(Label(text="", size_hint_y=None, height=dp(34)))
            for dia in range(1, dias_en_mes + 1):
                boton = BotonRedondeado(text=str(dia), size_hint_y=None, height=dp(34),
                                       font_size="13sp")

                def elegir(_, d=dia):
                    fecha_elegida = date(estado_mes["anio"], estado_mes["mes"], d).isoformat()
                    popup.dismiss()
                    al_elegir(fecha_elegida)

                boton.bind(on_release=elegir)
                grilla.add_widget(boton)

        def mes_anterior(*_):
            m, a = estado_mes["mes"] - 1, estado_mes["anio"]
            if m == 0:
                m, a = 12, a - 1
            estado_mes["mes"], estado_mes["anio"] = m, a
            pintar()

        def mes_siguiente(*_):
            m, a = estado_mes["mes"] + 1, estado_mes["anio"]
            if m == 13:
                m, a = 1, a + 1
            estado_mes["mes"], estado_mes["anio"] = m, a
            pintar()

        def anio_anterior(*_):
            estado_mes["anio"] -= 1
            pintar()

        def anio_siguiente(*_):
            estado_mes["anio"] += 1
            pintar()

        btn_prev.bind(on_release=mes_anterior)
        btn_next.bind(on_release=mes_siguiente)
        btn_prev_anio.bind(on_release=anio_anterior)
        btn_next_anio.bind(on_release=anio_siguiente)
        pintar()

        contenido.add_widget(self._fila_botones(("Cerrar", lambda *_: popup.dismiss())))
        popup = Popup(title="Elige la fecha", content=contenido,
                      size_hint=(0.92, None), height=dp(500), auto_dismiss=False)
        popup.open()

    # ----- Registrar lote -----

    def abrir_lote(self, upc, es_nuevo, prellenado=None):
        prellenado = prellenado or {}
        contenido = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(10))
        if es_nuevo:
            if prellenado.get("encontrado"):
                contenido.add_widget(Label(
                    text="Encontrado en Open Food Facts. Revisa y ajusta si hace falta.",
                    size_hint_y=None, height=dp(30), color=(0.35, 0.75, 0.45, 1)))
            elif prellenado.get("aviso_error"):
                contenido.add_widget(Label(
                    text=f"{prellenado['aviso_error']}\nCompleta los datos a mano.",
                    size_hint_y=None, height=dp(36), color=(1, 0.5, 0.45, 1)))

            f_nombre = self._campo(contenido, "Nombre del producto", prellenado.get("nombre", ""))
            f_upc_campo = self._campo(contenido, "UPC", upc)
            f_upc_campo.readonly = True
            f_upc_campo.foreground_color = COLOR_TEXTO_TENUE
            contenido.add_widget(Label(text="Tipo de unidad", size_hint_y=None, height=dp(22),
                                       halign="left", text_size=(dp(300), None)))
            f_unidad = Spinner(text=UNIDADES[0], values=UNIDADES,
                               size_hint_y=None, height=dp(46))
            f_unidad.bind(text=lambda inst, val: setattr(inst, "state", "normal"))
            contenido.add_widget(f_unidad)
        else:
            prod = self.db.get("catalogo", {}).get(upc, {})
            nombre = prod.get("nombre") or "Sin nombre"
            contenido.add_widget(Label(text=f"{nombre}\nUPC {upc}", size_hint_y=None,
                                       height=dp(50)))

        por_defecto = (date.today() + timedelta(days=14)).isoformat()
        contenido.add_widget(Label(text="Vencimiento (AAAA-MM-DD)", size_hint_y=None,
                                   height=dp(22), halign="left", text_size=(dp(300), None)))
        fila_fecha = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        f_fecha = TextInput(text=por_defecto, multiline=False)
        btn_calendario = BotonRedondeado(text="Fecha", size_hint_x=None, width=dp(80))
        fila_fecha.add_widget(f_fecha)
        fila_fecha.add_widget(btn_calendario)
        contenido.add_widget(fila_fecha)

        def abrir_cal(*_):
            self.abrir_calendario(f_fecha.text.strip(),
                                  lambda iso: setattr(f_fecha, "text", iso))
        btn_calendario.bind(on_release=abrir_cal)

        f_cant = self._campo(contenido, "Cantidad", "1", solo_numeros=True)
        msg = self._mensaje(contenido)

        def guardar(*_):
            try:
                fecha = date.fromisoformat(f_fecha.text.strip()).isoformat()
            except ValueError:
                msg.text = "Fecha no válida. Ejemplo: 2026-12-31"
                return
            if not f_cant.text.strip().isdigit() or int(f_cant.text) < 1:
                msg.text = "La cantidad debe ser 1 o más."
                return
            if es_nuevo:
                self.db.setdefault("catalogo", {})[upc] = {
                    "nombre": f_nombre.text.strip() or "Sin nombre",
                    "descripcion": prellenado.get("descripcion", ""),
                    "unidad": f_unidad.text,
                }
            self.db.setdefault("inventario", []).append({
                "id_lote": str(int(time.time() * 1000)),
                "codigo_upc": upc,
                "fecha_vencimiento": fecha,
                "cantidad": int(f_cant.text),
                "estado_alerta": "pendiente",
            })
            self.guardar_db()
            popup.dismiss()
            self.refrescar()

        contenido.add_widget(self._fila_botones(
            ("Cancelar", lambda *_: popup.dismiss()),
            ("Guardar lote", guardar)))
        alto = dp(630) if es_nuevo else dp(410)
        popup = Popup(title="Producto nuevo" if es_nuevo else "Registrar lote",
                      content=contenido, size_hint=(0.92, None), height=alto,
                      auto_dismiss=False)
        popup.open()

    # ----- Consumo o baja -----

    def abrir_detalle(self, id_lote):
        lote = next((l for l in self.db.get("inventario", []) if l.get("id_lote") == id_lote), None)
        if lote is None:
            return
        producto = self.db.get("catalogo", {}).get(lote.get("codigo_upc", ""), {})
        nombre = producto.get("nombre") or "Sin nombre"

        contenido = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        contenido.add_widget(Label(text=f"{nombre}\nUPC {lote.get('codigo_upc', '')}",
                                   size_hint_y=None, height=dp(54)))

        def ir_a_editar(*_):
            popup.dismiss()
            self.abrir_editar_producto(id_lote)

        def ir_a_baja(*_):
            popup.dismiss()
            self.abrir_baja(id_lote)

        contenido.add_widget(self._fila_botones(
            ("Editar producto", ir_a_editar),
            ("Dar de baja", ir_a_baja)))
        contenido.add_widget(self._fila_botones(
            ("Cancelar", lambda *_: popup.dismiss()),))
        popup = Popup(title="Opciones", content=contenido,
                      size_hint=(0.85, None), height=dp(280), auto_dismiss=False)
        popup.open()

    def abrir_editar_producto(self, id_lote):
        lote = next((l for l in self.db.get("inventario", []) if l.get("id_lote") == id_lote), None)
        if lote is None:
            return
        upc = lote.get("codigo_upc", "")
        producto = self.db.get("catalogo", {}).get(upc, {})

        contenido = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(10))
        f_nombre = self._campo(contenido, "Nombre del producto", producto.get("nombre", ""))
        f_upc_campo = self._campo(contenido, "UPC", upc)
        f_upc_campo.readonly = True
        f_upc_campo.foreground_color = COLOR_TEXTO_TENUE

        contenido.add_widget(Label(text="Tipo de unidad", size_hint_y=None, height=dp(22),
                                   halign="left", text_size=(dp(300), None)))
        unidad_actual = producto.get("unidad") or UNIDADES[0]
        f_unidad = Spinner(text=unidad_actual if unidad_actual in UNIDADES else UNIDADES[0],
                           values=UNIDADES, size_hint_y=None, height=dp(46))
        f_unidad.bind(text=lambda inst, val: setattr(inst, "state", "normal"))
        contenido.add_widget(f_unidad)

        contenido.add_widget(Label(text="Vencimiento de este lote (AAAA-MM-DD)",
                                   size_hint_y=None, height=dp(22), halign="left",
                                   text_size=(dp(300), None)))
        fila_fecha = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        f_fecha = TextInput(text=lote.get("fecha_vencimiento", ""), multiline=False)
        btn_calendario = BotonRedondeado(text="Fecha", size_hint_x=None, width=dp(80))
        fila_fecha.add_widget(f_fecha)
        fila_fecha.add_widget(btn_calendario)
        contenido.add_widget(fila_fecha)

        def abrir_cal(*_):
            self.abrir_calendario(f_fecha.text.strip(),
                                  lambda iso: setattr(f_fecha, "text", iso))
        btn_calendario.bind(on_release=abrir_cal)

        f_cant = self._campo(contenido, "Cantidad de este lote",
                             str(lote.get("cantidad", 1)), solo_numeros=True)
        msg = self._mensaje(contenido)

        def guardar(*_):
            try:
                fecha = date.fromisoformat(f_fecha.text.strip()).isoformat()
            except ValueError:
                msg.text = "Fecha no válida. Ejemplo: 2026-12-31"
                return
            if not f_cant.text.strip().isdigit() or int(f_cant.text) < 1:
                msg.text = "La cantidad debe ser 1 o más."
                return
            self.db.setdefault("catalogo", {})[upc] = {
                "nombre": f_nombre.text.strip() or "Sin nombre",
                "descripcion": producto.get("descripcion", ""),
                "unidad": f_unidad.text,
            }
            lote["fecha_vencimiento"] = fecha
            lote["cantidad"] = int(f_cant.text)
            self.guardar_db()
            popup.dismiss()
            self.refrescar()

        contenido.add_widget(self._fila_botones(
            ("Cancelar", lambda *_: popup.dismiss()),
            ("Guardar cambios", guardar)))
        popup = Popup(title="Editar producto", content=contenido,
                      size_hint=(0.92, None), height=dp(610), auto_dismiss=False)
        popup.open()

    def abrir_baja(self, id_lote):
        lote = next((l for l in self.db.get("inventario", []) if l.get("id_lote") == id_lote), None)
        if lote is None:
            return
        nombre = self.db.get("catalogo", {}).get(lote.get("codigo_upc", ""), {}).get("nombre") or "Sin nombre"
        cant_actual = lote.get("cantidad", 1)

        contenido = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(10))
        contenido.add_widget(Label(text=f"{nombre}\nHay {cant_actual} unidades",
                                   size_hint_y=None, height=dp(50)))
        f_cuanto = self._campo(contenido, "Unidades que salen", "1", solo_numeros=True)
        msg = self._mensaje(contenido)

        def dar_baja(*_):
            if not f_cuanto.text.strip().isdigit() or int(f_cuanto.text) < 1:
                msg.text = "Escribe 1 o más unidades."
                return
            cuanto = int(f_cuanto.text)
            if cuanto >= cant_actual:
                self.db["inventario"].remove(lote)
            else:
                lote["cantidad"] -= cuanto
            self.guardar_db()
            popup.dismiss()
            self.refrescar()

        contenido.add_widget(self._fila_botones(
            ("Cancelar", lambda *_: popup.dismiss()),
            ("Dar de baja", dar_baja)))
        popup = Popup(title="Consumo o baja", content=contenido,
                      size_hint=(0.9, None), height=dp(330), auto_dismiss=False)
        popup.open()


if __name__ == "__main__":
    SmartExpiryApp().run()
