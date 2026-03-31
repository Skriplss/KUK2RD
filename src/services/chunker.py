"""
Improved chunking with overlap and section awareness.
"""
from typing import List, Dict, Any
import re
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ImprovedChunker:
    """
    Advanced text chunking with overlap and structure awareness.
    """
    
    def __init__(
        self, 
        max_chunk_size: int = 4000,
        overlap_percentage: float = 0.15,
        min_chunk_size: int = 500
    ):
        self.max_chunk_size = max_chunk_size
        self.overlap_size = int(max_chunk_size * overlap_percentage)
        self.min_chunk_size = min_chunk_size
    
    @staticmethod
    def detect_headers(text: str) -> List[Dict[str, Any]]:
        """
        Detect section headers in text.
        Returns list of {position, text, level} dicts.
        """
        headers = []
        
        # Pattern 1: Numbered sections (1., 1.1, etc.)
        numbered_pattern = r'^(\d+\.(?:\d+\.)*)\s+(.+)$'
        
        # Pattern 2: ALL CAPS headers
        caps_pattern = r'^([A-Z\s]{3,})$'
        
        # Pattern 3: Common header keywords
        keyword_pattern = r'^(Chapter|Section|Part|Appendix|Introduction|Conclusion)\s+(.+)$'
        
        lines = text.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Check numbered sections
            match = re.match(numbered_pattern, line)
            if match:
                level = match.group(1).count('.')
                headers.append({
                    'position': text.find(line),
                    'text': line,
                    'level': level,
                    'line_num': i
                })
                continue
            
            # Check ALL CAPS (but not too long)
            if re.match(caps_pattern, line) and len(line) < 100:
                headers.append({
                    'position': text.find(line),
                    'text': line,
                    'level': 1,
                    'line_num': i
                })
                continue
            
            # Check keyword headers
            if re.match(keyword_pattern, line, re.IGNORECASE):
                headers.append({
                    'position': text.find(line),
                    'text': line,
                    'level': 1,
                    'line_num': i
                })
        
        return headers
    
    def chunk_with_overlap(self, text: str) -> List[Dict[str, Any]]:
        """
        Split text into overlapping chunks with metadata.
        
        Returns list of dicts with:
        - text: chunk content
        - start_pos: character position in original text
        - end_pos: character position in original text
        - chunk_id: sequential ID
        - has_overlap_prev: whether this chunk overlaps with previous
        - has_overlap_next: whether this chunk overlaps with next
        - headers: list of headers found in this chunk
        """
        if not text or len(text) < self.min_chunk_size:
            return [{
                'text': text,
                'start_pos': 0,
                'end_pos': len(text),
                'chunk_id': 0,
                'has_overlap_prev': False,
                'has_overlap_next': False,
                'headers': self.detect_headers(text)
            }]
        
        # Detect all headers first
        all_headers = self.detect_headers(text)
        logger.info(f"Detected {len(all_headers)} headers in document")
        
        # Split into paragraphs
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        
        chunks = []
        current_chunk = ""
        current_start = 0
        chunk_id = 0
        
        i = 0
        while i < len(paragraphs):
            para = paragraphs[i]
            
            # Check if adding this paragraph exceeds max size
            if len(current_chunk) + len(para) > self.max_chunk_size and current_chunk:
                # Save current chunk
                chunk_end = current_start + len(current_chunk)
                chunk_headers = [h for h in all_headers 
                               if current_start <= h['position'] < chunk_end]
                
                chunks.append({
                    'text': current_chunk.strip(),
                    'start_pos': current_start,
                    'end_pos': chunk_end,
                    'chunk_id': chunk_id,
                    'has_overlap_prev': chunk_id > 0,
                    'has_overlap_next': True,
                    'headers': chunk_headers
                })
                
                # Create overlap: take last N characters
                overlap_text = current_chunk[-self.overlap_size:] if len(current_chunk) > self.overlap_size else current_chunk
                
                # Find paragraph boundary for overlap
                overlap_para_start = overlap_text.rfind('\n\n')
                if overlap_para_start > 0:
                    overlap_text = overlap_text[overlap_para_start:].strip()
                
                current_chunk = overlap_text + "\n\n" + para
                current_start = chunk_end - len(overlap_text)
                chunk_id += 1
                i += 1
            else:
                # Add paragraph to current chunk
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
                    current_start = text.find(para)
                i += 1
        
        # Add final chunk
        if current_chunk.strip():
            chunk_end = current_start + len(current_chunk)
            chunk_headers = [h for h in all_headers 
                           if current_start <= h['position'] < chunk_end]
            
            chunks.append({
                'text': current_chunk.strip(),
                'start_pos': current_start,
                'end_pos': chunk_end,
                'chunk_id': chunk_id,
                'has_overlap_prev': chunk_id > 0,
                'has_overlap_next': False,
                'headers': chunk_headers
            })
        
        logger.info(f"Created {len(chunks)} overlapping chunks (overlap: {self.overlap_size} chars)")
        
        return chunks
    
    def chunk_pdf_with_pages(
        self, 
        page_texts: List[str], 
        page_numbers: List[int]
    ) -> List[Dict[str, Any]]:
        """
        Chunk PDF text while preserving page boundaries.
        
        Args:
            page_texts: List of text content per page
            page_numbers: List of page numbers (1-indexed)
        
        Returns:
            List of chunk dicts with additional 'pages' field
        """
        # Combine all text with page markers
        combined_text = ""
        page_markers = []
        
        for page_num, page_text in zip(page_numbers, page_texts):
            marker_pos = len(combined_text)
            page_markers.append({
                'page_num': page_num,
                'start_pos': marker_pos,
                'end_pos': marker_pos + len(page_text)
            })
            combined_text += page_text + "\n\n"
        
        # Create overlapping chunks
        chunks = self.chunk_with_overlap(combined_text)
        
        # Add page information to each chunk
        for chunk in chunks:
            chunk_start = chunk['start_pos']
            chunk_end = chunk['end_pos']
            
            # Find which pages this chunk spans
            chunk_pages = []
            for marker in page_markers:
                # Check if chunk overlaps with this page
                if not (chunk_end <= marker['start_pos'] or chunk_start >= marker['end_pos']):
                    chunk_pages.append(marker['page_num'])
            
            chunk['pages'] = chunk_pages
        
        logger.info(f"Created {len(chunks)} chunks from {len(page_texts)} pages")
        
        return chunks
