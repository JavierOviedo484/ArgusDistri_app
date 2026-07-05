"""
Servicio: Matcher.
Conecta el extractor de PDFs con la base de datos de colaboradores.

Flujo:
1. Escanea carpeta de PDFs de entrada
2. Extrae datos de cada PDF (nombre, identificador, teléfono, email)
3. Busca el identificador en la BD de colaboradores
4. Si existe → asigna automáticamente
5. Si no existe → marca como "sin dueño" (alerta en dashboard)
"""

from pathlib import Path
from typing import Optional
from sqlalchemy.orm import Session as DBSession

from app.services.pdf_extractor import ExtractorPDF, PDFExtractedData
from app.models.colaborador import Colaborador
from app.models.factura import Factura


class MatchResult:
    """Resultado del matching de un PDF contra la BD."""

    def __init__(
        self,
        extraido: PDFExtractedData,
        colaborador: Optional[Colaborador] = None,
        factura: Optional[Factura] = None,
        alertas: Optional[list[str]] = None,
    ):
        self.archivo = extraido.archivo
        self.extraido = extraido
        self.colaborador = colaborador
        self.factura = factura
        self.alertas = alertas or []

    @property
    def estado(self) -> str:
        """Estado del matching: 'ok', 'sin_dueño', 'error_extraccion'."""
        if self.extraido.error:
            return "error_extraccion"
        if self.colaborador:
            return "ok"
        return "sin_dueño"

    @property
    def resumen(self) -> str:
        if self.estado == "ok":
            return f"✅ {self.archivo} → {self.colaborador.nombre}"
        elif self.estado == "sin_dueño":
            nombre = self.extraido.nombre_colaborador or "???"
            id_ = self.extraido.identificador or "???"
            return f"⚠️  {self.archivo}: '{nombre}' (ID: {id_}) no está registrado"
        else:
            return f"❌ {self.archivo}: {self.extraido.error}"

    def dict(self) -> dict:
        return {
            "archivo": self.archivo,
            "estado": self.estado,
            "nombre_extraido": self.extraido.nombre_colaborador,
            "identificador_extraido": self.extraido.identificador,
            "telefono_extraido": self.extraido.telefono,
            "email_extraido": self.extraido.email,
            "periodo": self.extraido.periodo,
            "monto": self.extraido.monto,
            "colaborador": self.colaborador.dict() if self.colaborador else None,
            "factura": self.factura.dict() if self.factura else None,
            "alertas": self.alertas,
        }


class Matcher:
    """
    Escanea PDFs → extrae datos → matchea vs BD → devuelve resultados.
    """

    def __init__(
        self,
        carpeta_entrada: str | Path,
        db_session: DBSession,
        extractor: Optional[ExtractorPDF] = None,
        patrones_extra: Optional[dict] = None,
        auto_registrar: bool = True,
    ):
        self.carpeta = Path(carpeta_entrada)
        self.db = db_session
        self.extractor = extractor or ExtractorPDF(patrones_extra=patrones_extra)
        # Si el PDF trae nombre + identificador y el colaborador no existe,
        # se registra automáticamente (queda "sin dueño" solo cuando la
        # extracción no logra identificar a la persona).
        self.auto_registrar = auto_registrar

    def escanear(self) -> list[MatchResult]:
        """
        Escanea TODOS los PDFs en la carpeta de entrada.
        Devuelve lista de MatchResult.
        """
        pdfs = sorted(self.carpeta.glob("*.pdf"))
        if not pdfs:
            return []

        resultados = []
        for pdf in pdfs:
            resultado = self._procesar_pdf(pdf)
            resultados.append(resultado)

        return resultados

    def _procesar_pdf(self, ruta_pdf: Path) -> MatchResult:
        """Procesa un PDF: extrae datos, busca en BD, guarda factura."""
        extraido = self.extractor.extraer_datos(ruta_pdf)

        if extraido.error:
            return MatchResult(extraido=extraido)

        # Buscar colaborador por identificador (RUC/RUT)
        colaborador = None
        alertas = []

        if extraido.identificador:
            colaborador = (
                self.db.query(Colaborador)
                .filter_by(identificador=extraido.identificador)
                .first()
            )
        elif extraido.nombre_colaborador:
            # Fallback: buscar por nombre
            colaborador = (
                self.db.query(Colaborador)
                .filter_by(nombre=extraido.nombre_colaborador)
                .first()
            )
            if colaborador:
                alertas.append(
                    f"'{colaborador.nombre}' se encontró por nombre, no por ID. "
                    f"Considera registrar su RUC/cédula en la ficha del colaborador."
                )

        def _coinciden(tel_bd: str, tel_pdf: str) -> bool:
            """Compara teléfonos normalizando diferencias de formato.
            El PDF suele traer 0982967070, la BD guarda 593982967070."""
            import re
            def _core(n: str) -> str:
                n = re.sub(r'[^0-9]', '', n or '')
                if n.startswith('593'):
                    n = n[3:]
                return n.lstrip('0')
            return _core(tel_bd) == _core(tel_pdf)

        # Registro automático: el PDF identifica a la persona (nombre + RUC)
        # pero aún no está en la BD → se crea el colaborador con los datos
        # extraídos y la factura queda asignada en el mismo escaneo.
        if (
            not colaborador
            and self.auto_registrar
            and extraido.identificador
            and extraido.nombre_colaborador
        ):
            email = extraido.email if extraido.email and extraido.email != "sin correo" else None
            from app.services.whatsapp_sender import normalizar_telefono as _norm
            telf = _norm(extraido.telefono) if extraido.telefono else None
            colaborador = Colaborador(
                identificador=extraido.identificador,
                nombre=extraido.nombre_colaborador.strip(),
                email=email,
                telefono=telf,
            )
            self.db.add(colaborador)
            self.db.commit()
            alertas.append(
                f"🆕 '{colaborador.nombre}' registrado automáticamente "
                f"(RUC {colaborador.identificador})"
            )

        # Si se encontró colaborador, crear factura si no existe
        factura = None
        if colaborador:
            factura = self.db.query(Factura).filter_by(ruta_pdf=str(ruta_pdf)).first()
            if not factura:
                factura = Factura(
                    colaborador_id=colaborador.identificador,
                    archivo_original=ruta_pdf.name,
                    periodo=extraido.periodo,
                    monto=extraido.monto,
                    ruta_pdf=str(ruta_pdf),
                )
                self.db.add(factura)
                self.db.commit()

            # Alertas adicionales
            if colaborador.telefono and extraido.telefono:
                if not _coinciden(colaborador.telefono, extraido.telefono):
                    alertas.append(
                        f"Teléfono en PDF ({extraido.telefono}) difiere del registrado "
                        f"({colaborador.telefono})"
                    )

        return MatchResult(
            extraido=extraido,
            colaborador=colaborador,
            factura=factura,
            alertas=alertas,
        )
