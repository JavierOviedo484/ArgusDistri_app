"""
Configuración de base de datos SQLAlchemy.
SQLite para desarrollo, PostgreSQL para producción.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os
from pathlib import Path


# Ruta de la BD — raíz del proyecto /data/db/
DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "db"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{DATA_DIR / 'distribuidor.db'}"
)

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

# Forzar WAL mode en SQLite para mejor concurrencia
if "sqlite" in DATABASE_URL:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependency para FastAPI: entrega sesión y la cierra al terminar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Crea todas las tablas y seed de plantillas por defecto."""
    import app.models.colaborador  # noqa — fuerza registro de modelos
    import app.models.factura      # noqa
    import app.models.envio        # noqa
    import app.models.plantilla    # noqa
    import app.models.configuracion  # noqa
    Base.metadata.create_all(bind=engine)

    # Migración ligera (SQLite): create_all no agrega columnas a tablas ya
    # existentes — la columna enviado_sms se añade a mano si falta.
    if "sqlite" in DATABASE_URL:
        from sqlalchemy import text
        with engine.connect() as conn:
            try:
                conn.execute(text("ALTER TABLE facturas ADD COLUMN enviado_sms INTEGER DEFAULT 0"))
                conn.commit()
            except Exception:
                pass  # la columna ya existe

    # Seed plantillas por defecto (si no existen)
    from app.models.plantilla import Plantilla, PLANTILLAS_DEFAULT, AVISO_NO_CORRESPONDE
    db = SessionLocal()
    try:
        existing = db.query(Plantilla).count()
        if existing == 0:
            for p in PLANTILLAS_DEFAULT:
                db.add(Plantilla(**p))
        else:
            # Migración: plantillas ya sembradas con la marca antigua "ATOM"
            # se actualizan a "ARGUS" (no se tocan si el usuario ya las editó).
            for p in db.query(Plantilla).filter_by(nombre="factura").all():
                if p.cuerpo and "ATOM" in p.cuerpo:
                    p.cuerpo = p.cuerpo.replace("ATOM", "ARGUS")
                if p.asunto and "ATOM" in p.asunto:
                    p.asunto = p.asunto.replace("ATOM", "ARGUS")
            # Migración: aviso "si no es su factura, comuníquese urgentemente"
            # en plantillas email/whatsapp que aún no lo tengan.
            for p in db.query(Plantilla).filter(Plantilla.canal.in_(["email", "whatsapp"])).all():
                if p.cuerpo and "no le corresponde" not in p.cuerpo.lower():
                    p.cuerpo = p.cuerpo + AVISO_NO_CORRESPONDE
            # Migración: plantilla SMS si el canal aún no existe.
            if db.query(Plantilla).filter_by(canal="sms").count() == 0:
                for pd in PLANTILLAS_DEFAULT:
                    if pd["canal"] == "sms":
                        db.add(Plantilla(**pd))
        db.commit()
    finally:
        db.close()

    # Seed config por defecto (inserta si no existe, pero NO sobrescribe)
    from app.models.configuracion import Configuracion, CONFIG_DEFAULT
    db2 = SessionLocal()
    try:
        for clave, valor, desc in CONFIG_DEFAULT:
            exists = db2.query(Configuracion).filter_by(clave=clave).first()
            if not exists:
                db2.add(Configuracion(clave=clave, valor=valor, descripcion=desc))
            else:
                # Solo migra si el valor actual es exactamente el placeholder vacío
                # (ej: cuando se creó la tabla con seed original) — NUNCA sobrescribe
                # un valor que el usuario ya configuró.
                if exists.valor == "" and valor != "":
                    exists.valor = valor
                # Actualiza descripción si cambió
                if exists.descripcion != desc:
                    exists.descripcion = desc
        db2.commit()
    finally:
        db2.close()
