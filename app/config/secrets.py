from typing import Any, Dict

from app.core.security import mask_secret, sanitize_mapping, sanitize_text


def masked_configuration(values: Dict[str, Any]) -> Dict[str, Any]:
    return sanitize_mapping(values)


__all__ = ["mask_secret", "sanitize_mapping", "sanitize_text", "masked_configuration"]
