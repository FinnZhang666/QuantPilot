from functools import lru_cache

from app.data_manager.manager import DataRequestManager
from app.data_manager.models import DataEnvelope, DataFreshness


@lru_cache
def get_data_request_manager(config_path="config/data_request_policy_v1.yaml"):
    """One process-wide coordinator so independent consumers share requests."""
    return DataRequestManager(config_path)


__all__ = ["DataRequestManager", "DataEnvelope", "DataFreshness", "get_data_request_manager"]
