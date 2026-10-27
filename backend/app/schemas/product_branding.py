from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ProductBrandingRead(BaseModel):
    sidebar_logo_size: Literal["small", "medium", "large"] = "medium"
    version: str = "none"


class ProductBrandingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sidebar_logo_size: Literal["small", "medium", "large"]
    expected_version: str = Field(min_length=4, max_length=36)
