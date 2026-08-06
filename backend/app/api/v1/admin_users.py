"""
Admin user management.

WHY ROLE CHANGES REQUIRE SUPER_ADMIN, NOT JUST ADMIN:
Letting any ADMIN promote other users to ADMIN (or themselves to
SUPER_ADMIN) would mean a single compromised admin account could mint
unlimited new admin accounts — a privilege escalation path. Restricting
role changes to SUPER_ADMIN keeps "who can grant admin access" to a much
smaller, more carefully controlled set of accounts, mirroring how real
systems separate "can manage day-to-day operations" from "can manage who
has access at all."

WHY YOU CAN'T CHANGE YOUR OWN ROLE OR DEACTIVATE YOURSELF:
Without this guard, a super admin could accidentally demote themselves
(or deactivate their own account) with no one left who can undo it. It's
a small check that prevents a very annoying self-lockout.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.admin import AdminUserOut, UserRoleUpdate, UserStatusUpdate

router = APIRouter(prefix="/api/v1/admin/users", tags=["admin-users"])
admin_only = require_role(UserRole.ADMIN, UserRole.SUPER_ADMIN)
super_admin_only = require_role(UserRole.SUPER_ADMIN)


@router.get("", response_model=list[AdminUserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
    q: str | None = Query(default=None, description="Search by name or email"),
):
    query = db.query(User)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.full_name.ilike(like), User.email.ilike(like)))
    return query.order_by(User.created_at.desc()).all()


@router.put("/{user_id}/status", response_model=AdminUserOut)
def update_user_status(
    user_id: uuid.UUID,
    payload: UserStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    if user_id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate your own account")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}/role", response_model=AdminUserOut)
def update_user_role(
    user_id: uuid.UUID,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(super_admin_only),
):
    if user_id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot change your own role")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    user.role = payload.role
    db.commit()
    db.refresh(user)
    return user
