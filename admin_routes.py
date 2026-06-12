"""
Blueprint Admin — Dashboard para Vhiarly
Rutas: /admin/*, /admin/api/*
"""

import os
import json
from functools import wraps
from flask import Blueprint, render_template, request, session, redirect, jsonify, g
from db import execute

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "wappi2026")


def require_admin(f):
    """Decorator para verificar sesión admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_ok'):
            return redirect('/admin')
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('', methods=['GET', 'POST'])
def login():
    """Login admin con contraseña"""
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['admin_ok'] = True
            return redirect('/admin/dashboard')
        else:
            return render_template('admin/login.html', error='Contraseña incorrecta')
    return render_template('admin/login.html')


@admin_bp.route('/dashboard')
@require_admin
def dashboard():
    """Dashboard principal del admin"""
    return render_template('admin/dashboard.html')


@admin_bp.route('/negocio/<codigo>')
@require_admin
def negocio_detalle(codigo):
    """Detalle de un negocio específico"""
    negocio = execute(
        "SELECT codigo, nombre, tipo, modo, numero_negocio, activo FROM negocios WHERE codigo = %s",
        (codigo,),
        fetch='one'
    )
    if not negocio:
        return "Negocio no encontrado", 404
    return render_template('admin/negocio_detalle.html', negocio=negocio)


@admin_bp.route('/api/stats')
@require_admin
def api_stats():
    """JSON: Resumen global desde dashboard_stats"""
    result = execute(
        "SELECT stats FROM dashboard_stats WHERE codigo = %s",
        ('GLOBAL',),
        fetch='one'
    )
    if result and result[0]:
        return jsonify(json.loads(result[0]))
    return jsonify({"error": "Sin datos aún"}), 404


@admin_bp.route('/api/negocios')
@require_admin
def api_negocios():
    """JSON: Lista de negocios con su estado en vivo"""
    negocios = execute(
        "SELECT codigo, nombre, tipo, modo, numero_negocio, activo FROM negocios ORDER BY codigo",
        fetch='all'
    )

    result = []
    for neg in negocios or []:
        codigo, nombre, tipo, modo, numero, activo = neg

        # Stats del negocio
        stats = execute(
            "SELECT stats FROM dashboard_stats WHERE codigo = %s",
            (codigo,),
            fetch='one'
        )
        stats_data = json.loads(stats[0]) if stats and stats[0] else {}

        # Último mensaje
        ultimo_msg = execute(
            "SELECT actualizado_en FROM conversaciones_pedidos WHERE codigo = %s ORDER BY actualizado_en DESC LIMIT 1",
            (codigo,),
            fetch='one'
        )
        if not ultimo_msg:
            ultimo_msg = execute(
                "SELECT actualizado_en FROM conversaciones_citas WHERE codigo = %s ORDER BY actualizado_en DESC LIMIT 1",
                (codigo,),
                fetch='one'
            )

        result.append({
            "codigo": codigo,
            "nombre": nombre,
            "tipo": tipo,
            "modo": modo,
            "numero": numero,
            "activo": activo,
            "stats": stats_data,
            "ultimo_mensaje": str(ultimo_msg[0]) if ultimo_msg else "N/A",
        })

    return jsonify(result)


@admin_bp.route('/api/alertas')
@require_admin
def api_alertas():
    """JSON: Imprevistos abiertos"""
    alertas = execute(
        "SELECT id, codigo, tipo, descripcion, detalle, creado_en FROM imprevistos WHERE estado = 'abierto' ORDER BY creado_en DESC",
        fetch='all'
    )

    result = []
    for alerta in alertas or []:
        result.append({
            "id": alerta[0],
            "codigo": alerta[1],
            "tipo": alerta[2],
            "descripcion": alerta[3],
            "detalle": json.loads(alerta[4]) if alerta[4] else {},
            "creado_en": str(alerta[5]),
        })

    return jsonify(result)


@admin_bp.route('/api/resolver/<int:imprevisto_id>', methods=['POST'])
@require_admin
def api_resolver(imprevisto_id):
    """Marcar imprevisto como resuelto"""
    execute(
        "UPDATE imprevistos SET estado = 'resuelto', resuelto_en = NOW() WHERE id = %s",
        (imprevisto_id,)
    )
    return jsonify({"ok": True})


@admin_bp.route('/api/notificar/<codigo>', methods=['POST'])
@require_admin
def api_notificar(codigo):
    """Enviar WhatsApp al negocio (requiere import de app.py meta_send)"""
    mensaje = request.json.get('mensaje', '')
    if not mensaje:
        return jsonify({"error": "Mensaje vacío"}), 400

    # Obtener número del negocio
    negocio = execute(
        "SELECT numero_negocio FROM negocios WHERE codigo = %s",
        (codigo,),
        fetch='one'
    )
    if not negocio:
        return jsonify({"error": "Negocio no encontrado"}), 404

    # Meta_send se importa dinámicamente desde app.py para evitar circular import
    try:
        from app import meta_send
        meta_send(f"whatsapp:+{negocio[0]}", mensaje)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
