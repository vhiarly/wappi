# Scripts de Onboarding — Wasapeame

Scripts de bienvenida para enviar a nuevos negocios al activar su bot.

---

## Cómo usar

1. Localiza el negocio en `negocios.json` y obtén: código, PIN, nombre, número.
2. Sube el PDF de bienvenida a Azure Blob Storage (ver sección PDF más abajo).
3. Corre el script Python correspondiente al modo del negocio (`citas` o `pedidos`).

---

## Script Python — Envío vía Twilio

```python
import os
from twilio.rest import Client

# Cargar credenciales del .env manualmente
env = {}
with open("/ruta/wasapeame/.env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

client = Client(env["TWILIO_ACCOUNT_SID"], env["TWILIO_AUTH_TOKEN"])

# Datos del negocio
NOMBRE   = "Sir'Legal"          # negocio["nombre"]
CODIGO   = "SE1"                # clave en negocios.json
PIN      = "7391"               # negocio["pin"]
NUMERO   = "whatsapp:+18298192919"  # negocio["numero_negocio"]
PDF_URL  = "https://wasapeameassets.blob.core.windows.net/docs/WasapeameSE1.pdf"

mensaje = (
    f"Hola! Bienvenida a Wasapeame.\n\n"
    f"Tu bot de WhatsApp ya esta activo para {NOMBRE}.\n\n"
    f"Tu informacion:\n\n"
    f"Codigo de negocio: {CODIGO}\n"
    f"PIN de acceso: {PIN}\n"
    f"Numero del bot: +1 849 265 9906\n\n"
    f"Tus clientes escriben {CODIGO} al numero del bot para contactarte.\n\n"
    f"Te adjunto la guia de bienvenida. Cualquier duda estamos aqui!"
)

msg = client.messages.create(
    body=mensaje,
    from_=env["TWILIO_WHATSAPP_NUMBER"],
    to=NUMERO,
    media_url=[PDF_URL]
)

print(f"Enviado. SID: {msg.sid} | Status: {msg.status}")
```

---

## PDF de bienvenida — Azure Blob Storage

Los PDFs se alojan en:

```
https://wasapeameassets.blob.core.windows.net/docs/<NombreArchivo>.pdf
```

**Requisitos del PDF:**
- URL pública HTTPS (sin login)
- URL que termine en `.pdf`
- Contenedor `docs` con acceso público a nivel de blob

**Subir un nuevo PDF:**

```bash
ACCOUNT_KEY=$(az storage account keys list \
  --account-name wasapeameassets \
  --resource-group wasapeame-rg \
  --query "[0].value" -o tsv)

az storage blob upload \
  --account-name wasapeameassets \
  --account-key "$ACCOUNT_KEY" \
  --container-name docs \
  --file "/ruta/al/archivo.pdf" \
  --name "NombreArchivo.pdf" \
  --content-type "application/pdf"
```

---

## Plantilla de mensaje

```
Hola! Bienvenida a Wasapeame.

Tu bot de WhatsApp ya esta activo para {NOMBRE}.

Tu informacion:

Codigo de negocio: {CODIGO}
PIN de acceso: {PIN}
Numero del bot: +1 849 265 9906

Tus clientes escriben {CODIGO} al numero del bot para contactarte.

Te adjunto la guia de bienvenida. Cualquier duda estamos aqui!
```

---

## Historial de envíos

| Fecha      | Negocio   | Código | Número          | PDF                        |
|------------|-----------|--------|-----------------|----------------------------|
| 2026-06-03 | Sir'Legal | SE1    | +1 829 819 2919 | WasapeameSE1.pdf           |
