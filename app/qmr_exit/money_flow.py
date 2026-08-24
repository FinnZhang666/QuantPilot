from datetime import datetime, timezone

from app.data.providers.moomoo import MoomooConnectionManager
from app.data.capabilities import money_flow_capability
from app.data.quality import DataStatus, assess_quality


class MoomooMoneyFlowProvider:
    """Read-only adapter for OpenQuoteContext.get_capital_distribution()."""
    def __init__(self, manager=None):
        self.manager = manager or MoomooConnectionManager()

    def fetch(self, symbol):
        capability = money_flow_capability(symbol)
        if not capability.supported:
            quality = assess_quality("money_flow", None, 0, capability.provider,
                                     DataStatus.UNSUPPORTED.value, "MARKET_UNSUPPORTED")
            return {"data_available": False, "data_status": quality.status,
                    "source": capability.provider, "coverage": 0,
                    "confidence": quality.confidence, "raw_fields": {},
                    "capability": capability.as_dict(), "error": quality.error_code}
        context = None
        try:
            context = self.manager.open_quote_context()
            ret, frame = context.get_capital_distribution(
                symbol if symbol.startswith("US.") else "US." + symbol.upper())
            if ret != 0 or frame is None or getattr(frame, "empty", False):
                return self._unavailable(capability, "CAPITAL_DISTRIBUTION_UNAVAILABLE")
            row = frame.to_dict("records")[0]
            mapping = {"super_large": "super", "large": "big", "medium": "mid", "small": "small"}
            raw = {}
            for target, source in mapping.items():
                incoming = _float(row.get("capital_in_" + source))
                outgoing = _float(row.get("capital_out_" + source))
                raw[target + "_inflow"] = incoming
                raw[target + "_outflow"] = outgoing
                raw[target + "_net"] = None if incoming is None or outgoing is None else incoming - outgoing
            valid = [value for value in raw.values() if value is not None]
            raw["total_inflow"] = sum(raw[key] for key in raw if key.endswith("_inflow") and raw[key] is not None)
            raw["total_outflow"] = sum(raw[key] for key in raw if key.endswith("_outflow") and raw[key] is not None)
            raw["total_net"] = raw["total_inflow"] - raw["total_outflow"]
            raw["total_turnover"] = raw["total_inflow"] + raw["total_outflow"]
            timestamp = row.get("update_time") or datetime.now(timezone.utc)
            coverage = len(valid) / 8
            status = DataStatus.AVAILABLE.value if coverage == 1 else DataStatus.PARTIAL.value
            quality = assess_quality("money_flow", timestamp if isinstance(timestamp, datetime) else None,
                                     coverage, capability.provider, status)
            return {"data_available": quality.available, "data_status": quality.status,
                    "source": capability.provider, "timestamp": timestamp, "raw": raw,
                    "raw_fields": raw, "freshness": quality.freshness, "coverage": coverage,
                    "confidence": quality.confidence, "capability": capability.as_dict()}
        except Exception as exc:
            code = "PERMISSION_DENIED" if "permission" in str(exc).lower() else type(exc).__name__
            status = DataStatus.PERMISSION_DENIED.value if code == "PERMISSION_DENIED" else DataStatus.UNAVAILABLE.value
            return self._unavailable(capability, code, status)
        finally:
            if context is not None:
                try: context.close()
                except Exception: pass
            self.manager.close_all()

    @staticmethod
    def _unavailable(capability, error, status=DataStatus.UNAVAILABLE.value):
        quality = assess_quality("money_flow", None, 0, capability.provider, status, error)
        return {"data_available": False, "data_status": quality.status,
                "source": capability.provider, "coverage": 0,
                "confidence": quality.confidence, "raw_fields": {},
                "capability": capability.as_dict(), "error": error}


def _float(value):
    try: return float(value)
    except (TypeError, ValueError): return None
