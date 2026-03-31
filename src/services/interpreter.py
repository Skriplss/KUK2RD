from groq import AsyncGroq
from typing import List, Dict, Any
from src.core.models import ExtractionResult
from src.core.config import settings
from src.utils.logger import get_logger
import json

logger = get_logger(__name__)

# Initialize Groq async client
if settings.groq_api_key:
    masked_key = f"{settings.groq_api_key[:8]}...{settings.groq_api_key[-4:]}"
    logger.info(f"Groq Client initialized with key: {masked_key} (Length: {len(settings.groq_api_key)})")
else:
    logger.warning("Groq Client initialized WITHOUT an API key!")

client = AsyncGroq(api_key=settings.groq_api_key)

MODEL = "llama-3.3-70b-versatile"

system_prompt = """
You are a senior technical extractor for the rubber industry.
Your task is to analyze the following text from a technical document (in Slovak or English), 
extract relevant knowledge objects, and output them as structured JSON data matching the required schema.
You must always output data in English. Original names can be kept natively in the 'original_name' field.
Possible categories are: RawMaterial, Process, Manufacturer, Product, Intermediate, Equipment.

Be precise. If a category doesn't fit exactly, ignore the object or try to pick the most suitable.

IMPORTANT: You MUST respond with a valid JSON object in this exact format:
{
  "items": [
    {
      "category": "RawMaterial",
      "name_en": "...",
      "original_name": "...",
      "description": "...",
      "properties": {},
      "metadata": {},
      "chemical_composition": "...",
      "supplier": "...",
      "confidence": 0.95,
      "evidence": "exact text snippet from source that supports this extraction"
    }
  ]
}

CONFIDENCE SCORING:
- confidence: float 0.0-1.0 indicating extraction certainty
  * 0.9-1.0: Explicit mention with clear context (e.g., "Zinc oxide (ZnO) is used as...")
  * 0.7-0.9: Strong inference from context (e.g., "ZnO improves..." without full name)
  * 0.5-0.7: Weak inference or ambiguous mention
  * 0.0-0.5: Very uncertain, possibly incorrect

- evidence: Copy the exact text snippet (max 200 chars) that supports this extraction.
  This will be used for human review of low-confidence items.

Only include fields relevant to the category. The 'items' array may be empty if no objects are found.
"""

async def extract_knowledge_from_chunk(chunk_text: str) -> List[Dict[str, Any]]:
    logger.info(f"Sending text chunk to Groq ({MODEL}) for extraction...")
    logger.debug(f"Chunk preview (first 500 chars):\n{chunk_text[:500]}")
    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extract objects from this text:\n\n{chunk_text}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )

        content = response.choices[0].message.content
        if not content:
            logger.warning("Groq returned empty content.")
            return []

        # Parse the raw JSON using our Pydantic model for validation
        raw_data = json.loads(content)
        parsed_result = ExtractionResult.model_validate(raw_data)
        
        logger.info(f"Groq extracted {len(parsed_result.items)} objects.")
        return [item.model_dump() for item in parsed_result.items]

    except json.JSONDecodeError as e:
        logger.error(f"Groq returned invalid JSON: {e}")
        return []
    except Exception as e:
        logger.error(f"Error during Groq extraction: {e}")
        return []
