# src/file_services/converters/pdf_converter.py


def pdf_a_imagen(pdf_bytes: bytes, pagina: int = 0, dpi: int = 150) -> bytes:
    """
    Convierte una página de un PDF a JPEG usando PyMuPDF.
    Retorna los bytes de la imagen resultante.
    Requiere: PyMuPDF (pip install pymupdf)
    """
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pagina = min(pagina, len(doc) - 1)
    page = doc[pagina]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    return pix.tobytes("jpeg")
