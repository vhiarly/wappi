# app.py - Wasapeame Agent V2.0
# Bot de WhatsApp potenciado por Claude AI

import os
import json
import threading
import anthropic
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from dotenv import load_dotenv
from inventario import productos

load_dotenv()

app = Flask(__name__)

ACCOUNT_SID   = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
DUEÑO         = os.getenv("DUENO_WHATSAPP")

client_twilio  = Client(ACCOUNT_SID, AUTH_TOKEN)
client_claude  = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Estado de conversaciones
conversaciones = {}  # {numero: [{"role": "user/assistant", "content": "..."}]}
ordenes_activas = {}  # {numero: {"items": [], "direccion": "", "referencia": ""}}
estados = {}          # {numero: "pidiendo" | "esperando_direccion" | "esperando_referencia" | "confirmado"}
timers = {}

TIMEOUT_SEGUNDOS = 300


def get_menu_texto():
    """Genera texto del menú desde inventario."""
    lineas = []
    for clave, p in productos.items():
        if p["cantidad"] > 0:
            unidad = "/libra" if p["unidad"] == "libra" else " c/u"
            rebanado = " (se puede rebanar)" if p.get("rebanado") else ""
            lineas.append(f"- {p['nombre']}: RD${p['precio']}{unidad}{rebanado}")
    return "\n".join(lineas)


def get_system_prompt():
    menu = get_menu_texto()
    return f"""Eres el asistente virtual de Wasapeame, un servicio de pedidos por WhatsApp para negocios dominicanos. Eres amigable, natural y hablas como dominicano — usando expresiones como "dale", "ta bien", "perfecto", etc.

MENU DISPONIBLE:
{menu}

TU TRABAJO:
1. Ayudar al cliente a hacer su pedido de forma natural
2. Entender pedidos aunque estén escritos de forma informal
3. Confirmar los productos y cantidades antes de pedir la dirección
4. Manejar preguntas sobre productos disponibles

REGLAS IMPORTANTES:
- Solo puedes vender productos que están en el menú
- Si piden algo que no está, dilo amablemente y ofrece alternativas
- Siempre confirma el pedido con precios antes de pedir la dirección
- Para productos por libra, acepta: "media libra", "1/4 libra", "2 libras", etc.
- Para productos con opción de rebanado, pregunta si lo quieren rebanado
- Cuando el cliente confirme su pedido, responde EXACTAMENTE con este JSON (nada más):

ACCION_PEDIDO:{{"items": [{{"nombre": "nombre_producto", "cantidad": 0.5, "unidad": "libra", "precio_total": 60, "rebanado": false}}], "listo_para_direccion": true}}

- Cuando el cliente cancele, responde: ACCION_CANCELAR
- En cualquier otra situación, responde normalmente en español dominicano

IMPORTANTE: El JSON de ACCION_PEDIDO solo cuando el cliente confirme. Mientras tanto conversa normal."""


def limpiar_conversacion(numero):
    conversaciones[numero] = []
    ordenes_activas[numero] = {"items": [], "direccion": "", "referencia": ""}
    estados[numero] = "pidiendo"


def cancelar_por_timeout(numero):
    if estados.get(numero) != "confirmado":
        try:
            client_twilio.messages.create(
                body="⏰ Tu orden fue cancelada por inactividad.\n\nEscribe *hola* cuando quieras pedir de nuevo. 😊",
                from_=TWILIO_NUMBER,
                to=numero
            )
        except Exception:
            pass
        limpiar_conversacion(numero)


def reiniciar_timer(numero):
    if numero in timers:
        timers[numero].cancel()
    timer = threading.Timer(TIMEOUT_SEGUNDOS, cancelar_por_timeout, args=[numero])
    timer.daemon = True
    timer.start()
    timers[numero] = timer


def detener_timer(numero):
    if numero in timers:
        timers[numero].cancel()
        del timers[numero]


def notificar_dueno(numero):
    orden = ordenes_activas[numero]
    total = sum(i.get("precio_total", 0) for i in orden["items"])

    texto = "🔔 *ORDEN NUEVA — Wasapeame*\n\n🛒 *Pedido:*\n"
    for item in orden["items"]:
        unidad = "libra(s)" if item.get("unidad") == "libra" else "unidad(es)"
        rebanado = " — Rebanado" if item.get("rebanado") else ""
        texto += f"• {item['cantidad']} {unidad} de {item['nombre']}{rebanado} - RD${item['precio_total']}\n"
    texto += f"\n💰 Total: RD${total}\n"
    texto += f"📍 Dirección: {orden['direccion']}\n"
    texto += f"📌 Referencia: {orden['referencia']}\n"
    texto += f"📞 Cliente: {numero}"

    client_twilio.messages.create(body=texto, from_=TWILIO_NUMBER, to=DUEÑO)


def procesar_con_claude(numero, mensaje_usuario):
    """Envía mensaje a Claude y obtiene respuesta."""
    if numero not in conversaciones:
        conversaciones[numero] = []

    conversaciones[numero].append({"role": "user", "content": mensaje_usuario})

    # Limitar historial a últimos 20 mensajes para no exceder contexto
    historial = conversaciones[numero][-20:]

    response = client_claude.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=get_system_prompt(),
        messages=historial
    )

    respuesta = response.content[0].text
    conversaciones[numero].append({"role": "assistant", "content": respuesta})

    return respuesta


@app.route("/webhook", methods=["POST"])
def webhook():
    numero = request.form.get("From")
    mensaje = request.form.get("Body", "").strip()

    resp = MessagingResponse()
    msg = resp.message()

    # Inicializar si es nuevo
    if numero not in estados:
        limpiar_conversacion(numero)

    estado = estados.get(numero, "pidiendo")

    # ── ESPERANDO DIRECCIÓN ──
    if estado == "esperando_direccion":
        ordenes_activas[numero]["direccion"] = mensaje
        estados[numero] = "esperando_referencia"
        reiniciar_timer(numero)
        msg.body("📌 ¿Alguna referencia para encontrarte más fácil?\n\nEjemplo: *Al lado de la farmacia*, *Frente al parque*\n\nSi no tienes, escribe *ninguna*.")
        return str(resp)

    # ── ESPERANDO REFERENCIA ──
    if estado == "esperando_referencia":
        referencia = mensaje if mensaje.lower() != "ninguna" else "Sin referencia"
        ordenes_activas[numero]["referencia"] = referencia
        estados[numero] = "confirmado"

        orden = ordenes_activas[numero]
        total = sum(i.get("precio_total", 0) for i in orden["items"])

        resumen = "✅ *Orden confirmada!*\n\n🛒 *Tu pedido:*\n"
        for item in orden["items"]:
            unidad = "libra(s)" if item.get("unidad") == "libra" else "unidad(es)"
            rebanado = " — Rebanado" if item.get("rebanado") else ""
            resumen += f"• {item['cantidad']} {unidad} de {item['nombre']}{rebanado} - RD${item['precio_total']}\n"
        resumen += f"\n💰 *Total: RD${total}*\n"
        resumen += f"📍 *Dirección:* {orden['direccion']}\n"
        resumen += f"📌 *Referencia:* {referencia}\n\n"
        resumen += "¡Tu pedido está en camino! 🛵\n\n_Powered by Wasapeame_"

        msg.body(resumen)
        notificar_dueno(numero)
        detener_timer(numero)
        limpiar_conversacion(numero)
        return str(resp)

    # ── ESTADO NORMAL: CONVERSACIÓN CON CLAUDE ──
    reiniciar_timer(numero)

    try:
        respuesta_claude = procesar_con_claude(numero, mensaje)
    except Exception as e:
        msg.body("😅 Tuve un problemita técnico. Escribe *hola* para intentar de nuevo.")
        return str(resp)

    # Detectar acciones especiales en la respuesta de Claude
    if respuesta_claude.startswith("ACCION_PEDIDO:"):
        try:
            json_str = respuesta_claude.replace("ACCION_PEDIDO:", "").strip()
            datos = json.loads(json_str)

            if datos.get("listo_para_direccion"):
                ordenes_activas[numero]["items"] = datos["items"]
                estados[numero] = "esperando_direccion"

                total = sum(i.get("precio_total", 0) for i in datos["items"])
                confirmacion = "🛒 *Pedido confirmado:*\n"
                for item in datos["items"]:
                    unidad = "libra(s)" if item.get("unidad") == "libra" else "unidad(es)"
                    rebanado = " — Rebanado" if item.get("rebanado") else ""
                    confirmacion += f"• {item['cantidad']} {unidad} de {item['nombre']}{rebanado} - RD${item['precio_total']}\n"
                confirmacion += f"\n💰 Total: RD${total}\n\n"
                confirmacion += "📍 *¿A qué dirección te enviamos?*\n\nEscribe tu calle, número y sector."
                msg.body(confirmacion)
        except Exception:
            msg.body("Lo siento, hubo un error procesando tu pedido. Escribe *hola* para intentar de nuevo.")

    elif respuesta_claude.strip() == "ACCION_CANCELAR":
        limpiar_conversacion(numero)
        detener_timer(numero)
        msg.body("❌ *Orden cancelada.*\n\nEscribe *hola* cuando quieras pedir de nuevo. 😊")

    else:
        msg.body(respuesta_claude)

    return str(resp)


if __name__ == "__main__":
    app.run(debug=True, port=3000)
