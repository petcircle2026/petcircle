"""
PetCircle Phase 1 — File Reader Utility

Reads uploaded file content for GPT extraction:
    - Images (JPEG/PNG): Base64-encodes for GPT vision API.
    - PDFs: Extracts text using PyPDF2; renders scanned pages as images via PyMuPDF.

Rules:
    - No file content is stored in memory beyond the extraction call.
    - PDF text extraction is best-effort — scanned PDFs yield empty text.
    - Scanned PDFs are rendered to JPEG images for GPT vision fallback.
    - All errors are logged but never crash the caller.
"""

import base64
import io
import logging

logger = logging.getLogger(__name__)


def encode_image_base64(file_bytes: bytes, mime_type: str) -> str:
    """
    Base64-encode image bytes for the OpenAI vision API.

    Returns a data URI string: data:{mime_type};base64,{encoded_data}

    Args:
        file_bytes: Raw image bytes.
        mime_type: MIME type (image/jpeg or image/png).

    Returns:
        Data URI string for use in OpenAI vision API messages.
    """
    encoded = base64.b64encode(file_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def extract_pdf_text(file_bytes: bytes) -> str:
    """
    Extract text content from a PDF file using PyPDF2.

    For text-based PDFs, returns the full text content.
    For scanned PDFs (image-only), returns empty string.

    Args:
        file_bytes: Raw PDF bytes.

    Returns:
        Extracted text from all pages, or empty string if no text found.
    """
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(io.BytesIO(file_bytes))
        text_parts = []

        for page_num, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text.strip())
            except Exception as e:
                logger.warning(
                    "Failed to extract text from PDF page %d: %s",
                    page_num, str(e),
                )

        return "\n\n".join(text_parts)

    except Exception as e:
        logger.error("PDF text extraction failed: %s", str(e))
        return ""


def render_pdf_pages_as_images(file_bytes: bytes, max_pages: int = 3) -> list[str]:
    """
    Render PDF pages as JPEG base64 data URIs for GPT vision API.

    Uses PyMuPDF (fitz) to render each page at 200 DPI.
    This is the fallback for scanned PDFs where text extraction yields nothing.

    Args:
        file_bytes: Raw PDF bytes.
        max_pages: Maximum number of pages to render (default 3).

    Returns:
        List of data URI strings (data:image/jpeg;base64,...), one per page.
        Returns empty list if rendering fails or PyMuPDF is not installed.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error(
            "PyMuPDF (fitz) is not installed — cannot render scanned PDF pages. "
            "Install with: pip install PyMuPDF"
        )
        return []

    data_uris = []
    try:
        pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
        page_count = min(len(pdf_doc), max_pages)

        for page_num in range(page_count):
            try:
                page = pdf_doc[page_num]
                # Render at 200 DPI (default is 72; matrix scales by 200/72).
                zoom = 200 / 72
                matrix = fitz.Matrix(zoom, zoom)
                pixmap = page.get_pixmap(matrix=matrix)
                img_bytes = pixmap.tobytes("jpeg")
                encoded = base64.b64encode(img_bytes).decode("utf-8")
                data_uris.append(f"data:image/jpeg;base64,{encoded}")
            except Exception as e:
                logger.warning(
                    "Failed to render PDF page %d as image: %s",
                    page_num, str(e),
                )

        pdf_doc.close()
    except Exception as e:
        logger.error("PDF page rendering failed: %s", str(e))

    return data_uris
