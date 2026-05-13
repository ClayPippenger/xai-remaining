"""Provider result types for xAI Remaining.

Copyright (c) 2026 Clayton Pippenger.
Licensed under the MIT License.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class ProviderResult:
    provider_name: str
    balance_usd: Decimal | None
    status: str
    last_updated_utc: datetime
    error_message: str | None
    prepaid_total_usd: Decimal | None = None
    prepaid_used_usd: Decimal | None = None
    remaining_credit_usd: Decimal | None = None
    api_call_made: bool = False
    http_status_code: int | None = None
    prepaid_http_status_code: int | None = None
    usage_http_status_code: int | None = None
    raw_top_level_keys: tuple[str, ...] = ()
    usage_top_level_keys: tuple[str, ...] = ()
    balance_field_path: str | None = None
    used_field_path: str | None = None


class Provider:
    provider_name: str

    def initial_result(self) -> ProviderResult | None:
        return None

    def get_balance(self) -> ProviderResult:
        raise NotImplementedError
