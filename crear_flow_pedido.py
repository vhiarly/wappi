"""
Crea y publica un WhatsApp Flow DINÁMICO de pedidos para un negocio.

El catálogo (categorías/productos) lo provee en vivo el endpoint /flow-data,
así que el JSON solo define la estructura de las pantallas.

Uso:
    python crear_flow_pedido.py PA1

Requiere en .env:
    META_ACCESS_TOKEN, META_WABA_ID, DATABASE_URL
"""
import io
import json
import os
import sys
import requests
import psycopg2
from dotenv import load_dotenv

load_dotenv()

TOKEN        = os.getenv("META_ACCESS_TOKEN")
WABA_ID      = os.getenv("META_WABA_ID")
API          = "https://graph.facebook.com/v19.0"
ENDPOINT_URI = "https://wappi.do/flow-data"


def _db():
    return psycopg2.connect(os.getenv("DATABASE_URL"))


def guardar_flow_id(codigo, flow_id):
    conn = _db(); cur = conn.cursor()
    cur.execute("UPDATE negocios SET flow_id_pedidos = %s WHERE codigo = %s", (flow_id, codigo))
    conn.commit(); cur.close(); conn.close()


def flow_json():
    arr_item = {"type": "object", "properties": {
        "id": {"type": "string"}, "title": {"type": "string"}}}
    return {
        "version": "6.3",
        "data_api_version": "3.0",
        "routing_model": {"CATEGORIAS": ["PRODUCTOS"], "PRODUCTOS": ["ENTREGA"], "ENTREGA": []},
        "screens": [
            {
                "id": "CATEGORIAS",
                "title": "Haz tu pedido",
                "data": {"categorias": {"type": "array", "items": arr_item,
                                        "__example__": [{"id": "Postres", "title": "Postres"}]}},
                "layout": {"type": "SingleColumnLayout", "children": [
                    {"type": "Form", "name": "form", "children": [
                        {"type": "RadioButtonsGroup", "name": "categoria",
                         "label": "¿Qué deseas pedir?", "data-source": "${data.categorias}",
                         "required": True},
                        {"type": "Footer", "label": "Siguiente",
                         "on-click-action": {"name": "data_exchange",
                                             "payload": {"categoria": "${form.categoria}"}}},
                    ]}
                ]},
            },
            {
                "id": "PRODUCTOS",
                "title": "Productos",
                "data": {"productos": {"type": "array", "items": arr_item,
                                       "__example__": [{"id": "x", "title": "Producto RD$100"}]}},
                "layout": {"type": "SingleColumnLayout", "children": [
                    {"type": "Form", "name": "form", "children": [
                        {"type": "CheckboxGroup", "name": "productos",
                         "label": "Marca lo que quieras", "data-source": "${data.productos}",
                         "required": True},
                        {"type": "Footer", "label": "Continuar",
                         "on-click-action": {"name": "data_exchange",
                                             "payload": {"productos": "${form.productos}"}}},
                    ]}
                ]},
            },
            {
                "id": "ENTREGA",
                "title": "Datos de entrega",
                "terminal": True,
                "data": {
                    "productos_sel": {"type": "array", "items": {"type": "string"}, "__example__": ["x"]},
                    "codigo": {"type": "string", "__example__": "PA1"},
                },
                "layout": {"type": "SingleColumnLayout", "children": [
                    {"type": "Form", "name": "form", "children": [
                        {"type": "TextInput", "name": "nombre", "label": "Tu nombre", "required": True},
                        {"type": "TextInput", "name": "direccion", "label": "Dirección", "required": True},
                        {"type": "TextInput", "name": "sector", "label": "Sector / Zona", "required": True},
                        {"type": "TextInput", "name": "referencia", "label": "Punto de referencia", "required": False},
                        {"type": "TextArea", "name": "detalles", "label": "Cantidades / detalles", "required": False},
                        {"type": "RadioButtonsGroup", "name": "metodo_pago", "label": "Método de pago",
                         "data-source": [{"id": "efectivo", "title": "Efectivo"},
                                         {"id": "transferencia", "title": "Transferencia"}],
                         "required": True},
                        {"type": "Footer", "label": "Confirmar pedido",
                         "on-click-action": {"name": "complete", "payload": {
                             "codigo": "${data.codigo}",
                             "productos": "${data.productos_sel}",
                             "nombre": "${form.nombre}",
                             "direccion": "${form.direccion}",
                             "sector": "${form.sector}",
                             "referencia": "${form.referencia}",
                             "detalles": "${form.detalles}",
                             "metodo_pago": "${form.metodo_pago}",
                         }}},
                    ]}
                ]},
            },
        ],
    }


def crear_flow(nombre):
    r = requests.post(f"{API}/{WABA_ID}/flows",
                      headers={"Authorization": f"Bearer {TOKEN}"},
                      json={"name": nombre, "categories": ["OTHER"],
                            "endpoint_uri": ENDPOINT_URI}, timeout=15)
    r.raise_for_status()
    return r.json()["id"]


def subir_json(flow_id, fj):
    files = {"file": ("flow.json", io.BytesIO(json.dumps(fj).encode()), "application/json"),
             "name": (None, "flow.json"), "asset_type": (None, "FLOW_JSON")}
    r = requests.post(f"{API}/{flow_id}/assets",
                      headers={"Authorization": f"Bearer {TOKEN}"}, files=files, timeout=15)
    r.raise_for_status()
    return r.json()


def publicar(flow_id):
    r = requests.post(f"{API}/{flow_id}",
                      headers={"Authorization": f"Bearer {TOKEN}"},
                      json={"publish": True}, timeout=15)
    return r


if __name__ == "__main__":
    codigo = (sys.argv[1] if len(sys.argv) > 1 else "PA1").upper()
    if not TOKEN or not WABA_ID:
        raise SystemExit("Faltan META_ACCESS_TOKEN o META_WABA_ID en .env")

    print(f"→ Creando Flow de pedidos para {codigo}...")
    flow_id = crear_flow(f"pedidos_{codigo.lower()}")
    print(f"  Flow ID: {flow_id}")

    print("→ Subiendo JSON...")
    result = subir_json(flow_id, flow_json())
    errs = result.get("validation_errors", [])
    if errs:
        print("❌ Errores de validación:")
        for e in errs:
            print("  ", e)
        sys.exit(1)
    print("  JSON subido ✓")

    print("→ Publicando...")
    r = publicar(flow_id)
    print("  publish →", r.status_code, r.text[:300])

    guardar_flow_id(codigo, flow_id)
    print(f"\n✅ Flow {flow_id} guardado en flow_id_pedidos de {codigo}")
