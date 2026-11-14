from pydantic import BaseModel, ConfigDict


class PublicationPreviewRequest(BaseModel):
    """IDs come from the URL; clients cannot submit replacement scanner/workflow fields."""
    model_config = ConfigDict(extra="forbid")
