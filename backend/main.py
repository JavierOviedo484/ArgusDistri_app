"""
FastAPI main — punto de entrada del servidor.
Correr con: uvicorn main:app --reload
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.orm import Session
from jinja2 import Environment, FileSystemLoader

from app.core.database import init_db, get_db
from app.api.v1 import router as api_router
from app.schemas import ColaboradorCreate

app = FastAPI(title="Argus · Distribuidor de Documentos", version="1.0.0")

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
PARTIALS_DIR = TEMPLATES_DIR / "partials"

STATIC_DIR.mkdir(exist_ok=True)

# Jinja2 directo
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=False,
)
jinja_env_partials = Environment(
    loader=FileSystemLoader(str(PARTIALS_DIR)),
    autoescape=False,
)

def render(name: str, context: dict) -> HTMLResponse:
    """Renderiza template completo."""
    t = jinja_env.get_template(name)
    return HTMLResponse(content=t.render(**context))

def render_partial(name: str, context: dict) -> str:
    """Renderiza partial HTML (sin layout)."""
    t = jinja_env_partials.get_template(name)
    return t.render(**context)

def page(content_html: str, request: Request) -> HTMLResponse:
    """Envuelve contenido HTML en el layout completo.
    Si la petición viene via HTMX, devuelve solo el contenido."""
    # Detectar HTMX: si es petición parcial, devolver solo el contenido
    hx_request = request.headers.get("HX-Request") == "true"
    if hx_request:
        return HTMLResponse(content=content_html)
    t = jinja_env.get_template("dashboard.html")
    return HTMLResponse(content=t.render({"request": request, "content": content_html}))

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(api_router, prefix="/api/v1")


@app.on_event("startup")
def startup():
    init_db()


# ─── Páginas ─────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def pagina_dashboard(request: Request, db: Session = Depends(get_db)):
    return page(render_partial("dashboard_content.html", {"request": request}), request)


@app.get("/colaboradores", response_class=HTMLResponse)
def pagina_colaboradores(request: Request, db: Session = Depends(get_db)):
    from app.models.colaborador import Colaborador
    cols = db.query(Colaborador).order_by(Colaborador.nombre).all()
    return page(render_partial("colaboradores_content.html", {
        "request": request, "colaboradores": cols,
    }), request)


def _tabla_colaboradores_html(db: Session) -> str:
    from app.models.colaborador import Colaborador
    cols = db.query(Colaborador).order_by(Colaborador.nombre).all()
    return render_partial("colaboradores_tabla.html", {"colaboradores": cols})


@app.post("/colaboradores/guardar", response_class=HTMLResponse)
def guardar_colaborador(data: ColaboradorCreate, db: Session = Depends(get_db)):
    from app.models.colaborador import Colaborador

    existe = db.query(Colaborador).filter_by(identificador=data.identificador).first()
    if existe:
        for k, v in data.dict(exclude_unset=True).items():
            setattr(existe, k, v)
    else:
        db.add(Colaborador(**data.dict()))
    db.commit()

    return HTMLResponse(_tabla_colaboradores_html(db))


@app.delete("/colaboradores/{identificador}/eliminar", response_class=HTMLResponse)
def eliminar_colaborador_html(identificador: str, db: Session = Depends(get_db)):
    from app.models.colaborador import Colaborador

    colab = db.query(Colaborador).filter_by(identificador=identificador).first()
    if colab:
        db.delete(colab)
        db.commit()

    return HTMLResponse(_tabla_colaboradores_html(db))


@app.get("/plantillas", response_class=HTMLResponse)
def pagina_plantillas(request: Request, db: Session = Depends(get_db)):
    from app.models.plantilla import Plantilla
    plantillas = db.query(Plantilla).order_by(Plantilla.canal, Plantilla.nombre).all()
    return page(render_partial("plantillas_content.html", {
        "request": request, "plantillas": plantillas,
    }), request)


@app.get("/config", response_class=HTMLResponse)
def pagina_config(request: Request, db: Session = Depends(get_db)):
    from app.models.configuracion import Configuracion
    configs = db.query(Configuracion).order_by(Configuracion.clave).all()
    return page(render_partial("config_content.html", {
        "request": request, "configs": configs,
    }), request)


def _pdf_response(ruta: Path) -> FileResponse:
    """Sirve un PDF para visualización inline (no descarga).
    La carpeta de origen puede estar fuera del proyecto (p.ej. en el
    Escritorio), igual que ya permite el escaneo — por eso no restringimos
    a data/, solo verificamos que exista y sea realmente un .pdf."""
    if not ruta.exists() or ruta.suffix.lower() != ".pdf":
        raise HTTPException(404, "PDF no encontrado")
    return FileResponse(
        ruta,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{ruta.name}"'},
    )


@app.get("/pdf/factura/{factura_id}")
def ver_pdf_factura(factura_id: int, db: Session = Depends(get_db)):
    """Sirve el PDF de una factura ya escaneada/asignada, para verla inline."""
    from app.models.factura import Factura as FacturaModel

    factura = db.query(FacturaModel).filter_by(id=factura_id).first()
    if not factura or not factura.ruta_pdf:
        raise HTTPException(404, "Factura sin PDF asociado")
    return _pdf_response(Path(factura.ruta_pdf))


@app.get("/pdf/carpeta")
def ver_pdf_carpeta(carpeta: str = "", archivo: str = ""):
    """Sirve un PDF por carpeta+nombre (facturas 'sin dueño' aún no guardadas)."""
    from app.api.v1 import PDF_ENTRADA

    if not archivo:
        raise HTTPException(400, "Falta el nombre del archivo")
    carpeta_path = Path(carpeta) if carpeta else PDF_ENTRADA
    nombre = Path(archivo).name  # evita path traversal (../..)
    return _pdf_response(carpeta_path / nombre)


@app.get("/status-cards", response_class=HTMLResponse)
def status_cards(request: Request, db: Session = Depends(get_db)):
    from app.models.colaborador import Colaborador
    from app.models.factura import Factura
    from app.models.envio import Envio
    cols = db.query(Colaborador).count()
    facts = db.query(Factura).count()
    pend = db.query(Envio).filter_by(estado="pendiente").count()
    entrada = BASE_DIR.parent / "data" / "pdfs_entrada"
    pdfs_pendientes = len(list(entrada.glob("*.pdf"))) if entrada.exists() else 0
    return render("partials/status_cards.html", {
        "request": request, "colaboradores": cols, "facturas": facts,
        "pendientes": pend, "pdfs_pendientes": pdfs_pendientes,
    })


@app.get("/preview-factura/{factura_id}", response_class=HTMLResponse)
def preview_factura(request: Request, factura_id: int, db: Session = Depends(get_db)):
    """Modal de previsualización de una factura con datos extraídos."""
    from app.models.factura import Factura as FacturaModel
    from app.models.colaborador import Colaborador as ColaboradorModel

    factura = db.query(FacturaModel).filter_by(id=factura_id).first()
    if not factura:
        return HTMLResponse("<div class='text-red-400'>Factura no encontrada</div>")

    colab = db.query(ColaboradorModel).filter_by(identificador=factura.colaborador_id).first()

    # Re-extraer datos del PDF
    from app.services.pdf_extractor import ExtractorPDF
    pdf_path = Path(factura.ruta_pdf)
    extraido = {}
    texto_pdf = ""
    if pdf_path.exists():
        extractor = ExtractorPDF()
        resultado = extractor.extraer_datos(pdf_path)
        extraido = resultado.dict()
        texto_pdf = resultado.texto_completo[:2000]  # primeros 2000 chars

    return render("partials/preview_factura.html", {
        "request": request,
        "factura_id": factura_id,
        "extraido": extraido or {
            "archivo": pdf_path.name,
            "nombre_colaborador": colab.nombre if colab else "?",
            "identificador": colab.identificador if colab else "",
            "telefono": colab.telefono if colab else "",
            "email": colab.email if colab else "",
            "periodo": factura.periodo,
            "monto": factura.monto,
        },
        "tiene_email": bool(colab and colab.email and colab.email != "sin correo"),
        "tiene_telefono": bool(colab and colab.telefono),
        "texto_pdf": texto_pdf,
    })


ULTIMO_ESCANEO_JSON = BASE_DIR.parent / "data" / "ultimo_escaneo.json"


def _render_resultados(request: Request, db: Session) -> HTMLResponse:
    """
    Vista PERSISTENTE del estado de facturas: se reconstruye desde la BD
    (+ metadatos del último escaneo guardados en JSON), así no se pierde
    al navegar entre pestañas ni al reiniciar el servidor.
    """
    import json as _json
    from app.models.factura import Factura as FacturaModel
    from app.models.colaborador import Colaborador as ColaboradorModel
    from app.models.envio import Envio

    escaneo = {}
    if ULTIMO_ESCANEO_JSON.exists():
        try:
            escaneo = _json.loads(ULTIMO_ESCANEO_JSON.read_text(encoding="utf-8"))
        except Exception:
            escaneo = {}

    # Último envío por (factura, canal) — para mostrar el error si falló
    ultimo_envio = {}
    for e in db.query(Envio).order_by(Envio.id).all():
        ultimo_envio[(e.factura_id, e.canal)] = e

    facturas = []
    for fact in db.query(FacturaModel).order_by(FacturaModel.id).all():
        colab = db.query(ColaboradorModel).filter_by(identificador=fact.colaborador_id).first()

        def _error(canal):
            e = ultimo_envio.get((fact.id, canal))
            return e.error_msg if e and e.estado == "fallido" else None

        facturas.append({
            "id": fact.id,
            "colaborador_nombre": colab.nombre if colab else "(sin colaborador)",
            "archivo": fact.archivo_original,
            "periodo": fact.periodo,
            "monto": fact.monto,
            "email": colab.email if colab and colab.email and colab.email != "sin correo" else None,
            "telefono": colab.telefono if colab and colab.telefono else None,
            "enviado_email": bool(fact.enviado_email),
            "enviado_whatsapp": bool(fact.enviado_whatsapp),
            "enviado_sms": bool(getattr(fact, "enviado_sms", 0)),
            "error_email": _error("email"),
            "error_whatsapp": _error("whatsapp"),
            "error_sms": _error("sms"),
        })

    return render("partials/resultados_escaneo.html", {
        "request": request,
        "escaneado": bool(escaneo),
        "total": escaneo.get("total", len(facturas)),
        "sin_dueno": escaneo.get("sin_dueno", []),
        "errores": escaneo.get("errores", []),
        "alertas": escaneo.get("alertas", []),
        "tiempo_total": escaneo.get("tiempo_total", 0),
        "tiempo_por_pdf": escaneo.get("tiempo_por_pdf", 0),
        "carpeta": escaneo.get("carpeta", ""),
        "fecha_escaneo": escaneo.get("fecha", ""),
        "facturas": facturas,
    })


@app.get("/facturas-html", response_class=HTMLResponse)
def facturas_html(request: Request, db: Session = Depends(get_db)):
    """Estado actual de facturas — se carga al entrar al Dashboard sin re-escanear."""
    return _render_resultados(request, db)


@app.post("/escaneo-html")
def escaneo_html(
    request: Request,
    carpeta: str = Form(""),
    db: Session = Depends(get_db),
):
    """Escanea PDFs, persiste el resultado y devuelve la vista de estado."""
    import time
    import json as _json
    from datetime import datetime
    from app.services.matcher import Matcher
    from app.api.v1 import PDF_ENTRADA

    carpeta_path = Path(carpeta) if carpeta else PDF_ENTRADA
    if not carpeta_path.exists():
        aviso = (
            f"<div class='card' style='border-color:#fecaca;background:#fef2f2;margin-bottom:1rem;'>"
            f"<div class='text-sm' style='color:#dc2626;'>❌ Carpeta no encontrada: <code>{carpeta_path}</code></div></div>"
        )
        base = _render_resultados(request, db)
        return HTMLResponse(aviso + base.body.decode("utf-8"))

    t0 = time.time()
    matcher = Matcher(carpeta_path, db)
    resultados = matcher.escanear()
    tiempo_total = round(time.time() - t0, 2)

    sin_dueno = [r.dict() for r in resultados if r.estado == "sin_dueño"]
    errores = [r.dict() for r in resultados if r.estado == "error_extraccion"]
    alertas = []
    for r in resultados:
        for a in r.alertas:
            alertas.append(a)
    for r in resultados:
        if r.colaborador and not r.colaborador.telefono:
            alertas.append(f"⚠️ Sin teléfono registrado: {r.colaborador.nombre}")

    tiempo_por_pdf = round(tiempo_total / len(resultados), 2) if resultados else 0

    # Persistir metadatos del escaneo: la vista sobrevive navegación y reinicios
    ULTIMO_ESCANEO_JSON.parent.mkdir(parents=True, exist_ok=True)
    ULTIMO_ESCANEO_JSON.write_text(_json.dumps({
        "carpeta": str(carpeta_path),
        "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "total": len(resultados),
        "tiempo_total": tiempo_total,
        "tiempo_por_pdf": tiempo_por_pdf,
        "sin_dueno": [
            {"archivo": r.get("archivo", "?"),
             "nombre_extraido": (r.get("extraido") or {}).get("nombre_colaborador") or ""}
            for r in sin_dueno
        ],
        "errores": [
            {"archivo": r.get("archivo", "?"),
             "error": (r.get("extraido") or {}).get("error") or "error de extracción"}
            for r in errores
        ],
        "alertas": alertas,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    return _render_resultados(request, db)


# ─── ENVÍOS ─────────────────────────────────────────────────────


def _resultado_lote_html(enviados: int, fallidos: int, errores: list) -> str:
    """Tarjeta de resultado del envío masivo: verde si todo salió, roja con detalle si algo falló."""
    if fallidos == 0:
        return (
            "<div class='card' style='background:#ecfdf5;border-color:#a7f3d0;margin-bottom:1rem;'>"
            f"<div class='text-sm font-bold' style='color:#047857;'>✅ ¡Listo! Se enviaron las {enviados} factura(s) correctamente.</div>"
            "<div class='text-xs mt-1' style='color:#059669;'>Cada factura quedó marcada con su check ✓ en la lista.</div>"
            "</div>"
        )
    detalle = "".join(
        f"<li class='text-xs' style='color:#b91c1c;'>· {e}</li>" for e in errores[:15]
    )
    extra = f"<li class='text-xs' style='color:#b91c1c;'>… y {len(errores) - 15} más</li>" if len(errores) > 15 else ""
    return (
        "<div class='card' style='background:#fef2f2;border-color:#fecaca;margin-bottom:1rem;'>"
        f"<div class='text-sm font-bold' style='color:#dc2626;'>⚠️ Atención: {enviados} enviada(s), {fallidos} FALLARON</div>"
        f"<ul class='mt-1.5 space-y-0.5'>{detalle}{extra}</ul>"
        "<div class='text-xs mt-2' style='color:#64748b;'>Las que fallaron siguen como pendientes — corrige el problema y vuelve a enviar (solo se reenvían las pendientes).</div>"
        "</div>"
    )


@app.post("/api/v1/enviar/email/{factura_id}")
def enviar_email_individual(factura_id: int, request: Request, db: Session = Depends(get_db)):
    """Envía una factura por email."""
    from app.models.factura import Factura as FacturaModel
    from app.models.colaborador import Colaborador as ColaboradorModel
    from app.models.plantilla import Plantilla
    from app.models.configuracion import Configuracion
    from app.models.envio import Envio
    from app.services.email_sender import enviar_email

    factura = db.query(FacturaModel).filter_by(id=factura_id).first()
    if not factura:
        return HTMLResponse("<div class='text-red-400 text-sm'>Factura no encontrada</div>")

    colab = db.query(ColaboradorModel).filter_by(identificador=factura.colaborador_id).first()
    if not colab or not colab.email:
        return HTMLResponse("<div class='text-red-400 text-sm'>Colaborador sin email</div>")

    plantilla = db.query(Plantilla).filter_by(canal="email", activo=True).first()
    configs = {c.clave: c.valor for c in db.query(Configuracion).all()}

    asunto = plantilla.asunto.format(periodo=factura.periodo) if plantilla else f"Factura {factura.periodo}"
    cuerpo = plantilla.cuerpo.format(
        nombre=colab.nombre, periodo=factura.periodo, monto=factura.monto
    ) if plantilla else f"Factura de {colab.nombre}"

    pdf_path = Path(factura.ruta_pdf)

    resultado = enviar_email(
        para=colab.email,
        asunto=asunto,
        cuerpo=cuerpo,
        adjunto_pdf=pdf_path if pdf_path.exists() else None,
        smtp_user=configs.get("email_sender"),
        smtp_password=configs.get("gmail_app_password"),
    )

    # Registrar envío
    envio = Envio(
        factura_id=factura_id,
        canal="email",
        destinatario=colab.email,
        estado="enviado" if resultado["ok"] else "fallido",
        error_msg=None if resultado["ok"] else resultado["mensaje"],
    )
    db.add(envio)
    if resultado["ok"]:
        factura.enviado_email = True
    db.commit()

    css = "text-emerald-400" if resultado["ok"] else "text-red-400"
    icono = "✅" if resultado["ok"] else "❌"
    return HTMLResponse(
        f"<div class='{css} text-sm mt-2'>{icono} {resultado['mensaje']}</div>",
        headers={"HX-Trigger": "refrescarFacturas"},
    )


@app.post("/api/v1/enviar/whatsapp/{factura_id}")
def enviar_whatsapp_individual(factura_id: int, request: Request, db: Session = Depends(get_db)):
    """Envía una factura por WhatsApp."""
    from app.models.factura import Factura as FacturaModel
    from app.models.colaborador import Colaborador as ColaboradorModel
    from app.models.plantilla import Plantilla
    from app.models.configuracion import Configuracion
    from app.models.envio import Envio
    from app.services.whatsapp_sender import enviar_whatsapp

    factura = db.query(FacturaModel).filter_by(id=factura_id).first()
    if not factura:
        return HTMLResponse("<div class='text-red-400 text-sm'>Factura no encontrada</div>")

    colab = db.query(ColaboradorModel).filter_by(identificador=factura.colaborador_id).first()
    if not colab or not colab.telefono:
        return HTMLResponse("<div class='text-red-400 text-sm'>Colaborador sin teléfono</div>")

    plantilla = db.query(Plantilla).filter_by(canal="whatsapp", activo=True).first()
    configs = {c.clave: c.valor for c in db.query(Configuracion).all()}

    cuerpo = plantilla.cuerpo.format(
        nombre=colab.nombre, periodo=factura.periodo, monto=factura.monto
    ) if plantilla else f"Factura de {colab.nombre}"

    pdf_path = Path(factura.ruta_pdf) if factura.ruta_pdf else None
    resultado = enviar_whatsapp(
        numero=colab.telefono,
        mensaje=cuerpo,
        api_url=configs.get("whatsapp_api_url"),
        api_key=configs.get("whatsapp_api_key"),
        instance=configs.get("whatsapp_instance"),
        adjunto_pdf=pdf_path if pdf_path and pdf_path.exists() else None,
    )

    envio = Envio(
        factura_id=factura_id,
        canal="whatsapp",
        destinatario=colab.telefono,
        estado="enviado" if resultado["ok"] else "fallido",
        error_msg=None if resultado["ok"] else resultado["mensaje"],
    )
    db.add(envio)
    if resultado["ok"]:
        factura.enviado_whatsapp = True
    db.commit()

    css = "text-emerald-400" if resultado["ok"] else "text-red-400"
    icono = "✅" if resultado["ok"] else "❌"
    return HTMLResponse(
        f"<div class='{css} text-sm mt-2'>{icono} {resultado['mensaje']}</div>",
        headers={"HX-Trigger": "refrescarFacturas"},
    )


@app.post("/api/v1/enviar/sms/{factura_id}")
def enviar_sms_individual(factura_id: int, request: Request, db: Session = Depends(get_db)):
    """Envía la notificación de una factura por SMS (sin adjunto)."""
    from app.models.factura import Factura as FacturaModel
    from app.models.colaborador import Colaborador as ColaboradorModel
    from app.models.plantilla import Plantilla
    from app.models.configuracion import Configuracion
    from app.models.envio import Envio
    from app.services.sms_sender import enviar_sms

    factura = db.query(FacturaModel).filter_by(id=factura_id).first()
    if not factura:
        return HTMLResponse("<div class='text-red-400 text-sm'>Factura no encontrada</div>")

    colab = db.query(ColaboradorModel).filter_by(identificador=factura.colaborador_id).first()
    if not colab or not colab.telefono:
        return HTMLResponse("<div class='text-red-400 text-sm'>Colaborador sin teléfono</div>")

    plantilla = db.query(Plantilla).filter_by(canal="sms", activo=True).first()
    configs = {c.clave: c.valor for c in db.query(Configuracion).all()}

    cuerpo = plantilla.cuerpo.format(
        nombre=colab.nombre, periodo=factura.periodo, monto=factura.monto
    ) if plantilla else f"ARGUS: factura {factura.periodo} de {colab.nombre}"

    resultado = enviar_sms(
        numero=colab.telefono,
        mensaje=cuerpo,
        api_url=configs.get("sms_api_url"),
        api_key=configs.get("sms_api_key"),
    )

    envio = Envio(
        factura_id=factura_id,
        canal="sms",
        destinatario=colab.telefono,
        estado="enviado" if resultado["ok"] else "fallido",
        error_msg=None if resultado["ok"] else resultado["mensaje"],
    )
    db.add(envio)
    if resultado["ok"]:
        factura.enviado_sms = True
    db.commit()

    css = "text-emerald-400" if resultado["ok"] else "text-red-400"
    icono = "✅" if resultado["ok"] else "❌"
    return HTMLResponse(
        f"<div class='{css} text-sm mt-2'>{icono} {resultado['mensaje']}</div>",
        headers={"HX-Trigger": "refrescarFacturas"},
    )


@app.get("/api/v1/probar-whatsapp", response_class=HTMLResponse)
def probar_whatsapp(db: Session = Depends(get_db)):
    """Comprueba conexión con Evolution API y estado de la instancia (para el botón de Config)."""
    from app.models.configuracion import Configuracion
    from app.services.whatsapp_sender import probar_conexion

    configs = {c.clave: c.valor for c in db.query(Configuracion).all()}
    r = probar_conexion(
        api_url=configs.get("whatsapp_api_url"),
        api_key=configs.get("whatsapp_api_key"),
        instance=configs.get("whatsapp_instance"),
    )
    if r["ok"]:
        estilo = "background:#ecfdf5;border:1px solid #a7f3d0;color:#047857;"
        icono = "✅"
    elif r["estado"] in ("apagada", "sin_config"):
        estilo = "background:#fef2f2;border:1px solid #fecaca;color:#b91c1c;"
        icono = "🔴"
    else:
        estilo = "background:#fffbeb;border:1px solid #fde68a;color:#92400e;"
        icono = "⚠️"
    return HTMLResponse(
        f"<div class='text-xs rounded-lg p-2.5' style='{estilo}'>{icono} {r['mensaje']}</div>"
    )


@app.get("/resumen-envio/{canal}", response_class=HTMLResponse)
def resumen_envio(canal: str, request: Request, db: Session = Depends(get_db)):
    """
    Paso de verificación ANTES del envío masivo: muestra exactamente
    a quién se enviará cada factura y qué datos faltan.
    El envío real solo ocurre al presionar 'Confirmar envío'.
    """
    from app.models.factura import Factura as FacturaModel
    from app.models.colaborador import Colaborador as ColaboradorModel

    if canal not in ("email", "whatsapp", "sms"):
        return HTMLResponse("<div class='text-red-400 text-sm'>Canal inválido</div>")

    flags = {
        "email": FacturaModel.enviado_email,
        "whatsapp": FacturaModel.enviado_whatsapp,
        "sms": FacturaModel.enviado_sms,
    }
    facturas = db.query(FacturaModel).filter(flags[canal] == False).all()  # noqa: E712

    listos = []      # (factura, colaborador, destinatario)
    sin_datos = []   # (factura, colaborador|None, motivo)
    for f in facturas:
        colab = db.query(ColaboradorModel).filter_by(identificador=f.colaborador_id).first()
        if not colab:
            sin_datos.append((f, None, "sin colaborador asignado"))
            continue
        dest = colab.email if canal == "email" else colab.telefono
        if not dest or dest == "sin correo":
            sin_datos.append((f, colab, f"sin {'email' if canal == 'email' else 'teléfono'} registrado"))
        else:
            listos.append((f, colab, dest))

    return render("partials/resumen_envio.html", {
        "request": request,
        "canal": canal,
        "listos": listos,
        "sin_datos": sin_datos,
    })


@app.post("/api/v1/enviar-lote/email")
def enviar_lote_email(request: Request, db: Session = Depends(get_db)):
    """Envía todas las facturas pendientes por email."""
    from app.models.factura import Factura as FacturaModel
    from app.models.envio import Envio
    enviados = 0
    fallidos = 0
    errores = []
    facturas = db.query(FacturaModel).filter_by(enviado_email=False).all()
    if not facturas:
        return HTMLResponse(
            "<div class='text-sm mt-2 text-slate-400'>No hay facturas pendientes de enviar por email.</div>"
        )
    for factura in facturas:
        from app.models.colaborador import Colaborador as ColaboradorModel
        colab = db.query(ColaboradorModel).filter_by(identificador=factura.colaborador_id).first()
        if not colab or not colab.email:
            continue
        from app.models.plantilla import Plantilla
        from app.models.configuracion import Configuracion
        from app.services.email_sender import enviar_email
        plantilla = db.query(Plantilla).filter_by(canal="email", activo=True).first()
        configs = {c.clave: c.valor for c in db.query(Configuracion).all()}
        asunto = plantilla.asunto.format(periodo=factura.periodo) if plantilla else f"Factura {factura.periodo}"
        cuerpo = plantilla.cuerpo.format(nombre=colab.nombre, periodo=factura.periodo, monto=factura.monto) if plantilla else ""
        pdf_path = Path(factura.ruta_pdf)
        r = enviar_email(
            para=colab.email, asunto=asunto, cuerpo=cuerpo,
            adjunto_pdf=pdf_path if pdf_path.exists() else None,
            smtp_user=configs.get("email_sender"),
            smtp_password=configs.get("gmail_app_password"),
        )
        envio = Envio(factura_id=factura.id, canal="email", destinatario=colab.email,
                      estado="enviado" if r["ok"] else "fallido", error_msg=None if r["ok"] else r["mensaje"])
        db.add(envio)
        if r["ok"]:
            factura.enviado_email = True
            enviados += 1
        else:
            fallidos += 1
            errores.append(f"{colab.nombre}: {r['mensaje']}")
    db.commit()
    return HTMLResponse(_resultado_lote_html(enviados, fallidos, errores), headers={"HX-Trigger": "refrescarFacturas"})


@app.post("/api/v1/enviar-lote/whatsapp")
def enviar_lote_whatsapp(request: Request, db: Session = Depends(get_db)):
    """Envía todas las facturas pendientes por WhatsApp."""
    from app.models.factura import Factura as FacturaModel
    from app.models.envio import Envio
    enviados = 0
    fallidos = 0
    errores = []
    facturas = db.query(FacturaModel).filter_by(enviado_whatsapp=False).all()
    if not facturas:
        return HTMLResponse(
            "<div class='text-sm mt-2 text-slate-400'>No hay facturas pendientes de enviar por WhatsApp.</div>"
        )
    for factura in facturas:
        from app.models.colaborador import Colaborador as ColaboradorModel
        colab = db.query(ColaboradorModel).filter_by(identificador=factura.colaborador_id).first()
        if not colab or not colab.telefono:
            continue
        from app.models.plantilla import Plantilla
        from app.models.configuracion import Configuracion
        from app.services.whatsapp_sender import enviar_whatsapp
        plantilla = db.query(Plantilla).filter_by(canal="whatsapp", activo=True).first()
        configs = {c.clave: c.valor for c in db.query(Configuracion).all()}
        cuerpo = plantilla.cuerpo.format(nombre=colab.nombre, periodo=factura.periodo, monto=factura.monto) if plantilla else ""
        pdf_path = Path(factura.ruta_pdf) if factura.ruta_pdf else None
        r = enviar_whatsapp(
            numero=colab.telefono, mensaje=cuerpo,
            api_url=configs.get("whatsapp_api_url"),
            api_key=configs.get("whatsapp_api_key"),
            instance=configs.get("whatsapp_instance"),
            adjunto_pdf=pdf_path if pdf_path and pdf_path.exists() else None,
        )
        envio = Envio(factura_id=factura.id, canal="whatsapp", destinatario=colab.telefono,
                      estado="enviado" if r["ok"] else "fallido", error_msg=None if r["ok"] else r["mensaje"])
        db.add(envio)
        if r["ok"]:
            factura.enviado_whatsapp = True
            enviados += 1
        else:
            fallidos += 1
            errores.append(f"{colab.nombre}: {r['mensaje']}")
    db.commit()
    return HTMLResponse(_resultado_lote_html(enviados, fallidos, errores), headers={"HX-Trigger": "refrescarFacturas"})


@app.post("/api/v1/enviar-lote/sms")
def enviar_lote_sms(request: Request, db: Session = Depends(get_db)):
    """Envía la notificación SMS de todas las facturas pendientes."""
    from app.models.factura import Factura as FacturaModel
    from app.models.colaborador import Colaborador as ColaboradorModel
    from app.models.plantilla import Plantilla
    from app.models.configuracion import Configuracion
    from app.models.envio import Envio
    from app.services.sms_sender import enviar_sms

    enviados = 0
    fallidos = 0
    errores = []
    facturas = db.query(FacturaModel).filter_by(enviado_sms=False).all()
    if not facturas:
        return HTMLResponse(
            "<div class='text-sm mt-2 text-slate-400'>No hay facturas pendientes de enviar por SMS.</div>"
        )
    plantilla = db.query(Plantilla).filter_by(canal="sms", activo=True).first()
    configs = {c.clave: c.valor for c in db.query(Configuracion).all()}
    for factura in facturas:
        colab = db.query(ColaboradorModel).filter_by(identificador=factura.colaborador_id).first()
        if not colab or not colab.telefono:
            continue
        cuerpo = plantilla.cuerpo.format(
            nombre=colab.nombre, periodo=factura.periodo, monto=factura.monto
        ) if plantilla else f"ARGUS: factura {factura.periodo} de {colab.nombre}"
        r = enviar_sms(
            numero=colab.telefono, mensaje=cuerpo,
            api_url=configs.get("sms_api_url"),
            api_key=configs.get("sms_api_key"),
        )
        envio = Envio(factura_id=factura.id, canal="sms", destinatario=colab.telefono,
                      estado="enviado" if r["ok"] else "fallido", error_msg=None if r["ok"] else r["mensaje"])
        db.add(envio)
        if r["ok"]:
            factura.enviado_sms = True
            enviados += 1
        else:
            fallidos += 1
            errores.append(f"{colab.nombre}: {r['mensaje']}")
    db.commit()
    return HTMLResponse(_resultado_lote_html(enviados, fallidos, errores), headers={"HX-Trigger": "refrescarFacturas"})


# ─── BORRAR TODO ────────────────────────────────────────────────


@app.post("/borrar-todo")
def borrar_todo(request: Request, db: Session = Depends(get_db)):
    """
    Resetea el sistema: borra BD, mueve PDFs procesados a respaldo,
    deja la carpeta de entrada intacta.
    """
    import shutil
    from app.models.colaborador import Colaborador
    from app.models.factura import Factura as FacturaModel
    from app.models.envio import Envio
    from app.models.plantilla import Plantilla
    from app.models.configuracion import Configuracion

    proyecto = BASE_DIR.parent
    respaldo = proyecto / "data" / "backup_borrar" / "pdfs_procesados"
    respaldo.mkdir(parents=True, exist_ok=True)

    # Mover PDFs procesados a respaldo
    proc = proyecto / "data" / "pdfs_procesados"
    if proc.exists():
        for f in proc.glob("*.pdf"):
            shutil.move(str(f), str(respaldo / f.name))

    sin_dueno = proyecto / "data" / "pdfs_sin_dueno"
    if sin_dueno.exists():
        for f in sin_dueno.glob("*.pdf"):
            shutil.move(str(f), str(respaldo / f.name))

    # Borrar BD
    for model in [Envio, FacturaModel, Colaborador]:
        db.query(model).delete()
    db.commit()

    # Borrar también el estado del último escaneo (la vista queda vacía)
    if ULTIMO_ESCANEO_JSON.exists():
        ULTIMO_ESCANEO_JSON.unlink()

    return HTMLResponse("""
    <div class="text-sm text-emerald-400 bg-slate-900 rounded-lg p-4 border border-emerald-800/50">
        ✅ <strong>Sistema reseteado</strong>
        <ul class="mt-2 space-y-1 text-slate-300">
            <li>✓ Base de datos limpiada (colaboradores, facturas, envíos)</li>
            <li>✓ PDFs procesados movidos a <code>data/backup_borrar/</code></li>
            <li>✓ Los PDFs en carpeta de entrada están intactos</li>
        </ul>
        <p class="mt-2 text-xs text-slate-500">Las plantillas y configuración se conservan.</p>
    </div>
    """, headers={"HX-Trigger": "refrescarFacturas"})


# ─── PREVIEW / VERIFICACIÓN DE EXTRACCIÓN ─────────────────────


@app.post("/preview-extraccion")
def preview_extraccion(request: Request, archivo: str = Form(""), carpeta: str = Form(""), db: Session = Depends(get_db)):
    """Muestra los datos extraídos de un PDF para verificación."""
    from app.services.pdf_extractor import ExtractorPDF
    from app.api.v1 import PDF_ENTRADA

    if not archivo:
        return HTMLResponse("<div class='text-red-400 text-sm p-3'>Falta archivo</div>")

    carpeta_path = Path(carpeta) if carpeta else PDF_ENTRADA
    pdf_path = carpeta_path / archivo

    if not pdf_path.exists():
        return HTMLResponse(f"<div class='text-red-400 text-sm p-3'>PDF no encontrado: {pdf_path}</div>")

    extractor = ExtractorPDF()
    datos = extractor.extraer_datos(str(pdf_path))

    # Verificar si ya existe el colaborador en BD
    from app.models.colaborador import Colaborador
    colab_exists = False
    if datos.identificador:
        colab_exists = db.query(Colaborador).filter_by(identificador=datos.identificador).first() is not None

    return render("partials/preview_extraccion.html", {
        "request": request,
        "archivo": archivo,
        "carpeta": str(carpeta_path),
        "nombre": datos.nombre_colaborador or "",
        "identificador": datos.identificador or "",
        "telefono": datos.telefono or "",
        "email": datos.email or "sin correo",
        "periodo": datos.periodo or "",
        "monto": datos.monto or "",
        "error": datos.error,
        "es_valido": datos.es_valido,
        "colab_existe": colab_exists,
        "texto_pdf": datos.texto_completo[:2000] if datos.texto_completo else "",
    })


@app.post("/registrar-colaborador-desde-preview")
def registrar_colaborador_desde_preview(
    request: Request,
    nombre: str = Form(...),
    identificador: str = Form(...),
    telefono: str = Form(""),
    email: str = Form(""),
    carpeta: str = Form(""),
    archivos_pendientes: str = Form(""),
):
    """Registra un colaborador desde la preview de extracción."""
    from app.core.database import SessionLocal
    from app.models.colaborador import Colaborador

    db = SessionLocal()
    try:
        exists = db.query(Colaborador).filter_by(identificador=identificador).first()
        if exists:
            msg = f"⚠️ {nombre} ya existe como '{exists.nombre}'"
        else:
            colab = Colaborador(
                identificador=identificador,
                nombre=nombre.strip(),
                email=email.strip() if email and email != "sin correo" else None,
                telefono=telefono.strip() if telefono else None,
            )
            db.add(colab)
            db.commit()
            msg = f"✅ {nombre} registrado como colaborador"
    finally:
        db.close()

    return HTMLResponse(f"""
    <div class="text-sm space-y-2 p-3">
        <div class="{'text-emerald-400' if '✅' in msg else 'text-amber-400'}">{msg}</div>
        <button hx-post="/escaneo-html" hx-include="#carpeta-input"
                hx-target="#resultados" hx-swap="innerHTML"
                class="bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-1.5 rounded text-xs font-medium">
            🔍 Re-escanear para asignar facturas
        </button>
    </div>
    """)
