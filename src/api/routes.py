from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.utils.logger import get_logger
from src.core.database import get_db, KnowledgeObject
from src.services.parser import DocumentParser
from src.services.interpreter import extract_knowledge_from_chunk
from src.services.chunker import ImprovedChunker
from src.services.deduplicator import Deduplicator, ExtractionCandidate

logger = get_logger(__name__)

router = APIRouter()

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    TWO-STAGE EXTRACTION PIPELINE:
    1. Extract candidates from each chunk
    2. Normalize, deduplicate, and validate at document level
    3. Save only unique, high-quality objects to DB
    """
    if not (file.filename.endswith(".pdf") or file.filename.endswith(".docx")):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported.")
        
    logger.info(f"Received file for processing: {file.filename}")
    
    try:
        # 1. Read file into memory
        file_bytes = await file.read()
        
        # 2. Parse Document
        if file.filename.endswith(".pdf"):
            text = DocumentParser.extract_text_from_pdf(file_bytes)
        else:
            text = DocumentParser.extract_text_from_docx(file_bytes)
        
        # 3. Improved Chunking with overlap
        chunker = ImprovedChunker(max_chunk_size=4000, overlap_percentage=0.15)
        chunks = chunker.chunk_with_overlap(text)
        logger.info(f"Document segmented into {len(chunks)} overlapping chunks.")
        
        # STAGE 1: Extract candidates from all chunks
        all_candidates = []
        
        for chunk_info in chunks:
            chunk_text = chunk_info['text']
            chunk_id = chunk_info['chunk_id']
            
            logger.info(f"Processing chunk {chunk_id + 1}/{len(chunks)}...")
            objects_data = await extract_knowledge_from_chunk(chunk_text)
            
            for obj in objects_data:
                # Convert to ExtractionCandidate
                candidate = ExtractionCandidate(
                    category=obj.get("category", ""),
                    name_en=obj.get("name_en", ""),
                    original_name=obj.get("original_name", ""),
                    description=obj.get("description"),
                    properties=obj.get("properties", {}),
                    metadata={
                        "source_file": file.filename,
                        "source_chunk_idx": chunk_id,
                        "chunk_start_pos": chunk_info['start_pos'],
                        "chunk_end_pos": chunk_info['end_pos'],
                        "has_overlap": chunk_info['has_overlap_prev'] or chunk_info['has_overlap_next'],
                        "headers": [h['text'] for h in chunk_info.get('headers', [])]
                    },
                    chemical_composition=obj.get("chemical_composition"),
                    supplier=obj.get("supplier"),
                    confidence=obj.get("confidence", 1.0),
                    evidence=obj.get("evidence", "")
                )
                all_candidates.append(candidate)
        
        logger.info(f"STAGE 1 complete: Extracted {len(all_candidates)} candidates")
        
        # STAGE 2: Deduplicate and normalize at document level
        unique_candidates = Deduplicator.deduplicate_batch(all_candidates)
        logger.info(f"STAGE 2 complete: {len(unique_candidates)} unique objects after deduplication")
        
        # 4. Check against existing DB entries (cross-document deduplication)
        saved_count = 0
        skipped_duplicates = 0
        low_confidence_count = 0
        
        for candidate in unique_candidates:
            # Check if already exists in DB
            normalized_key = Deduplicator.normalize_key(candidate.name_en)
            
            existing = await db.execute(
                select(KnowledgeObject).where(
                    KnowledgeObject.category == candidate.category,
                    KnowledgeObject.data["name_en"].as_string() == candidate.name_en
                ).limit(1)
            )
            
            if existing.scalars().first() is not None:
                logger.info(f"Skipping DB duplicate: [{candidate.category}] {candidate.name_en}")
                skipped_duplicates += 1
                continue
            
            # Convert candidate to dict for storage
            obj_data = {
                "category": candidate.category,
                "name_en": candidate.name_en,
                "original_name": candidate.original_name,
                "description": candidate.description,
                "properties": candidate.properties,
                "metadata": candidate.metadata,
                "confidence": candidate.confidence,
                "evidence": candidate.evidence
            }
            
            # Add category-specific fields
            if candidate.chemical_composition:
                obj_data["chemical_composition"] = candidate.chemical_composition
            if candidate.supplier:
                obj_data["supplier"] = candidate.supplier
            
            # Determine initial status based on confidence
            status = "PENDING"
            if candidate.confidence < 0.7:
                status = "LOW_CONFIDENCE"
                low_confidence_count += 1
            
            db_obj = KnowledgeObject(
                category=candidate.category,
                data=obj_data,
                status=status
            )
            db.add(db_obj)
            saved_count += 1
        
        # Commit all to DB
        await db.commit()
        
        return {
            "message": "Document processed successfully with two-stage extraction",
            "filename": file.filename,
            "chunks_processed": len(chunks),
            "candidates_extracted": len(all_candidates),
            "unique_after_dedup": len(unique_candidates),
            "saved_to_db": saved_count,
            "skipped_duplicates": skipped_duplicates,
            "low_confidence_items": low_confidence_count,
            "deduplication_ratio": f"{(1 - len(unique_candidates)/max(len(all_candidates), 1)):.1%}"
        }
        
    except Exception as e:
        logger.error(f"Error processing document {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/rejected")
async def delete_rejected_objects(db: AsyncSession = Depends(get_db)):
    count_result = await db.execute(
        select(func.count()).select_from(KnowledgeObject).where(KnowledgeObject.status == "REJECTED")
    )
    count = count_result.scalar() or 0
    await db.execute(delete(KnowledgeObject).where(KnowledgeObject.status == "REJECTED"))
    await db.commit()
    return {"deleted": count}

@router.get("/objects")
async def get_objects(
    category: str = None,
    status: str = None,
    min_confidence: float = 0.0,
    max_confidence: float = 1.0,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """
    Get knowledge objects with filtering and pagination.
    Useful for curator UI to review low-confidence items.
    """
    query = select(KnowledgeObject)
    
    # Apply filters
    if category:
        query = query.where(KnowledgeObject.category == category)
    
    if status:
        query = query.where(KnowledgeObject.status == status)
    
    # Filter by confidence (stored in data JSON field)
    if min_confidence > 0.0 or max_confidence < 1.0:
        query = query.where(
            KnowledgeObject.data["confidence"].as_float() >= min_confidence,
            KnowledgeObject.data["confidence"].as_float() <= max_confidence
        )
    
    # Order by confidence (lowest first for review)
    query = query.order_by(KnowledgeObject.data["confidence"].as_float())
    
    # Pagination
    query = query.limit(limit).offset(offset)
    
    result = await db.execute(query)
    objects = result.scalars().all()
    
    # Get total count
    count_query = select(func.count()).select_from(KnowledgeObject)
    if category:
        count_query = count_query.where(KnowledgeObject.category == category)
    if status:
        count_query = count_query.where(KnowledgeObject.status == status)
    
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0
    
    return {
        "objects": [
            {
                "id": obj.id,
                "category": obj.category,
                "status": obj.status,
                "data": obj.data
            }
            for obj in objects
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }

@router.patch("/objects/{object_id}/status")
async def update_object_status(
    object_id: int,
    status: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Update status of a knowledge object (for curator workflow).
    Valid statuses: PENDING, APPROVED, REJECTED, LOW_CONFIDENCE
    """
    valid_statuses = ["PENDING", "APPROVED", "REJECTED", "LOW_CONFIDENCE"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")
    
    result = await db.execute(
        select(KnowledgeObject).where(KnowledgeObject.id == object_id)
    )
    obj = result.scalars().first()
    
    if not obj:
        raise HTTPException(status_code=404, detail="Object not found")
    
    obj.status = status
    await db.commit()
    
    return {"id": object_id, "status": status}

@router.post("/preview")
async def preview_document(file: UploadFile = File(...)):
    if not (file.filename.endswith(".pdf") or file.filename.endswith(".docx")):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported.")

    logger.info(f"Preview request for: {file.filename}")
    try:
        file_bytes = await file.read()
        if file.filename.endswith(".pdf"):
            text = DocumentParser.extract_text_from_pdf(file_bytes)
        else:
            text = DocumentParser.extract_text_from_docx(file_bytes)

        # Use improved chunker
        chunker = ImprovedChunker(max_chunk_size=4000, overlap_percentage=0.15)
        chunks = chunker.chunk_with_overlap(text)
        
        return {
            "filename": file.filename,
            "chunks_count": len(chunks),
            "chunks": [
                {
                    "chunk_id": c['chunk_id'],
                    "text": c['text'][:500] + "..." if len(c['text']) > 500 else c['text'],
                    "full_length": len(c['text']),
                    "has_overlap_prev": c['has_overlap_prev'],
                    "has_overlap_next": c['has_overlap_next'],
                    "headers": [h['text'] for h in c.get('headers', [])]
                }
                for c in chunks
            ],
        }
    except Exception as e:
        logger.error(f"Error previewing document {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
