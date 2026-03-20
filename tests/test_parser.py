from src.services.parser import PDFParser

def test_chunk_text():
    text = "Paragraph 1\n\nParagraph 2\n\nParagraph 3"
    # Small max length forces it to split
    chunks = PDFParser.chunk_text(text, max_chunk_len=10)
    assert len(chunks) == 3
    assert chunks[0] == "Paragraph 1"
