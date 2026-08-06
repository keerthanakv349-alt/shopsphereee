from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.deps import require_role
from app.db.session import get_db
from app.models.coupon import Coupon
from app.models.user import User, UserRole
from app.schemas.order import CouponCreate, CouponOut

router = APIRouter(prefix="/api/v1/admin/coupons", tags=["admin-coupons"])
admin_only = require_role(UserRole.ADMIN, UserRole.SUPER_ADMIN)


@router.post("", response_model=CouponOut, status_code=status.HTTP_201_CREATED)
def create_coupon(payload: CouponCreate, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    code = payload.code.upper()
    if db.query(Coupon).filter(Coupon.code == code).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A coupon with this code already exists")

    coupon = Coupon(**{**payload.model_dump(), "code": code})
    db.add(coupon)
    db.commit()
    db.refresh(coupon)
    return coupon


@router.get("", response_model=list[CouponOut])
def list_coupons(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return db.query(Coupon).order_by(Coupon.created_at.desc()).all()
