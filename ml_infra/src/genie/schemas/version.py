"""Product Version schemas for SCD Type 2 packaging lifecycles."""
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PackagingSpec(BaseModel):
    primary_color_hex: Optional[str] = None
    secondary_color_hex: Optional[str] = None
    has_hologram_seal: bool = False
    has_tamper_seal: bool = False
    has_micro_text: bool = False
    distinctive_features: List[str] = Field(default_factory=list)


class ProductVersionBase(BaseModel):
    version_label: str = Field(..., example="2024 Design with Holographic Seal")
    valid_from: date
    valid_to: Optional[date] = None
    status: str = Field(default="active", example="active")  # active, superseded, retired
    packaging_spec: PackagingSpec = Field(default_factory=PackagingSpec)
    batch_number_regex: Optional[str] = Field(None, example="^[A-Z]{2}[0-9]{4}$")
    shelf_life_months: int = Field(default=24, example=24)


class ProductVersionCreate(ProductVersionBase):
    product_id: UUID
    evidence_ids: List[str] = Field(default_factory=list)


class ProductVersionRead(ProductVersionBase):
    id: UUID
    product_id: UUID
    evidence_ids: List[str]
    created_at: datetime

    class Config:
        from_attributes = True
