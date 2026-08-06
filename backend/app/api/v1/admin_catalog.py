# """
# Admin catalog endpoints — everything here requires ADMIN or SUPER_ADMIN role.

# --- WHAT HAPPENS WHEN AN ADMIN CLICKS "ADD PRODUCT" (the full walkthrough
#     the original brief asked for) ---

# 1. FRONTEND: the admin fills a form (name, description, category, brand,
#    price, discount %, GST %, status, and one or more variant rows —
#    size/color/stock/optional price override). React Hook Form validates
#    client-side against a Zod schema mirroring ProductCreate below.

# 2. REQUEST: POST /api/v1/admin/products with a JSON body. The Authorization
#    header carries the admin's access token.

# 3. AUTH: require_role(ADMIN, SUPER_ADMIN) runs BEFORE the route body —
#    a customer-role token gets a 403 here and the handler never executes.

# 4. VALIDATION: Pydantic's ProductCreate model parses the body. Anything
#    malformed (negative price, empty variants list, duplicate SKUs within
#    the submission — see the field_validator in schemas/catalog.py) is
#    rejected with a 422 before we touch the database at all.

# 5. FOREIGN KEY CHECKS: we explicitly verify category_id and brand_id
#    exist before inserting — better to return a clean 404 ("Category not
#    found") than let Postgres reject the insert with a raw foreign-key
#    violation, which is a confusing 500 error the frontend can't render
#    meaningfully.

# 6. SLUG GENERATION: the product's URL slug ("nike-air-max-90") is derived
#    from the name server-side, then checked for uniqueness (retrying with
#    a numeric suffix on collision) — the admin never has to think about
#    URLs at all.

# 7. THE DATABASE TRANSACTION (this is the important part): the Product row
#    AND all its ProductVariant rows are created in the SAME db.commit().
#    If anything fails partway — e.g. a duplicate SKU that slipped past
#    validation somehow — SQLAlchemy rolls back the ENTIRE transaction, so
#    we never end up with a Product that has zero variants, or variants
#    pointing at a Product that didn't actually get created. This
#    all-or-nothing guarantee is exactly why relational databases and ORMs
#    default to explicit transactions instead of auto-committing each
#    insert individually.

# 8. RESPONSE: the newly created product (re-fetched with variants/images
#    eagerly loaded) is serialized through ProductDetailOut and returned
#    with 201 Created.

# 9. IMAGES ARE A SEPARATE STEP: POST /api/v1/admin/products/{id}/images,
#    called once per image AFTER the product exists (images need a
#    product_id to attach to). See app/core/images.py for the compression/
#    storage details. This is also why product creation and image upload
#    are two different endpoints instead of one giant multipart request —
#    simpler validation, and the admin can add/remove/reorder images later
#    without resubmitting the whole product.
# """
# import uuid

# from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
# from sqlalchemy import select
# from sqlalchemy.orm import Session, selectinload

# from app.api.v1.deps import require_role
# from app.core.images import delete_product_image, save_product_image
# from app.db.session import get_db
# from app.models.catalog import Brand, Category, Product, ProductImage, ProductVariant
# from app.models.user import User, UserRole
# from app.schemas.catalog import (
#     BrandCreate,
#     BrandOut,
#     CategoryCreate,
#     CategoryOut,
#     PaginatedProducts,
#     ProductCreate,
#     ProductDetailOut,
#     ProductImageOut,
#     ProductOut,
#     ProductUpdate,
#     slugify,
# )

# router = APIRouter(prefix="/api/v1/admin", tags=["admin-catalog"])

# admin_only = require_role(UserRole.ADMIN, UserRole.SUPER_ADMIN)


# def _unique_slug(db: Session, model, base_name: str) -> str:
#     base_slug = slugify(base_name)
#     slug = base_slug
#     suffix = 1
#     while db.query(model).filter(model.slug == slug).first() is not None:
#         suffix += 1
#         slug = f"{base_slug}-{suffix}"
#     return slug


# # --- Categories ---
# @router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
# def create_category(
#     payload: CategoryCreate, db: Session = Depends(get_db), _: User = Depends(admin_only)
# ):
#     if payload.parent_id and db.get(Category, payload.parent_id) is None:
#         raise HTTPException(status.HTTP_404_NOT_FOUND, "Parent category not found")

#     category = Category(
#         name=payload.name.strip(),
#         slug=_unique_slug(db, Category, payload.name),
#         parent_id=payload.parent_id,
#     )
#     db.add(category)
#     db.commit()
#     db.refresh(category)
#     return category


# # --- Brands ---
# @router.post("/brands", response_model=BrandOut, status_code=status.HTTP_201_CREATED)
# def create_brand(payload: BrandCreate, db: Session = Depends(get_db), _: User = Depends(admin_only)):
#     brand = Brand(
#         name=payload.name.strip(),
#         slug=_unique_slug(db, Brand, payload.name),
#         logo_url=payload.logo_url,
#     )
#     db.add(brand)
#     db.commit()
#     db.refresh(brand)
#     return brand


# # --- Products ---
# def _load_product_or_404(db: Session, product_id: uuid.UUID) -> Product:
#     stmt = (
#         select(Product)
#         .where(Product.id == product_id)
#         .options(selectinload(Product.variants), selectinload(Product.images))
#     )
#     product = db.execute(stmt).scalar_one_or_none()
#     if product is None:
#         raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
#     return product


# @router.post("/products", response_model=ProductDetailOut, status_code=status.HTTP_201_CREATED)
# def create_product(payload: ProductCreate, db: Session = Depends(get_db), _: User = Depends(admin_only)):
#     if db.get(Category, payload.category_id) is None:
#         raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
#     if db.get(Brand, payload.brand_id) is None:
#         raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand not found")

#     existing_skus = {
#         sku
#         for (sku,) in db.query(ProductVariant.sku)
#         .filter(ProductVariant.sku.in_([v.sku for v in payload.variants]))
#         .all()
#     }
#     if existing_skus:
#         raise HTTPException(
#             status.HTTP_409_CONFLICT, f"SKU(s) already in use: {', '.join(sorted(existing_skus))}"
#         )

#     product = Product(
#         name=payload.name.strip(),
#         slug=_unique_slug(db, Product, payload.name),
#         description=payload.description,
#         category_id=payload.category_id,
#         brand_id=payload.brand_id,
#         base_price=payload.base_price,
#         discount_percentage=payload.discount_percentage,
#         gst_percentage=payload.gst_percentage,
#         status=payload.status,
#         is_featured=payload.is_featured,
#         is_trending=payload.is_trending,
#     )
#     # Building variant ORM objects and attaching them to product.variants
#     # BEFORE the first db.add/commit means SQLAlchemy inserts the Product
#     # row and all ProductVariant rows in one transaction — see docstring
#     # point 7 above for why that matters.
#     product.variants = [
#         ProductVariant(
#             sku=v.sku,
#             size=v.size,
#             color=v.color,
#             stock_quantity=v.stock_quantity,
#             price_override=v.price_override,
#         )
#         for v in payload.variants
#     ]

#     db.add(product)
#     db.commit()

#     return _load_product_or_404(db, product.id)


# @router.get("/products", response_model=PaginatedProducts)
# def admin_list_products(
#     db: Session = Depends(get_db),
#     _: User = Depends(admin_only),
#     page: int = Query(1, ge=1),
#     page_size: int = Query(20, ge=1, le=100),
# ):
#     # Unlike the public listing, this deliberately includes draft/inactive
#     # products — admins need to see and edit products before they go live.
#     base_query = select(Product).options(
#         selectinload(Product.category), selectinload(Product.brand), selectinload(Product.images)
#     )
#     total = db.execute(select(Product.id)).scalars().all()
#     items = db.execute(
#         base_query.order_by(Product.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
#     ).scalars().all()
#     total_count = len(total)
#     return PaginatedProducts(
#         items=items,
#         total=total_count,
#         page=page,
#         page_size=page_size,
#         total_pages=max(1, (total_count + page_size - 1) // page_size),
#     )


# @router.put("/products/{product_id}", response_model=ProductDetailOut)
# def update_product(
#     product_id: uuid.UUID,
#     payload: ProductUpdate,
#     db: Session = Depends(get_db),
#     _: User = Depends(admin_only),
# ):
#     product = _load_product_or_404(db, product_id)

#     update_data = payload.model_dump(exclude_unset=True)
#     if "category_id" in update_data and db.get(Category, update_data["category_id"]) is None:
#         raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
#     if "brand_id" in update_data and db.get(Brand, update_data["brand_id"]) is None:
#         raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand not found")

#     for field, value in update_data.items():
#         setattr(product, field, value)

#     db.commit()
#     return _load_product_or_404(db, product_id)


# @router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
# def delete_product(product_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(admin_only)):
#     # SOFT delete (status -> inactive), not a row deletion. Once a product
#     # has ever been ordered, hard-deleting it would orphan OrderItem rows
#     # that reference it (Phase 3) and destroy sales history/analytics.
#     # This is standard e-commerce practice — "delete" in the admin UI
#     # almost never means DROP the row.
#     product = _load_product_or_404(db, product_id)
#     from app.models.catalog import ProductStatus

#     product.status = ProductStatus.INACTIVE
#     db.commit()
#     return None


# @router.post(
#     "/products/{product_id}/images", response_model=ProductImageOut, status_code=status.HTTP_201_CREATED
# )
# async def upload_product_image(
#     product_id: uuid.UUID,
#     file: UploadFile = File(...),
#     is_primary: bool = False,
#     db: Session = Depends(get_db),
#     _: User = Depends(admin_only),
# ):
#     product = _load_product_or_404(db, product_id)
#     image_url = await save_product_image(product_id, file)

#     if is_primary:
#         # Only one primary image per product — unset any existing one.
#         for existing in product.images:
#             existing.is_primary = False

#     image = ProductImage(
#         product_id=product_id,
#         image_url=image_url,
#         is_primary=is_primary,
#         display_order=len(product.images),
#     )
#     db.add(image)
#     db.commit()
#     db.refresh(image)
#     return image


# @router.delete("/products/{product_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
# def delete_image(
#     product_id: uuid.UUID,
#     image_id: uuid.UUID,
#     db: Session = Depends(get_db),
#     _: User = Depends(admin_only),
# ):
#     image = db.get(ProductImage, image_id)
#     if image is None or image.product_id != product_id:
#         raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")

#     delete_product_image(image.image_url)
#     db.delete(image)
#     db.commit()
#     return None




"""
Admin catalog endpoints — everything here requires ADMIN or SUPER_ADMIN role.

--- WHAT HAPPENS WHEN AN ADMIN CLICKS "ADD PRODUCT" (the full walkthrough
    the original brief asked for) ---

1. FRONTEND: the admin fills a form (name, description, category, brand,
   price, discount %, GST %, status, and one or more variant rows —
   size/color/stock/optional price override). React Hook Form validates
   client-side against a Zod schema mirroring ProductCreate below.

2. REQUEST: POST /api/v1/admin/products with a JSON body. The Authorization
   header carries the admin's access token.

3. AUTH: require_role(ADMIN, SUPER_ADMIN) runs BEFORE the route body —
   a customer-role token gets a 403 here and the handler never executes.

4. VALIDATION: Pydantic's ProductCreate model parses the body. Anything
   malformed (negative price, empty variants list, duplicate SKUs within
   the submission — see the field_validator in schemas/catalog.py) is
   rejected with a 422 before we touch the database at all.

5. FOREIGN KEY CHECKS: we explicitly verify category_id and brand_id
   exist before inserting — better to return a clean 404 ("Category not
   found") than let Postgres reject the insert with a raw foreign-key
   violation, which is a confusing 500 error the frontend can't render
   meaningfully.

6. SLUG GENERATION: the product's URL slug ("nike-air-max-90") is derived
   from the name server-side, then checked for uniqueness (retrying with
   a numeric suffix on collision) — the admin never has to think about
   URLs at all.

7. THE DATABASE TRANSACTION (this is the important part): the Product row
   AND all its ProductVariant rows are created in the SAME db.commit().
   If anything fails partway — e.g. a duplicate SKU that slipped past
   validation somehow — SQLAlchemy rolls back the ENTIRE transaction, so
   we never end up with a Product that has zero variants, or variants
   pointing at a Product that didn't actually get created. This
   all-or-nothing guarantee is exactly why relational databases and ORMs
   default to explicit transactions instead of auto-committing each
   insert individually.

8. RESPONSE: the newly created product (re-fetched with variants/images
   eagerly loaded) is serialized through ProductDetailOut and returned
   with 201 Created.

9. IMAGES ARE A SEPARATE STEP: POST /api/v1/admin/products/{id}/images,
   called once per image AFTER the product exists (images need a
   product_id to attach to). See app/core/images.py for the compression/
   storage details. This is also why product creation and image upload
   are two different endpoints instead of one giant multipart request —
   simpler validation, and the admin can add/remove/reorder images later
   without resubmitting the whole product.
"""
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.v1.deps import require_role
from app.core.images import delete_product_image, save_product_image
from app.db.session import get_db
from app.models.catalog import Brand, Category, Product, ProductImage, ProductVariant
from app.models.user import User, UserRole
from app.schemas.catalog import (
    BrandCreate,
    BrandOut,
    CategoryCreate,
    CategoryOut,
    PaginatedProducts,
    ProductCreate,
    ProductDetailOut,
    ProductImageOut,
    ProductOut,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantOut,
    ProductVariantUpdate,
    slugify,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin-catalog"])

admin_only = require_role(UserRole.ADMIN, UserRole.SUPER_ADMIN)


def _unique_slug(db: Session, model, base_name: str) -> str:
    base_slug = slugify(base_name)
    slug = base_slug
    suffix = 1
    while db.query(model).filter(model.slug == slug).first() is not None:
        suffix += 1
        slug = f"{base_slug}-{suffix}"
    return slug


# --- Categories ---
@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate, db: Session = Depends(get_db), _: User = Depends(admin_only)
):
    if payload.parent_id and db.get(Category, payload.parent_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Parent category not found")

    category = Category(
        name=payload.name.strip(),
        slug=_unique_slug(db, Category, payload.name),
        parent_id=payload.parent_id,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


# --- Brands ---
@router.post("/brands", response_model=BrandOut, status_code=status.HTTP_201_CREATED)
def create_brand(payload: BrandCreate, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    brand = Brand(
        name=payload.name.strip(),
        slug=_unique_slug(db, Brand, payload.name),
        logo_url=payload.logo_url,
    )
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


# --- Products ---
def _load_product_or_404(db: Session, product_id: uuid.UUID) -> Product:
    stmt = (
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.variants), selectinload(Product.images))
    )
    product = db.execute(stmt).scalar_one_or_none()
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product


@router.post("/products", response_model=ProductDetailOut, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    if db.get(Category, payload.category_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    if db.get(Brand, payload.brand_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand not found")

    existing_skus = {
        sku
        for (sku,) in db.query(ProductVariant.sku)
        .filter(ProductVariant.sku.in_([v.sku for v in payload.variants]))
        .all()
    }
    if existing_skus:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"SKU(s) already in use: {', '.join(sorted(existing_skus))}"
        )

    product = Product(
        name=payload.name.strip(),
        slug=_unique_slug(db, Product, payload.name),
        description=payload.description,
        category_id=payload.category_id,
        brand_id=payload.brand_id,
        base_price=payload.base_price,
        discount_percentage=payload.discount_percentage,
        gst_percentage=payload.gst_percentage,
        status=payload.status,
        is_featured=payload.is_featured,
        is_trending=payload.is_trending,
    )
    # Building variant ORM objects and attaching them to product.variants
    # BEFORE the first db.add/commit means SQLAlchemy inserts the Product
    # row and all ProductVariant rows in one transaction — see docstring
    # point 7 above for why that matters.
    product.variants = [
        ProductVariant(
            sku=v.sku,
            size=v.size,
            color=v.color,
            stock_quantity=v.stock_quantity,
            price_override=v.price_override,
        )
        for v in payload.variants
    ]

    db.add(product)
    db.commit()

    return _load_product_or_404(db, product.id)


@router.get("/products", response_model=PaginatedProducts)
def admin_list_products(
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    # Unlike the public listing, this deliberately includes draft/inactive
    # products — admins need to see and edit products before they go live.
    base_query = select(Product).options(
        selectinload(Product.category), selectinload(Product.brand), selectinload(Product.images)
    )
    total = db.execute(select(Product.id)).scalars().all()
    items = db.execute(
        base_query.order_by(Product.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    total_count = len(total)
    return PaginatedProducts(
        items=items,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=max(1, (total_count + page_size - 1) // page_size),
    )


@router.get("/products/{product_id}", response_model=ProductDetailOut)
def admin_get_product(
    product_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(admin_only)
):
    # Powers the "Edit Product" screen — unlike the public GET
    # /api/v1/products/{slug} endpoint, this deliberately does NOT filter
    # by status, so a draft or inactive product can still be opened and
    # edited by an admin (that's the whole point of a draft state).
    return _load_product_or_404(db, product_id)


@router.put("/products/{product_id}", response_model=ProductDetailOut)
def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    product = _load_product_or_404(db, product_id)

    update_data = payload.model_dump(exclude_unset=True)
    if "category_id" in update_data and db.get(Category, update_data["category_id"]) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    if "brand_id" in update_data and db.get(Brand, update_data["brand_id"]) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand not found")

    for field, value in update_data.items():
        setattr(product, field, value)

    db.commit()
    return _load_product_or_404(db, product_id)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    # SOFT delete (status -> inactive), not a row deletion. Once a product
    # has ever been ordered, hard-deleting it would orphan OrderItem rows
    # that reference it (Phase 3) and destroy sales history/analytics.
    # This is standard e-commerce practice — "delete" in the admin UI
    # almost never means DROP the row.
    product = _load_product_or_404(db, product_id)
    from app.models.catalog import ProductStatus

    product.status = ProductStatus.INACTIVE
    db.commit()
    return None


@router.post(
    "/products/{product_id}/images", response_model=ProductImageOut, status_code=status.HTTP_201_CREATED
)
async def upload_product_image(
    product_id: uuid.UUID,
    file: UploadFile = File(...),
    is_primary: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    product = _load_product_or_404(db, product_id)
    image_url = await save_product_image(product_id, file)

    if is_primary:
        # Only one primary image per product — unset any existing one.
        for existing in product.images:
            existing.is_primary = False

    image = ProductImage(
        product_id=product_id,
        image_url=image_url,
        is_primary=is_primary,
        display_order=len(product.images),
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image


@router.put("/products/{product_id}/images/{image_id}/primary", response_model=ProductImageOut)
def set_primary_image(
    product_id: uuid.UUID,
    image_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    product = _load_product_or_404(db, product_id)
    target = next((img for img in product.images if img.id == image_id), None)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")

    for image in product.images:
        image.is_primary = image.id == image_id

    db.commit()
    db.refresh(target)
    return target


@router.delete("/products/{product_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_image(
    product_id: uuid.UUID,
    image_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    image = db.get(ProductImage, image_id)
    if image is None or image.product_id != product_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")

    delete_product_image(image.image_url)
    db.delete(image)
    db.commit()
    return None


# --- Variants ---
# Kept as separate endpoints from update_product() above for the same
# reason images are: a variant carries its own SKU/stock, and bulk-
# replacing the whole variants array on every product edit risks
# clobbering rows that already have order history attached (Phase 3+).
@router.post(
    "/products/{product_id}/variants", response_model=ProductVariantOut, status_code=status.HTTP_201_CREATED
)
def create_variant(
    product_id: uuid.UUID,
    payload: ProductVariantCreate,
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    product = _load_product_or_404(db, product_id)

    if db.query(ProductVariant).filter(ProductVariant.sku == payload.sku).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"SKU already in use: {payload.sku}")

    variant = ProductVariant(
        product_id=product.id,
        sku=payload.sku,
        size=payload.size,
        color=payload.color,
        stock_quantity=payload.stock_quantity,
        price_override=payload.price_override,
    )
    db.add(variant)
    db.commit()
    db.refresh(variant)
    return variant


@router.put("/products/{product_id}/variants/{variant_id}", response_model=ProductVariantOut)
def update_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    payload: ProductVariantUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    variant = db.get(ProductVariant, variant_id)
    if variant is None or variant.product_id != product_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Variant not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "sku" in update_data and update_data["sku"] != variant.sku:
        clash = db.query(ProductVariant).filter(ProductVariant.sku == update_data["sku"]).first()
        if clash is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"SKU already in use: {update_data['sku']}")

    for field, value in update_data.items():
        setattr(variant, field, value)

    db.commit()
    db.refresh(variant)
    return variant
