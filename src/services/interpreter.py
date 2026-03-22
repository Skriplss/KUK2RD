from openai import AsyncOpenAI
from typing import List, Dict, Any
from src.core.models import ExtractionResult
from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Initialize AsyncOpenAI client
client = AsyncOpenAI(api_key=settings.openai_api_key)

system_prompt = """
You are a senior technical extractor for the rubber industry.
Your task is to analyze the following text from a technical document (in Slovak or English), 
extract relevant knowledge objects, and output them as structured JSON data matching the required schema.
You must always output data in English. Original names can be kept natively in the 'original_name' field.
Possible categories are: RawMaterial, Process, Manufacturer, Product, Intermediate, Equipment.

Be precise. If a category doesn't fit exactly, ignore the object or try to pick the most suitable.
"""

async def extract_knowledge_from_chunk(chunk_text: str) -> List[Dict[str, Any]]:
    """
    Sends a text chunk to OpenAI GPT-4o with structured output to extract knowledge objects.
    """
    logger.info("Sending text chunk to OpenAI for extraction...")
    try:
        response = await client.beta.chat.completions.parse(
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extract objects from this text:\n\n{chunk_text}"}
            ],
            response_format=ExtractionResult,
            temperature=0.0
        )
        
        parsed_result: ExtractionResult = response.choices[0].message.parsed
        if parsed_result is None:
            return []
            
        return [item.model_dump() for item in parsed_result.items]
        
    except Exception as e:
        logger.error(f"Error during OpenAI extraction: {e}")
        return []
