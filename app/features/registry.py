import hashlib
import json
from typing import Dict, Iterable, List, Optional

from app.features.definitions import default_feature_definitions
from app.features.models import FeatureDefinition


def parameters_hash(parameters: Optional[dict]) -> str:
    raw = json.dumps(parameters or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class FeatureRegistry:
    def __init__(self):
        self._items: Dict[str, FeatureDefinition] = {}

    def register(self, definition: FeatureDefinition) -> None:
        key = definition.feature_name + ":" + definition.version
        if key in self._items:
            raise ValueError("特征名称和版本重复：" + key)
        self._items[key] = definition

    def get(self, name: str, version: str = "1.0.0") -> FeatureDefinition:
        key = name + ":" + version
        if key not in self._items:
            raise KeyError("未注册特征：" + key)
        return self._items[key]

    def list(self) -> List[FeatureDefinition]:
        return list(self._items.values())

    @classmethod
    def defaults(cls) -> "FeatureRegistry":
        value = cls()
        for item in default_feature_definitions():
            value.register(item)
        return value
