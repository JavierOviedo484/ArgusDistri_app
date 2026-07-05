"""
API v1 — endpoints del distribuidor de documentos.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.orm import Session
from pathlib import Path
import shutil

from app.core.database import get_db
from app.models.colaborador import Colaborador
from app.models.factura import Factura
from app.models.envio import Envio
from app.models.plantilla import Plantilla
from app.models.configuracion import Configuracion
from app.services.matcher import Matcher
from app.schemas import ColaboradorCreate, EnvioConfirm, PlantillaUpdate, ConfigUpdate

router = APIRouter()

BASE_DIR = Path(__file__).parent.parent.parent.parent  # backend/
PROJECT_DIR = BASE_DIR.parent  # distribuidor-pdfs/
PDF_ENTRADA = PROJECT_DIR / "data" / "pdfs_entrada"
PDF_PROCESADOS = PROJECT_DIR / "data" / "pdfs_procesados"
PDF_SIN_DUENO = PROJECT_DIR / "data" / "pdfs_sin_dueno"
PDF_PROCESADOS.mkdir(parents=True, exist_ok=True)
PDF_SIN_DUENO.mkdir(parents=True, exist_ok=True)


# ─── COLABORADORES ──────────────────────────────────────────────

@router.get("/colaboradores")
def listar_colaboradores(db: Session = Depends(get_db)):
    cols = db.query(Colaborador).order_by(Colaborador.nombre).all()
    return [c.dict() for c in cols]


@router.post("/colaboradores")
def crear_colaborador(data: ColaboradorCreate, db: Session = Depends(get_db)):
    exists = db.query(Colaborador).filter_by(identificador=data.identificador).first()
    if exists:
        # Actualizar existente
        for k, v in data.dict(exclude_unset=True).items():
            setattr(exists, k, v)
        db.commit()
        return exists.dict()
    colab = Colaborador(**data.dict())
    db.add(colab)
    db.commit()
    return colab.dict()


@router.delete("/colaboradores/{identificador}")
def eliminar_colaborador(identificador: str, db: Session = Depends(get_db)):
    colab = db.query(Colaborador).filter_by(identificador=identificador).first()
    if not colab:
        raise HTTPException(404, "Colaborador no encontrado")
    db.delete(colab)
    db.commit()
    return {"ok": True}


# ─── ESCANEO ────────────────────────────────────────────────────

@router.post("/escaneo")
def escanear_pdfs(db: Session = Depends(get_db)):
    """Escanea carpeta de entrada y devuelve resultados del matching."""
    matcher = Matcher(PDF_ENTRADA, db)
    resultados = matcher.escanear()

    ok = [r.dict() for r in resultados if r.estado == "ok"]
    sin_dueno = [r.dict() for r in resultados if r.estado == "sin_dueño"]
    errores = [r.dict() for r in resultados if r.estado == "error_extraccion"]
    
    # Alertas
    alertas = []
    total_colabs = db.query(Colaborador).count()
    for r in resultados:
        for a in r.alertas:
            alertas.append(a)
    
    # Verificar si hay colaboradores sin facturas
    colabs_con_pdf = set(r.colaborador.identificador for r in resultados if r.colaborador)
    if total_colabs > 0:
        cols_sin_factura = db.query(Colaborador).filter(
            ~Colaborador.identificador.in_(colabs_con_pdf)
        ).all() if colabs_con_pdf else []
    else:
        cols_sin_factura = []

    # Verificar teléfonos faltantes
    cols_sin_telefono = []
    for r in resultados:
        if r.colaborador and not r.colaborador.telefono:
            cols_sin_telefono.append(r.colaborador.nombre)

    return {
        "total": len(resultados),
        "ok": ok,
        "sin_dueno": sin_dueno,
        "errores": errores,
        "alertas": [
            *alertas,
            *[f"⚠️ Sin teléfono registrado: {n}" for n in cols_sin_telefono],
            *[f"⚠️ {c.nombre} no tiene factura en este lote" for c in cols_sin_factura],
        ],
    }


# ─── FACTURAS ──────────────────────────────────────────────────

@router.get("/facturas")
def listar_facturas(db: Session = Depends(get_db)):
    facturas = db.query(Factura).order_by(Factura.procesado_en.desc()).limit(50).all()
    return [f.dict() for f in facturas]


# ─── ENVÍO ──────────────────────────────────────────────────────
#
# El envío real de facturas individuales/en lote (con HTML de respuesta
# para los botones htmx del dashboard) vive en backend/main.py, ya que
# necesita los templates Jinja. Estas rutas JSON puras se dejan solo
# para "confirmar-envio" (registro masivo de envíos pendientes).

@router.post("/confirmar-envio")
def confirmar_envio(data: EnvioConfirm, db: Session = Depends(get_db)):
    """
    Confirma el envío de todas las facturas OK.
    Mueve PDFs a procesados y crea logs de envío.
    """
    enviados = 0
    errores = []

    for item in data.envios:
        factura = db.query(Factura).filter_by(id=item.factura_id).first()
        if not factura:
            errores.append({"factura_id": item.factura_id, "error": "No encontrada"})
            continue

        colab = factura.colaborador
        if not colab:
            errores.append({"factura_id": item.factura_id, "error": "Sin colaborador"})
            continue

        # WhatsApp
        if colab.telefono:
            env_wp = Envio(
                factura_id=factura.id,
                canal="whatsapp",
                destinatario=colab.telefono,
                estado="pendiente",
            )
            db.add(env_wp)
        else:
            errores.append(f"Factura #{factura.id}: {colab.nombre} sin teléfono")

        # Email
        if colab.email and colab.email != "sin correo":
            env_em = Envio(
                factura_id=factura.id,
                canal="email",
                destinatario=colab.email,
                estado="pendiente",
            )
            db.add(env_em)
        else:
            errores.append(f"Factura #{factura.id}: {colab.nombre} sin email")

        # Mover PDF a procesados
        src = Path(factura.ruta_pdf) if factura.ruta_pdf else None
        if src and src.exists():
            dst = PDF_PROCESADOS / src.name
            shutil.move(str(src), str(dst))
            factura.ruta_pdf = str(dst)

        enviados += 1

    db.commit()
    return {
        "enviados": enviados,
        "errores": errores,
        "mensaje": f"{enviados} facturas procesadas, {len(errores)} alertas",
    }


# ─── EVOLUTION API STATUS ──────────────────────────────────────

@router.get("/status")
def status(db: Session = Depends(get_db)):
    """Estado general del sistema."""
    cols = db.query(Colaborador).count()
    facts = db.query(Factura).count()
    envs_pend = db.query(Envio).filter_by(estado="pendiente").count()
    envs_total = db.query(Envio).count()
    return {
        "colaboradores": cols,
        "facturas": facts,
        "envios_pendientes": envs_pend,
        "envios_totales": envs_total,
    }


# ─── PLANTILLAS ──────────────────────────────────────────────────

@router.get("/plantillas")
def listar_plantillas(db: Session = Depends(get_db)):
    plantillas = db.query(Plantilla).order_by(Plantilla.canal, Plantilla.nombre).all()
    return [p.dict() for p in plantillas]


@router.get("/plantillas/{plantilla_id}")
def obtener_plantilla(plantilla_id: int, db: Session = Depends(get_db)):
    p = db.query(Plantilla).filter_by(id=plantilla_id).first()
    if not p:
        raise HTTPException(404, "Plantilla no encontrada")
    return p.dict()


@router.put("/plantillas/{plantilla_id}")
def actualizar_plantilla(
    plantilla_id: int, data: PlantillaUpdate, db: Session = Depends(get_db)
):
    p = db.query(Plantilla).filter_by(id=plantilla_id).first()
    if not p:
        raise HTTPException(404, "Plantilla no encontrada")
    update_data = data.dict(exclude_unset=True)
    for k, v in update_data.items():
        setattr(p, k, v)
    db.commit()
    return p.dict()


@router.get("/plantillas/{plantilla_id}/preview")
def previsualizar_plantilla(
    plantilla_id: int,
    nombre: str = "Colaborador",
    periodo: str = "ENERO 2026",
    monto: str = "100.00",
    db: Session = Depends(get_db),
):
    """Renderiza la plantilla con valores de ejemplo para previsualización."""
    p = db.query(Plantilla).filter_by(id=plantilla_id).first()
    if not p:
        raise HTTPException(404, "Plantilla no encontrada")
    cuerpo = p.cuerpo.format(nombre=nombre, periodo=periodo, monto=monto)
    asunto = p.asunto.format(nombre=nombre, periodo=periodo, monto=monto) if p.asunto else ""
    return {"asunto": asunto, "cuerpo": cuerpo}


# ─── CONFIGURACIÓN ──────────────────────────────────────────────

@router.get("/config")
def listar_config(db: Session = Depends(get_db)):
    configs = db.query(Configuracion).order_by(Configuracion.clave).all()
    return {c.clave: c.valor for c in configs}


@router.put("/config/{clave}")
def actualizar_config(clave: str, data: ConfigUpdate, db: Session = Depends(get_db)):
    c = db.query(Configuracion).filter_by(clave=clave).first()
    if not c:
        raise HTTPException(404, f"Configuración '{clave}' no encontrada")
    c.valor = data.valor
    db.commit()
    return {"clave": c.clave, "valor": c.valor}


# ─── ENVÍO EN LOTE (Email / WhatsApp / SMS) ──────────────────────


@router.post("/enviar-lote/{canal}")
def enviar_lote(canal: str, db: Session = Depends(get_db)):
    """
    Envía todas las facturas pendientes por el canal indicado.
    Devuelve HTML para HTMX (swap en #resultado-envio).
    """
    import os as _os
    from app.services.email_sender import enviar_email
    from app.services.whatsapp_sender import enviar_whatsapp
    from app.services.sms_sender import enviar_sms

    if canal not in ("email", "whatsapp", "sms"):
        return HTMLResponse("<div class='text-red-400 text-sm'>Canal inválido</div>")

    # Columnas según canal
    col_enviado = {
        "email": Factura.enviado_email,
        "whatsapp": Factura.enviado_whatsapp,
        "sms": Factura.enviado_sms,
    }
    col_destino = {
        "email": Colaborador.email,
        "whatsapp": Colaborador.telefono,
        "sms": Colaborador.telefono,
    }

    facturas = (
        db.query(Factura)
        .filter(col_enviado[canal] == False)
        .all()
    )

    if not facturas:
        return HTMLResponse(
            "<div class='card' style='background:#f0fdf4;border-color:#bbf7d0;margin-bottom:1rem;'>"
            "<div class='text-sm font-bold' style='color:#16a34a;'>📭 No hay facturas pendientes de enviar.</div></div>"
        )

    enviados = 0
    fallidos = 0
    errores = []

    for f in facturas:
        colab = db.query(Colaborador).filter_by(identificador=f.colaborador_id).first()
        if not colab:
            fallidos += 1
            errores.append(f"Factura #{f.id}: sin colaborador")
            continue

        destino = getattr(colab, col_destino[canal].key, "")
        if not destino or destino == "sin correo":
            fallidos += 1
            errores.append(f"{colab.nombre}: sin {'email' if canal == 'email' else 'teléfono'}")
            continue

        pdf_path = Path(f.ruta_pdf) if f.ruta_pdf else None

        if canal == "email":
            result = enviar_email(
                para=destino,
                asunto=f"📄 Documento {f.archivo_original or ''} · {f.periodo or ''}",
                cuerpo=f"Hola {colab.nombre},\n\nAdjuntamos su documento correspondiente al período {f.periodo} por un monto de ${f.monto}.\n\nAtentamente,\nARGUS · Distribuidor de Documentos",
                adjunto_pdf=pdf_path if (pdf_path and pdf_path.exists()) else None,
                smtp_user=_os.environ.get("EMAIL_SENDER", ""),
                smtp_password=_os.environ.get("GMAIL_APP_PASSWORD", ""),
            )

        elif canal == "whatsapp":
            config = {c.clave: c.valor for c in db.query(Configuracion).all()}
            result = enviar_whatsapp(
                numero=destino,
                mensaje=f"Hola {colab.nombre}, reciba su documento del período {f.periodo} por ${f.monto}.",
                api_url=config.get("whatsapp_api_url", ""),
                api_key=config.get("whatsapp_api_key", ""),
                instance=config.get("whatsapp_instance", "argus"),
                adjunto_pdf=pdf_path if (pdf_path and pdf_path.exists()) else None,
            )

        else:  # sms
            config = {c.clave: c.valor for c in db.query(Configuracion).all()}
            result = enviar_sms(
                numero=destino,
                mensaje=f"{colab.nombre}, su documento {f.periodo} por ${f.monto} está listo. ARGUS.",
                api_url=config.get("sms_api_url", ""),
                api_key=config.get("sms_api_key", ""),
            )

        if result.get("ok"):
            setattr(f, col_enviado[canal].key, True)
            enviados += 1
        else:
            fallidos += 1
            errores.append(f"{colab.nombre}: {result.get('mensaje', 'error')}")

    db.commit()

    # HTML respuesta
    if fallidos == 0:
        html = (
            "<div class='card' style='background:#f0fdf4;border-color:#bbf7d0;margin-bottom:1rem;'>"
            f"<div class='text-sm font-bold' style='color:#16a34a;'>✅ {enviados} factura(s) enviadas correctamente por {'email' if canal == 'email' else ('WhatsApp' if canal == 'whatsapp' else 'SMS')}.</div>"
            "</div>"
        )
    else:
        detalle = "".join(f"<li>{e}</li>" for e in errores[:10])
        html = (
            "<div class='card' style='background:#fef2f2;border-color:#fecaca;margin-bottom:1rem;'>"
            f"<div class='text-sm font-bold' style='color:#dc2626;'>⚠️ {enviados} enviadas, {fallidos} fallos</div>"
            f"<ul class='text-xs mt-1' style='color:#991b1b;'>{detalle}</ul>"
            "</div>"
        )

    return HTMLResponse(html)

