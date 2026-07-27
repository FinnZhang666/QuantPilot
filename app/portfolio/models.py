from pydantic import BaseModel


class PortfolioSummary(BaseModel):
    code: str
    cash: float
    equity: float
    currency: str
