from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List, Literal, Annotated

class BaseKnowledgeObject(BaseModel):
    name_en: str = Field(description="English name of the object")
    original_name: str = Field(description="Original name of the object extracted from text")
    description: Optional[str] = Field(default=None, description="Detailed description")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Generic properties as key-value pairs")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata such as source, source_chunk, etc.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence score 0.0-1.0")
    evidence: str = Field(default="", description="Text snippet supporting this extraction")

class RawMaterial(BaseKnowledgeObject):
    category: Literal["RawMaterial"] = "RawMaterial"
    chemical_composition: Optional[str] = Field(default=None, description="Chemical composition if applicable")
    supplier: Optional[str] = Field(default=None, description="Primary supplier or vendor")

class Process(BaseKnowledgeObject):
    category: Literal["Process"] = "Process"
    temperature: Optional[str] = Field(default=None, description="Processing temperature (e.g., '150 C')")
    pressure: Optional[str] = Field(default=None, description="Processing pressure")
    duration: Optional[str] = Field(default=None, description="Duration of the process")

class Manufacturer(BaseKnowledgeObject):
    category: Literal["Manufacturer"] = "Manufacturer"
    country: Optional[str] = Field(default=None, description="Country of origin")
    portfolio: Optional[str] = Field(default=None, description="Overview of the product portfolio")

class Product(BaseKnowledgeObject):
    category: Literal["Product"] = "Product"

class Intermediate(BaseKnowledgeObject):
    category: Literal["Intermediate"] = "Intermediate"

class Equipment(BaseKnowledgeObject):
    category: Literal["Equipment"] = "Equipment"

ObjectTypes = Annotated[
    RawMaterial | Process | Manufacturer | Product | Intermediate | Equipment, 
    Field(discriminator='category')
]

class ExtractionResult(BaseModel):
    items: List[ObjectTypes]
