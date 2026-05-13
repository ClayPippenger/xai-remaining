"""xAI Remaining.

Copyright (c) 2026 Clayton Pippenger.
Licensed under the MIT License.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
import importlib
import json
import math
import os
from pathlib import Path
import sys
import threading
from typing import Any
import webbrowser


def runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_NAME = "xAI Remaining"
STARTING_TITLE = "xAI starting..."
BILLING_CONSOLE_URL = "https://console.x.ai/"
REFRESH_INTERVAL_SECONDS = 5 * 60
STATE_DIR = runtime_dir() / "state"
CACHE_PATH = STATE_DIR / "cache.json"
CONFIG_DIR = runtime_dir() / "config"
CONFIG_PATH = CONFIG_DIR / "settings.json"

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"
STATUS_CACHED = "cached"
STATUS_PENDING = "pending"

WARNING_BALANCE_DOLLARS = Decimal("25")
CRITICAL_BALANCE_DOLLARS = Decimal("10")
DEFAULT_LOW_BALANCE_ALERT_THRESHOLD_USD = Decimal("60.00")
DEFAULT_LOW_BALANCE_FLASH_INTERVAL_SECONDS = 1.0

ICON_SIZE = 64
ICON_TEXT_MAX_WIDTH = 58
ICON_TEXT_MAX_HEIGHT = 46
ICON_COLORS = {
    "normal": (22, 163, 74, 255),
    "warning": (245, 158, 11, 255),
    "critical": (220, 38, 38, 255),
    "error": (75, 85, 99, 255),
    "starting": (75, 85, 99, 255),
}
CONFIGURED_PROVIDER_NAME = "xAI"

pystray: Any = None
Image: Any = None
ImageDraw: Any = None
ImageFont: Any = None
ProviderResult: Any = None
XaiProvider: Any = None


@dataclass(frozen=True)
class AppSettings:
    low_balance_alert_threshold_usd: Decimal
    flash_interval_seconds: float
    warning_message: str | None = None


def main() -> None:
    if "--diagnose" in sys.argv[1:]:
        run_diagnostics()
        return
    if "--debug-billing-fields" in sys.argv[1:]:
        sys.exit(run_debug_billing_fields())
    if "--debug-usage-fields" in sys.argv[1:]:
        sys.exit(run_debug_usage_fields())
    if "--debug-once" in sys.argv[1:]:
        sys.exit(run_debug_once())

    load_runtime_dependencies()
    app = XaiRemainingApp(debug_tray="--debug-tray" in sys.argv[1:])
    app.run()


def load_runtime_dependencies() -> None:
    global Image, ImageDraw, ImageFont, ProviderResult, XaiProvider, pystray

    load_provider_dependencies()

    if pystray is None:
        pystray = importlib.import_module("pystray")
    if Image is None:
        Image = importlib.import_module("PIL.Image")
    if ImageDraw is None:
        ImageDraw = importlib.import_module("PIL.ImageDraw")
    if ImageFont is None:
        ImageFont = importlib.import_module("PIL.ImageFont")


def load_provider_dependencies() -> None:
    global ProviderResult, XaiProvider

    if ProviderResult is None:
        providers = importlib.import_module("providers")
        ProviderResult = providers.ProviderResult
        XaiProvider = providers.XaiProvider


def load_app_settings() -> AppSettings:
    defaults = default_app_settings()
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return replace(defaults, warning_message=f"could not create config folder ({exc.__class__.__name__})")

    if not CONFIG_PATH.exists():
        if not write_default_settings_file(CONFIG_PATH):
            return replace(defaults, warning_message="could not create config/settings.json")
        return defaults

    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return replace(defaults, warning_message=f"config unreadable, using defaults ({exc.__class__.__name__})")

    if not isinstance(payload, dict):
        return replace(defaults, warning_message="config root is not an object, using defaults")

    threshold, threshold_warning = parse_decimal_setting(
        payload,
        "low_balance_alert_threshold_usd",
        defaults.low_balance_alert_threshold_usd,
    )
    interval, interval_warning = parse_float_setting(
        payload,
        "flash_interval_seconds",
        defaults.flash_interval_seconds,
    )

    warnings = [warning for warning in [threshold_warning, interval_warning] if warning]
    return AppSettings(
        low_balance_alert_threshold_usd=threshold,
        flash_interval_seconds=interval,
        warning_message="; ".join(warnings) if warnings else None,
    )


def default_app_settings() -> AppSettings:
    return AppSettings(
        low_balance_alert_threshold_usd=DEFAULT_LOW_BALANCE_ALERT_THRESHOLD_USD,
        flash_interval_seconds=DEFAULT_LOW_BALANCE_FLASH_INTERVAL_SECONDS,
    )


def write_default_settings_file(config_path: Path) -> bool:
    payload = {
        "low_balance_alert_threshold_usd": float(DEFAULT_LOW_BALANCE_ALERT_THRESHOLD_USD),
        "flash_interval_seconds": DEFAULT_LOW_BALANCE_FLASH_INTERVAL_SECONDS,
    }
    try:
        config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return True
    except Exception:
        return False


def parse_decimal_setting(
    payload: dict[str, Any],
    key: str,
    default: Decimal,
) -> tuple[Decimal, str | None]:
    value = payload.get(key, default)
    if isinstance(value, bool):
        return default, f"{key} is not numeric"

    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default, f"{key} is not numeric"

    if not parsed.is_finite():
        return default, f"{key} must be finite"
    if parsed < Decimal("0"):
        return default, f"{key} must be >= 0"
    return parsed.quantize(Decimal("0.01")), None


def parse_float_setting(
    payload: dict[str, Any],
    key: str,
    default: float,
) -> tuple[float, str | None]:
    value = payload.get(key, default)
    if isinstance(value, bool):
        return default, f"{key} is not numeric"

    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default, f"{key} is not numeric"

    if not math.isfinite(parsed):
        return default, f"{key} must be finite"
    if parsed <= 0:
        return default, f"{key} must be > 0"
    return parsed, None


def run_diagnostics() -> None:
    settings = load_app_settings()
    print(APP_NAME)
    print("Diagnostics")
    print("")
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    print("")
    print("Required packages:")
    for label, module_name in [
        ("pystray", "pystray"),
        ("Pillow", "PIL.Image"),
        ("requests", "requests"),
    ]:
        print(f"  {label}: {diagnose_import(module_name)}")

    print("")
    print("Environment:")
    print(f"  xAI Management Key (XAI_MGMT_KEY): {diagnose_env_var('XAI_MGMT_KEY')}")
    print(f"  XAI_TEAM_ID: {diagnose_env_var('XAI_TEAM_ID')}")
    print(f"  XAI_PREPAID_TOTAL_FIELD_PATH: {diagnose_env_var('XAI_PREPAID_TOTAL_FIELD_PATH')}")
    print(f"  XAI_PREPAID_USED_FIELD_PATH: {diagnose_env_var('XAI_PREPAID_USED_FIELD_PATH')}")
    print("")
    print(f"Cache path: {CACHE_PATH}")
    print(f"Config path: {CONFIG_PATH}")
    print(f"Loaded low-balance threshold: {format_usd(settings.low_balance_alert_threshold_usd)}")
    print(f"Loaded flash interval: {settings.flash_interval_seconds:g} seconds")
    if settings.warning_message:
        print(f"Config warning: {settings.warning_message}")
    print("")
    print("Provider:")
    for provider_name in diagnose_provider_names():
        print(f"  {provider_name}")
    print("")
    print("No API calls were made. Tray app was not started.")


def diagnose_import(module_name: str) -> str:
    try:
        importlib.import_module(module_name)
    except Exception as exc:
        return f"missing or failed import ({exc.__class__.__name__})"
    return "OK"


def diagnose_env_var(name: str) -> str:
    return "set" if os.environ.get(name) else "not set"


def diagnose_provider_names() -> list[str]:
    return [CONFIGURED_PROVIDER_NAME]


def format_bool(value: bool) -> str:
    return "yes" if value else "no"


def run_debug_once() -> int:
    print(APP_NAME)
    print("Debug once")
    print("")
    print("Tray app was not started. No loop will run.")
    print("")
    print("Environment:")
    print(f"  xAI Management Key (XAI_MGMT_KEY): {diagnose_env_var('XAI_MGMT_KEY')}")
    print(f"  XAI_TEAM_ID: {diagnose_env_var('XAI_TEAM_ID')}")
    print(f"  XAI_PREPAID_TOTAL_FIELD_PATH: {diagnose_env_var('XAI_PREPAID_TOTAL_FIELD_PATH')}")
    print(f"  XAI_PREPAID_USED_FIELD_PATH: {diagnose_env_var('XAI_PREPAID_USED_FIELD_PATH')}")
    print("")
    print(f"Cache path: {CACHE_PATH}")

    try:
        load_provider_dependencies()
    except Exception as exc:
        print("")
        print(f"Provider load failed: {exc.__class__.__name__}")
        return 1

    manager = RefreshManager(XaiProvider(), CACHE_PATH)

    print("")
    print("Provider loaded:")
    print(f"  {manager.provider.provider_name}: enabled")

    print("")
    print("Refreshing xAI once...")
    manager.refresh_xai()

    print("")
    print("Results:")
    xai_result = manager.current_result()
    print_debug_result(xai_result)

    print("")
    print(f"Cache written: {format_bool(manager.last_cache_write_succeeded)}")

    xai_configured = bool(os.environ.get("XAI_MGMT_KEY")) and bool(os.environ.get("XAI_TEAM_ID"))
    if xai_configured and xai_result.status != STATUS_OK:
        return 1
    return 0


def run_debug_billing_fields() -> int:
    print(APP_NAME)
    print("Debug billing fields")
    print("")
    print("Tray app was not started. Full prepaid billing JSON will not be printed.")
    print("")
    print("Environment:")
    print(f"  xAI Management Key (XAI_MGMT_KEY): {diagnose_env_var('XAI_MGMT_KEY')}")
    print(f"  XAI_TEAM_ID: {diagnose_env_var('XAI_TEAM_ID')}")

    try:
        load_provider_dependencies()
        xai_provider = importlib.import_module("providers.xai_provider")
    except Exception as exc:
        print("")
        print(f"Provider load failed: {exc.__class__.__name__}")
        return 1

    selected_path = xai_provider.selected_balance_field_path()
    print("Endpoint: GET /v1/billing/teams/{team_id}/prepaid/balance")
    print(f"Selected prepaid-total field path: {selected_path}")
    print("")

    try:
        payload, status_code = xai_provider.fetch_prepaid_balance_payload()
    except Exception as exc:
        print(f"HTTP status: {getattr(exc, 'http_status_code', 'unavailable')}")
        print(f"Error: {xai_provider.safe_error_message(exc)}")
        print(f"Selected prepaid-total field path: {getattr(exc, 'balance_field_path', selected_path)}")
        return 1

    print(f"HTTP status: {status_code}")
    top_keys = xai_provider.top_level_keys(payload)
    print(f"Top-level keys: {', '.join(top_keys) if top_keys else '(none)'}")
    print(f"Selected prepaid-total field path: {selected_path}")
    print("")
    print("Safe billing numeric candidates:")
    candidates = xai_provider.billing_numeric_candidates(payload)
    if not candidates:
        print("  (none found)")
    for path, value in candidates:
        print(f"  {path}: {value}")
    return 0


def run_debug_usage_fields() -> int:
    print(APP_NAME)
    print("Debug usage fields")
    print("")
    print("Tray app was not started. Full billing usage JSON will not be printed.")
    print("")
    print("Environment:")
    print(f"  xAI Management Key (XAI_MGMT_KEY): {diagnose_env_var('XAI_MGMT_KEY')}")
    print(f"  XAI_TEAM_ID: {diagnose_env_var('XAI_TEAM_ID')}")

    try:
        load_provider_dependencies()
        xai_provider = importlib.import_module("providers.xai_provider")
    except Exception as exc:
        print("")
        print(f"Provider load failed: {exc.__class__.__name__}")
        return 1

    selected_path = xai_provider.selected_used_field_path()
    print("Endpoint: GET /v1/billing/teams/{team_id}/postpaid/invoice/preview")
    print(f"Selected prepaid-used field path: {selected_path}")
    print("")

    try:
        payload, status_code = xai_provider.fetch_billing_usage_payload()
    except Exception as exc:
        print(f"HTTP status: {getattr(exc, 'http_status_code', 'unavailable')}")
        print(f"Error: {xai_provider.safe_error_message(exc)}")
        print(f"Selected prepaid-used field path: {getattr(exc, 'used_field_path', selected_path)}")
        return 1

    print(f"HTTP status: {status_code}")
    top_keys = xai_provider.top_level_keys(payload)
    print(f"Top-level keys: {', '.join(top_keys) if top_keys else '(none)'}")
    print(f"Selected prepaid-used field path: {selected_path}")
    print("")
    print("Safe billing usage numeric candidates:")
    candidates = xai_provider.billing_numeric_candidates(payload)
    if not candidates:
        print("  (none found)")
    for path, value in candidates:
        print(f"  {path}: {value}")
    return 0


def print_debug_result(result: Any) -> None:
    print(f"  {result.provider_name}:")
    print(f"    Status: {format_status(result)}")
    print("    Enabled: yes")
    print(f"    API call made: {format_bool(result.api_call_made)}")
    if result.api_call_made:
        print(f"    Prepaid total HTTP status: {format_optional_status(result.prepaid_http_status_code)}")
        print(f"    Billing usage HTTP status: {format_optional_status(result.usage_http_status_code)}")
        if result.raw_top_level_keys:
            print(f"    Prepaid top-level billing keys: {', '.join(result.raw_top_level_keys)}")
        if result.usage_top_level_keys:
            print(f"    Usage top-level billing keys: {', '.join(result.usage_top_level_keys)}")
    if result.balance_field_path:
        print(f"    Prepaid total field path: {result.balance_field_path}")
    if result.used_field_path:
        print(f"    Prepaid used field path: {result.used_field_path}")

    if result.prepaid_total_usd is not None:
        print(f"    Prepaid total: {format_usd(result.prepaid_total_usd)}")
    if result.prepaid_used_usd is not None:
        print(f"    Prepaid used: {format_usd(result.prepaid_used_usd)}")
    if result.remaining_credit_usd is not None:
        label = "Parsed remaining credit" if result.status == STATUS_OK else "Cached remaining credit"
        print(f"    {label}: {format_usd(result.remaining_credit_usd)}")

    if result.error_message:
        print(f"    Error: {result.error_message}")


class RefreshManager:
    def __init__(self, provider: Any, cache_path: Path) -> None:
        self.provider = provider
        self.cache_path = cache_path
        self.refresh_lock = threading.Lock()
        self.results_lock = threading.RLock()
        self.result: Any | None = None
        self.last_refresh_utc: datetime | None = None
        self.last_cache_write_succeeded = False

        self.load_cache()
        self.seed_provider_defaults()

    def try_acquire_refresh(self) -> bool:
        return self.refresh_lock.acquire(blocking=False)

    def release_refresh(self) -> None:
        self.refresh_lock.release()

    def refresh_xai(self) -> None:
        self.last_cache_write_succeeded = False
        result = self.provider.get_balance()

        if result.status == STATUS_OK:
            with self.results_lock:
                self.result = result
        else:
            # Keep the last known credit visible when a live refresh fails.
            with self.results_lock:
                cached = self.result
                if cached and cached.balance_usd is not None:
                    self.result = replace(
                        cached,
                        status=STATUS_WARNING,
                        error_message=result.error_message,
                        api_call_made=result.api_call_made,
                        http_status_code=result.http_status_code,
                        prepaid_http_status_code=result.prepaid_http_status_code,
                        usage_http_status_code=result.usage_http_status_code,
                        raw_top_level_keys=result.raw_top_level_keys,
                        usage_top_level_keys=result.usage_top_level_keys,
                        balance_field_path=result.balance_field_path,
                        used_field_path=result.used_field_path,
                    )
                else:
                    self.result = result

        with self.results_lock:
            self.last_refresh_utc = datetime.now(UTC)
        if result.status == STATUS_OK and result.balance_usd is not None:
            self.last_cache_write_succeeded = self.save_cache()

    def current_result(self) -> Any:
        with self.results_lock:
            if self.result is not None:
                return self.result
            return ProviderResult(
                provider_name=self.provider.provider_name,
                balance_usd=None,
                status=STATUS_PENDING,
                last_updated_utc=datetime.now(UTC),
                error_message=None,
            )

    def load_cache(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            return

        if not self.cache_path.exists():
            write_empty_cache_file(self.cache_path)
            return

        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            return

        with self.results_lock:
            self.last_refresh_utc = parse_datetime(payload.get("last_refresh_utc"))

        result = provider_result_from_cache(CONFIGURED_PROVIDER_NAME, payload)
        if result is None:
            result = provider_result_from_legacy_cache(payload)
        if result is not None:
            with self.results_lock:
                self.result = result

    def save_cache(self) -> bool:
        with self.results_lock:
            last_refresh_utc = self.last_refresh_utc
            result = self.result

        if (
            result is None
            or result.prepaid_total_usd is None
            or result.prepaid_used_usd is None
            or result.remaining_credit_usd is None
        ):
            return False
        if result.status not in {STATUS_OK, STATUS_CACHED, STATUS_WARNING}:
            return False

        payload = {
            "provider_name": CONFIGURED_PROVIDER_NAME,
            "prepaid_total_usd": format_decimal_for_cache(result.prepaid_total_usd),
            "prepaid_used_usd": format_decimal_for_cache(result.prepaid_used_usd),
            "remaining_credit_usd": format_decimal_for_cache(result.remaining_credit_usd),
            "status": STATUS_OK,
            "last_updated_utc": result.last_updated_utc.isoformat(),
            "last_refresh_utc": (
                last_refresh_utc.isoformat() if last_refresh_utc else None
            ),
        }

        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.cache_path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            temp_path.replace(self.cache_path)
            return True
        except Exception:
            return False

    def seed_provider_defaults(self) -> None:
        with self.results_lock:
            has_result = self.result is not None
        if has_result:
            return

        initial_result = self.provider.initial_result()
        if initial_result is not None:
            with self.results_lock:
                self.result = initial_result


class XaiRemainingApp:
    def __init__(self, debug_tray: bool = False) -> None:
        self.icon: Any = None
        self.stop_event = threading.Event()
        self.state_lock = threading.RLock()
        self.settings = load_app_settings()
        self.is_refreshing = False
        self.tray_ready = False
        self.low_balance_alert_active = False
        self.flash_show_warning = False
        self.refresh_thread: threading.Thread | None = None
        self.flasher_thread: threading.Thread | None = None
        self.debug_tray = debug_tray
        self.manager = RefreshManager(XaiProvider(), CACHE_PATH)
        if self.settings.warning_message:
            self.debug_log(f"config warning: {self.settings.warning_message}")

    def run(self) -> None:
        self.debug_log("creating icon")
        menu = pystray.Menu(
            pystray.MenuItem(lambda item: self.menu_status_text(), self.noop, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Refresh now", self.refresh_now),
            pystray.MenuItem("Open xAI Billing Console", self.open_billing_console),
            pystray.MenuItem("Exit", self.exit_app),
        )
        self.icon = pystray.Icon(
            APP_NAME,
            self.make_placeholder_icon_image(),
            APP_NAME,
            menu,
        )
        self.debug_log("starting icon loop")
        try:
            self.icon.run(setup=self.setup)
        except Exception as exc:
            self.debug_log(f"sanitized tray error: {exc.__class__.__name__}")
            raise

    def setup(self, icon: Any) -> None:
        self.debug_log("setup callback entered")
        self.icon = icon
        self.apply_placeholder_icon()
        with self.state_lock:
            self.tray_ready = True
        self.start_refresh_thread()
        threading.Thread(target=self.refresh_loop, name="xai-refresh-loop", daemon=True).start()

    def refresh_loop(self) -> None:
        while not self.stop_event.wait(REFRESH_INTERVAL_SECONDS):
            self.start_refresh_thread()

    def start_refresh_thread(self, show_refreshing: bool = False) -> None:
        if not self.manager.try_acquire_refresh():
            return

        self.debug_log("refresh started")
        if show_refreshing:
            with self.state_lock:
                self.is_refreshing = True
            self.update_tray()

        refresh_thread = threading.Thread(
            target=self.refresh_balance,
            name="xai-refresh",
            daemon=True,
        )
        self.refresh_thread = refresh_thread
        try:
            refresh_thread.start()
        except Exception as exc:
            with self.state_lock:
                self.is_refreshing = False
            self.manager.release_refresh()
            self.debug_log(f"sanitized tray error: {exc.__class__.__name__}")
            self.update_tray()

    def refresh_now(self, icon: Any, item: Any) -> None:
        self.start_refresh_thread(show_refreshing=True)

    def refresh_balance(self) -> None:
        try:
            self.manager.refresh_xai()
        except Exception as exc:
            self.debug_log(f"sanitized tray error: {exc.__class__.__name__}")
        finally:
            with self.state_lock:
                self.is_refreshing = False
            self.manager.release_refresh()
            self.debug_log("refresh completed")
            if not self.stop_event.is_set():
                self.update_tray()

    def update_tray(self) -> None:
        icon = self.icon
        if icon is None or self.stop_event.is_set():
            return

        with self.state_lock:
            if not self.tray_ready:
                return
            result = self.manager.current_result()
            title = self.hover_title_text(result)
            self.configure_low_balance_alert(result)
            use_warning_icon = self.flash_show_warning

        try:
            icon.icon = self.make_icon_for_current_alert_state(result, use_warning_icon)
            icon.title = title
            icon.update_menu()
            self.debug_log("icon updated")
        except Exception as exc:
            self.debug_log(f"sanitized tray error: {exc.__class__.__name__}")

    def apply_placeholder_icon(self) -> None:
        icon = self.icon
        if icon is None:
            return

        try:
            icon.icon = self.make_placeholder_icon_image()
            icon.title = STARTING_TITLE
            icon.visible = True
            icon.update_menu()
            self.debug_log("placeholder icon applied")
        except Exception as exc:
            self.debug_log(f"sanitized tray error: {exc.__class__.__name__}")

    def configure_low_balance_alert(self, result: Any) -> None:
        should_alert = low_balance_alert_should_flash(
            result,
            self.settings.low_balance_alert_threshold_usd,
        )
        self.low_balance_alert_active = should_alert
        if not should_alert:
            self.flash_show_warning = False
            return

        if self.flasher_thread and self.flasher_thread.is_alive():
            return

        self.flasher_thread = threading.Thread(
            target=self.flash_loop,
            name="xai-low-balance-flasher",
            daemon=True,
        )
        self.flasher_thread.start()

    def flash_loop(self) -> None:
        while not self.stop_event.wait(self.settings.flash_interval_seconds):
            with self.state_lock:
                # The flasher exits as soon as refresh state clears the alert.
                if not self.tray_ready or not self.low_balance_alert_active:
                    return
                self.flash_show_warning = not self.flash_show_warning
                use_warning_icon = self.flash_show_warning
                result = self.manager.current_result()

            self.apply_flash_icon(result, use_warning_icon)

    def apply_flash_icon(self, result: Any, use_warning_icon: bool) -> None:
        icon = self.icon
        if icon is None or self.stop_event.is_set():
            return

        try:
            with self.state_lock:
                if not self.tray_ready:
                    return
            icon.icon = self.make_icon_for_current_alert_state(result, use_warning_icon)
            icon.title = self.hover_title_text(result)
        except Exception as exc:
            self.debug_log(f"sanitized tray error: {exc.__class__.__name__}")

    def hover_title_text(self, result: Any) -> str:
        if result.status in {STATUS_ERROR, STATUS_WARNING}:
            return "xAI refresh failed"

        remaining_credit = remaining_credit_value(result)
        if remaining_credit is not None:
            return f"xAI {format_usd(remaining_credit)} remaining"

        return "xAI refresh failed"

    def menu_status_text(self) -> str:
        with self.state_lock:
            if self.is_refreshing:
                return "Refreshing..."
            result = self.manager.current_result()

        remaining_credit = remaining_credit_value(result)
        if remaining_credit is not None:
            if result.status == STATUS_WARNING and result.error_message:
                return f"xAI refresh failed | cached {format_usd(remaining_credit)} remaining"
            if result.prepaid_total_usd is not None and result.prepaid_used_usd is not None:
                return (
                    f"xAI {format_usd(remaining_credit)} remaining | "
                    f"{format_usd(result.prepaid_used_usd)} used of "
                    f"{format_usd(result.prepaid_total_usd)}"
                )
            if result.prepaid_used_usd is not None:
                return (
                    f"xAI {format_usd(remaining_credit)} remaining | "
                    f"{format_usd(result.prepaid_used_usd)} used"
                )
            return f"xAI {format_usd(remaining_credit)} remaining"
        if result.status == STATUS_ERROR:
            return "xAI error"
        return "xAI credit unavailable"

    def make_icon_image(self, result: Any) -> Any:
        state = aggregate_visual_state(result)
        label = "!" if state == "error" else "xAI"

        image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), ICON_COLORS[state])
        draw = ImageDraw.Draw(image)

        draw.rectangle(
            (0, 0, ICON_SIZE - 1, ICON_SIZE - 1),
            outline=(255, 255, 255, 210),
            width=2,
        )

        if state == "error":
            font = fit_font(
                draw,
                label,
                max_width=ICON_TEXT_MAX_WIDTH,
                max_height=ICON_TEXT_MAX_HEIGHT,
                start_size=40,
                min_size=10,
            )
            draw_centered_text(draw, label, font=font, fill=(255, 255, 255, 255))
        else:
            xai_amount = xai_icon_amount(result)
            if xai_amount is not None:
                draw_xai_credit_text(draw, xai_amount, fill=(255, 255, 255, 255))
            else:
                font = fit_font(
                    draw,
                    label,
                    max_width=ICON_TEXT_MAX_WIDTH,
                    max_height=ICON_TEXT_MAX_HEIGHT,
                    start_size=40,
                    min_size=10,
                )
                draw_centered_text(draw, label, font=font, fill=(255, 255, 255, 255))
        return image

    def make_icon_for_current_alert_state(self, result: Any, use_warning_icon: bool) -> Any:
        if use_warning_icon:
            return self.make_low_balance_warning_icon_image()
        return self.make_icon_image(result)

    def make_low_balance_warning_icon_image(self) -> Any:
        image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), ICON_COLORS["critical"])
        draw = ImageDraw.Draw(image)
        draw.rectangle(
            (0, 0, ICON_SIZE - 1, ICON_SIZE - 1),
            outline=(255, 255, 255, 230),
            width=2,
        )
        font = fit_font(
            draw,
            "LOW",
            max_width=ICON_TEXT_MAX_WIDTH,
            max_height=ICON_TEXT_MAX_HEIGHT,
            start_size=34,
            min_size=10,
        )
        draw_centered_text(draw, "LOW", font=font, fill=(255, 255, 255, 255))
        return image

    def make_placeholder_icon_image(self) -> Any:
        image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), ICON_COLORS["starting"])
        draw = ImageDraw.Draw(image)
        draw.rectangle(
            (0, 0, ICON_SIZE - 1, ICON_SIZE - 1),
            outline=(255, 255, 255, 210),
            width=2,
        )
        font = fit_font(
            draw,
            "X?",
            max_width=ICON_TEXT_MAX_WIDTH,
            max_height=ICON_TEXT_MAX_HEIGHT,
            start_size=40,
            min_size=10,
        )
        draw_centered_text(draw, "X?", font=font, fill=(255, 255, 255, 255))
        return image

    def open_billing_console(self, icon: Any, item: Any) -> None:
        webbrowser.open(BILLING_CONSOLE_URL)

    def exit_app(self, icon: Any, item: Any) -> None:
        self.stop_event.set()
        with self.state_lock:
            self.tray_ready = False
            self.low_balance_alert_active = False
            self.flash_show_warning = False
        try:
            icon.stop()
        except Exception as exc:
            self.debug_log(f"sanitized tray error: {exc.__class__.__name__}")

    def noop(self, icon: Any, item: Any) -> None:
        return

    def debug_log(self, message: str) -> None:
        if self.debug_tray:
            print(message, flush=True)


def provider_result_from_cache(provider_name: str, raw_result: Any) -> Any:
    if not isinstance(raw_result, dict):
        return None

    raw_prepaid_total = raw_result.get("prepaid_total_usd")
    raw_prepaid_used = raw_result.get("prepaid_used_usd")
    if raw_prepaid_total is None or raw_prepaid_used is None:
        return None

    prepaid_total_usd = parse_cache_usd(raw_prepaid_total)
    prepaid_used_usd = parse_cache_usd(raw_prepaid_used)
    if prepaid_total_usd is None or prepaid_used_usd is None:
        return None

    remaining_credit_usd = (prepaid_total_usd - prepaid_used_usd).quantize(Decimal("0.01"))
    last_updated_utc = parse_datetime(raw_result.get("last_updated_utc"))
    if last_updated_utc is None:
        last_updated_utc = datetime.now(UTC)

    return ProviderResult(
        provider_name=provider_name,
        balance_usd=remaining_credit_usd,
        prepaid_total_usd=prepaid_total_usd,
        prepaid_used_usd=prepaid_used_usd,
        remaining_credit_usd=remaining_credit_usd,
        status=STATUS_CACHED,
        last_updated_utc=last_updated_utc,
        error_message=None,
    )


def parse_cache_usd(value: Any) -> Decimal | None:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite():
        return None
    return amount.quantize(Decimal("0.01"))


def provider_result_from_legacy_cache(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return None

    providers = payload.get("providers")
    if not isinstance(providers, dict):
        return None

    return provider_result_from_cache(CONFIGURED_PROVIDER_NAME, providers.get(CONFIGURED_PROVIDER_NAME))


def write_empty_cache_file(cache_path: Path) -> bool:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"provider_name": CONFIGURED_PROVIDER_NAME}, indent=2) + "\n",
            encoding="utf-8",
        )
        return True
    except Exception:
        return False


def parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def format_status(result: Any) -> str:
    status = result.status.lower()
    if status == STATUS_OK:
        return "OK"
    if status == STATUS_CACHED:
        return "Cached"
    if status == STATUS_WARNING:
        return append_error("Warning", result.error_message)
    if status == STATUS_ERROR:
        return append_error("Error", result.error_message)
    if status == STATUS_PENDING:
        return "Pending"
    return status.title()


def append_error(prefix: str, error_message: str | None) -> str:
    if not error_message:
        return prefix
    return f"{prefix} - {error_message}"


def format_usd(amount: Decimal) -> str:
    return f"${amount:,.2f}"


def format_optional_status(status_code: int | None) -> str:
    if status_code is None:
        return "unavailable"
    return str(status_code)


def format_decimal_for_cache(amount: Decimal) -> str:
    return f"{amount:.2f}"


def remaining_credit_value(result: Any) -> Decimal | None:
    if result.remaining_credit_usd is not None:
        return result.remaining_credit_usd
    return result.balance_usd


def low_balance_alert_should_flash(result: Any, threshold_usd: Decimal) -> bool:
    remaining_credit = remaining_credit_value(result)
    return (
        remaining_credit is not None
        and remaining_credit <= threshold_usd
    )


def aggregate_visual_state(result: Any) -> str:
    remaining_credit = remaining_credit_value(result)
    if remaining_credit is not None and remaining_credit < CRITICAL_BALANCE_DOLLARS:
        return "critical"

    if result.status == STATUS_ERROR:
        return "warning" if remaining_credit is not None else "error"

    if remaining_credit is not None and remaining_credit < WARNING_BALANCE_DOLLARS:
        return "warning"

    if result.status == STATUS_OK:
        return "normal"

    return "warning"


def xai_icon_amount(result: Any) -> str | None:
    remaining_credit = remaining_credit_value(result)
    if remaining_credit is not None:
        return format_icon_amount(remaining_credit)
    return None


def format_icon_amount(dollars: Decimal) -> str:
    whole_dollars = int(dollars.to_integral_value(rounding=ROUND_FLOOR))
    if whole_dollars < 1000:
        return str(whole_dollars)

    if whole_dollars < 10000:
        compact = (Decimal(whole_dollars) / Decimal("1000")).quantize(Decimal("0.1"))
        compact_text = f"{compact:.1f}".rstrip("0").rstrip(".")
        return f"{compact_text}k"

    return f"{whole_dollars // 1000}k"


def load_font(size: int, bold: bool = False) -> Any:
    font_names = ["segoeuib.ttf", "arialbd.ttf"] if bold else ["segoeui.ttf", "arial.ttf"]
    for font_name in font_names:
        try:
            return ImageFont.truetype(font_name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def fit_font(
    draw: Any,
    text: str,
    max_width: int,
    max_height: int,
    start_size: int,
    min_size: int,
) -> Any:
    for size in range(start_size, min_size - 1, -1):
        font = load_font(size, bold=True)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width and bbox[3] - bbox[1] <= max_height:
            return font
    return load_font(min_size, bold=True)


def draw_centered_text(
    draw: Any,
    text: str,
    font: Any,
    fill: tuple[int, int, int, int],
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x = (ICON_SIZE - width) // 2 - bbox[0]
    y = (ICON_SIZE - height) // 2 - bbox[1] - 1
    draw.text((x, y), text, font=font, fill=fill)


def draw_xai_credit_text(
    draw: Any,
    amount_text: str,
    fill: tuple[int, int, int, int],
) -> None:
    credit_text = f"${amount_text}"

    for amount_size in range(30, 11, -1):
        brand_size = min(18, max(12, amount_size // 2 + 4))
        brand_font = load_font(brand_size, bold=True)
        amount_font = load_font(amount_size, bold=True)

        brand_bbox = draw.textbbox((0, 0), "xAI", font=brand_font)
        amount_bbox = draw.textbbox((0, 0), credit_text, font=amount_font)
        brand_width = brand_bbox[2] - brand_bbox[0]
        brand_height = brand_bbox[3] - brand_bbox[1]
        amount_width = amount_bbox[2] - amount_bbox[0]
        amount_height = amount_bbox[3] - amount_bbox[1]
        gap = 1
        total_height = brand_height + gap + amount_height

        if (
            brand_width <= ICON_TEXT_MAX_WIDTH
            and amount_width <= ICON_TEXT_MAX_WIDTH
            and total_height <= ICON_TEXT_MAX_HEIGHT
        ):
            start_y = (ICON_SIZE - total_height) // 2
            brand_x = (ICON_SIZE - brand_width) // 2 - brand_bbox[0]
            brand_y = start_y - brand_bbox[1]
            amount_x = (ICON_SIZE - amount_width) // 2 - amount_bbox[0]
            amount_y = start_y + brand_height + gap - amount_bbox[1]
            draw.text((brand_x, brand_y), "xAI", font=brand_font, fill=fill)
            draw.text((amount_x, amount_y), credit_text, font=amount_font, fill=fill)
            return

    font = fit_font(
        draw,
        "xAI",
        max_width=ICON_TEXT_MAX_WIDTH,
        max_height=ICON_TEXT_MAX_HEIGHT,
        start_size=32,
        min_size=10,
    )
    draw_centered_text(draw, "xAI", font=font, fill=fill)


if __name__ == "__main__":
    main()
