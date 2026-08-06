"""
Address endpoints.

WHY EVERY QUERY FILTERS BY current_user.id:
There's no "get address by ID" endpoint that trusts the ID alone — every
lookup is `WHERE id = :id AND user_id = :current_user.id`. Without that
second condition, any logged-in user could read or delete ANY other
user's address just by guessing/incrementing an ID (an IDOR
vulnerability — Insecure Direct Object Reference, a very common real-world
bug class). Scoping every query to the authenticated user closes that off
structurally, not just "we remembered to check permissions."
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.db.session import get_db
from app.models.address import Address
from app.models.user import User
from app.schemas.address import AddressCreate, AddressOut

router = APIRouter(prefix="/api/v1/addresses", tags=["addresses"])


@router.get("", response_model=list[AddressOut])
def list_addresses(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return (
        db.query(Address)
        .filter(Address.user_id == current_user.id)
        .order_by(Address.is_default.desc(), Address.created_at.desc())
        .all()
    )


@router.post("", response_model=AddressOut, status_code=status.HTTP_201_CREATED)
def create_address(
    payload: AddressCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    if payload.is_default:
        # Only one default address per user — unset any existing default
        # rather than expressing this as a DB constraint (see model docstring).
        db.query(Address).filter(Address.user_id == current_user.id, Address.is_default.is_(True)).update(
            {"is_default": False}
        )

    address = Address(user_id=current_user.id, **payload.model_dump())
    db.add(address)
    db.commit()
    db.refresh(address)
    return address


@router.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_address(
    address_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    address = (
        db.query(Address).filter(Address.id == address_id, Address.user_id == current_user.id).first()
    )
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Address not found")
    db.delete(address)
    db.commit()
    return None
