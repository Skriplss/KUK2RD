import fitz
import docx
import io
import pytesseract
from PIL import Image
from typing import List
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Minimum characters from text extraction to consider the doc non-scanned
_OCR_FALLBACK_THRESHOLD = 50
# Tesseract language: Slovak + English
_TESS_LANG = "slk+eng"


def _auto_rotate(img: Image.Image) -> Image.Image:
    """Detect and correct image rotation using Tesseract OSD."""
    try:
        osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
        angle = osd.get("rotate", 0)
        if angle != 0:
            logger.info(f"Auto-rotating image by {angle} degrees.")
            img = img.rotate(-angle, expand=True)
    except Exception as e:
        logger.warning(f"OSD rotation detection failed, skipping: {e}")
    return img


class DocumentParser:
    @staticmethod
    def extract_text_from_pdf(file_bytes: bytes) -> str:
        logger.info("Extracting text from PDF...")
        text = ""
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page in doc:
                page_text = page.get_text()
                if len(page_text.strip()) < _OCR_FALLBACK_THRESHOLD:
                    # Scanned page — render and OCR
                    pix = page.get_pixmap(dpi=300)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    img = _auto_rotate(img)
                    page_text = pytesseract.image_to_string(img, lang=_TESS_LANG)
                    logger.info(f"PDF page OCR fallback used.")
                text += page_text + "\n\n"
            doc.close()
            return text
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}")
            raise

    @staticmethod
    def extract_text_from_docx(file_bytes: bytes) -> str:
        logger.info("Extracting text from DOCX...")
        try:
            doc = docx.Document(io.BytesIO(file_bytes))

            # Try normal text extraction first
            text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())

            if len(text.strip()) >= _OCR_FALLBACK_THRESHOLD:
                return text

            # Fallback: extract embedded images and OCR them
            logger.info("DOCX has little text — attempting OCR on embedded images...")
            ocr_parts: List[str] = []
            for rel in doc.part.rels.values():
                if "image" in rel.reltype:
                    img_bytes = rel.target_part.blob
                    try:
                        img = Image.open(io.BytesIO(img_bytes))
                        img = _auto_rotate(img)
                        ocr_text = pytesseract.image_to_string(img, lang=_TESS_LANG)
                        if ocr_text.strip():
                            ocr_parts.append(ocr_text.strip())
                    except Exception as img_err:
                        logger.warning(f"Could not OCR image in DOCX: {img_err}")

            if ocr_parts:
                logger.info(f"OCR extracted text from {len(ocr_parts)} images.")
                return "\n\n".join(ocr_parts)

            logger.warning("DOCX: no text and no usable images found.")
            return text

        except Exception as e:
            logger.error(f"Error extracting text from DOCX: {e}")
            raise

    @staticmethod
    def chunk_text(text: str, max_chunk_len: int = 4000) -> List[str]:
        paragraphs = text.split("\n\n")
        chunks: List[str] = []
        current_chunk = ""

        for p in paragraphs:
            p = p.strip()
            if not p:
                continue
            if len(current_chunk) + len(p) > max_chunk_len and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = p + "\n\n"
            else:
                current_chunk += p + "\n\n"

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        logger.info(f"Split text into {len(chunks)} semantic chunks.")
        return chunks
