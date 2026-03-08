"""
PetCircle Phase 1 — File Reader Utility

Reads uploaded file content for GPT extraction:
    - Images (JPEG/PNG): Base64-encodes for GPT vision API.
    - PDFs: Extracts text using PyPDF2.

Rules:
    - No file content is stored in memory beyond the extraction call.
    - PDF text extraction is best-effort — scanned PDFs yield empty text.
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
