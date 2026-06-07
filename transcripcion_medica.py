import os
import io
import requests
import anthropic
from fpdf import FPDF

AZURE_SPEECH_KEY    = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "eastus")
META_ACCESS_TOKEN   = os.getenv("META_ACCESS_TOKEN")


def descargar_audio_meta(media_id):
    headers = {"Authorization": f"Bearer {META_ACCESS_TOKEN}"}
    r = requests.get(
        f"https://graph.facebook.com/v19.0/{media_id}",
        headers=headers, timeout=10
    )
    r.raise_for_status()
    url = r.json().get("url")
    if not url:
        return None
    r2 = requests.get(url, headers=headers, timeout=30)
    r2.raise_for_status()
    return r2.content


def transcribir_audio(audio_bytes):
    if not AZURE_SPEECH_KEY:
        raise RuntimeError("AZURE_SPEECH_KEY no configurado")
    url = (
        f"https://{AZURE_SPEECH_REGION}.stt.speech.microsoft.com"
        "/speech/recognition/conversation/cognitiveservices/v1"
        "?language=es-DO&format=simple"
    )
    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY,
        "Content-Type": "audio/ogg; codecs=opus",
    }
    r = requests.post(url, headers=headers, data=audio_bytes, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("RecognitionStatus") == "Success":
        return data.get("DisplayText", "")
    return None


def estructurar_historia_clinica(transcripcion):
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        system=(
            "Eres un asistente medico. Recibes la transcripcion de una nota de voz de un medico. "
            "Extrae y estructura la informacion como historia clinica breve. "
            "Usa solo las secciones con informacion: Motivo, Sintomas, Antecedentes, Evaluacion, Plan. "
            "Sin markdown. Responde en espanol."
        ),
        messages=[{"role": "user", "content": f"Transcripcion:\n{transcripcion}"}]
    )
    return msg.content[0].text


def generar_pdf_historia(transcripcion, historia, nombre_negocio):
    """Genera PDF en memoria con transcripción + historia clínica. Retorna bytes."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_margins(20, 20, 20)

    # Encabezado
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, nombre_negocio, ln=True, align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "Historia Clinica", ln=True, align="C")
    pdf.ln(4)
    pdf.set_draw_color(40, 167, 69)
    pdf.set_line_width(0.5)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(6)

    # Historia clínica
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Historia Clinica Estructurada", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, historia.encode("latin-1", errors="replace").decode("latin-1"))
    pdf.ln(6)

    # Transcripción original
    pdf.set_draw_color(200, 200, 200)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, "Transcripcion Original", ln=True)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(80, 80, 80)
    pdf.multi_cell(0, 5, transcripcion.encode("latin-1", errors="replace").decode("latin-1"))

    return bytes(pdf.output())


def subir_media_meta(pdf_bytes, nombre_archivo):
    """Sube PDF a Meta y retorna media_id."""
    url = f"https://graph.facebook.com/v19.0/{os.getenv('META_PHONE_NUMBER_ID')}/media"
    headers = {"Authorization": f"Bearer {META_ACCESS_TOKEN}"}
    files = {
        "file": (nombre_archivo, pdf_bytes, "application/pdf"),
        "type": (None, "application/pdf"),
        "messaging_product": (None, "whatsapp"),
    }
    r = requests.post(url, headers=headers, files=files, timeout=30)
    r.raise_for_status()
    return r.json().get("id")


def enviar_pdf_historia(transcripcion, historia, negocio, twilio_send, numero_destino):
    """Genera PDF, lo sube a Meta y lo envía como documento."""
    try:
        pdf_bytes = generar_pdf_historia(transcripcion, historia, negocio.get("nombre", "Historia Clinica"))
        media_id  = subir_media_meta(pdf_bytes, "historia_clinica.pdf")
        if not media_id:
            return False
        phone = numero_destino.replace("whatsapp:+", "").replace("+", "").strip()
        requests.post(
            f"https://graph.facebook.com/v19.0/{os.getenv('META_PHONE_NUMBER_ID')}/messages",
            headers={"Authorization": f"Bearer {META_ACCESS_TOKEN}", "Content-Type": "application/json"},
            json={
                "messaging_product": "whatsapp",
                "to": phone,
                "type": "document",
                "document": {"id": media_id, "filename": "Historia_Clinica.pdf"}
            },
            timeout=10
        ).raise_for_status()
        return True
    except Exception as e:
        print(f"[PDF] Error: {e}")
        return False


def procesar_nota_voz_medica(media_id, negocio, twilio_send=None, numero_doctor=None):
    try:
        audio = descargar_audio_meta(media_id)
        if not audio:
            return "No pude descargar el audio. Intenta de nuevo."

        transcripcion = transcribir_audio(audio)
        if not transcripcion:
            return "No se detectaron palabras en el audio."

        historia = estructurar_historia_clinica(transcripcion)

        # Enviar PDF si tenemos los datos necesarios
        if twilio_send and numero_doctor:
            enviado = enviar_pdf_historia(transcripcion, historia, negocio, twilio_send, numero_doctor)
            if enviado:
                return f"Transcripcion:\n{transcripcion}"

        return (
            f"Transcripcion:\n{transcripcion}\n\n"
            f"Historia clinica:\n\n{historia}"
        )
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        print(f"[Transcripcion] Error: {e}")
        return "Error procesando la nota de voz."


def procesar_nota_voz_paciente(media_id):
    """Transcribe nota de voz del paciente. Retorna texto estructurado o None si falla."""
    try:
        audio = descargar_audio_meta(media_id)
        if not audio:
            return None

        transcripcion = transcribir_audio(audio)
        if not transcripcion:
            return None

        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=(
                "Eres un asistente medico. Recibes la transcripcion de la nota de voz de un paciente "
                "describiendo el motivo de su consulta. Resume en 3-5 lineas lo mas relevante para el medico. "
                "Sin markdown. En espanol."
            ),
            messages=[{"role": "user", "content": f"Transcripcion del paciente:\n{transcripcion}"}]
        )
        return msg.content[0].text
    except Exception as e:
        print(f"[Transcripcion paciente] Error: {e}")
        return None
