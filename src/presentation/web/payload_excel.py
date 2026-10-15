"""Small streaming XLSX writer for the payload result tables."""
from datetime import date, datetime
from decimal import Decimal
import re
from tempfile import TemporaryFile
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from src.presentation.web.formatters import datetime_lima


COLUMNS = {
    "00021": [
        ("Fecha Hora", "run_ts"), ("Run", "run_id"), ("IB_BANNER", "ib_banner"),
        ("DNI", "dni"), ("APELLIDOS", "apellidos"), ("Estado run", "status"),
        ("HTTP", "http_status"), ("MPL-ID", "texto_mpl_id"),
        ("Mensaje CPI", "texto_legible"),
    ],
    "00022": [
        ("Fecha Hora", "run_ts"), ("Run", "run_id"), ("IB_BANNER", "ib_banner"),
        ("BP", "bp"), ("SURROGATE", "surrogate"), ("MATNR", "matnr"),
        ("AUDAT (Fecha)", "fecha_audat"), ("ZVALORTOTAL (Monto)", "total_amount"),
        ("Estado run", "status"), ("Mensaje de error SAP", "failed_body"),
    ],
    "00023": [
        ("Fecha Hora", "run_ts"), ("Run", "run_id"), ("IB_BANNER", "ib_banner"),
        ("BP", "bp"), ("SURROGATE", "surrogate"), ("BLDAT (Fecha)", "document_date"),
        ("WRBTR (Monto)", "payment_amount"), ("HKONT (Cuenta)", "account"),
        ("Estado run", "status"), ("HTTP", "http_status"),
        ("Mensaje de error SAP", "payment_message"),
    ],
}
INCIDENT_COLUMNS = [
    ("Fecha (Lima)", "fecha_error"), ("ID BANNER", "identifier"),
    ("Veces del mismo error", "total_intentos_fallidos"),
    ("Intentos fallidos del día", "total_por_identificador"),
    ("Mensaje de error", "error_body"),
]
MAX_DATA_ROWS = 1_048_575
_INVALID_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _cell(value) -> str:
    if value is None:
        value = ""
    if isinstance(value, datetime):
        value = datetime_lima(value)
    elif isinstance(value, date):
        value = value.strftime("%d/%m/%Y")
    elif isinstance(value, (int, Decimal)) and not isinstance(value, bool):
        return f"<c><v>{value}</v></c>"
    return f'<c t="inlineStr"><is><t xml:space="preserve">{escape(_INVALID_XML.sub("", str(value)))}</t></is></c>'


def workbook(pi_id: str | None, rows, columns=None):
    """Return a seekable temporary XLSX; rows are consumed incrementally."""
    output = TemporaryFile()
    try:
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
            archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
            archive.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Resultados" sheetId="1" r:id="rId1"/></sheets></workbook>')
            archive.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
            with archive.open("xl/worksheets/sheet1.xml", "w") as sheet:
                sheet.write(b'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>')
                columns = columns if columns is not None else COLUMNS[pi_id]
                sheet.write(("<row r=\"1\">" + "".join(_cell(label) for label, _ in columns) + "</row>").encode("utf-8"))
                for index, item in enumerate(rows, 2):
                    if index > MAX_DATA_ROWS + 1:
                        raise ValueError("La selección excede el límite de filas de Excel; reduzca el rango de fechas.")
                    sheet.write((f'<row r="{index}">' + "".join(_cell(item.get("sap_error_message") or item.get(key) if label == "Mensaje de error SAP" else item.get(key)) for label, key in columns) + "</row>").encode("utf-8"))
                sheet.write(b"</sheetData></worksheet>")
        output.seek(0)
        return output
    except Exception:
        output.close()
        raise
