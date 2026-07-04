"""
Seed rápido: registra los 30 colaboradores de prueba y sus facturas.
Correr: python seed_test.py
"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app.core.database import init_db, get_db, SessionLocal
from app.models.colaborador import Colaborador
from app.models.factura import Factura
from app.services.pdf_extractor import ExtractorPDF

CARPETA = Path("/mnt/c/Users/javie/Desktop/AUTOM/Correos/facturas")

def main():
    # Usar BD temporal para pruebas
    os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).parent / 'data' / 'db' / 'distribuidor.db'}"
    init_db()
    db = SessionLocal()

    ex = ExtractorPDF()
    pdfs = sorted(CARPETA.glob("*.pdf"))
    creados = 0

    for pdf in pdfs:
        res = ex.extraer_datos(str(pdf))
        if not res.identificador:
            print(f"  ⏭️  {pdf.name}: sin RUC, saltando")
            continue

        colab = db.query(Colaborador).filter_by(identificador=res.identificador).first()
        if not colab:
            colab = Colaborador(
                identificador=res.identificador,
                nombre=res.nombre_colaborador or pdf.stem,
                email=res.email or "",
                telefono=res.telefono or "",
            )
            db.add(colab)
            db.flush()

        exists = db.query(Factura).filter_by(ruta_pdf=str(pdf)).first()
        if not exists:
            fact = Factura(
                colaborador_id=colab.identificador,
                archivo_original=pdf.name,
                ruta_pdf=str(pdf),
                periodo=res.periodo or "SIN PERIODO",
                monto=res.monto or "0.00",
            )
            db.add(fact)

        creados += 1

    db.commit()
    total_c = db.query(Colaborador).count()
    total_f = db.query(Factura).count()
    db.close()
    print(f"\n✅ Seed completo: {total_c} colaboradores, {total_f} facturas ({creados} PDFs procesados)")

if __name__ == "__main__":
    main()
