"""xAI Management API integration for xAI Remaining.

Copyright (c) 2026 Clayton Pippenger.
Licensed under the MIT License.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import math
import os
from typing import Any
from urllib.parse import quote

import requests

from .base import Provider, ProviderResult


API_BASE_URL = "https://management-api.x.ai"
PREPAID_BALANCE_URL_TEMPLATE = f"{API_BASE_URL}/v1/billing/teams/{{team_id}}/prepaid/balance"
BILLING_USAGE_URL_TEMPLATE = f"{API_BASE_URL}/v1/billing/teams/{{team_id}}/postpaid/invoice/preview"
REQUEST_TIMEOUT_SECONDS = 30

DEFAULT_PREPAID_TOTAL_FIELD_PATH = "total.val"
DEFAULT_PREPAID_USED_FIELD_PATH = "coreInvoice.prepaidCreditsUsed.val"
PREPAID_TOTAL_FIELD_PATH_ENV = "XAI_PREPAID_TOTAL_FIELD_PATH"
PREPAID_USED_FIELD_PATH_ENV = "XAI_PREPAID_USED_FIELD_PATH"

CANDIDATE_FIELD_SUFFIXES = (
    "val",
    "amount",
    "balance",
    "remaining",
    "credit",
    "credits",
    "debit",
    "used",
    "spend",
    "total",
)


class BalanceError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        api_call_made: bool = False,
        http_status_code: int | None = None,
        prepaid_http_status_code: int | None = None,
        usage_http_status_code: int | None = None,
        raw_top_level_keys: tuple[str, ...] = (),
        usage_top_level_keys: tuple[str, ...] = (),
        balance_field_path: str | None = None,
        used_field_path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.api_call_made = api_call_made
        self.http_status_code = http_status_code
        self.prepaid_http_status_code = prepaid_http_status_code
        self.usage_http_status_code = usage_http_status_code
        self.raw_top_level_keys = raw_top_level_keys
        self.usage_top_level_keys = usage_top_level_keys
        self.balance_field_path = balance_field_path or selected_balance_field_path()
        self.used_field_path = used_field_path or selected_used_field_path()


class XaiProvider(Provider):
    provider_name = "xAI"

    def get_balance(self) -> ProviderResult:
        last_updated_utc = datetime.now(UTC)

        try:
            (
                prepaid_total_usd,
                prepaid_used_usd,
                remaining_credit_usd,
                prepaid_http_status_code,
                usage_http_status_code,
                prepaid_top_level_keys,
                usage_top_level_keys,
                balance_field_path,
                used_field_path,
            ) = fetch_balance_usd()
        except Exception as exc:
            api_call_made = getattr(exc, "api_call_made", isinstance(exc, requests.RequestException))
            return ProviderResult(
                provider_name=self.provider_name,
                balance_usd=None,
                status="error",
                last_updated_utc=last_updated_utc,
                error_message=safe_error_message(exc),
                api_call_made=api_call_made,
                http_status_code=getattr(exc, "http_status_code", None),
                prepaid_http_status_code=getattr(exc, "prepaid_http_status_code", None),
                usage_http_status_code=getattr(exc, "usage_http_status_code", None),
                raw_top_level_keys=getattr(exc, "raw_top_level_keys", ()),
                usage_top_level_keys=getattr(exc, "usage_top_level_keys", ()),
                balance_field_path=getattr(exc, "balance_field_path", selected_balance_field_path()),
                used_field_path=getattr(exc, "used_field_path", selected_used_field_path()),
            )

        return ProviderResult(
            provider_name=self.provider_name,
            balance_usd=remaining_credit_usd,
            prepaid_total_usd=prepaid_total_usd,
            prepaid_used_usd=prepaid_used_usd,
            remaining_credit_usd=remaining_credit_usd,
            status="ok",
            last_updated_utc=last_updated_utc,
            error_message=None,
            api_call_made=True,
            http_status_code=usage_http_status_code,
            prepaid_http_status_code=prepaid_http_status_code,
            usage_http_status_code=usage_http_status_code,
            raw_top_level_keys=prepaid_top_level_keys,
            usage_top_level_keys=usage_top_level_keys,
            balance_field_path=balance_field_path,
            used_field_path=used_field_path,
        )


def fetch_balance_usd() -> tuple[
    Decimal,
    Decimal,
    Decimal,
    int,
    int,
    tuple[str, ...],
    tuple[str, ...],
    str,
    str,
]:
    total_path = selected_balance_field_path()
    used_path = selected_used_field_path()

    prepaid_payload, prepaid_status_code = fetch_prepaid_balance_payload()
    prepaid_top_level_keys = top_level_keys(prepaid_payload)
    try:
        prepaid_total_usd = extract_credit_amount_usd(
            prepaid_payload,
            total_path,
            field_label="prepaid total",
        )
    except BalanceError as exc:
        raise BalanceError(
            str(exc),
            api_call_made=True,
            http_status_code=prepaid_status_code,
            prepaid_http_status_code=prepaid_status_code,
            raw_top_level_keys=prepaid_top_level_keys,
            balance_field_path=total_path,
            used_field_path=used_path,
        ) from exc

    usage_status_code: int | None = None
    usage_top_level_keys: tuple[str, ...] = ()
    try:
        usage_payload, usage_status_code = fetch_billing_usage_payload()
        usage_top_level_keys = top_level_keys(usage_payload)
        prepaid_used_usd = extract_credit_amount_usd(
            usage_payload,
            used_path,
            field_label="prepaid used",
        )
    except BalanceError as exc:
        raise BalanceError(
            str(exc),
            api_call_made=True,
            http_status_code=exc.http_status_code,
            prepaid_http_status_code=prepaid_status_code,
            usage_http_status_code=usage_status_code or exc.usage_http_status_code or exc.http_status_code,
            raw_top_level_keys=prepaid_top_level_keys,
            usage_top_level_keys=usage_top_level_keys or exc.usage_top_level_keys,
            balance_field_path=total_path,
            used_field_path=used_path,
        ) from exc

    remaining_credit_usd = (prepaid_total_usd - prepaid_used_usd).quantize(Decimal("0.01"))

    return (
        prepaid_total_usd,
        prepaid_used_usd,
        remaining_credit_usd,
        prepaid_status_code,
        usage_status_code,
        prepaid_top_level_keys,
        usage_top_level_keys,
        total_path,
        used_path,
    )


def fetch_prepaid_balance_payload() -> tuple[Any, int]:
    _, team_id = required_credentials()
    url = PREPAID_BALANCE_URL_TEMPLATE.format(team_id=quote(team_id, safe=""))
    return get_json(url, endpoint_label="prepaid balance", prepaid=True)


def fetch_billing_usage_payload() -> tuple[Any, int]:
    _, team_id = required_credentials()
    url = BILLING_USAGE_URL_TEMPLATE.format(team_id=quote(team_id, safe=""))
    return get_json(url, endpoint_label="postpaid invoice preview", usage=True)


def get_json(
    url: str,
    *,
    endpoint_label: str,
    prepaid: bool = False,
    usage: bool = False,
) -> tuple[Any, int]:
    api_key, _ = required_credentials()
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        raise BalanceError(
            f"{endpoint_label} HTTP {response.status_code}",
            api_call_made=True,
            http_status_code=response.status_code,
            prepaid_http_status_code=response.status_code if prepaid else None,
            usage_http_status_code=response.status_code if usage else None,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise BalanceError(
            f"{endpoint_label} invalid JSON response",
            api_call_made=True,
            http_status_code=response.status_code,
            prepaid_http_status_code=response.status_code if prepaid else None,
            usage_http_status_code=response.status_code if usage else None,
        ) from exc

    return payload, response.status_code


def required_credentials() -> tuple[str, str]:
    api_key = os.environ.get("XAI_MGMT_KEY")
    team_id = os.environ.get("XAI_TEAM_ID")
    missing = []
    if not api_key:
        missing.append("XAI_MGMT_KEY")
    if not team_id:
        missing.append("XAI_TEAM_ID")
    if missing:
        raise BalanceError(f"missing environment variable: {', '.join(missing)}")
    return api_key, team_id


def selected_balance_field_path() -> str:
    configured_path = os.environ.get(PREPAID_TOTAL_FIELD_PATH_ENV, "").strip()
    return configured_path or DEFAULT_PREPAID_TOTAL_FIELD_PATH


def selected_used_field_path() -> str:
    configured_path = os.environ.get(PREPAID_USED_FIELD_PATH_ENV, "").strip()
    return configured_path or DEFAULT_PREPAID_USED_FIELD_PATH


def top_level_keys(payload: Any) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        return ()
    return tuple(sorted(str(key) for key in payload.keys()))


def extract_credit_amount_usd(payload: Any, field_path: str, *, field_label: str) -> Decimal:
    cents = extract_decimal(payload, field_path, field_label=field_label)
    # xAI billing values are cents; some credit fields arrive negative.
    positive_cents = -cents if cents < 0 else cents
    return (positive_cents / Decimal("100")).quantize(Decimal("0.01"))


def extract_decimal(payload: Any, field_path: str, *, field_label: str) -> Decimal:
    if not isinstance(payload, dict):
        raise BalanceError(f"unexpected {field_label} response shape")

    value = value_at_dotted_path(payload, field_path)
    if value is None:
        raise BalanceError(f"missing selected {field_label} field: {field_path}")

    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise BalanceError(f"invalid selected {field_label} field: {field_path}") from exc
    if not parsed.is_finite():
        raise BalanceError(f"invalid selected {field_label} field: {field_path}")
    return parsed


def value_at_dotted_path(payload: Any, field_path: str) -> Any:
    current = payload
    for part in field_path.split("."):
        if not part:
            return None
        if isinstance(current, dict):
            current = current.get(part)
            continue
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return None
            current = current[index]
            continue
        return None
    return current


def billing_numeric_candidates(payload: Any) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    collect_billing_numeric_candidates(payload, "", candidates)
    return candidates


def collect_billing_numeric_candidates(
    value: Any,
    path: str,
    candidates: list[tuple[str, str]],
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            collect_billing_numeric_candidates(child, child_path, candidates)
        return

    if isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}.{index}" if path else str(index)
            collect_billing_numeric_candidates(child, child_path, candidates)
        return

    if path_matches_billing_candidate(path) and scalar_is_numeric_like(value):
        candidates.append((path, str(value)))


def path_matches_billing_candidate(path: str) -> bool:
    if not path:
        return False
    last_part = path.split(".")[-1].lower()
    return any(last_part.endswith(suffix) for suffix in CANDIDATE_FIELD_SUFFIXES)


def scalar_is_numeric_like(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Decimal):
        return value.is_finite()
    if isinstance(value, str):
        try:
            parsed = Decimal(value)
        except InvalidOperation:
            return False
        return parsed.is_finite()
    return False


def safe_error_message(exc: Exception) -> str:
    if isinstance(exc, BalanceError):
        return str(exc)
    if isinstance(exc, requests.Timeout):
        return "request timed out"
    if isinstance(exc, requests.RequestException):
        return "request failed"
    return "unexpected error"
