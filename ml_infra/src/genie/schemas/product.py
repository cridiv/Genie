"""Product schemas."""
from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ProductCategory(str, Enum):
    PHARMACEUTICALS_ANTIMALARIALS = "pharmaceuticals_antimalarials"
    PHARMACEUTICALS_ANTIBIOTICS = "pharmaceuticals_antibiotics"
    PHARMACEUTICALS_GENERAL = "pharmaceuticals_general"
    FMCG_FOOD_BEVERAGES = "fmcg_food_beverages"
    COSMETICS = "cosmetics"


class ProductBase(BaseModel):
    brand_name: str = Field(..., example="Coartem")
    generic_name: Optional[str] = Field(None, example="Artemether / Lumefantrine")
    manufacturer: str = Field(..., example="Novartis Pharma AG")
    category: ProductCategory = Field(default=ProductCategory.PHARMACEUTICALS_ANTIMALARIALS)
    active_ingredients: List[str] = Field(default_factory=list, example=["Artemether", "Lumefantrine"])
    dosage_form: Optional[str] = Field(None, example="Tablet")
    strength: Optional[str] = Field(None, example="80 mg / 480 mg")
    primary_nafdac_number: Optional[str] = Field(None, example="A4-6238")
    gtin_list: List[str] = Field(default_factory=list, example=["06151234567893"])


class ProductCreate(ProductBase):
    status: str = Field(default="staging")


class ProductRead(ProductBase):
    id: UUID
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
