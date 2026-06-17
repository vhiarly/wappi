# Pendientes — Optimización de Listas y Diálogos (Indiana)

## 🔴 PROBLEMAS ENCONTRADOS (2026-06-17)

### 1. Listas con >10 items
- **✅ CORREGIDO:** `_enviar_lista_horas` — limitada a 10 items
- **⚠️ PENDIENTE:** `_enviar_lista_servicios` — SE1 tiene 14 servicios, se pasa de 10
  - **Afectados:** SE1 (14), PA1 (podría), cualquier negocio con >10 servicios
  - **Solución:** Limitar a 10 o usar categorías como filtro (SE1 ya lo hace)

### 2. Diálogos con texto libre que podrían ser botones
- **Línea 187:** "Escribe numero o *cancelar*" → Podrían ser botones
- **Línea 230:** Día selección "...o *cancelar*" → Botón de cancelar
- **Línea 240:** Hora selección "...o *cancelar*" → Botón de cancelar
- **Línea 530:** "Escribe *1* para reagendar o *2* para cancelar" → YA SON BOTONES ✓
- **Línea 607:** "Escribe *1*/*2*/*3*..." → Soporta ambos (botones + texto)

### 3. Input de texto libre que requiere validación
- **Nombre** (línea 1671) — Necesario texto libre, sin validación (ok)
- **Email** (línea 1677) — Necesario texto libre, CON validación ✓
- **Dirección** (línea 1503) — Necesario texto libre (se guarda en `lugar`)

## 📋 TAREAS PARA INDIANA

### Fase 1 — Limitaciones de listas
- [ ] Validar que todos los negocios con servicios >10 tengan categorías configuradas
- [ ] Si no, reducir a máximo 10 servicios al registrar
- [ ] Advertencia en Indiana: "Si tienes >10 servicios, agrúpalos en categorías"

### Fase 2 — Botones para cancelar
- [ ] Líneas 187, 230, 240: Reemplazar "escribe cancelar" con botón de cancelar
- [ ] Test en SE1, ME1, ME2, PA1

### Fase 3 — Mejor UX en confirmación
- [ ] Mantener datos capturados (nombre/email) en botones de confirmación (YA ESTÁ ✓)
- [ ] Agregar "Editar datos" como botón en lugar de escribir números

## 🔧 DETALLES TÉCNICOS

**SE1 — Caso crítico:**
- 14 servicios → Se pasa de 10
- Pero tiene 4 categorías (Trámites, Visas, Empresa, Marca)
- Flujo actual: Primero categoría → luego servicios por categoría
- Status: ✓ Funciona (listas pequeñas por categoría)

**PA1 — Fresco del Horno:**
- 70+ productos en 7 categorías
- Modo: PEDIDOS (no citas), usa `flujo_pedidos.py`
- Status: NO AFECTADO (pedidos no usa estas listas)

## ✅ YA ESTÁ BIEN

- Confirmación de datos (nombre/email) → USA BOTONES
- Confirmación de cita → USA BOTONES
- Reagendar/Cancelar cita → USA BOTONES + texto

## 📌 PENDIENTE PRINCIPAL

**Limitar `_enviar_lista_servicios` a 10 items** — igual que horas
