from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Quote(BaseModel):
    symbol: str
    price: float
    low: Optional[float] = None
    high: Optional[float] = None
    timestamp: datetime
