# SmartExpiry Pro - Fase 2: interfaz Kivy
# Misma lógica de la Fase 1, ahora con pantalla táctil.
# Este archivo se llama main.py porque Buildozer lo necesitará así.

import json
import os
import ssl
import threading
import time
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
from kivy.properties import StringProperty
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

Window.softinput_mode = "below_target"  # mantiene visible el campo donde escribes

# En Android hay que pedir permiso de cámara en tiempo de ejecución.
if platform == "android":
    from android.permissions import Permission, check_permission, request_permissions
else:
    Permission = check_permission = request_permissions = None

# Todo lo relacionado a cámara/escaneo se carga con cuidado: si algo falla
# (muy común la primera vez en Android), la app sigue abriendo con el
# registro manual disponible, en vez de cerrarse de golpe.
CAMARA_DISPONIBLE = True
_error_camara = ""

try:
    if platform == "android":
        # ctypes no siempre encuentra libzbar.so por sí solo en Android;
        # la precargamos desde la carpeta de librerías nativas de la app.
        import ctypes
        from jnius import autoclass
        _actividad = autoclass("org.kivy.android.PythonActivity").mActivity
        _carpeta_libs = _actividad.getApplicationInfo().nativeLibraryDir
        try:
            ctypes.CDLL(os.path.join(_carpeta_libs, "libzbar.so"))
        except OSError:
            pass  # si esto falla, dejamos que pyzbar lo intente por su cuenta

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


# ---------- Lógica (igual que la Fase 1) ----------

def dias_para_vencer(fecha_texto):
    return (date.fromisoformat(fecha_texto) - date.today()).days


def estado(dias):
    """Devuelve el texto de estado y su color (rojo, amarillo o verde)."""
    if dias < 0:
        return "VENCIDO", (0.75, 0.25, 0.22, 1)
    if dias <= DIAS_ALERTA:
        return f"POR VENCER ({dias}d)", (0.78, 0.55, 0.15, 1)
    return f"OK ({dias}d)", (0.22, 0.50, 0.34, 1)


def lotes_ordenados(db, filtro=""):
    filtro = filtro.lower().strip()
    resultado = []
    for lote in db["inventario"]:
        nombre = db["catalogo"].get(lote["codigo_upc"], {}).get("nombre", "")
        if filtro in nombre.lower() or filtro in lote["codigo_upc"]:
            resultado.append(lote)
    return sorted(resultado, key=lambda l: l["fecha_vencimiento"])


# ---------- Diseño de la pantalla (lenguaje KV) ----------

KV = """
<FilaLote>:
    background_normal: ''
    markup: True
    halign: 'left'
    valign: 'middle'
    text_size: self.width - dp(28), self.height
    font_size: '15sp'

FloatLayout:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(10)
        spacing: dp(8)
        Label:
            id: titulo
            size_hint_y: None
            height: dp(40)
            font_size: '18sp'
            bold: True
            halign: 'left'
            text_size: self.size
        BoxLayout:
            size_hint_y: None
            height: dp(48)
            spacing: dp(8)
            TextInput:
                id: buscar
                hint_text: 'Buscar producto o UPC...'
                multiline: False
                on_text: app.refrescar()
            Button:
                text: 'Escanear'
                size_hint_x: None
                width: dp(110)
                on_release: app.abrir_escaneo('filtro')
        RecycleView:
            id: rv
            viewclass: 'FilaLote'
            RecycleBoxLayout:
                default_size: None, dp(72)
                default_size_hint: 1, None
                size_hint_y: None
                height: self.minimum_height
                orientation: 'vertical'
                spacing: dp(6)
    Button:
        text: '+'
        font_size: '32sp'
        size_hint: None, None
        size: dp(64), dp(64)
        pos_hint: {'right': 0.97, 'y': 0.03}
        on_release: app.abrir_escaneo('nuevo')
"""


class FilaLote(Button):
    """Una fila de la lista. Al tocarla se abre el diálogo de baja."""
    id_lote = StringProperty("")

    def on_release(self):
        App.get_running_app().abrir_baja(self.id_lote)


class SmartExpiryApp(App):

    # ----- Inicio y datos -----

    def build(self):
        self.archivo = os.path.join(self.user_data_dir, "smart_expiry_db.json")
        self.db = self.cargar_db()
        return Builder.load_string(KV)

    def on_start(self):
        self.refrescar()

    def cargar_db(self):
        if not os.path.exists(self.archivo):
            return {"catalogo": {}, "inventario": [],
                    "config": {"rotacion_camara": 0, "rotacion_pantalla_base": 0}}
        with open(self.archivo, "r", encoding="utf-8") as f:
            datos = json.load(f)
        config = datos.setdefault("config", {})
        config.setdefault("rotacion_camara", 0)
        config.setdefault("rotacion_pantalla_base", 0)
        return datos

    def guardar_db(self):
        with open(self.archivo, "w", encoding="utf-8") as f:
            json.dump(self.db, f, ensure_ascii=False, indent=2)

    # ----- Lista principal -----

    def refrescar(self):
        ids = self.root.ids
        lotes = lotes_ordenados(self.db, ids.buscar.text)
        datos = []
        for lote in lotes:
            producto = self.db["catalogo"].get(lote["codigo_upc"], {})
            nombre = escape_markup(producto.get("nombre", "Sin nombre"))
            detalle = escape_markup(producto.get("descripcion", ""))
            unidad = producto.get("unidad", "")
            if unidad and unidad != "Unidad":
                detalle = f"{detalle} · {escape_markup(unidad)}" if detalle else escape_markup(unidad)
            texto_estado, color = estado(dias_para_vencer(lote["fecha_vencimiento"]))
            datos.append({
                "text": (f"[b]{nombre}[/b] {detalle}\n"
                         f"Cant: {lote['cantidad']} | Vence: {lote['fecha_vencimiento']} | {texto_estado}"),
                "background_color": color,
                "id_lote": lote["id_lote"],
            })
        ids.rv.data = datos

        por_vencer = sum(1 for l in self.db["inventario"]
                         if dias_para_vencer(l["fecha_vencimiento"]) <= DIAS_ALERTA)
        ids.titulo.text = (f"SmartExpiry Pro | {len(self.db['inventario'])} lotes | "
                           f"{por_vencer} por vencer")

    # ----- Ayudas para armar diálogos -----

    def _fila_botones(self, *pares):
        fila = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(10))
        for texto, accion in pares:
            boton = Button(text=texto)
            boton.bind(on_release=accion)
            fila.add_widget(boton)
        return fila

    def _campo(self, contenido, etiqueta, texto="", solo_numeros=False):
        contenido.add_widget(Label(text=etiqueta, size_hint_y=None, height=dp(24),
                                   halign="left", text_size=(dp(300), None)))
        campo = TextInput(text=texto, multiline=False, size_hint_y=None, height=dp(46),
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
        """Con el UPC ya leído (por cámara o a mano), sigue el flujo del blueprint."""
        if modo == "filtro":
            self.root.ids.buscar.text = upc
            return
        if upc in self.db["catalogo"]:
            self.abrir_lote(upc, es_nuevo=False)
            return
        # Producto nuevo: primero probamos Open Food Facts (Paso 3 del blueprint)
        self._mostrar_buscando()

        def al_terminar(nombre, cantidad_texto, error_texto):
            self._cerrar_buscando()
            if error_texto:
                self._mostrar_aviso(
                    "No se pudo consultar Open Food Facts (puede que el producto "
                    "simplemente no esté no esté en su base, o sea un problema de "
                    "conexión). Completa los datos a mano.\n\n"
                    f"Detalle técnico: {error_texto[:160]}")
            self.abrir_lote(upc, es_nuevo=True, prellenado={
                "nombre": nombre or "",
                "descripcion": cantidad_texto or "",
                "encontrado": bool(nombre),
            })

        self._consultar_openfoodfacts(upc, al_terminar)

    def _consultar_openfoodfacts(self, upc, on_listo):
        """Busca el producto en Open Food Facts en un hilo aparte para no
        congelar la pantalla mientras responde. Siempre llama a on_listo,
        haya encontrado algo o no. error_texto queda vacío si la consulta
        se hizo bien pero el producto simplemente no estaba en su base."""
        def tarea():
            nombre = None
            cantidad_texto = ""
            error_texto = ""
            try:
                url = f"https://world.openfoodfacts.org/api/v2/product/{upc}.json"
                peticion = urllib.request.Request(
                    url, headers={"User-Agent": "SmartExpiryPro/1.0"})
                with urllib.request.urlopen(peticion, timeout=10,
                                            context=_CONTEXTO_SSL) as resp:
                    datos = json.loads(resp.read().decode("utf-8"))
                if datos.get("status") == 1:
                    producto = datos.get("product", {})
                    nombre = (producto.get("product_name_es")
                              or producto.get("product_name") or None)
                    cantidad_texto = producto.get("quantity", "") or ""
                # si status no es 1, el producto no está en su base: no es un error
            except Exception as e:
                error_texto = f"{type(e).__name__}: {e}"
            Clock.schedule_once(lambda dt: on_listo(nombre, cantidad_texto, error_texto), 0)

        threading.Thread(target=tarea, daemon=True).start()

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

    # ----- Escritura manual (respaldo si la cámara falla o no hay una) -----

    def abrir_manual(self, modo):
        contenido = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        campo = self._campo(contenido, "Escribe el código UPC", solo_numeros=True)
        contenido.add_widget(Label())  # espacio flexible

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
        """Ángulo calibrado, ajustado automáticamente si la tablet
        está en una posición distinta a cuando se calibró."""
        config = self.db["config"]
        pantalla_ahora = _rotacion_pantalla_actual()
        diferencia = (pantalla_ahora - config["rotacion_pantalla_base"]) % 360
        return (config["rotacion_camara"] + diferencia) % 360

    # ----- Escaneo real con la cámara -----

    def abrir_camara(self, modo):
        if not CAMARA_DISPONIBLE:
            self._mostrar_aviso(
                "El escaneo con cámara no está disponible en esta compilación.\n"
                "Usa 'Escribir a mano' mientras lo ajustamos.\n\n"
                f"Detalle técnico: {_error_camara[:120]}")
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
        envoltorio.add_widget(Widget())  # centra el visor
        envoltorio.add_widget(contenedor)
        envoltorio.add_widget(Widget())
        contenido.add_widget(envoltorio)

        estado_txt = Label(text="Preparando cámara...", size_hint_y=None, height=dp(30))
        contenido.add_widget(estado_txt)

        def girar(*_):
            nueva = (contenedor.rotation + 90) % 360
            contenedor.rotation = nueva
            self.db["config"]["rotacion_camara"] = nueva
            self.db["config"]["rotacion_pantalla_base"] = _rotacion_pantalla_actual()
            self.guardar_db()

        contenido.add_widget(self._fila_botones(
            ("Girar imagen ⟳", girar),
            ("Cancelar", lambda *_: cerrar())))

        popup = Popup(title="Escaneando", content=contenido,
                      size_hint=(0.95, None), height=dp(520), auto_dismiss=False)

        tarea = None
        fotogramas_a_descartar = [6]  # ignora los primeros, pueden venir de la sesión anterior

        def intentar_leer(dt):
            if fotogramas_a_descartar[0] > 0:
                fotogramas_a_descartar[0] -= 1
                if fotogramas_a_descartar[0] == 0:
                    estado_txt.text = "Apunta al código de barras..."
                return
            textura = camara.texture
            if textura is None:
                return
            try:
                ancho, alto = textura.size
                datos = textura.pixels
                imagen = PILImage.frombytes("RGBA", (ancho, alto), datos).convert("L")
                resultados = zbar_decode(imagen)
            except Exception:
                return
            if resultados:
                codigo = resultados[0].data.decode("utf-8", errors="ignore").strip()
                if codigo:
                    cerrar()
                    self._procesar_codigo(codigo, modo)

        def cerrar(*_):
            if tarea:
                tarea.cancel()
            camara.play = False
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

    # ----- Calendario para elegir fechas -----

    def abrir_calendario(self, fecha_inicial_iso, al_elegir):
        try:
            base = date.fromisoformat(fecha_inicial_iso)
        except Exception:
            base = date.today()
        estado_mes = {"anio": base.year, "mes": base.month}

        contenido = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(10))
        cabecera = BoxLayout(size_hint_y=None, height=dp(40))
        btn_prev = Button(text="◀", size_hint_x=None, width=dp(44))
        lbl_mes = Label(text="")
        btn_next = Button(text="▶", size_hint_x=None, width=dp(44))
        cabecera.add_widget(btn_prev)
        cabecera.add_widget(lbl_mes)
        cabecera.add_widget(btn_next)
        contenido.add_widget(cabecera)

        grilla = GridLayout(cols=7, size_hint_y=None, height=dp(260), spacing=dp(2))
        contenido.add_widget(grilla)

        def pintar():
            lbl_mes.text = f"{NOMBRES_MES[estado_mes['mes'] - 1].capitalize()} {estado_mes['anio']}"
            grilla.clear_widgets()
            for inicial in ["L", "M", "M", "J", "V", "S", "D"]:
                grilla.add_widget(Label(text=inicial, size_hint_y=None, height=dp(34)))
            primer_dia, dias_en_mes = monthrange(estado_mes["anio"], estado_mes["mes"])
            for _ in range(primer_dia):
                grilla.add_widget(Label(text="", size_hint_y=None, height=dp(34)))
            for dia in range(1, dias_en_mes + 1):
                boton = Button(text=str(dia), size_hint_y=None, height=dp(34))

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

        btn_prev.bind(on_release=mes_anterior)
        btn_next.bind(on_release=mes_siguiente)
        pintar()

        contenido.add_widget(self._fila_botones(("Cerrar", lambda *_: popup.dismiss())))
        popup = Popup(title="Elige la fecha", content=contenido,
                      size_hint=(0.92, None), height=dp(430), auto_dismiss=False)
        popup.open()

    # ----- Registrar lote (Pasos 4 y 5 del blueprint) -----

    def abrir_lote(self, upc, es_nuevo, prellenado=None):
        prellenado = prellenado or {}
        contenido = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(10))
        if es_nuevo:
            if prellenado.get("encontrado"):
                contenido.add_widget(Label(
                    text="Encontrado en Open Food Facts. Revisa y ajusta si hace falta.",
                    size_hint_y=None, height=dp(30), color=(0.35, 0.75, 0.45, 1)))
            f_nombre = self._campo(contenido, "Nombre del producto", prellenado.get("nombre", ""))
            f_desc = self._campo(contenido, "Presentación (ej. 1 Litro)",
                                 prellenado.get("descripcion", ""))
            contenido.add_widget(Label(text="Tipo de unidad", size_hint_y=None, height=dp(22),
                                       halign="left", text_size=(dp(300), None)))
            f_unidad = Spinner(text=UNIDADES[0], values=UNIDADES,
                               size_hint_y=None, height=dp(46))
            contenido.add_widget(f_unidad)
        else:
            nombre = self.db["catalogo"][upc]["nombre"]
            contenido.add_widget(Label(text=f"{nombre}\nUPC {upc}", size_hint_y=None,
                                       height=dp(50)))

        por_defecto = (date.today() + timedelta(days=14)).isoformat()
        contenido.add_widget(Label(text="Vencimiento (AAAA-MM-DD)", size_hint_y=None,
                                   height=dp(22), halign="left", text_size=(dp(300), None)))
        fila_fecha = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        f_fecha = TextInput(text=por_defecto, multiline=False)
        btn_calendario = Button(text="📅", size_hint_x=None, width=dp(56))
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
                self.db["catalogo"][upc] = {
                    "nombre": f_nombre.text.strip() or "Sin nombre",
                    "descripcion": f_desc.text.strip(),
                    "unidad": f_unidad.text,
                }
            self.db["inventario"].append({
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
        alto = dp(610) if es_nuevo else dp(410)
        popup = Popup(title="Producto nuevo" if es_nuevo else "Registrar lote",
                      content=contenido, size_hint=(0.92, None), height=alto,
                      auto_dismiss=False)
        popup.open()

    # ----- Consumo o baja (al tocar una fila) -----

    def abrir_baja(self, id_lote):
        lote = next((l for l in self.db["inventario"] if l["id_lote"] == id_lote), None)
        if lote is None:
            return
        nombre = self.db["catalogo"].get(lote["codigo_upc"], {}).get("nombre", "Sin nombre")
        contenido = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(10))
        contenido.add_widget(Label(text=f"{nombre}\nHay {lote['cantidad']} unidades",
                                   size_hint_y=None, height=dp(50)))
        f_cuanto = self._campo(contenido, "Unidades que salen", "1", solo_numeros=True)
        msg = self._mensaje(contenido)

        def dar_baja(*_):
            if not f_cuanto.text.strip().isdigit() or int(f_cuanto.text) < 1:
                msg.text = "Escribe 1 o más unidades."
                return
            cuanto = int(f_cuanto.text)
            if cuanto >= lote["cantidad"]:
                self.db["inventario"].remove(lote)   # lote agotado
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


SmartExpiryApp().run()
