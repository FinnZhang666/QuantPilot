from dataclasses import asdict, dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class TelegramActionButton:
    label: str
    action: str
    target_id: str
    deep_link: str
    enabled: bool = True


@dataclass(frozen=True)
class TelegramFeedbackAction:
    label: str
    action: str
    callback_data: str
    category: str


@dataclass(frozen=True)
class TelegramSymbolOverview:
    schema_version: str
    language: str
    symbol: str
    market: str
    title: str
    sections: List[Dict[str, str]]
    buttons: List[TelegramActionButton]
    empty_state: Optional[str] = None

    def model_dump(self):
        return asdict(self)
