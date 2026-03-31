"""
Two-stage extraction pipeline: candidate extraction + normalization/deduplication.
"""
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import re
from rapidfuzz import fuzz
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ExtractionCandidate:
    """Raw candidate extracted from a chunk before normalization."""
    category: str
    name_en: str
    original_name: str
    description: Optional[str] = None
    properties: Dict[str, Any] = None
    metadata: Dict[str, Any] = None
    chemical_composition: Optional[str] = None
    supplier: Optional[str] = None
    confidence: float = 1.0
    evidence: str = ""  # Text snippet that supports this extraction
    
    def __post_init__(self):
        if self.properties is None:
            self.properties = {}
        if self.metadata is None:
            self.metadata = {}


class Deduplicator:
    """
    Handles normalization, deduplication, and merging of extraction candidates.
    """
    
    # Fuzzy match threshold (0-100)
    FUZZY_THRESHOLD = 85
    
    @staticmethod
    def normalize_key(text: str) -> str:
        """
        Create normalized key for comparison:
        - lowercase
        - trim whitespace
        - remove punctuation
        - collapse multiple spaces
        """
        if not text:
            return ""
        
        # Lowercase and strip
        normalized = text.lower().strip()
        
        # Remove punctuation except hyphens (important for chemical names)
        normalized = re.sub(r'[^\w\s\-]', '', normalized)
        
        # Collapse multiple spaces
        normalized = re.sub(r'\s+', ' ', normalized)
        
        return normalized
    
    @staticmethod
    def fuzzy_match_score(text1: str, text2: str) -> float:
        """
        Calculate fuzzy match score between two strings using token_sort_ratio.
        Returns score 0-100.
        """
        if not text1 or not text2:
            return 0.0
        
        # Use token_sort_ratio to handle word order differences
        return fuzz.token_sort_ratio(text1, text2)
    
    @classmethod
    def are_duplicates(cls, candidate1: ExtractionCandidate, candidate2: ExtractionCandidate) -> bool:
        """
        Determine if two candidates represent the same entity using multiple strategies.
        """
        # Must be same category
        if candidate1.category != candidate2.category:
            return False
        
        # Strategy 1: Exact normalized key match
        key1 = cls.normalize_key(candidate1.name_en)
        key2 = cls.normalize_key(candidate2.name_en)
        
        if key1 == key2 and key1:
            logger.debug(f"Exact match: {candidate1.name_en} == {candidate2.name_en}")
            return True
        
        # Strategy 2: Fuzzy match on name_en
        fuzzy_score = cls.fuzzy_match_score(candidate1.name_en, candidate2.name_en)
        if fuzzy_score >= cls.FUZZY_THRESHOLD:
            logger.debug(f"Fuzzy match ({fuzzy_score}): {candidate1.name_en} ~= {candidate2.name_en}")
            return True
        
        # Strategy 3: Check original_name similarity
        if candidate1.original_name and candidate2.original_name:
            orig_key1 = cls.normalize_key(candidate1.original_name)
            orig_key2 = cls.normalize_key(candidate2.original_name)
            
            if orig_key1 == orig_key2 and orig_key1:
                logger.debug(f"Original name match: {candidate1.original_name} == {candidate2.original_name}")
                return True
            
            orig_fuzzy = cls.fuzzy_match_score(candidate1.original_name, candidate2.original_name)
            if orig_fuzzy >= cls.FUZZY_THRESHOLD:
                logger.debug(f"Original fuzzy match ({orig_fuzzy}): {candidate1.original_name} ~= {candidate2.original_name}")
                return True
        
        # Strategy 4: Rule-based merge for RawMaterial
        if candidate1.category == "RawMaterial":
            # Check chemical composition + supplier combination
            if (candidate1.chemical_composition and candidate2.chemical_composition and
                candidate1.supplier and candidate2.supplier):
                
                comp_match = cls.fuzzy_match_score(
                    candidate1.chemical_composition, 
                    candidate2.chemical_composition
                ) >= 80
                
                supplier_match = cls.fuzzy_match_score(
                    candidate1.supplier,
                    candidate2.supplier
                ) >= 80
                
                if comp_match and supplier_match:
                    logger.debug(f"RawMaterial rule match: composition + supplier")
                    return True
        
        return False
    
    @classmethod
    def merge_candidates(cls, candidates: List[ExtractionCandidate]) -> ExtractionCandidate:
        """
        Merge multiple duplicate candidates into a single consolidated candidate.
        Keeps the highest confidence version and merges metadata.
        """
        if not candidates:
            raise ValueError("Cannot merge empty candidate list")
        
        if len(candidates) == 1:
            return candidates[0]
        
        # Sort by confidence (highest first)
        sorted_candidates = sorted(candidates, key=lambda c: c.confidence, reverse=True)
        primary = sorted_candidates[0]
        
        # Merge metadata from all candidates
        merged_metadata = primary.metadata.copy()
        all_sources = []
        all_evidence = []
        
        for candidate in sorted_candidates:
            # Collect all source files
            if "source_file" in candidate.metadata:
                all_sources.append(candidate.metadata["source_file"])
            
            # Collect evidence
            if candidate.evidence:
                all_evidence.append(candidate.evidence)
            
            # Merge properties (keep non-empty values)
            for key, value in candidate.properties.items():
                if value and key not in primary.properties:
                    primary.properties[key] = value
        
        # Update merged metadata
        if all_sources:
            merged_metadata["all_sources"] = list(set(all_sources))
            merged_metadata["occurrence_count"] = len(all_sources)
        
        if all_evidence:
            merged_metadata["all_evidence"] = all_evidence
        
        primary.metadata = merged_metadata
        primary.evidence = " | ".join(all_evidence[:3])  # Keep first 3 evidence snippets
        
        logger.info(f"Merged {len(candidates)} candidates into: {primary.name_en}")
        
        return primary
    
    @classmethod
    def deduplicate_batch(cls, candidates: List[ExtractionCandidate]) -> List[ExtractionCandidate]:
        """
        Deduplicate a batch of candidates using clustering approach.
        Returns list of unique, merged candidates.
        """
        if not candidates:
            return []
        
        logger.info(f"Deduplicating batch of {len(candidates)} candidates...")
        
        # Group candidates into clusters of duplicates
        clusters: List[List[ExtractionCandidate]] = []
        processed = set()
        
        for i, candidate in enumerate(candidates):
            if i in processed:
                continue
            
            # Start new cluster
            cluster = [candidate]
            processed.add(i)
            
            # Find all duplicates
            for j, other in enumerate(candidates[i+1:], start=i+1):
                if j in processed:
                    continue
                
                if cls.are_duplicates(candidate, other):
                    cluster.append(other)
                    processed.add(j)
            
            clusters.append(cluster)
        
        # Merge each cluster
        deduplicated = [cls.merge_candidates(cluster) for cluster in clusters]
        
        logger.info(f"Deduplication complete: {len(candidates)} -> {len(deduplicated)} unique objects")
        
        return deduplicated
