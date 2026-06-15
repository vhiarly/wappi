"""
Blueprint Cliente — Dashboard para dueños de negocio
Rutas: /cliente/*, /cliente/api/*
"""

import json
from functools import wraps
from flask import Blueprint, render_template, request, session, redirect, jsonify
from db import execute

cliente_bp = Blueprint('cliente', __name__, url_prefix='/cliente')


def require_cliente(f):
    """Decorator para verificar sesión cliente"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        codigo = session.get('cliente_codigo')
        if not codigo:
            return redirect('/cliente')
        return f(codigo, *args, **kwargs)
    return decorated_function


@cliente_bp.route('', methods=['GET', 'POST'])
def login():
    """Login cliente con código + PIN"""
    if request.method == 'POST':
        codigo = request.form.get('codigo', '').upper()
        pin = request.form.get('pin', '')

        try:
            negocio = execute(
                "SELECT codigo, nombre, pin FROM negocios WHERE codigo = %s",
                (codigo,),
                fetch='one'
            )

            if negocio and negocio['pin'] == pin:
                session['cliente_codigo'] = codigo
                return redirect('/cliente/dashboard')
            else:
                return render_template('cliente/login.html', error='Código o PIN inválido')
        except:
            return render_template('cliente/login.html', error='Código o PIN inválido')

    return render_template('cliente/login.html')


@cliente_bp.route('/dashboard')
@require_cliente
def dashboard(codigo):
    """Dashboard del negocio"""
    negocio = execute(
        "SELECT nombre, modo FROM negocios WHERE codigo = %s",
        (codigo,),
        fetch='one'
    )
    if not negocio:
        return "Negocio no encontrado", 404

    return render_template('cliente/dashboard.html', codigo=codigo, negocio_nombre=negocio['nombre'], modo=negocio['modo'])


@cliente_bp.route('/api/stats')
@require_cliente
def api_stats(codigo):
    """JSON: Estadísticas del negocio desde dashboard_stats"""
    result = execute(
        "SELECT stats FROM dashboard_stats WHERE codigo = %s",
        (codigo,),
        fetch='one'
    )
    if result and result['stats']:
        return jsonify(json.loads(result['stats']))
    return jsonify({"error": "Sin datos aún"}), 404


@cliente_bp.route('/api/pedidos')
@require_cliente
def api_pedidos(codigo):
    """JSON: Pedidos activos + recientes"""
    activos = execute(
        "SELECT numero_cliente, estado, items, total, actualizado_en FROM conversaciones_pedidos WHERE codigo = %s ORDER BY actualizado_en DESC LIMIT 10",
        (codigo,),
        fetch='all'
    )

    result = []
    for p in activos or []:
        result.append({
            "numero": p['numero_cliente'],
            "estado": p['estado'],
            "items": json.loads(p['items']) if p['items'] else [],
            "total": float(p['total']) if p['total'] else 0,
            "actualizado": str(p['actualizado_en']),
            "tipo": "activo"
        })

    recientes = execute(
        "SELECT numero_cliente, estado, items, total, creado_en FROM pedidos WHERE codigo = %s ORDER BY creado_en DESC LIMIT 20",
        (codigo,),
        fetch='all'
    )

    for p in recientes or []:
        result.append({
            "numero": p['numero_cliente'],
            "estado": p['estado'],
            "items": json.loads(p['items']) if p['items'] else [],
            "total": float(p['total']) if p['total'] else 0,
            "creado": str(p['creado_en']),
            "tipo": "reciente"
        })

    return jsonify(result)


@cliente_bp.route('/api/citas')
@require_cliente
def api_citas(codigo):
    """JSON: Citas del día + próximas"""
    activas = execute(
        "SELECT numero_cliente, servicio, dia, hora, actualizado_en FROM conversaciones_citas WHERE codigo = %s ORDER BY actualizado_en DESC LIMIT 10",
        (codigo,),
        fetch='all'
    )

    result = []
    for c in activas or []:
        result.append({
            "numero": c['numero_cliente'],
            "servicio": c['servicio'],
            "dia": c['dia'],
            "hora": c['hora'],
            "actualizado": str(c['actualizado_en']),
            "tipo": "activa"
        })

    confirmadas = execute(
        "SELECT numero_cliente, nombre_servicio, fecha, hora, estado, creado_en FROM citas WHERE codigo = %s ORDER BY fecha DESC LIMIT 20",
        (codigo,),
        fetch='all'
    )

    for c in confirmadas or []:
        result.append({
            "numero": c['numero_cliente'],
            "servicio": c['nombre_servicio'],
            "fecha": str(c['fecha']),
            "hora": c['hora'],
            "estado": c['estado'],
            "creado": str(c['creado_en']),
            "tipo": "confirmada"
        })

    return jsonify(result)


@cliente_bp.route('/api/catalogo')
@require_cliente
def api_catalogo(codigo):
    """JSON: Productos/servicios del negocio"""
    negocio = execute(
        "SELECT modo FROM negocios WHERE codigo = %s",
        (codigo,),
        fetch='one'
    )
    if not negocio:
        return jsonify({"error": "Negocio no encontrado"}), 404

    modo = negocio['modo']

    if modo == 'pedidos':
        items = execute(
            "SELECT id, nombre, precio, unidad, cantidad, activo FROM catalogo WHERE codigo = %s ORDER BY nombre",
            (codigo,),
            fetch='all'
        )
        return jsonify([{
            "id": i['id'],
            "nombre": i['nombre'],
            "precio": float(i['precio']),
            "unidad": i['unidad'],
            "cantidad": i['cantidad'],
            "activo": i['activo']
        } for i in items or []])
    else:
        items = execute(
            "SELECT id, nombre, precio, duracion_minutos, activo FROM servicios WHERE codigo = %s ORDER BY nombre",
            (codigo,),
            fetch='all'
        )
        return jsonify([{
            "id": i['id'],
            "nombre": i['nombre'],
            "precio": float(i['precio']),
            "duracion": i['duracion_minutos'],
            "activo": i['activo']
        } for i in items or []])


@cliente_bp.route('/api/catalogo/<int:item_id>', methods=['POST'])
@require_cliente
def api_catalogo_update(codigo, item_id):
    """Actualizar precio/cantidad/estado de producto"""
    data = request.json
    precio = data.get('precio')
    cantidad = data.get('cantidad')
    activo = data.get('activo')

    negocio = execute(
        "SELECT modo FROM negocios WHERE codigo = %s",
        (codigo,),
        fetch='one'
    )
    if not negocio:
        return jsonify({"error": "Negocio no encontrado"}), 404

    modo = negocio['modo']

    if modo == 'pedidos':
        if precio is not None:
            execute("UPDATE catalogo SET precio = %s WHERE id = %s AND codigo = %s", (precio, item_id, codigo))
        if cantidad is not None:
            execute("UPDATE catalogo SET cantidad = %s WHERE id = %s AND codigo = %s", (cantidad, item_id, codigo))
        if activo is not None:
            execute("UPDATE catalogo SET activo = %s WHERE id = %s AND codigo = %s", (activo, item_id, codigo))
    else:
        if precio is not None:
            execute("UPDATE servicios SET precio = %s WHERE id = %s AND codigo = %s", (precio, item_id, codigo))
        if activo is not None:
            execute("UPDATE servicios SET activo = %s WHERE id = %s AND codigo = %s", (activo, item_id, codigo))

    return jsonify({"ok": True})


@cliente_bp.route('/api/horarios')
@require_cliente
def api_horarios(codigo):
    """JSON: Horarios del negocio"""
    horarios = execute(
        "SELECT dia, trabaja, inicio, fin FROM horarios WHERE codigo = %s ORDER BY dia",
        (codigo,),
        fetch='all'
    )

    return jsonify([{
        "dia": h['dia'],
        "trabaja": h['trabaja'],
        "inicio": h['inicio'],
        "fin": h['fin']
    } for h in horarios or []])


@cliente_bp.route('/api/horarios/<dia>', methods=['POST'])
@require_cliente
def api_horarios_update(codigo, dia):
    """Actualizar horario de un día"""
    data = request.json
    trabaja = data.get('trabaja', True)
    inicio = data.get('inicio')
    fin = data.get('fin')

    execute(
        "UPDATE horarios SET trabaja = %s, inicio = %s, fin = %s WHERE codigo = %s AND dia = %s",
        (trabaja, inicio, fin, codigo, dia)
    )

    return jsonify({"ok": True})


@cliente_bp.route('/api/pago')
@require_cliente
def api_pago(codigo):
    """JSON: configuración de cobro del negocio"""
    neg = execute(
        "SELECT cuenta_pago_ultimos4, requiere_comprobante FROM negocios WHERE codigo = %s",
        (codigo,),
        fetch='one'
    )
    if not neg:
        return jsonify({"error": "Negocio no encontrado"}), 404
    return jsonify({
        "cuenta_pago_ultimos4": neg.get('cuenta_pago_ultimos4') or "",
        "requiere_comprobante": neg.get('requiere_comprobante'),
    })


@cliente_bp.route('/api/pago', methods=['POST'])
@require_cliente
def api_pago_update(codigo):
    """Actualizar los últimos 4 dígitos de la cuenta de cobro (para validar comprobantes)"""
    data = request.json or {}
    cuenta = (data.get('cuenta_pago_ultimos4') or "").strip()
    if cuenta and (not cuenta.isdigit() or len(cuenta) != 4):
        return jsonify({"error": "Deben ser exactamente 4 dígitos"}), 400
    execute(
        "UPDATE negocios SET cuenta_pago_ultimos4 = %s WHERE codigo = %s",
        (cuenta or None, codigo)
    )
    return jsonify({"ok": True})
