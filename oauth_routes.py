# oauth_routes.py — Wasapeame
# Blueprint Flask para el flujo OAuth de Google Calendar
# Registrar en app.py: app.register_blueprint(oauth_bp)

from flask import Blueprint, request, redirect
from google_calendar import get_auth_url, handle_oauth_callback

oauth_bp = Blueprint("oauth", __name__)

@oauth_bp.route("/oauth/google/<codigo>")
def iniciar_oauth(codigo):
    """
    El dueño del negocio visita esta URL (se la mandas por WhatsApp una sola vez).
    Lo redirige a la pantalla de consentimiento de Google.
    """
    return redirect(get_auth_url(codigo))

@oauth_bp.route("/oauth/callback")
def oauth_callback():
    """
    Google redirige aquí con ?code=...&state=negocio_id
    Intercambia el code, guarda tokens, confirma al dueño.
    """
    code  = request.args.get("code")
    state = request.args.get("state")

    if not code or not state:
        return "Error: parámetros incompletos.", 400

    try:
        negocio_id = handle_oauth_callback(code, state)
        return (
            f"✅ Google Calendar conectado correctamente para el negocio #{negocio_id}. "
            f"Puedes cerrar esta ventana."
        ), 200
    except Exception as e:
        return f"Error al conectar Google Calendar: {e}", 500
