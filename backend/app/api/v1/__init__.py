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

@router.post("/enviar/{canal}/{factura_id}")
def enviar_factura(
    canal: str,
    factura_id: int,
    db: Session = Depends(get_db),
):
    """Envía UNA factura por email o WhatsApp (prepara el log)."""
    if canal not in ("email", "whatsapp"):
        raise HTTPException(400, "Canal debe ser 'email' o 'whatsapp'")

    factura = db.query(Factura).filter_by(id=factura_id).first()
    if not factura:
        raise HTTPException(404, "Factura no encontrada")
    colab = factura.colaborador
    if not colab:
        raise HTTPException(400, "Factura sin colaborador")

    destinatario = colab.email if canal == "email" else colab.telefono
    if not destinatario:
        raise HTTPException(400, f"{colab.nombre} no tiene {'email' if canal == 'email' else 'teléfono'}")

    # Renderizar plantilla
    plantilla = db.query(Plantilla).filter_by(canal=canal, nombre="factura", activo=True).first()
    if not plantilla:
        raise HTTPException(500, f"No hay plantilla activa para {canal}")

    cuerpo = plantilla.cuerpo.format(
        nombre=colab.nombre,
        periodo=factura.periodo,
        monto=str(factura.monto),
    )

    # Si es email, enviar realmente via SMTP
    if canal == "email":
        from app.services.email_sender import enviar_factura_email
        result = enviar_factura_email(
            db=db,
            destinatario=destinatario,
            asunto=plantilla.asunto.format(periodo=factura.periodo),
            cuerpo=cuerpo,
            pdf_path=factura.ruta_pdf,
        )
        if result["ok"]:
            envio = Envio(
                factura_id=factura.id,
                canal=canal,
                destinatario=destinatario,
                estado="enviado",
            )
            db.add(envio)
            db.commit()
        return result

    # WhatsApp: solo crear log pendiente (se enviará después con Evolution API)
    envio = Envio(
        factura_id=factura.id,
        canal=canal,
        destinatario=destinatario,
        estado="pendiente",
    )
    db.add(envio)
    db.commit()
    return {"ok": True, "mensaje": f"Encuolado para {canal} a {destinatario}"}


@router.post("/enviar-lote/{canal}")
def enviar_lote(
    canal: str,
    db: Session = Depends(get_db),
):
    """Envía TODAS las facturas pendientes por el canal especificado."""
    if canal not in ("email", "whatsapp"):
        raise HTTPException(400, "Canal debe ser 'email' o 'whatsapp'")

    facturas = db.query(Factura).filter(
        Factura.colaborador_id.isnot(None)
    ).all()

    enviados = 0
    errores = []

    plantilla = db.query(Plantilla).filter_by(canal=canal, nombre="factura", activo=True).first()

    for factura in facturas:
        colab = factura.colaborador
        destinatario = colab.email if canal == "email" else colab.telefono
        if not destinatario:
            errores.append(f"{colab.nombre}: sin {'email' if canal == 'email' else 'teléfono'}")
            continue

        cuerpo = plantilla.cuerpo.format(
            nombre=colab.nombre,
            periodo=factura.periodo,
            monto=str(factura.monto),
        ) if plantilla else f"Factura {factura.periodo}"

        if canal == "email":
            from app.services.email_sender import enviar_factura_email
            result = enviar_factura_email(
                db=db,
                destinatario=destinatario,
                asunto=plantilla.asunto.format(periodo=factura.periodo) if plantilla else f"Factura {factura.periodo}",
                cuerpo=cuerpo,
                pdf_path=factura.ruta_pdf,
            )
            if result["ok"]:
                db.add(Envio(factura_id=factura.id, canal=canal, destinatario=destinatario, estado="enviado"))
                enviados += 1
            else:
                errores.append(f"{colab.nombre}: {result['mensaje']}")
        else:
            # WhatsApp: pendiente
            db.add(Envio(factura_id=factura.id, canal=canal, destinatario=destinatario, estado="pendiente"))
            enviados += 1

    db.commit()
    return {"enviados": enviados, "errores": errores, "mensaje": f"{enviados} enviados, {len(errores)} errores"}


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

