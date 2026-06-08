from typing import List, Optional

from pydantic import BaseModel


class ProfileCreate(BaseModel):
    identity: str
    directions: List[str]
    target_companies: List[str]
    regions: Optional[List[str]] = None
    custom_needs: Optional[str] = None


class ProfileResponse(BaseModel):
    id: str
    identity: str
    directions: List[str]
    target_companies: List[str]
    regions: Optional[List[str]] = None
    custom_needs: Optional[str] = None
