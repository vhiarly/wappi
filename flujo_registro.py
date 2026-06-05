import re
from db import execute

NUMERO_WASAPEAME = "whatsapp:+18298789906"


def _get_estado(numero):
    return execute(
        "SELECT * FROM conversaciones_registro WHERE numero_cliente = %s",
        (numero,), fetch="one"
    )

def _set_estado(numero, data):
    execute("""
        INSERT INTO conversaciones_registro (numero_cliente, estado, nombre_negocio, tipo)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (numero_cliente) DO UPDATE SET
            estado         = EXCLUDED.estado,
            nombre_negocio = EXCLUDED.nombre_negocio,
            tipo           = EXCLUDED.tipo,
            actualizado_en = NOW()
    """, (numero, data["estado"], data.get("nombre_negocio"), data.get("tipo")))

def _del_estado(numero):
    execute("DELETE FROM conversaciones_registro WHERE numero_cliente = %s", (numero,))

def _guardar_lead(numero, nombre, tipo, numero_contacto):
    execute("""
        INSERT INTO leads_negocios (numero_whatsapp, nombre_negocio, tipo, numero_contacto)
        VALUES (%s, %s, %s, %s)
    """, (numero, nombre, tipo, numero_contacto))


def tiene_flujo_registro(numero):
    return _get_estado(numero) is not None


def manejar_registro(numero, mensaje, twilio_send):
    msg = mensaje.strip()
    msg_low = msg.lower()

    if any(p in msg_low for p in ["cancelar", "salir", "cancel"]):
        _del_estado(numero)
        return "Registro cancelado. Escribe *4* cuando quieras intentarlo de nuevo."

    estado = _get_estado(numero)

    if not estado:
        return None

    s = estado["estado"]

    # ── ESPERANDO NOMBRE ──
    if s == "esperando_nombre_negocio":
        _set_estado(numero, {**estado, "estado": "esperando_tipo", "nombre_negocio": msg})
        return (
            f"¿Qué tipo de negocio es *{msg}*?\n\n"
            "1. Pedidos\n"
            "2. Agendar Citas\n\n"
            "Escribe *cancelar* para salir."
        )

    # ── ESPERANDO TIPO ──
    if s == "esperando_tipo":
        if msg_low in ("1", "pedidos"):
            tipo = "Pedidos"
        elif msg_low in ("2", "agendar citas", "citas"):
            tipo = "Agendar Citas"
        else:
            return "Escribe *1* para Pedidos o *2* para Agendar Citas."
        _set_estado(numero, {**estado, "estado": "esperando_contacto", "tipo": tipo})
        return "¿Cuál es el número de contacto del negocio?\nEjemplo: 8091234567"

    # ── ESPERANDO CONTACTO ──
    if s == "esperando_contacto":
        numero_contacto = re.sub(r"\D", "", msg)
        if len(numero_contacto) < 8:
            return "Ese número no parece válido. Escríbelo de nuevo.\nEjemplo: 8091234567"

        nombre = estado["nombre_negocio"]
        tipo   = estado["tipo"]

        _guardar_lead(numero, nombre, tipo, numero_contacto)
        _del_estado(numero)

        twilio_send(
            NUMERO_WASAPEAME,
            f"🆕 NUEVO LEAD\n\n"
            f"Negocio:  {nombre}\n"
            f"Tipo:     {tipo}\n"
            f"Contacto: {numero_contacto}\n"
            f"WhatsApp: {numero}"
        )

        return (
            f"✅ Recibimos tu solicitud para *{nombre}*.\n\n"
            "Nuestro equipo se pondrá en contacto contigo pronto. ¡Gracias por tu interés en Wasapeame! 🙌"
        )

    return None


def iniciar_registro(numero, twilio_send):
    _set_estado(numero, {"estado": "esperando_nombre_negocio", "nombre_negocio": None, "tipo": None})
    return "¿Cómo se llama tu negocio?\n\nEscribe *cancelar* para salir."
