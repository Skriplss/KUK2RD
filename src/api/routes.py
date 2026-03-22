from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from src.utils.logger import get_logger
from src.core.database import get_db, KnowledgeObject
from src.services.parser import DocumentParser
from src.services.interpreter import extract_knowledge_from_chunk

logger = get_logger(__name__)

router = APIRouter()

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Uploads a PDF or DOCX document, extracts text, chunks it,
    runs it through the LLM, and stores KnowledgeObjects into the database.
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
        
        # 3. Segment Text
        chunks = DocumentParser.chunk_text(text)
        logger.info(f"Document segmented into {len(chunks)} chunks.")
        
        extracted_objects_count = 0
        
        # 4 & 5. AI Extraction and DB Save
        for idx, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {idx + 1}/{len(chunks)}...")
            objects_data = await extract_knowledge_from_chunk(chunk)
            
            for obj in objects_data:
                # Provide source context to the metadata dict
                if "metadata" not in obj:
                    obj["metadata"] = {}
                obj["metadata"]["source_file"] = file.filename
                obj["metadata"]["source_chunk_idx"] = idx
                
                # Create Database entity
                db_obj = KnowledgeObject(
                    category=obj.get("category", "Unknown"),
                    data=obj,
                    status="PENDING"
                )
                db.add(db_obj)
                extracted_objects_count += 1
                
        # Commit all to DB
        await db.commit()
        
        return {
            "message": "Document processed successfully",
            "filename": file.filename,
            "chunks_processed": len(chunks),
            "objects_extracted": extracted_objects_count
        }
        
    except Exception as e:
        logger.error(f"Error processing document {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
