# """
# Catalog schemas.

# WHY ProductOut (list) AND ProductDetailOut (single) ARE DIFFERENT:
# The product listing page shows a grid of 20-40 cards — sending full
# variant/image arrays for every card would bloat the response for data
# the grid doesn't render (grid shows one thumbnail + price, not every
# size/color combo). The detail page needs everything. Two schemas let
# each endpoint return exactly what its screen needs — a common production
# pattern once list payloads start mattering for load time.
# """
# import re
# import uuid
# from datetime import datetime
# from decimal import Decimal

# from pydantic import BaseModel, ConfigDict, Field, field_validator

# from app.models.catalog import ProductStatus


# def slugify(value: str) -> str:
#     value = value.strip().lower()
#     value = re.sub(r"[^a-z0-9]+", "-", value)
#     return value.strip("-")


# # --- Category ---
# class CategoryCreate(BaseModel):
#     name: str = Field(min_length=2, max_length=100)
#     parent_id: uuid.UUID | None = None


# class CategoryOut(BaseModel):
#     model_config = ConfigDict(from_attributes=True)
#     id: uuid.UUID
#     name: str
#     slug: str
#     parent_id: uuid.UUID | None


# # --- Brand ---
# class BrandCreate(BaseModel):
#     name: str = Field(min_length=2, max_length=100)
#     logo_url: str | None = None


# class BrandOut(BaseModel):
#     model_config = ConfigDict(from_attributes=True)
#     id: uuid.UUID
#     name: str
#     slug: str
#     logo_url: str | None


# # --- Variant ---
# class ProductVariantCreate(BaseModel):
#     sku: str = Field(min_length=1, max_length=64)
#     size: str | None = Field(default=None, max_length=20)
#     color: str | None = Field(default=None, max_length=40)
#     stock_quantity: int = Field(ge=0, default=0)
#     price_override: Decimal | None = Field(default=None, gt=0)


# class ProductVariantOut(BaseModel):
#     model_config = ConfigDict(from_attributes=True)
#     id: uuid.UUID
#     sku: str
#     size: str | None
#     color: str | None
#     stock_quantity: int
#     price_override: Decimal | None


# # --- Image ---
# class ProductImageOut(BaseModel):
#     model_config = ConfigDict(from_attributes=True)
#     id: uuid.UUID
#     image_url: str
#     is_primary: bool
#     display_order: int
#     variant_id: uuid.UUID | None


# # --- Product ---
# class ProductCreate(BaseModel):
#     name: str = Field(min_length=2, max_length=200)
#     description: str = Field(default="", max_length=10000)
#     category_id: uuid.UUID
#     brand_id: uuid.UUID
#     base_price: Decimal = Field(gt=0)
#     discount_percentage: Decimal = Field(default=Decimal("0"), ge=0, le=100)
#     gst_percentage: Decimal = Field(default=Decimal("0"), ge=0, le=100)
#     status: ProductStatus = ProductStatus.DRAFT
#     is_featured: bool = False
#     is_trending: bool = False
#     variants: list[ProductVariantCreate] = Field(min_length=1)

#     @field_validator("variants")
#     @classmethod
#     def skus_must_be_unique_within_product(cls, v: list[ProductVariantCreate]):
#         skus = [variant.sku for variant in v]
#         if len(skus) != len(set(skus)):
#             raise ValueError("Duplicate SKU within the same product submission")
#         return v


# class ProductUpdate(BaseModel):
#     # All optional — PATCH-style partial update. Variants/images are
#     # managed through their own endpoints, not bulk-replaced here, since
#     # blindly overwriting the variant list risks deleting variants that
#     # already have order history attached to them (Phase 3+ concern).
#     name: str | None = Field(default=None, min_length=2, max_length=200)
#     description: str | None = Field(default=None, max_length=10000)
#     category_id: uuid.UUID | None = None
#     brand_id: uuid.UUID | None = None
#     base_price: Decimal | None = Field(default=None, gt=0)
#     discount_percentage: Decimal | None = Field(default=None, ge=0, le=100)
#     gst_percentage: Decimal | None = Field(default=None, ge=0, le=100)
#     status: ProductStatus | None = None
#     is_featured: bool | None = None
#     is_trending: bool | None = None


# class ProductOut(BaseModel):
#     """Lightweight — used in list/grid responses."""

#     model_config = ConfigDict(from_attributes=True)
#     id: uuid.UUID
#     name: str
#     slug: str
#     base_price: Decimal
#     discount_percentage: Decimal
#     status: ProductStatus
#     is_featured: bool
#     is_trending: bool
#     category: CategoryOut
#     brand: BrandOut
#     primary_image_url: str | None = None


# class ProductDetailOut(BaseModel):
#     """Full detail — used on the PDP (product detail page)."""

#     model_config = ConfigDict(from_attributes=True)
#     id: uuid.UUID
#     name: str
#     slug: str
#     description: str
#     base_price: Decimal
#     discount_percentage: Decimal
#     gst_percentage: Decimal
#     status: ProductStatus
#     is_featured: bool
#     is_trending: bool
#     created_at: datetime
#     category: CategoryOut
#     brand: BrandOut
#     variants: list[ProductVariantOut]
#     images: list[ProductImageOut]


# class PaginatedProducts(BaseModel):
#     items: list[ProductOut]
#     total: int
#     page: int
#     page_size: int
#     total_pages: int




"""
Catalog schemas.

WHY ProductOut (list) AND ProductDetailOut (single) ARE DIFFERENT:
The product listing page shows a grid of 20-40 cards — sending full
variant/image arrays for every card would bloat the response for data
the grid doesn't render (grid shows one thumbnail + price, not every
size/color combo). The detail page needs everything. Two schemas let
each endpoint return exactly what its screen needs — a common production
pattern once list payloads start mattering for load time.
"""
import re
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.catalog import ProductStatus


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


# --- Category ---
class CategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    parent_id: uuid.UUID | None = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    slug: str
    parent_id: uuid.UUID | None


# --- Brand ---
class BrandCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    logo_url: str | None = None


class BrandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    slug: str
    logo_url: str | None


# --- Variant ---
class ProductVariantCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    size: str | None = Field(default=None, max_length=20)
    color: str | None = Field(default=None, max_length=40)
    stock_quantity: int = Field(ge=0, default=0)
    price_override: Decimal | None = Field(default=None, gt=0)


class ProductVariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    sku: str
    size: str | None
    color: str | None
    stock_quantity: int
    price_override: Decimal | None


# --- Image ---
class ProductImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    image_url: str
    is_primary: bool
    display_order: int
    variant_id: uuid.UUID | None


# --- Product ---
class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=10000)
    category_id: uuid.UUID
    brand_id: uuid.UUID
    base_price: Decimal = Field(gt=0)
    discount_percentage: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    gst_percentage: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    status: ProductStatus = ProductStatus.DRAFT
    is_featured: bool = False
    is_trending: bool = False
    variants: list[ProductVariantCreate] = Field(min_length=1)

    @field_validator("variants")
    @classmethod
    def skus_must_be_unique_within_product(cls, v: list[ProductVariantCreate]):
        skus = [variant.sku for variant in v]
        if len(skus) != len(set(skus)):
            raise ValueError("Duplicate SKU within the same product submission")
        return v


class ProductUpdate(BaseModel):
    # All optional — PATCH-style partial update. Variants/images are
    # managed through their own endpoints, not bulk-replaced here, since
    # blindly overwriting the variant list risks deleting variants that
    # already have order history attached to them (Phase 3+ concern).
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    category_id: uuid.UUID | None = None
    brand_id: uuid.UUID | None = None
    base_price: Decimal | None = Field(default=None, gt=0)
    discount_percentage: Decimal | None = Field(default=None, ge=0, le=100)
    gst_percentage: Decimal | None = Field(default=None, ge=0, le=100)
    status: ProductStatus | None = None
    is_featured: bool | None = None
    is_trending: bool | None = None


class ProductVariantUpdate(BaseModel):
    # All optional — partial update for a single existing variant, used by
    # the admin "Edit Product" screen to adjust stock/price/size/color
    # without touching the other variants on the product.
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    size: str | None = Field(default=None, max_length=20)
    color: str | None = Field(default=None, max_length=40)
    stock_quantity: int | None = Field(default=None, ge=0)
    price_override: Decimal | None = Field(default=None, gt=0)


class ProductOut(BaseModel):
    """Lightweight — used in list/grid responses."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    slug: str
    base_price: Decimal
    discount_percentage: Decimal
    status: ProductStatus
    is_featured: bool
    is_trending: bool
    category: CategoryOut
    brand: BrandOut
    primary_image_url: str | None = None


class ProductDetailOut(BaseModel):
    """Full detail — used on the PDP (product detail page)."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    slug: str
    description: str
    base_price: Decimal
    discount_percentage: Decimal
    gst_percentage: Decimal
    status: ProductStatus
    is_featured: bool
    is_trending: bool
    created_at: datetime
    category: CategoryOut
    brand: BrandOut
    variants: list[ProductVariantOut]
    images: list[ProductImageOut]


class PaginatedProducts(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int
    total_pages: int
