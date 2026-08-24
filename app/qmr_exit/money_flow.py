from datetime import datetime, timezone

from app.data.providers.moomoo import MoomooConnectionManager


class MoomooMoneyFlowProvider:
    """Read-only adapter for OpenQuoteContext.get_capital_distribution()."""
    def __init__(self, manager=None):
        self.manager = manager or MoomooConnectionManager()

    def fetch(self, symbol):
        context = None
        try:
            context = self.manager.open_quote_context()
            ret, frame = context.get_capital_distribution(
                symbol if symbol.startswith("US.") else "US." + symbol.upper())
            if ret != 0 or frame is None or getattr(frame, "empty", False):
                return {"data_available": False, "source": "MOOMOO_CAPITAL_DISTRIBUTION",
                        "error": "CAPITAL_DISTRIBUTION_UNAVAILABLE"}
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
            return {"data_available": len(valid) == 8, "source": "MOOMOO_CAPITAL_DISTRIBUTION",
                    "timestamp": row.get("update_time") or datetime.now(timezone.utc), "raw": raw}
        except Exception as exc:
            return {"data_available": False, "source": "MOOMOO_CAPITAL_DISTRIBUTION",
                    "error": type(exc).__name__}
        finally:
            if context is not None:
                try: context.close()
                except Exception: pass
            self.manager.close_all()


def _float(value):
    try: return float(value)
    except (TypeError, ValueError): return None
