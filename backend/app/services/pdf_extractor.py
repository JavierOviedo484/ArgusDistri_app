#!/usr/bin/env python3
"""
Extractor de datos desde facturas PDF.
Usa PyMuPDF (fitz) para extraer texto y regex para encontrar los campos.
Soporta múltiples formatos: Ecuador (RUC), Chile (RUT), genérico.
"""

import re
import fitz  # PyMuPDF
from pathlib import Path
from typing import Optional


class PDFExtractedData:
    """Datos extraídos de una factura PDF."""
    def __init__(
        self,
        archivo: str,
        nombre_colaborador: Optional[str] = None,
        identificador: Optional[str] = None,
        telefono: Optional[str] = None,
        email: Optional[str] = None,
        periodo: Optional[str] = None,
        monto: Optional[str] = None,
        texto_completo: str = "",
        error: Optional[str] = None,
    ):
        self.archivo = archivo
        self.nombre_colaborador = nombre_colaborador
        self.identificador = identificador  # RUC (Ecuador) o RUT (Chile)
        self.telefono = telefono
        self.email = email
        self.periodo = periodo
        self.monto = monto
        self.texto_completo = texto_completo
        self.error = error

    @property
    def es_valido(self) -> bool:
        return self.nombre_colaborador is not None and self.error is None

    def dict(self) -> dict:
        return {
            "archivo": self.archivo,
            "nombre_colaborador": self.nombre_colaborador,
            "identificador": self.identificador,
            "telefono": self.telefono,
            "email": self.email,
            "periodo": self.periodo,
            "monto": self.monto,
            "error": self.error,
        }

    def __repr__(self) -> str:
        status = "✅" if self.es_valido else "⚠️"
        return f"{status} {self.archivo}: {self.nombre_colaborador or 'sin identificar'}"


class ExtractorPDF:
    """
    Extrae datos de facturas PDF.
    Los patrones regex se adaptan al formato real de las facturas.
    """

    def __init__(self, patrones_extra: Optional[dict] = None):
        if patrones_extra:
            for key, regex_list in patrones_extra.items():
                if key in self.PATRONES:
                    self.PATRONES[key].extend(regex_list)
                else:
                    self.PATRONES[key] = regex_list

    PATRONES = {
        "nombre": [
            # TELERAPID: "Nombres:\n<CLIENTE>"
            r"Nombres:\s*\n(.+)",
            # OMNI INTEL: "Razón Social / Nombres y Apellidos:\nIdentificación\nFecha\nGuía\n<CLIENTE>"
            r"Raz.n Social / Nombres y Apellidos:\s*\nIdentificación\s*\nFecha\s*\nGuía\s*\n(.+)",
            # TELERAPID antiguo (con RUC intermedio)
            r"Nombres:\s*\nRUC:\s*\n[^\n]+\n([A-ZÁÉÍÓÚÑÜ\s]+?)(?:\n|\d)",
            # Chile / genérico
            r"(?:Nombre|Cliente|Colaborador)\s*:\s*(.+)",
        ],
        "identificador": [
            # TELERAPID client RUC: después de "RUC:\n" (sin punto, es cliente)
            r"(?<!\w)RUC:\s*\n\s*(\d{10,13})",
            # OMNI INTEL: RUC del cliente — después de "Razón Social"
            r"Raz.n Social / Nombres y Apellidos:[\s\S]*?\n(\d{13})",
            # TELERAPID / Ecuador genérico
            r"[A-Z][A-ZÁÉÍÓÚÑ\s]{8,}\n(\d{10,13})",
            # Ecuador emisor
            r"RUC\.?\s*:\s*(\d+)",
            # Chile
            r"RUT:\s*([\d.]+-[\dkK])",
            r"(?:RUT|Cedula|C\.I\.?)\s*:\s*([\d.]+-[\dkK])",
        ],
        "telefono": [
            # Teléfono del cliente (admite +593, espacios internos, etc.)
            r"(?<!\d)Telefono:\s*([+\d][\d \-]{5,}\d)",
            # Variante con tilde, pero NUNCA la línea "Teléfono N:" del emisor
            r"Tel(?:é|e)fono(?!\s*\d\s*:)(?:.*?):\s*([+\d][\d \-]{5,}\d)",
            # Teléfono del emisor (usar solo si no hay otro)
            r"Tel(?:é|e)fono\s+\d:\s*(\d+)",
        ],
        "email": [
            # OMNI INTEL: "Email:\n<email>" (en Información Adicional)
            r"Información Adicional[\s\S]*?Email:\s*\n\s*([\w.@-]+)",
            r"Informacion Adicional[\s\S]*?Email:\s*\n\s*([\w.@-]+)",
            r"Email:\s*\n\s*([\w.@-]+)",
            # TELERAPID: "correo  : email" en info adicional
            r"INFORMACIÓN ADICIONAL[\s\S]*?correo\s*:\s*([\w.@]+)",
            r"INFORMACION ADICIONAL[\s\S]*?correo\s*:\s*([\w.@]+)",
            # Genérico
            r"correo\s*:\s*([\w.@]+)",
            r"Email?\s*:\s*([\w.@]+)",
        ],
        "periodo": [
            # OMNI INTEL: fecha después de la sección "Razón Social"
            r"Raz.n Social / Nombres y Apellidos:[\s\S]*?(\d{2}/\d{2}/\d{4})",
            # TELERAPID: "observación: CONSUMO- DEL 01 DE DICIEMBRE AL 31 DE DICIEMBRE 2025"
            r"observación\s*:\s*CONSUMO-\s*DEL\s+\d+\s+DE\s+\w+\s+AL\s+\d+\s+DE\s+(\w+\s+\d+)",
            r"observación\s*:\s*(.+)",
            # Chile / genérico
            r"Periodo:\s*(.+)",
            r"Periodo\s+(.+)",
        ],
        "monto": [
            # OMNI INTEL / Ecuador: número justo después de "VALOR TOTAL" (misma línea o la siguiente)
            r"VALOR TOTAL\s*\$?\s*([\d.,]+)",
            # Valor en línea de Forma de Pago
            r"Sin Utilización Del Sistema Financiero\s+([\d.,]+)",
            # Chile / genérico
            r"Total:\s*\$?([\d.,]+)",
            r"Total a pagar:\s*\$?([\d.,]+)",
        ],
    }

    def extraer_datos(self, ruta_pdf: str | Path) -> PDFExtractedData:
        """
        Abre un PDF, extrae texto completo y busca los patrones.
        """
        ruta = Path(ruta_pdf)
        if not ruta.exists():
            return PDFExtractedData(
                archivo=ruta.name,
                error=f"Archivo no encontrado: {ruta_pdf}"
            )

        try:
            doc = fitz.open(ruta)
            texto = ""
            for pagina in doc:
                texto += pagina.get_text()
            doc.close()
        except Exception as e:
            return PDFExtractedData(
                archivo=ruta.name,
                error=f"Error al leer PDF: {str(e)}"
            )

        if not texto.strip():
            return PDFExtractedData(
                archivo=ruta.name,
                error="PDF vacío o sin texto extraíble (¿escaneado/imagen?)"
            )

        # Buscar cada campo
        nombre = self._buscar(texto, "nombre")
        if nombre:
            # "Las letras van al final" — limpiar dígitos/sobrantes
            # que las regex greedy puedan haber capturado después del nombre
            nombre = re.sub(r'[\d\s]+$', '', nombre).strip()
        identificador = self._buscar(texto, "identificador")
        telefono = self._buscar(texto, "telefono")
        email = self._buscar(texto, "email")
        monto = self._buscar(texto, "monto")

        # Periodo con lógica extra para formato Ecuador
        periodo = self._extraer_periodo(texto)

        return PDFExtractedData(
            archivo=ruta.name,
            nombre_colaborador=nombre.strip() if nombre else None,
            identificador=identificador.strip() if identificador else None,
            telefono=self._limpiar_telefono(telefono) if telefono else None,
            email=email.strip() if email else "sin correo",
            periodo=periodo,
            monto=monto.strip() if monto else None,
            texto_completo=texto,
        )

    def _extraer_periodo(self, texto: str) -> Optional[str]:
        """Extrae y normaliza el período."""
        # OMNI INTEL: extraer fecha dd/mm/aaaa y convertir a mes año
        m = re.search(
            r"Raz.n Social / Nombres y Apellidos:[\s\S]*?(\d{2})/(\d{2})/(\d{4})",
            texto, re.IGNORECASE
        )
        if m:
            dias, mes, anio = m.group(1), m.group(2), m.group(3)
            meses = {
                "01": "ENERO", "02": "FEBRERO", "03": "MARZO",
                "04": "ABRIL", "05": "MAYO", "06": "JUNIO",
                "07": "JULIO", "08": "AGOSTO", "09": "SEPTIEMBRE",
                "10": "OCTUBRE", "11": "NOVIEMBRE", "12": "DICIEMBRE",
            }
            nombre_mes = meses.get(mes, mes)
            return f"{nombre_mes} {anio}"

        # TELERAPID: "observación: CONSUMO- DEL 01 DE DICIEMBRE AL 31 DE DICIEMBRE 2025"
        m = re.search(
            r"observación\s*:\s*CONSUMO-\s*DEL\s+\d+\s+DE\s+\w+\s+AL\s+\d+\s+DE\s+(\w+\s+\d+)",
            texto, re.IGNORECASE
        )
        if m:
            return m.group(1)

        # Patrones genéricos del diccionario
        for pat in self.PATRONES.get("periodo", []):
            if "Raz.n Social" not in pat and "observación" not in pat:
                m = re.search(pat, texto, re.IGNORECASE | re.MULTILINE)
                if m:
                    return m.group(1).strip() if m.lastindex and m.lastindex >= 1 else None
        return None

    def _limpiar_telefono(self, t: str) -> str:
        """Limpia formato de teléfono y normaliza a formato internacional Ecuador (+593 sin +).

        Casos:
          '0982967070'  → '593982967070'  (celular local)
          '+593 98 296 7070' → '593982967070'
          '593982967070' → '593982967070' (ya normalizado)
        """
        t = re.sub(r'[^0-9]', '', t)
        if len(t) == 10 and t.startswith("09"):
            t = "593" + t[1:]
        elif len(t) == 9 and t.startswith("9"):
            t = "593" + t
        return t

    def _buscar(self, texto: str, campo: str) -> Optional[str]:
        """Busca el primer match de cualquier patrón para el campo dado."""
        patrones = self.PATRONES.get(campo, [])
        for pat in patrones:
            match = re.search(pat, texto, re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1).strip()
        return None


# --- Demostración / test rápido ---
if __name__ == "__main__":
    import sys

    data_dir = Path(__file__).parent.parent.parent.parent / "data" / "pdfs_entrada"
    pdfs = sorted(data_dir.glob("*.pdf"))

    if not pdfs:
        print("No hay PDFs en", data_dir)
        sys.exit(1)

    # Si existe ejemplo.pdf, procesarlo solo a él
    ejemplo = data_dir / "ejemplo.pdf"
    if ejemplo.exists():
        pdfs = [ejemplo]

    extractor = ExtractorPDF()
    print("=" * 60)
    print("EXTRACTOR DE FACTURAS PDF")
    print("=" * 60)

    resultados = []
    for pdf in pdfs:
        datos = extractor.extraer_datos(pdf)

        print(f"\n📄 {datos.archivo}")
        if datos.error:
            print(f"   ❌ ERROR: {datos.error}")
        else:
            print(f"   👤 Nombre:       {datos.nombre_colaborador}")
            print(f"   🆔 Identificador: {datos.identificador}")
            print(f"   📱 Teléfono:     {datos.telefono or 'no encontrado'}")
            print(f"   ✉️  Email:       {datos.email}")
            print(f"   📅 Periodo:      {datos.periodo}")
            print(f"   💰 Monto:        {datos.monto}")

        resultados.append({
            "archivo": datos.archivo,
            "nombre": datos.nombre_colaborador,
            "identificador": datos.identificador,
            "telefono": datos.telefono,
            "email": datos.email,
            "periodo": datos.periodo,
            "monto": datos.monto,
            "es_valido": datos.es_valido,
            "error": datos.error,
        })

    validos = sum(1 for r in resultados if r["es_valido"])
    print(f"\n{'=' * 60}")
    print(f"Resumen: {validos}/{len(resultados)} PDFs identificados correctamente")
    print(f"{'=' * 60}")
