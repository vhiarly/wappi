"""
Endpoint de datos para WhatsApp Flow dinámico de pedidos.

Maneja el protocolo de data-exchange cifrado de Meta:
  - ping          → health check
  - INIT          → primera pantalla (categorías en vivo)
  - data_exchange → siguiente pantalla (productos / checkout)

El cifrado: Meta manda {encrypted_flow_data, encrypted_aes_key, initial_vector}.
Se descifra la AES key con la RSA privada (OAEP-SHA256), y con esa AES key (GCM)
se descifra el cuerpo. La respuesta se cifra con la misma AES key y el IV invertido.

Requiere en env:
  FLOW_PRIVATE_KEY   — llave privada RSA (PEM)
"""
import os
import json
import base64

from flask import Blueprint, request
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from db import execute

flow_bp = Blueprint("flow", __name__)

_PRIVATE_KEY_PEM = os.getenv("FLOW_PRIVATE_KEY", "")


# ── Cifrado ─────────────────────────────────────────────────────────────────────

def _descifrar(body):
    private_key = serialization.load_pem_private_key(_PRIVATE_KEY_PEM.encode(), password=None)
    aes_key = private_key.decrypt(
        base64.b64decode(body["encrypted_aes_key"]),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                     algorithm=hashes.SHA256(), label=None),
    )
    iv = base64.b64decode(body["initial_vector"])
    flow_data = base64.b64decode(body["encrypted_flow_data"])
    decrypted = AESGCM(aes_key).decrypt(iv, flow_data, None)
    return json.loads(decrypted.decode()), aes_key, iv

def _cifrar(respuesta, aes_key, iv):
    iv_flip = bytes(b ^ 0xFF for b in iv)
    cipher = AESGCM(aes_key).encrypt(iv_flip, json.dumps(respuesta).encode(), None)
    return base64.b64encode(cipher).decode()


# ── Datos de las pantallas (en vivo desde la DB) ─────────────────────────────────

def _codigo_de_token(flow_token):
    """flow_token tiene formato 'PA1:uuid' — extrae el código del negocio."""
    if flow_token and ":" in flow_token:
        return flow_token.split(":", 1)[0]
    return None

def _categorias(codigo):
    rows = execute(
        "SELECT DISTINCT categoria FROM catalogo WHERE codigo=%s AND activo=TRUE AND categoria IS NOT NULL ORDER BY categoria",
        (codigo,), fetch="all") or []
    return [{"id": r["categoria"], "title": r["categoria"][:30]} for r in rows]

def _productos(codigo, categoria):
    rows = execute(
        "SELECT clave, nombre, precio FROM catalogo WHERE codigo=%s AND categoria=%s AND activo=TRUE ORDER BY nombre",
        (codigo, categoria), fetch="all") or []
    out = []
    for r in rows:
        precio = f" — RD${r['precio']:.0f}" if r["precio"] and r["precio"] > 0 else ""
        out.append({"id": r["clave"], "title": (r["nombre"][:28] + precio)[:30]})
    return out


# ── Lógica de pantallas ──────────────────────────────────────────────────────────

def _manejar(decrypted):
    action = decrypted.get("action")

    if action == "ping":
        return {"data": {"status": "active"}}

    flow_token = decrypted.get("flow_token", "")
    codigo = _codigo_de_token(flow_token) or "PA1"
    screen = decrypted.get("screen")
    data = decrypted.get("data") or {}

    # Primera pantalla: categorías
    if action == "INIT":
        return {"screen": "CATEGORIAS", "data": {"categorias": _categorias(codigo)}}

    if action == "data_exchange":
        # Vienen de CATEGORIAS → mostrar productos de la categoría elegida
        if screen == "CATEGORIAS":
            categoria = data.get("categoria")
            return {"screen": "PRODUCTOS", "data": {
                "categoria_nombre": categoria,
                "productos": _productos(codigo, categoria),
            }}
        # Vienen de PRODUCTOS → ir al checkout (datos de entrega)
        if screen == "PRODUCTOS":
            return {"screen": "ENTREGA", "data": {
                "productos_sel": data.get("productos") or [],
                "codigo": codigo,
            }}

    # Fallback seguro
    return {"screen": "CATEGORIAS", "data": {"categorias": _categorias(codigo)}}


# ── Endpoint ─────────────────────────────────────────────────────────────────────

@flow_bp.route("/flow-data", methods=["POST"])
def flow_data():
    body = request.get_json(silent=True) or {}
    try:
        decrypted, aes_key, iv = _descifrar(body)
    except Exception as e:
        print(f"[FLOW] Error descifrando: {e}")
        # 421 le dice a Meta que refresque la llave pública
        return "", 421

    try:
        respuesta = _manejar(decrypted)
    except Exception as e:
        print(f"[FLOW] Error en lógica: {e}")
        respuesta = {"data": {"status": "active"}}

    return _cifrar(respuesta, aes_key, iv), 200
