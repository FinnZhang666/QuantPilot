from dataclasses import asdict, dataclass
from typing import Tuple


@dataclass(frozen=True)
class MoneyFlowCapability:
    symbol: str
    market: str
    asset_type: str
    provider: str
    supported: bool
    session_supported: Tuple[str, ...]
    historical_supported: bool
    realtime_supported: bool
    fields_supported: Tuple[str, ...]
    reason: str = ""

    def as_dict(self):
        value = asdict(self)
        value["session_supported"] = list(self.session_supported)
        value["fields_supported"] = list(self.fields_supported)
        return value


MOOMOO_CAPITAL_FIELDS = (
    "super_large_inflow", "super_large_outflow", "large_inflow", "large_outflow",
    "medium_inflow", "medium_outflow", "small_inflow", "small_outflow",
)


def money_flow_capability(symbol: str, market="US", asset_type="EQUITY",
                          provider="MOOMOO_CAPITAL_DISTRIBUTION"):
    market = market.upper()
    supported = market in {"US", "HK", "CN"}
    return MoneyFlowCapability(symbol.upper().removeprefix(market + "."), market,
        asset_type.upper(), provider, supported, ("REGULAR",), False, True,
        MOOMOO_CAPITAL_FIELDS if supported else (),
        "PROVIDER_AND_PERMISSION_DEPENDENT" if supported else "MARKET_UNSUPPORTED")
