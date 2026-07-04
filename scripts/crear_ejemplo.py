#!/usr/bin/env python3
"""Genera facturas PDF de ejemplo para probar el extractor."""

from fpdf import FPDF
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
ENTRADA_DIR = os.path.join(DATA_DIR, "pdfs_entrada")

class Factura(FPDF):
    def factura(self, nro: int, nombre: str, rut: str, monto: str, periodo: str):
        self.add_page()
        # Encabezado
        self.set_font("Helvetica", "B", 18)
        self.cell(0, 12, "FACTURA ELECTRONICA", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 10)
        self.cell(0, 6, f"N° {nro:04d}", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(8)

        # Datos del emisor
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 8, "EMISOR:", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 10)
        self.cell(0, 6, "OMNI INTEL · El Ordeno · Plataforma CAVOUND", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 6, "RUT: 76.123.456-7", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 6, "Direccion: Av. Principal 1234, Santiago", new_x="LMARGIN", new_y="NEXT")
        self.ln(5)

        # Datos del colaborador
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 8, "COLABORADOR:", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 10)
        self.cell(0, 6, f"Nombre: {nombre}", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 6, f"RUT: {rut}", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 6, f"Periodo: {periodo}", new_x="LMARGIN", new_y="NEXT")
        self.ln(5)

        # Tabla de items
        self.set_font("Helvetica", "B", 10)
        col_w = [80, 30, 30, 30, 30]
        headers = ["Descripcion", "Cant.", "P/U", "Total"]
        self.set_fill_color(220, 220, 220)
        for i, h in enumerate(headers):
            self.cell(col_w[i], 8, h, border=1, align="C", fill=True)
        self.ln()

        self.set_font("Helvetica", "", 10)
        items = [
            ("Servicios logisticos mensuales", "1", f"${monto}", f"${monto}"),
        ]
        for row in items:
            for i, val in enumerate(row):
                align = "L" if i == 0 else "R"
                self.cell(col_w[i], 7, val, border=1, align=align)
            self.ln()

        self.ln(5)
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 8, f"Total: ${monto}", align="R", new_x="LMARGIN", new_y="NEXT")
        self.ln(10)
        self.set_font("Helvetica", "", 8)
        self.cell(0, 5, "Documento generado electronicamente.", new_x="LMARGIN", new_y="NEXT")


def main():
    os.makedirs(ENTRADA_DIR, exist_ok=True)

    colaboradores = [
        ("Juan Perez Garcia", "12.345.678-9", "450000", "Marzo 2025"),
        ("Maria Garcia Lopez", "23.456.789-0", "320000", "Marzo 2025"),
        ("Luis Torres Munoz", "34.567.890-1", "510000", "Marzo 2025"),
        ("Ana Rodriguez Silva", "45.678.901-2", "280000", "Febrero 2025"),
        ("Carlos Munoz Vega", "56.789.012-3", "390000", "Marzo 2025"),
    ]

    for i, (nombre, rut, monto, periodo) in enumerate(colaboradores, 1):
        pdf = Factura(orientation="P", unit="mm", format="A4")
        pdf.factura(i, nombre=nombre, rut=rut, monto=monto, periodo=periodo)
        path = os.path.join(ENTRADA_DIR, f"factura_{i:02d}.pdf")
        pdf.output(path)
        print(f"  ✅ {path}")

    print(f"\nTotal: {len(colaboradores)} facturas generadas en {ENTRADA_DIR}")

if __name__ == "__main__":
    main()
