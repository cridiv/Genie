"""SQLAlchemy 2.0 ORM models for Genie Product Intelligence."""
import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    brand_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    generic_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    manufacturer: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(100), default="pharmaceuticals_antimalarials")
    active_ingredients: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    dosage_form: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    strength: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    primary_nafdac_number: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    gtin_list: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(50), default="staging")  # staging, approved, recalled
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    versions: Mapped[List["ProductVersion"]] = relationship("ProductVersion", back_populates="product", cascade="all, delete-orphan")


class ProductVersion(Base):
    __tablename__ = "product_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    version_label: Mapped[str] = mapped_column(String(255), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active")  # active, superseded, retired
    packaging_spec: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    batch_number_regex: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    shelf_life_months: Mapped[int] = mapped_column(Integer, default=24)
    evidence_ids: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    product: Mapped["Product"] = relationship("Product", back_populates="versions")
    reference_images: Mapped[List["ReferenceImage"]] = relationship("ReferenceImage", back_populates="version", cascade="all, delete-orphan")


class ReferenceImage(Base):
    __tablename__ = "reference_images"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    product_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product_versions.id"), nullable=False, index=True)
    face_type: Mapped[str] = mapped_column(String(50), nullable=False)  # front, back, blister, side
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    dhash_64bit: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    semantic_regions: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    quality_grade: Mapped[str] = mapped_column(String(10), default="A")
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    trust_tier: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    version: Mapped["ProductVersion"] = relationship("ProductVersion", back_populates="reference_images")


class EvidenceClaimRecord(Base):
    __tablename__ = "evidence_claims"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("products.id"), nullable=True)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    verbatim_quote: Mapped[str] = mapped_column(Text, nullable=False)
    verified_in_source: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ScanRecord(Base):
    __tablename__ = "scan_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scan_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user_session_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    image_storage_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    decoded_barcode: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ocr_extracted_fields: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    matched_product_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("products.id"), nullable=True)
    matched_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("product_versions.id"), nullable=True)
    signal_scores: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    final_verdict: Mapped[str] = mapped_column(String(50), nullable=False)
    calibrated_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    model_git_commit: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    execution_time_ms: Mapped[float] = mapped_column(Float, default=0.0)


class Pharmacy(Base):
    __tablename__ = "pharmacies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    license_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PharmacyInventory(Base):
    __tablename__ = "pharmacy_inventory"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pharmacies.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), nullable=False)
    availability_status: Mapped[str] = mapped_column(String(50), default="unconfirmed")  # confirmed, unconfirmed, out_of_stock
    last_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
