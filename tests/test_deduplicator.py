"""
Tests for the deduplication module.
"""
import pytest
from src.services.deduplicator import Deduplicator, ExtractionCandidate


class TestNormalization:
    def test_normalize_key_basic(self):
        assert Deduplicator.normalize_key("Zinc Oxide") == "zinc oxide"
        assert Deduplicator.normalize_key("  ZINC  OXIDE  ") == "zinc oxide"
    
    def test_normalize_key_punctuation(self):
        assert Deduplicator.normalize_key("Zinc-Oxide") == "zinc-oxide"
        assert Deduplicator.normalize_key("Zinc, Oxide!") == "zinc oxide"
    
    def test_normalize_key_empty(self):
        assert Deduplicator.normalize_key("") == ""
        assert Deduplicator.normalize_key(None) == ""


class TestFuzzyMatching:
    def test_exact_match(self):
        score = Deduplicator.fuzzy_match_score("Zinc Oxide", "Zinc Oxide")
        assert score == 100.0
    
    def test_case_insensitive(self):
        score = Deduplicator.fuzzy_match_score("Zinc Oxide", "zinc oxide")
        assert score == 100.0
    
    def test_word_order(self):
        score = Deduplicator.fuzzy_match_score("Oxide Zinc", "Zinc Oxide")
        assert score == 100.0  # token_sort_ratio handles word order
    
    def test_typo_tolerance(self):
        score = Deduplicator.fuzzy_match_score("Zinc Oxyde", "Zinc Oxide")
        assert score > 80.0  # Should be high similarity
    
    def test_different_strings(self):
        score = Deduplicator.fuzzy_match_score("Zinc Oxide", "Carbon Black")
        assert score < 50.0


class TestDuplicateDetection:
    def test_exact_duplicate(self):
        c1 = ExtractionCandidate(
            category="RawMaterial",
            name_en="Zinc Oxide",
            original_name="Zinc Oxide"
        )
        c2 = ExtractionCandidate(
            category="RawMaterial",
            name_en="Zinc Oxide",
            original_name="Zinc Oxide"
        )
        assert Deduplicator.are_duplicates(c1, c2)
    
    def test_case_variation(self):
        c1 = ExtractionCandidate(
            category="RawMaterial",
            name_en="Zinc Oxide",
            original_name="Zinc Oxide"
        )
        c2 = ExtractionCandidate(
            category="RawMaterial",
            name_en="zinc oxide",
            original_name="zinc oxide"
        )
        assert Deduplicator.are_duplicates(c1, c2)
    
    def test_fuzzy_duplicate(self):
        c1 = ExtractionCandidate(
            category="RawMaterial",
            name_en="Zinc Oxide",
            original_name="Zinc Oxide"
        )
        c2 = ExtractionCandidate(
            category="RawMaterial",
            name_en="Zinc Oxyde",  # Typo
            original_name="Zinc Oxyde"
        )
        assert Deduplicator.are_duplicates(c1, c2)
    
    def test_different_category_not_duplicate(self):
        c1 = ExtractionCandidate(
            category="RawMaterial",
            name_en="Zinc Oxide",
            original_name="Zinc Oxide"
        )
        c2 = ExtractionCandidate(
            category="Product",
            name_en="Zinc Oxide",
            original_name="Zinc Oxide"
        )
        assert not Deduplicator.are_duplicates(c1, c2)
    
    def test_original_name_match(self):
        c1 = ExtractionCandidate(
            category="RawMaterial",
            name_en="Zinc Oxide",
            original_name="Oxid zinočnatý"
        )
        c2 = ExtractionCandidate(
            category="RawMaterial",
            name_en="ZnO",
            original_name="Oxid zinočnatý"
        )
        assert Deduplicator.are_duplicates(c1, c2)
    
    def test_chemical_composition_supplier_match(self):
        c1 = ExtractionCandidate(
            category="RawMaterial",
            name_en="White Powder A",
            original_name="White Powder A",
            chemical_composition="ZnO 99%",
            supplier="Acme Corp"
        )
        c2 = ExtractionCandidate(
            category="RawMaterial",
            name_en="White Powder B",
            original_name="White Powder B",
            chemical_composition="ZnO 99%",
            supplier="Acme Corporation"
        )
        assert Deduplicator.are_duplicates(c1, c2)


class TestCandidateMerging:
    def test_merge_single_candidate(self):
        c1 = ExtractionCandidate(
            category="RawMaterial",
            name_en="Zinc Oxide",
            original_name="Zinc Oxide",
            confidence=0.9
        )
        merged = Deduplicator.merge_candidates([c1])
        assert merged.name_en == "Zinc Oxide"
        assert merged.confidence == 0.9
    
    def test_merge_keeps_highest_confidence(self):
        c1 = ExtractionCandidate(
            category="RawMaterial",
            name_en="Zinc Oxide",
            original_name="Zinc Oxide",
            confidence=0.7,
            metadata={"source_file": "doc1.pdf"}
        )
        c2 = ExtractionCandidate(
            category="RawMaterial",
            name_en="Zinc Oxide",
            original_name="ZnO",
            confidence=0.95,
            metadata={"source_file": "doc2.pdf"}
        )
        merged = Deduplicator.merge_candidates([c1, c2])
        assert merged.confidence == 0.95
        assert merged.name_en == "Zinc Oxide"
    
    def test_merge_combines_metadata(self):
        c1 = ExtractionCandidate(
            category="RawMaterial",
            name_en="Zinc Oxide",
            original_name="Zinc Oxide",
            metadata={"source_file": "doc1.pdf"},
            evidence="Found in section 1"
        )
        c2 = ExtractionCandidate(
            category="RawMaterial",
            name_en="Zinc Oxide",
            original_name="ZnO",
            metadata={"source_file": "doc2.pdf"},
            evidence="Found in section 2"
        )
        merged = Deduplicator.merge_candidates([c1, c2])
        assert "all_sources" in merged.metadata
        assert len(merged.metadata["all_sources"]) == 2
        assert merged.metadata["occurrence_count"] == 2


class TestBatchDeduplication:
    def test_empty_batch(self):
        result = Deduplicator.deduplicate_batch([])
        assert result == []
    
    def test_no_duplicates(self):
        candidates = [
            ExtractionCandidate(category="RawMaterial", name_en="Zinc Oxide", original_name="ZnO"),
            ExtractionCandidate(category="RawMaterial", name_en="Carbon Black", original_name="CB"),
            ExtractionCandidate(category="Process", name_en="Vulcanization", original_name="Vulcanization")
        ]
        result = Deduplicator.deduplicate_batch(candidates)
        assert len(result) == 3
    
    def test_simple_duplicates(self):
        candidates = [
            ExtractionCandidate(category="RawMaterial", name_en="Zinc Oxide", original_name="ZnO"),
            ExtractionCandidate(category="RawMaterial", name_en="Zinc Oxide", original_name="Zinc Oxide"),
            ExtractionCandidate(category="RawMaterial", name_en="Carbon Black", original_name="CB")
        ]
        result = Deduplicator.deduplicate_batch(candidates)
        assert len(result) == 2
    
    def test_multiple_duplicate_groups(self):
        candidates = [
            ExtractionCandidate(category="RawMaterial", name_en="Zinc Oxide", original_name="ZnO"),
            ExtractionCandidate(category="RawMaterial", name_en="Zinc Oxide", original_name="Zinc Oxide"),
            ExtractionCandidate(category="RawMaterial", name_en="Carbon Black", original_name="CB"),
            ExtractionCandidate(category="RawMaterial", name_en="Carbon Black", original_name="Carbon Black"),
            ExtractionCandidate(category="Process", name_en="Vulcanization", original_name="Vulcanization")
        ]
        result = Deduplicator.deduplicate_batch(candidates)
        assert len(result) == 3  # 3 unique entities
