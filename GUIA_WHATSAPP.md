# 📲 Guía: configurar el envío por WhatsApp

ARGUS envía los WhatsApp (con la factura PDF adjunta) a través de **Evolution API**,
un servidor local que vincula un número de WhatsApp igual que WhatsApp Web.
Todo corre en tu propia máquina — no se paga a nadie ni se envían datos a terceros.

---

## Puesta en marcha (una sola vez)

### 1. Encender Evolution API

En la terminal de **Ubuntu (WSL)**:

```bash
cd ~/distribuidor-pdfs/whatsapp-evolution
docker compose up -d
```

La primera vez descarga las imágenes (2–5 min). Verifica que está arriba:

```bash
docker compose ps        # ambos servicios deben decir "running"
```

### 2. Vincular tu número de WhatsApp (escanear QR)

1. Abre en el navegador: **http://localhost:8080/manager**
2. Ingresa con la API Key: `argus-whatsapp-2026`
3. Crea una instancia con el nombre exacto: **`argus`**
   - Channel: **Baileys**
4. Presiona **Connect / Get QR** — aparece un código QR
5. En el teléfono del número emisor (+593 96 291 1218):
   **WhatsApp → Ajustes → Dispositivos vinculados → Vincular dispositivo** → escanea el QR

> El teléfono debe quedar con internet. Si se desvincula, se repite este paso.

### 3. Verificar desde ARGUS

1. Abre ARGUS → pestaña **Configuración**
2. Revisa que estén así (ya vienen prellenados):
   - `whatsapp_api_url` = `http://localhost:8080`
   - `whatsapp_api_key` = `argus-whatsapp-2026`
   - `whatsapp_instance` = `argus`
3. Presiona **🔌 Probar conexión** → debe decir **"Conectado ✓"**

### 4. Enviar

En el Dashboard: **💬 Enviar todo por WhatsApp** → revisa la lista de
destinatarios → **Confirmar envío**. Cada factura sale con su PDF adjunto
y queda marcada con ✓.

---

## Uso diario

Evolution API queda encendida y arranca sola con Docker. Si reiniciaste la PC:

```bash
cd ~/distribuidor-pdfs/whatsapp-evolution && docker compose up -d
```

## Problemas comunes

| Síntoma | Solución |
|---|---|
| "Evolution API no responde" | `docker compose up -d` en `~/distribuidor-pdfs/whatsapp-evolution` |
| "La instancia 'argus' no existe" | Crear la instancia en http://localhost:8080/manager (paso 2) |
| "Estado 'connecting' o 'close'" | Volver a escanear el QR (paso 2.4) |
| "API Key incorrecta" | `whatsapp_api_key` debe ser `argus-whatsapp-2026` (o cambia ambos lados) |
| El mensaje llega sin PDF | El PDF ya no está en la carpeta original — vuelve a escanear |

## ⚠️ Recomendaciones anti-bloqueo

WhatsApp puede restringir números que envían masivamente a contactos que no
los tienen agendado. Para 31 facturas mensuales el riesgo es bajo, pero:

- Usa un número que los colaboradores **ya conozcan** (ideal: el oficial de la empresa).
- Pide a los colaboradores agendar el número.
- No reenvíes todo varias veces el mismo día.
- Si el volumen crece mucho (cientos), considera la API oficial
  de WhatsApp Business (Meta) — de pago pero sin riesgo de bloqueo.
