import uuid

from pydantic import BaseModel, ConfigDict, Field


class AddressCreate(BaseModel):
    label: str = Field(default="Home", max_length=50)
    full_name: str = Field(min_length=2, max_length=120)
    phone_number: str = Field(min_length=6, max_length=20)
    line1: str = Field(min_length=3, max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=2, max_length=100)
    state: str = Field(min_length=2, max_length=100)
    postal_code: str = Field(min_length=3, max_length=20)
    country: str = Field(default="India", max_length=100)
    is_default: bool = False


class AddressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    label: str
    full_name: str
    phone_number: str
    line1: str
    line2: str | None
    city: str
    state: str
    postal_code: str
    country: str
    is_default: bool
