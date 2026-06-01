import re
from psycopg2.extras import Json
from db import execute
from negocio_router import obtener_negocio

_CONFIRMAR = {"confirmar", "confirma", "si", "sí", "dale", "ok", "okay", "listo", "va", "adelante", "procede"}
_CANCELAR  = {"cancelar", "cancel", "salir", "exit", "bye", "chao", "nada", "olvida", "adios", "adiós"}


def _norm(t):
    t = t.lower().strip()
    for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ü","u"),("ñ","n")]:
        t = t.replace(a, b)
    return t


# ── Helpers de estado de conversación ────────────────────────────────────────

def _get_estado(numero_cliente):
    return execute(
        "SELECT * FROM conversaciones_pedidos WHERE numero_cliente = %s",
        (numero_cliente,), fetch="one"
    )

def _set_estado(numero_cliente, data):
    execute("""
        INSERT INTO conversaciones_pedidos
            (numero_cliente, codigo, estado, items, direccion, referencia,
             item_pendiente_rebanado, cola_rebanado, rebanado_origen,
             item_sin_stock, timeout_en)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW() + INTERVAL '5 minutes')
        ON CONFLICT (numero_cliente) DO UPDATE SET
            codigo                  = EXCLUDED.codigo,
            estado                  = EXCLUDED.estado,
            items                   = EXCLUDED.items,
            direccion               = EXCLUDED.direccion,
            referencia              = EXCLUDED.referencia,
            item_pendiente_rebanado = EXCLUDED.item_pendiente_rebanado,
            cola_rebanado           = EXCLUDED.cola_rebanado,
            rebanado_origen         = EXCLUDED.rebanado_origen,
            item_sin_stock          = EXCLUDED.item_sin_stock,
            timeout_en              = EXCLUDED.timeout_en,
            actualizado_en          = NOW()
    """, (
        numero_cliente,
        data["codigo"],
        data["estado"],
        Json(data.get("items", [])),
        data.get("direccion", ""),
        data.get("referencia", ""),
        Json(data["item_pendiente_rebanado"]) if data.get("item_pendiente_rebanado") is not None else None,
        Json(data["cola_rebanado"])           if data.get("cola_rebanado")           is not None else None,
        data.get("rebanado_origen"),
        Json(data["item_sin_stock"])          if data.get("item_sin_stock")          is not None else None,
    ))

def _del_estado(numero_cliente):
    execute("DELETE FROM conversaciones_pedidos WHERE numero_cliente = %s", (numero_cliente,))


# ── Helpers de pedidos y cola ─────────────────────────────────────────────────

def _get_pedido(numero_cliente):
    return execute(
        "SELECT * FROM pedidos WHERE numero_cliente = %s AND estado = 'pendiente'",
        (numero_cliente,), fetch="one"
    )

def _get_cola(codigo):
    rows = execute(
        "SELECT numero_cliente FROM pedidos WHERE codigo = %s AND estado = 'pendiente' ORDER BY creado_en ASC",
        (codigo,), fetch="all"
    )
    return [r["numero_cliente"] for r in rows] if rows else []

def _siguiente_turno(codigo):
    row = execute("""
        INSERT INTO contadores_turnos (codigo, contador) VALUES (%s, 1)
        ON CONFLICT (codigo) DO UPDATE SET contador = contadores_turnos.contador + 1
        RETURNING contador
    """, (codigo,), fetch="one")
    return row["contador"]

def _guardar_pedido(numero_cliente, codigo, items, total, turno, direccion, referencia):
    execute("""
        INSERT INTO pedidos (numero_cliente, codigo, turno, items, total, direccion, referencia, estado)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'pendiente')
        ON CONFLICT DO NOTHING
    """, (numero_cliente, codigo, turno, Json(items), total, direccion, referencia))

def _eliminar_pedido(numero_cliente):
    execute("DELETE FROM pedidos WHERE numero_cliente = %s AND estado = 'pendiente'", (numero_cliente,))


# ── Utilidades de formato ─────────────────────────────────────────────────────

def _extraer_cantidad(msg, nombre_norm, unidad):
    if unidad == "libra":
        FRACCIONES = [
            ("tres cuartos", 0.75), ("3/4", 0.75),
            ("media libra",  0.5),  ("media", 0.5), ("1/2", 0.5),
            ("un cuarto",    0.25), ("cuarto", 0.25), ("1/4", 0.25),
        ]
        for frase, val in FRACCIONES:
            if frase in msg:
                return val, frase
        m = re.search(r"(\d+(?:\.\d+)?)\s*libra", msg)
        if m:
            v = float(m.group(1))
            return v, f"{m.group(1)} libra{'s' if v != 1 else ''}"
        return 1.0, "1 libra"
    else:
        idx = msg.find(nombre_norm)
        if idx >= 0:
            m = re.search(r"(\d+)\s*$", msg[max(0, idx - 10):idx].strip())
            if m:
                return int(m.group(1)), m.group(1)
            m = re.search(r"^(\d+)", msg[idx + len(nombre_norm):idx + len(nombre_norm) + 10].strip())
            if m:
                return int(m.group(1)), m.group(1)
        return 1, "1"


def _parsear_productos(mensaje, catalogo):
    msg = _norm(mensaje)
    disponibles = []
    agotados = []
    for clave, prod in catalogo.items():
        if not prod.get("activo", True):
            continue
        nombre_norm = _norm(prod["nombre"])
        if nombre_norm not in msg and clave not in msg:
            continue
        if prod.get("cantidad", 1) <= 0:
            agotados.append(prod["nombre"])
            continue
        cantidad, texto = _extraer_cantidad(msg, nombre_norm, prod["unidad"])
        disponibles.append((clave, prod, cantidad, texto))
    return disponibles, agotados


def _fmt(item):
    pref = f" ({item['rebanado_pref']})" if item.get("rebanado_pref") else ""
    if item["unidad"] == "libra":
        return f"• {item['texto']} de {item['nombre']}{pref} - ${item['precio']:.0f} pesos"
    return f"• {item['texto']}x {item['nombre']}{pref} - ${item['precio']:.0f} pesos"


def _menu(negocio):
    lineas = [f"Bienvenido a {negocio['nombre']}!\n\nNuestros productos:\n"]
    for clave, prod in negocio.get("catalogo", {}).items():
        if prod.get("activo", True) and prod.get("cantidad", 1) > 0:
            suf = "/libra" if prod["unidad"] == "libra" else ""
            lineas.append(f"• {prod['nombre']} - ${prod['precio']} pesos{suf}")
    lineas += ["", "Escribe lo que quieres pedir.", "Escribe *cancelar* para salir."]
    return "\n".join(lineas)


def _resumen(items, pie=""):
    total = sum(i["precio"] for i in items)
    lineas = ["Tu orden:\n"] + [_fmt(i) for i in items] + [f"\nTotal: ${total:.0f} pesos"]
    if pie:
        lineas.append(pie)
    return "\n".join(lineas)


# ── Notificaciones ────────────────────────────────────────────────────────────

def _notificar_posiciones(codigo, twilio_send):
    cola = _get_cola(codigo)
    for i, cliente in enumerate(cola[1:], start=1):
        s = "s" if i > 1 else ""
        twilio_send(cliente, f"Hay {i} pedido{s} antes que el tuyo. Te avisamos cuando sea tu turno.")


def _enviar_pedido_a_negocio(numero_negocio, numero_cliente, pedido, twilio_send, prefijo="NUEVO PEDIDO"):
    turno = pedido.get("turno", "?")
    txt  = f"{prefijo} — Turno #T-{turno} de {numero_cliente}\n\n"
    txt += "\n".join(_fmt(i) for i in pedido.get("items", []))
    txt += f"\n\nTotal: ${pedido.get('total', 0):.0f} pesos"
    txt += f"\nDireccion: {pedido.get('direccion', '')}"
    txt += f"\nReferencia: {pedido.get('referencia', '')}"
    txt += "\n\nSi algo no esta disponible escribe: no hay [producto]"
    twilio_send(numero_negocio, txt)


# ── API pública ───────────────────────────────────────────────────────────────

def tiene_flujo_activo(numero_cliente):
    return execute(
        "SELECT 1 FROM conversaciones_pedidos WHERE numero_cliente = %s",
        (numero_cliente,), fetch="one"
    ) is not None


def limpiar_flujo(numero_cliente):
    _eliminar_pedido(numero_cliente)
    _del_estado(numero_cliente)


def manejar_pedido(numero_cliente, codigo, mensaje, twilio_send):
    msg = _norm(mensaje)

    estado = _get_estado(numero_cliente)
    if estado:
        codigo = estado["codigo"]
    elif not codigo:
        return None

    negocio = obtener_negocio(codigo)
    if not negocio:
        return "Negocio no encontrado."

    if not estado:
        estado = {
            "numero_cliente": numero_cliente,
            "codigo": codigo, "items": [], "estado": "pidiendo",
            "direccion": "", "referencia": "",
            "item_pendiente_rebanado": None, "cola_rebanado": None,
            "rebanado_origen": None, "item_sin_stock": None,
        }
        _set_estado(numero_cliente, estado)

    s = estado["estado"]
    items = estado.get("items") or []

    # Cancelar desde cualquier estado
    if any(re.search(r"\b" + p + r"\b", msg) for p in _CANCELAR):
        cola = _get_cola(codigo)
        era_primero = bool(cola) and cola[0] == numero_cliente
        if s in ("pedido_enviado", "esperando_decision"):
            twilio_send(negocio["numero_negocio"],
                        f"El cliente {numero_cliente} cancelo su pedido.")
        _eliminar_pedido(numero_cliente)
        _del_estado(numero_cliente)
        if era_primero:
            cola_actual = _get_cola(codigo)
            if cola_actual:
                siguiente = cola_actual[0]
                pedido_sig = _get_pedido(siguiente)
                _enviar_pedido_a_negocio(negocio["numero_negocio"], siguiente,
                                         pedido_sig, twilio_send, prefijo="SIGUIENTE PEDIDO")
                twilio_send(siguiente, "Tu pedido está siendo preparado, sale en unos minutos!")
                _notificar_posiciones(codigo, twilio_send)
        return "Orden cancelada. Escribe el codigo del negocio cuando quieras pedir de nuevo."

    # ── PIDIENDO ──
    if s == "pidiendo":
        if not msg or any(p in msg for p in ["hola", "buenas", "menu", "menú", "que tienen"]):
            return _menu(negocio)

        if any(re.search(r"\b" + p + r"\b", msg) for p in _CONFIRMAR):
            if not items:
                return "No tienes productos en tu orden. Escribe *menú* para ver lo que tenemos."
            estado["estado"] = "esperando_confirmacion"
            _set_estado(numero_cliente, estado)
            return _resumen(items, "\nEscribe *sí* para confirmar o *cancelar* para salir.")

        disponibles, agotados = _parsear_productos(mensaje, negocio.get("catalogo", {}))

        if not disponibles:
            if agotados:
                return "Ese producto está agotado ahorita. Escribe *menú* para ver lo que tenemos."
            return "No encontre ese producto. Escribe *menú* para ver lo que tenemos."

        cola_rebanado = []
        for clave, prod, cantidad, texto in disponibles:
            item = {
                "clave": clave, "nombre": prod["nombre"],
                "cantidad": cantidad, "texto": texto,
                "unidad": prod["unidad"], "precio": prod["precio"] * cantidad,
            }
            if prod.get("rebanado"):
                cola_rebanado.append(item)
            else:
                items.append(item)

        if cola_rebanado:
            primero = cola_rebanado.pop(0)
            estado["items"] = items
            estado["item_pendiente_rebanado"] = primero
            estado["cola_rebanado"] = cola_rebanado
            estado["rebanado_origen"] = "pidiendo"
            estado["estado"] = "esperando_rebanado"
            _set_estado(numero_cliente, estado)
            return (f"¿Cómo quieres el {primero['nombre']}?\n\n"
                    "• Escribe *rebanado*\n"
                    "• Escribe *en pieza*")

        estado["items"] = items
        _set_estado(numero_cliente, estado)
        respuesta = _resumen(items, "\nEscribe mas productos o *confirmar* para pedir.")
        if agotados:
            respuesta += f"\n\n(Nota: {', '.join(agotados)} está agotado y no se agregó a tu orden.)"
        return respuesta

    # ── ESPERANDO CONFIRMACION ──
    if s == "esperando_confirmacion":
        if any(re.search(r"\b" + p + r"\b", msg) for p in _CONFIRMAR):
            estado["estado"] = "esperando_direccion"
            _set_estado(numero_cliente, estado)
            return ("A que direccion te enviamos?\n\n"
                    "Ejemplo: Calle Duarte 45, Los Jardines, Santo Domingo")
        return _resumen(items, "\nEscribe *sí* para confirmar o *cancelar* para salir.")

    # ── ESPERANDO DIRECCIÓN ──
    if s == "esperando_direccion":
        estado["direccion"] = mensaje
        estado["estado"] = "esperando_referencia"
        _set_estado(numero_cliente, estado)
        return ("Alguna referencia para encontrarte mas facil?\n\n"
                "Ejemplo: Al lado de la farmacia, Casa azul\n\n"
                "Si no tienes, escribe *ninguna*.")

    # ── ESPERANDO REFERENCIA ──
    if s == "esperando_referencia":
        estado["referencia"] = mensaje if msg != "ninguna" else "Sin referencia"
        total = sum(i["precio"] for i in items)
        turno = _siguiente_turno(codigo)

        _guardar_pedido(
            numero_cliente, codigo, items, total, turno,
            estado["direccion"], estado["referencia"]
        )
        estado["estado"] = "pedido_enviado"
        _set_estado(numero_cliente, estado)

        cola = _get_cola(codigo)
        posicion = len(cola)

        if posicion == 1:
            pedido = _get_pedido(numero_cliente)
            _enviar_pedido_a_negocio(negocio["numero_negocio"], numero_cliente, pedido, twilio_send)

        r  = f"Pedido enviado a {negocio['nombre']}! Turno *#T-{turno}*\n\n"
        r += "Tu pedido:\n"
        r += "\n".join(_fmt(i) for i in items)
        r += f"\n\nTotal: ${total:.0f} pesos"
        r += f"\nDireccion: {estado['direccion']}"
        r += f"\nReferencia: {estado['referencia']}"
        if posicion == 1:
            r += "\n\n*Tu pedido está siendo preparado.*"
        else:
            s_plural = "s" if posicion - 1 > 1 else ""
            r += f"\n\nHay {posicion - 1} pedido{s_plural} antes que el tuyo. Te avisamos cuando sea tu turno."
        r += "\n\nPuedes escribir *cancelar* si cambias de opinion antes de que sea procesado."
        return r

    # ── PEDIDO ENVIADO ──
    if s == "pedido_enviado":
        if "ajustar" in msg:
            estado["estado"] = "ajustando"
            _set_estado(numero_cliente, estado)
            return (_resumen(items) +
                    "\n\nQue quieres cambiar?\n\n"
                    "• *quitar* [producto] para eliminarlo\n"
                    "• escribe un producto para agregarlo\n"
                    "• *listo* para confirmar los cambios")
        return ("*Tu pedido esta pendiente.*\n\n"
                "Escribe *ajustar* para modificarlo o *cancelar* para cancelarlo.")

    # ── ESPERANDO REBANADO ──
    if s == "esperando_rebanado":
        item = estado.get("item_pendiente_rebanado") or {}
        nombre = item.get("nombre", "")

        if any(p in msg for p in ["rebanado", "rebana", "rebanada"]):
            item["rebanado_pref"] = "rebanado"
        elif any(p in msg for p in ["pieza", "entero", "entera", "sin rebanar"]):
            item["rebanado_pref"] = "en pieza"
        else:
            return (f"¿Cómo quieres el {nombre}?\n\n"
                    "• Escribe *rebanado*\n"
                    "• Escribe *en pieza*\n"
                    "• Escribe *cancelar* para cancelar el pedido")

        items.append(item)
        cola_reb = estado.get("cola_rebanado") or []

        if cola_reb:
            siguiente = cola_reb.pop(0)
            estado["items"] = items
            estado["item_pendiente_rebanado"] = siguiente
            estado["cola_rebanado"] = cola_reb
            _set_estado(numero_cliente, estado)
            return (f"¿Cómo quieres el {siguiente['nombre']}?\n\n"
                    "• Escribe *rebanado*\n"
                    "• Escribe *en pieza*")

        origen = estado.get("rebanado_origen", "pidiendo")
        estado["items"] = items
        estado["item_pendiente_rebanado"] = None
        estado["cola_rebanado"] = None
        estado["rebanado_origen"] = None
        estado["estado"] = origen
        _set_estado(numero_cliente, estado)

        if origen == "ajustando":
            return _resumen(items, "\nSigue ajustando o escribe *listo* para confirmar.")
        return _resumen(items, "\nEscribe mas productos o *confirmar* para pedir.")

    # ── ESPERANDO DECISION (producto no disponible) ──
    if s == "esperando_decision":
        item = estado.get("item_sin_stock") or {}
        nombre = item.get("nombre", "ese producto")

        if "continuar" in msg:
            items = [i for i in items if i["clave"] != item.get("clave")]
            if not items:
                cola = _get_cola(codigo)
                era_primero = bool(cola) and cola[0] == numero_cliente
                _eliminar_pedido(numero_cliente)
                _del_estado(numero_cliente)
                if era_primero:
                    cola_actual = _get_cola(codigo)
                    if cola_actual:
                        siguiente = cola_actual[0]
                        pedido_sig = _get_pedido(siguiente)
                        _enviar_pedido_a_negocio(negocio["numero_negocio"], siguiente,
                                                 pedido_sig, twilio_send, prefijo="SIGUIENTE PEDIDO")
                        twilio_send(siguiente, "Tu pedido está siendo preparado, sale en unos minutos!")
                        _notificar_posiciones(codigo, twilio_send)
                return "Tu pedido quedó vacío. Escribe el codigo del negocio cuando quieras hacer un nuevo pedido."

            pedido = _get_pedido(numero_cliente)
            total = sum(i["precio"] for i in items)
            execute("""
                UPDATE pedidos SET items = %s, total = %s
                WHERE numero_cliente = %s AND estado = 'pendiente'
            """, (Json(items), total, numero_cliente))
            estado["items"] = items
            estado["estado"] = "pedido_enviado"
            estado["item_sin_stock"] = None
            _set_estado(numero_cliente, estado)

            txt  = f"PEDIDO ACTUALIZADO de {numero_cliente} — se eliminó {nombre}\n\n"
            txt += "\n".join(_fmt(i) for i in items)
            txt += f"\n\nTotal: ${total:.0f} pesos"
            twilio_send(negocio["numero_negocio"], txt)
            return _resumen(items, "\n\nPedido actualizado. Tu orden sigue en camino.")

        return (f"¿Qué prefieres?\n\n"
                f"• Escribe *continuar* para seguir sin {nombre}\n"
                f"• Escribe *cancelar* para cancelar el pedido")

    # ── AJUSTANDO ──
    if s == "ajustando":
        if re.search(r"\blisto\b", msg):
            total = sum(i["precio"] for i in items)
            pedido = _get_pedido(numero_cliente)
            execute("""
                UPDATE pedidos SET items = %s, total = %s
                WHERE numero_cliente = %s AND estado = 'pendiente'
            """, (Json(items), total, numero_cliente))
            estado["estado"] = "pedido_enviado"
            _set_estado(numero_cliente, estado)

            txt  = f"PEDIDO AJUSTADO de {numero_cliente}\n\n"
            txt += "\n".join(_fmt(i) for i in items)
            txt += f"\n\nTotal: ${total:.0f} pesos"
            txt += f"\nDireccion: {estado['direccion']}"
            txt += f"\nReferencia: {estado['referencia']}"
            twilio_send(negocio["numero_negocio"], txt)
            return _resumen(items, "\n\nPedido actualizado y reenviado al negocio.")

        m = re.match(r"quitar\s+(.+)", msg)
        if m:
            buscado = m.group(1).strip()
            antes = len(items)
            items = [i for i in items if buscado not in _norm(i["nombre"])]
            if len(items) == antes:
                return f"No encontre '{buscado}' en tu pedido."
            if not items:
                estado["items"] = items
                _set_estado(numero_cliente, estado)
                return "Eliminaste todos los productos. Agrega algo o escribe *cancelar*."
            estado["items"] = items
            _set_estado(numero_cliente, estado)
            return _resumen(items, "\nSigue ajustando o escribe *listo* para confirmar.")

        disponibles, agotados = _parsear_productos(mensaje, negocio.get("catalogo", {}))
        if disponibles:
            cola_rebanado = []
            for clave, prod, cantidad, texto in disponibles:
                item = {
                    "clave": clave, "nombre": prod["nombre"],
                    "cantidad": cantidad, "texto": texto,
                    "unidad": prod["unidad"], "precio": prod["precio"] * cantidad,
                }
                if prod.get("rebanado"):
                    cola_rebanado.append(item)
                else:
                    items.append(item)

            if cola_rebanado:
                primero = cola_rebanado.pop(0)
                estado["items"] = items
                estado["item_pendiente_rebanado"] = primero
                estado["cola_rebanado"] = cola_rebanado
                estado["rebanado_origen"] = "ajustando"
                estado["estado"] = "esperando_rebanado"
                _set_estado(numero_cliente, estado)
                return (f"¿Cómo quieres el {primero['nombre']}?\n\n"
                        "• Escribe *rebanado*\n"
                        "• Escribe *en pieza*")

            estado["items"] = items
            _set_estado(numero_cliente, estado)
            return _resumen(items, "\nSigue ajustando o escribe *listo* para confirmar.")

        if agotados:
            return "Ese producto está agotado ahorita. Escribe *menú* para ver lo que tenemos."

        return "No entendi. Escribe *quitar* [producto], agrega un producto, o *listo* para confirmar."

    return None


def manejar_negocio(numero_negocio, codigo_negocio, mensaje, twilio_send):
    msg = _norm(mensaje)

    # "no hay [producto]"
    m = re.match(r"no\s+hay\s+(.+)", msg)
    if m:
        buscado = m.group(1).strip()
        pedidos_pendientes = execute(
            "SELECT numero_cliente, items FROM pedidos WHERE codigo = %s AND estado = 'pendiente'",
            (codigo_negocio,), fetch="all"
        ) or []
        for pedido_row in reversed(pedidos_pendientes):
            cliente = pedido_row["numero_cliente"]
            for item in (pedido_row["items"] or []):
                if buscado in _norm(item["nombre"]):
                    estado = _get_estado(cliente)
                    if estado:
                        estado["estado"] = "esperando_decision"
                        estado["item_sin_stock"] = item
                        _set_estado(cliente, estado)
                    negocio = obtener_negocio(codigo_negocio)
                    twilio_send(
                        cliente,
                        f"Lo sentimos, *{item['nombre']}* no está disponible. ¿Qué prefieres?\n\n"
                        "• Escribe *continuar* para seguir sin ese producto\n"
                        "• Escribe *cancelar* para cancelar el pedido"
                    )
                    return f"Cliente notificado sobre {item['nombre']}."
        return "No encontre pedidos pendientes con ese producto."

    # "listo" → pedido despachado
    if re.search(r"\blisto\b", msg):
        cola = _get_cola(codigo_negocio)
        if not cola:
            return "No hay pedidos pendientes."

        cliente_actual = cola[0]
        estado_actual = _get_estado(cliente_actual)
        if estado_actual and estado_actual.get("estado") == "esperando_decision":
            return "El pedido actual tiene un producto pendiente de decisión del cliente. Espera su respuesta."

        pedido_actual = _get_pedido(cliente_actual)
        turno_actual = pedido_actual.get("turno", "?") if pedido_actual else "?"

        twilio_send(cliente_actual, "🛵 Tu pedido está en camino!")
        execute(
            "UPDATE pedidos SET estado = 'despachado' WHERE numero_cliente = %s AND estado = 'pendiente'",
            (cliente_actual,)
        )
        _del_estado(cliente_actual)

        cola_actual = _get_cola(codigo_negocio)
        if not cola_actual:
            return "✅ Listo! No hay más pedidos por ahora."

        siguiente = cola_actual[0]
        pedido_sig = _get_pedido(siguiente)
        _enviar_pedido_a_negocio(numero_negocio, siguiente, pedido_sig, twilio_send, prefijo="SIGUIENTE PEDIDO")
        twilio_send(siguiente, "Tu pedido está siendo preparado, sale en unos minutos!")
        _notificar_posiciones(codigo_negocio, twilio_send)

        turno_sig = pedido_sig.get("turno", "?") if pedido_sig else "?"
        return f"Turno #T-{turno_actual} despachado. Enviando turno #T-{turno_sig} al siguiente."

    return None
