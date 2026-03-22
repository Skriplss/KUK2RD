import fitz
import docx
import io
from typing import List
from src.utils.logger import get_logger

logger = get_logger(__name__)

class DocumentParser:
    @staticmethod
    def extract_text_from_pdf(file_bytes: bytes) -> str:
        """Extracts text from a PDF file using PyMuPDF."""
        logger.info("Extracting text from PDF...")
        text = ""
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page in doc:
                text += page.get_text() + "\n\n"
            doc.close()
            return text
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}")
            raise

    @staticmethod
    def extract_text_from_docx(file_bytes: bytes) -> str:
        """Extracts text from a DOCX file using python-docx."""
        logger.info("Extracting text from DOCX...")
        text = ""
        try:
            doc = docx.Document(io.BytesIO(file_bytes))
            for para in doc.paragraphs:
                text += para.text + "\n\n"
            return text
        except Exception as e:
            logger.error(f"Error extracting text from DOCX: {e}")
            raise

    @staticmethod
    def chunk_text(text: str, max_chunk_len: int = 4000) -> List[str]:
        """
        Splits text by double new lines (\n\n) to preserve whole paragraphs.
        Groups paragraphs up to a maximum chunk length for processing.
        """
        paragraphs = text.split('\n\n')
        chunks = []
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
