import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.user import UserRole
from app.schemas.order import OrderOut


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    full_name: str
    email: EmailStr
    role: UserRole
    is_active: bool
    is_email_verified: bool
    created_at: datetime


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserRoleUpdate(BaseModel):
    role: UserRole


class DashboardSummary(BaseModel):
    total_revenue: Decimal
    total_orders: int
    total_customers: int
    total_products: int
    low_stock_variant_count: int
    recent_orders: list[OrderOut]



class NotificationOut(BaseModel):
    title: str
    message: str
    type: str
    created_at: datetime


class NotificationListResponse(BaseModel):
    notifications: list[NotificationOut]