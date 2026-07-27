from pydantic import BaseModel


class BacktestResult(BaseModel):
    status: str = "not_implemented"
