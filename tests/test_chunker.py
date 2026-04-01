"""
Tests for the improved chunker module.
"""
import pytest
from src.services.chunker import ImprovedChunker


class TestHeaderDetection:
    def test_detect_numbered_headers(self):
        text = """
1. Introduction
Some text here.

1.1 Background
More text.

2. Methods
Even more text.
"""
        headers = ImprovedChunker.detect_headers(text)
        assert len(headers) >= 3
        assert any("Introduction" in h['text'] for h in headers)
        assert any("Background" in h['text'] for h in headers)
    
    def test_detect_caps_headers(self):
        text = """
INTRODUCTION

Some text here.

METHODS AND MATERIALS

More text.
"""
        headers = ImprovedChunker.detect_headers(text)
        assert len(headers) >= 2
        assert any("INTRODUCTION" in h['text'] for h in headers)
    
    def test_detect_keyword_headers(self):
        text = """
Chapter 1: Getting Started

Some text.

Section 2: Advanced Topics

More text.
"""
        headers = ImprovedChunker.detect_headers(text)
        assert len(headers) >= 2


class TestChunkingWithOverlap:
    def test_short_text_single_chunk(self):
        chunker = ImprovedChunker(max_chunk_size=1000, overlap_percentage=0.15)
        text = "This is a short text."
        chunks = chunker.chunk_with_overlap(text)
        
        assert len(chunks) == 1
        assert chunks[0]['text'] == text
        assert chunks[0]['chunk_id'] == 0
        assert not chunks[0]['has_overlap_prev']
        assert not chunks[0]['has_overlap_next']
    
    def test_long_text_multiple_chunks(self):
        chunker = ImprovedChunker(max_chunk_size=100, overlap_percentage=0.2)
        
        # Create text with multiple paragraphs
        paragraphs = [f"Paragraph {i} with some content." for i in range(10)]
        text = "\n\n".join(paragraphs)
        
        chunks = chunker.chunk_with_overlap(text)
        
        assert len(chunks) > 1
        assert chunks[0]['chunk_id'] == 0
        assert not chunks[0]['has_overlap_prev']
        assert chunks[0]['has_overlap_next']
        
        if len(chunks) > 1:
            assert chunks[1]['has_overlap_prev']
    
    def test_overlap_exists(self):
        chunker = ImprovedChunker(max_chunk_size=200, overlap_percentage=0.2)
        
        text = "A" * 150 + "\n\n" + "B" * 150 + "\n\n" + "C" * 150
        chunks = chunker.chunk_with_overlap(text)
        
        if len(chunks) > 1:
            # Check that consecutive chunks have some overlap
            for i in range(len(chunks) - 1):
                chunk1_end = chunks[i]['text'][-50:]
                chunk2_start = chunks[i+1]['text'][:100]
                # There should be some common content
                assert len(chunk1_end) > 0 and len(chunk2_start) > 0
    
    def test_chunk_metadata(self):
        chunker = ImprovedChunker(max_chunk_size=100, overlap_percentage=0.15)
        text = "Para 1\n\nPara 2\n\nPara 3\n\nPara 4\n\nPara 5"
        
        chunks = chunker.chunk_with_overlap(text)
        
        for chunk in chunks:
            assert 'text' in chunk
            assert 'start_pos' in chunk
            assert 'end_pos' in chunk
            assert 'chunk_id' in chunk
            assert 'has_overlap_prev' in chunk
            assert 'has_overlap_next' in chunk
            assert 'headers' in chunk
    
    def test_headers_in_chunks(self):
        chunker = ImprovedChunker(max_chunk_size=200, overlap_percentage=0.15)
        text = """
1. Introduction

Some introductory text here.

2. Methods

Methodology description.

3. Results

Results go here.
"""
        chunks = chunker.chunk_with_overlap(text)
        
        # At least one chunk should contain headers
        has_headers = any(len(chunk['headers']) > 0 for chunk in chunks)
        assert has_headers


class TestPDFChunking:
    def test_pdf_chunking_with_pages(self):
        chunker = ImprovedChunker(max_chunk_size=200, overlap_percentage=0.15)
        
        page_texts = [
            "Page 1 content with some text.",
            "Page 2 content with more text.",
            "Page 3 content with even more text."
        ]
        page_numbers = [1, 2, 3]
        
        chunks = chunker.chunk_pdf_with_pages(page_texts, page_numbers)
        
        assert len(chunks) > 0
        
        # Each chunk should have page information
        for chunk in chunks:
            assert 'pages' in chunk
            assert isinstance(chunk['pages'], list)
            assert len(chunk['pages']) > 0
    
    def test_chunk_spans_multiple_pages(self):
        chunker = ImprovedChunker(max_chunk_size=500, overlap_percentage=0.15)
        
        # Short pages that will be combined into single chunks
        page_texts = [
            "Short page 1.",
            "Short page 2.",
            "Short page 3."
        ]
        page_numbers = [1, 2, 3]
        
        chunks = chunker.chunk_pdf_with_pages(page_texts, page_numbers)
        
        # At least one chunk should span multiple pages
        multi_page_chunks = [c for c in chunks if len(c['pages']) > 1]
        assert len(multi_page_chunks) > 0
