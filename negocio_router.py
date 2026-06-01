import re
from db import execute

def detectar_codigo(mensaje):
    """Retorna (codigo, resto_mensaje) si el mensaje empieza con un código válido, o (None, mensaje)."""
    match = re.match(r'^([A-Z]{2}\d+)\s*(.*)', mensaje.strip(), re.IGNORECASE)
    if not match:
        return None, mensaje
    codigo = match.group(1).upper()
    row = execute("SELECT codigo FROM negocios WHERE codigo = %s AND activo = TRUE", (codigo,), fetch="one")
    if row:
        return codigo, match.group(2).strip()
    return None, mensaje

def obtener_negocio(codigo):
    """
    Retorna dict con config completa del negocio (estática) o None.
    Incluye catalogo, servicios y horario reconstruidos desde BD.
    Los campos dinámicos (citas, bloqueos, pedidos_activos) se consultan
    directamente en flujo_citas.py y flujo_pedidos.py.
    """
    neg = execute(
        "SELECT codigo, nombre, tipo, modo, numero_negocio, pin, activo "
        "FROM negocios WHERE codigo = %s",
        (codigo.upper(),), fetch="one"
    )
    if not neg:
        return None

    catalogo = {}
    for row in execute(
        "SELECT clave, nombre, precio, unidad, rebanado, activo, cantidad "
        "FROM catalogo WHERE codigo = %s",
        (codigo,), fetch="all"
    ) or []:
        catalogo[row["clave"]] = {
            "nombre":   row["nombre"],
            "precio":   float(row["precio"]),
            "unidad":   row["unidad"],
            "rebanado": row["rebanado"],
            "activo":   row["activo"],
            "cantidad": row["cantidad"],
        }

    servicios = {}
    for row in execute(
        "SELECT clave, nombre, duracion_minutos, precio, activo "
        "FROM servicios WHERE codigo = %s",
        (codigo,), fetch="all"
    ) or []:
        servicios[row["clave"]] = {
            "nombre":            row["nombre"],
            "duracion_minutos":  row["duracion_minutos"],
            "precio":            float(row["precio"]),
            "activo":            row["activo"],
        }

    horario = {}
    for row in execute(
        "SELECT dia, trabaja, inicio, fin FROM horarios WHERE codigo = %s",
        (codigo,), fetch="all"
    ) or []:
        horario[row["dia"]] = {
            "trabaja": row["trabaja"],
            "inicio":  row["inicio"],
            "fin":     row["fin"],
        }

    neg["catalogo"] = catalogo
    neg["servicios"] = servicios
    neg["horario"]   = horario
    return neg

def es_admin(mensaje, negocio):
    """Retorna True si el mensaje es exactamente 'admin <pin>'."""
    patron = re.compile(r'^admin\s+' + re.escape(negocio["pin"]) + r'$', re.IGNORECASE)
    return bool(patron.match(mensaje.strip()))

def obtener_modo(codigo):
    neg = obtener_negocio(codigo)
    return neg.get("modo") if neg else None

def es_numero_negocio(numero):
    """Retorna el codigo si el numero pertenece a un negocio registrado, o None."""
    row = execute(
        "SELECT codigo FROM negocios WHERE numero_negocio = %s AND activo = TRUE",
        (numero,), fetch="one"
    )
    return row["codigo"] if row else None
