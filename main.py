# SmartExpiry Pro - Fase 2: interfaz Kivy
# Misma lógica de la Fase 1, ahora con pantalla táctil.
# Este archivo se llama main.py porque Buildozer lo necesitará así.

import json
import os
import time
from datetime import date, timedelta

from kivy.app import App
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.utils import escape_markup

Window.softinput_mode = "pan"  # evita que el teclado tape los campos

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
            return {"catalogo": {}, "inventario": []}
        with open(self.archivo, "r", encoding="utf-8") as f:
            return json.load(f)

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

    # ----- Escaneo simulado (Paso 1 del blueprint) -----

    def abrir_escaneo(self, modo):
        contenido = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        campo = self._campo(contenido, "Escribe el UPC (la cámara real llega en la Fase 3)",
                            solo_numeros=True)
        contenido.add_widget(Label())  # espacio flexible

        def aceptar(*_):
            upc = campo.text.strip()
            if not upc:
                return
            popup.dismiss()
            if modo == "filtro":
                self.root.ids.buscar.text = upc   # filtra la lista por ese UPC
            else:
                self.abrir_lote(upc, es_nuevo=upc not in self.db["catalogo"])

        contenido.add_widget(self._fila_botones(
            ("Cancelar", lambda *_: popup.dismiss()),
            ("Aceptar", aceptar)))
        popup = Popup(title="Escanear producto", content=contenido,
                      size_hint=(0.9, None), height=dp(260), auto_dismiss=False)
        popup.open()

    # ----- Registrar lote (Pasos 4 y 5 del blueprint) -----

    def abrir_lote(self, upc, es_nuevo):
        contenido = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(10))
        if es_nuevo:
            f_nombre = self._campo(contenido, "Nombre del producto")
            f_desc = self._campo(contenido, "Presentación (ej. 1 Litro)")
        else:
            nombre = self.db["catalogo"][upc]["nombre"]
            contenido.add_widget(Label(text=f"{nombre}\nUPC {upc}", size_hint_y=None,
                                       height=dp(50)))
        por_defecto = (date.today() + timedelta(days=14)).isoformat()
        f_fecha = self._campo(contenido, "Vencimiento (AAAA-MM-DD)", por_defecto)
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
        alto = dp(470) if es_nuevo else dp(390)
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
