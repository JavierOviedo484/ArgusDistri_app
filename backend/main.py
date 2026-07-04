"""
FastAPI main — punto de entrada del servidor.
Correr con: uvicorn main:app --reload
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, Request, Depends, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from jinja2 import Environment, FileSystemLoader

from app.core.database import init_db, get_db
from app.api.v1 import router as api_router

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
    """Envuelve contenido HTML en el layout completo."""
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


@app.get("/preview/{archivo}", response_class=HTMLResponse)
def preview_pdf(request: Request, archivo: str):
    return render("partials/preview.html", {
        "request": request, "archivo": archivo,
    })


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


@app.post("/escaneo-html")
def escaneo_html(
    request: Request,
    carpeta: str = Form(""),
    db: Session = Depends(get_db),
):
    """Escanea PDFs y devuelve HTML para HTMX con métricas de tiempo."""
    import time
    from app.services.matcher import Matcher
    from app.api.v1 import PDF_ENTRADA

    carpeta_path = Path(carpeta) if carpeta else PDF_ENTRADA
    if not carpeta_path.exists():
        return render("partials/resultados_escaneo.html", {
            "request": request, "total": 0, "ok": [], "sin_dueno": [],
            "errores": [{"archivo": "Carpeta no encontrada", "extraido": {"error": f"No existe: {carpeta_path}"}}],
            "alertas": [], "facturas": [], "tiempo_total": 0, "tiempo_por_pdf": 0,
        })

    t0 = time.time()
    matcher = Matcher(carpeta_path, db)
    resultados = matcher.escanear()
    tiempo_total = round(time.time() - t0, 2)

    ok = [r.dict() for r in resultados if r.estado == "ok"]
    sin_dueno = [r.dict() for r in resultados if r.estado == "sin_dueño"]
    errores = [r.dict() for r in resultados if r.estado == "error_extraccion"]
    alertas = []
    for r in resultados:
        for a in r.alertas:
            alertas.append(a)

    # Facturas (para botones de envío individual)
    facturas = []
    from app.models.factura import Factura as FacturaModel
    for r in resultados:
        if r.estado == "ok":
            fact = db.query(FacturaModel).filter_by(ruta_pdf=str(carpeta_path / r.archivo)).first()
            if fact:
                facturas.append({
                    "id": fact.id,
                    "colaborador_nombre": r.colaborador.nombre if r.colaborador else "?",
                    "colaborador_ruc": r.colaborador.identificador if r.colaborador else "",
                    "archivo": r.archivo,
                    "periodo": r.extraido.periodo,
                    "monto": r.extraido.monto,
                    "email": r.colaborador.email if r.colaborador and r.colaborador.email and r.colaborador.email != "sin correo" else None,
                    "telefono": r.colaborador.telefono if r.colaborador else None,
                    "extraido": r.extraido.dict() if hasattr(r.extraido, 'dict') else {},
                })

    cols_sin_telefono = []
    for r in resultados:
        if r.colaborador and not r.colaborador.telefono:
            cols_sin_telefono.append(r.colaborador.nombre)
    for n in cols_sin_telefono:
        alertas.append(f"⚠️ Sin teléfono registrado: {n}")

    # Tiempo estimado por PDF
    tiempo_por_pdf = round(tiempo_total / len(resultados), 2) if resultados else 0

    return render("partials/resultados_escaneo.html", {
        "request": request,
        "total": len(resultados),
        "ok": ok,
        "sin_dueno": sin_dueno,
        "errores": errores,
        "alertas": alertas,
        "facturas": facturas,
        "tiempo_total": tiempo_total,
        "tiempo_por_pdf": tiempo_por_pdf,
    })


# ─── ENVÍOS ─────────────────────────────────────────────────────


@app.post("/api/v1/enviar/email/{factura_id}")
def enviar_email_individual(factura_id: int, request: Request, db: Session = Depends(get_db)):
    """Envía una factura por email."""
    from app.models.factura import Factura as FacturaModel
    from app.models.colaborador import Colaborador as ColaboradorModel
    from app.models.plantilla import Plantilla
    from app.models.configuracion import Configuracion
    from app.models.envio import Envio
    from app.services.email_sender import enviar_email
    from app.schemas import EnvioCreate

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
        respuesta=resultado["mensaje"],
    )
    db.add(envio)
    db.commit()

    css = "text-green-400" if resultado["ok"] else "text-red-400"
    return HTMLResponse(f"<div class='{css} text-sm mt-2'>{resultado['mensaje']}</div>")


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

    resultado = enviar_whatsapp(
        numero=colab.telefono,
        mensaje=cuerpo,
        api_url=configs.get("whatsapp_api_url"),
        api_key=configs.get("whatsapp_api_key"),
    )

    envio = Envio(
        factura_id=factura_id,
        canal="whatsapp",
        destinatario=colab.telefono,
        estado="enviado" if resultado["ok"] else "fallido",
        respuesta=resultado["mensaje"],
    )
    db.add(envio)
    db.commit()

    css = "text-green-400" if resultado["ok"] else "text-red-400"
    return HTMLResponse(f"<div class='{css} text-sm mt-2'>{resultado['mensaje']}</div>")


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
        facturas = db.query(FacturaModel).all()
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
                      estado="enviado" if r["ok"] else "fallido", respuesta=r["mensaje"])
        db.add(envio)
        if r["ok"]:
            factura.enviado_email = True
            enviados += 1
        else:
            fallidos += 1
            errores.append(f"{colab.nombre}: {r['mensaje']}")
    db.commit()
    return HTMLResponse(
        f"<div class='text-sm mt-2 text-green-400'>✅ {enviados} enviados, ❌ {fallidos} fallidos</div>"
        + ("".join(f"<div class='text-xs text-red-400'>{e}</div>" for e in errores))
    )


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
        facturas = db.query(FacturaModel).all()
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
        r = enviar_whatsapp(
            numero=colab.telefono, mensaje=cuerpo,
            api_url=configs.get("whatsapp_api_url"),
            api_key=configs.get("whatsapp_api_key"),
        )
        envio = Envio(factura_id=factura.id, canal="whatsapp", destinatario=colab.telefono,
                      estado="enviado" if r["ok"] else "fallido", respuesta=r["mensaje"])
        db.add(envio)
        if r["ok"]:
            factura.enviado_whatsapp = True
            enviados += 1
        else:
            fallidos += 1
            errores.append(f"{colab.nombre}: {r['mensaje']}")
    db.commit()
    return HTMLResponse(
        f"<div class='text-sm mt-2 text-green-400'>✅ {enviados} enviados, ❌ {fallidos} fallidos</div>"
        + ("".join(f"<div class='text-xs text-red-400'>{e}</div>" for e in errores))
    )


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
    """)


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
    })


@app.post("/preview-sin-dueno", response_class=HTMLResponse)
def preview_sin_dueno(request: Request, archivo: str = Form(""), carpeta: str = Form(""), db: Session = Depends(get_db)):
    """Modal con datos extraídos de un PDF sin dueño."""
    from app.services.pdf_extractor import ExtractorPDF
    from app.api.v1 import PDF_ENTRADA

    carpeta_path = Path(carpeta) if carpeta else PDF_ENTRADA
    pdf_path = carpeta_path / archivo

    if not pdf_path.exists():
        return HTMLResponse("<div class='text-red-400 text-sm'>PDF no encontrado</div>")

    extractor = ExtractorPDF()
    datos = extractor.extraer_datos(str(pdf_path))

    return render("partials/preview_sin_dueno.html", {
        "request": request,
        "archivo": archivo,
        "nombre": datos.nombre_colaborador or "",
        "identificador": datos.identificador or "",
        "telefono": datos.telefono or "",
        "email": datos.email or "",
        "periodo": datos.periodo or "",
        "monto": datos.monto or "",
        "error": datos.error,
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
