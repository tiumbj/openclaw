import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import requests


def load_dotenv_file(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        current = os.environ.get(key)
        if current is None or not str(current).strip():
            os.environ[key] = value


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_json_file(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def load_trading_config(path: str = "trading_config.json") -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        "runtime": {
            "default_symbol": "XAUUSD",
            "trade_check_interval_seconds": 30,
            "enable_signal_csv_log": True,
        },
        "sensitivity": {
            "level": 2,
            "min_distance_points": {"min": 20, "base": 50, "per_level_delta": 10},
            "gatekeeper_cooldown_seconds": {"min": 60, "base": 120, "per_level_delta": 30},
            "gatekeeper_atr_multiplier": {"min": 1.0, "base": 1.4, "per_level_delta": 0.12},
            "gatekeeper_min_points": {"min": 40.0, "base": 90.0, "per_level_delta": 15.0},
            "confluence_threshold_delta_per_level": 4.0,
        },
        "mtf": {
            "scan_timeframes": ["M5", "M15", "M30", "H1"],
            "weights": {"M5": 0.20, "M15": 0.25, "M30": 0.25, "H1": 0.30},
            "min_timeframes_required": 2,
        },
        "market_filters": {
            "max_spread_points": 200,
        },
        "risk": {
            "max_open_trades": 4,
            "max_risk_usd": 200.0,
        },
        "sl_tp": {
            "timeframe_profiles": {
                "M5": {"sl_atr_multiplier": 0.75, "rr_ratio": 1.4, "sl_min_points": 30.0, "sl_max_points": 120.0},
                "M15": {"sl_atr_multiplier": 1.00, "rr_ratio": 1.7, "sl_min_points": 50.0, "sl_max_points": 180.0},
                "M30": {"sl_atr_multiplier": 1.25, "rr_ratio": 2.0, "sl_min_points": 80.0, "sl_max_points": 260.0},
                "H1": {"sl_atr_multiplier": 1.50, "rr_ratio": 2.2, "sl_min_points": 110.0, "sl_max_points": 360.0},
            }
        },
        "confluence_thresholds": {
            "base_by_timeframe": {"M5": 34.0, "M15": 40.0, "M30": 46.0, "H1": 50.0},
            "default": 42.0,
            "regime_adjustments": {
                "VOLATILE_CHAOS": 8.0,
                "LIQUIDITY_CRISIS": 10.0,
                "MEAN_REVERTING": 4.0,
                "TRENDING": -2.0,
                "QUIET": -1.0
            },
            "min": 30.0,
            "max": 58.0,
        },
        "execution_filters": {
            "one_trade_per_candle": True,
            "momentum_candle_guard": True,
            "momentum_candle_atr_ratio": 0.55,
        },
        "telegram": {
            "enabled": True,
            "startup_notify": True,
            "order_notify": True,
            "timeout_seconds": 10,
        },
        "help": {
            "sensitivity.level": "0-3: ยิ่งสูงยิ่งเข้าเงื่อนไขง่ายขึ้นและเทรดถี่ขึ้น แต่เสี่ยงโดน noise มากขึ้น",
            "runtime.trade_check_interval_seconds": "ยิ่งน้อยยิ่งเช็คบ่อย/ถี่ขึ้น แต่เสี่ยงยิงถี่ในช่วงตลาดสวิงและโหลดระบบมากขึ้น",
            "market_filters.max_spread_points": "สเปรดสูง = ค่าเข้าแพง/โดนไส้เทียนง่าย ถ้าต่ำเกินไปอาจพลาดโอกาส",
            "mtf.min_timeframes_required": "ขั้นต่ำของ TF ที่ต้องมีข้อมูลสำหรับคำนวณ confluence ถ้าสูงขึ้นจะปลอดภัยขึ้นแต่เทรดน้อยลง",
            "risk.max_risk_usd": "ความเสี่ยงเป็น USD ต่อ 1 ออเดอร์ ยิ่งสูง PnL แกว่งสูงขึ้น",
            "risk.max_open_trades": "จำกัดจำนวนออเดอร์ค้าง ยิ่งสูงยิ่งเพิ่ม exposure และความเสี่ยงรวมหากตลาดวิ่งสวน",
            "sl_tp.timeframe_profiles": "SL/TP ตาม TF: TF เล็ก SL/TP เล็ก (ไว/โดน stop ง่าย), TF ใหญ่ SL/TP ใหญ่ (นิ่งกว่าแต่ถือยาวขึ้น)",
        },
    }

    override: Dict[str, Any] = {}
    primary = Path("config.json")
    if primary.exists():
        override = load_json_file(str(primary))
    else:
        override = load_json_file(path)
    return _deep_merge(defaults, override)


class TelegramNotifier:
    def __init__(
        self,
        *,
        enabled: bool,
        token: str,
        chat_id: str,
        timeout_seconds: int = 10,
        preview_if_missing: bool = True,
    ):
        self.enabled = enabled
        self.token = token
        self.chat_id = chat_id
        self.timeout_seconds = timeout_seconds
        self.preview_if_missing = preview_if_missing

    @classmethod
    def from_env_and_config(cls, config: Dict[str, Any]) -> "TelegramNotifier":
        telegram_cfg = config.get("telegram", {}) if isinstance(config.get("telegram"), dict) else {}
        enabled = bool(telegram_cfg.get("enabled", True))
        timeout_seconds = int(telegram_cfg.get("timeout_seconds", 10))
        token = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
        chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
        return cls(
            enabled=enabled,
            token=token,
            chat_id=chat_id,
            timeout_seconds=timeout_seconds,
        )

    def send_html(self, message: str) -> bool:
        if not self.enabled:
            return False
        if not self.token or not self.chat_id:
            if self.preview_if_missing:
                print("⚠️ Telegram not configured (missing TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID)")
                print(f"📢 [Telegram Preview]\n{message}")
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}
        try:
            response = requests.post(url, json=payload, timeout=self.timeout_seconds)
            return response.status_code == 200
        except Exception:
            return False


@dataclass
class RiskParameters:
    max_drawdown: float = 0.15
    risk_per_trade: float = 0.02
    max_position_size: float = 0.1
    stop_loss_pct: float = 0.01
    take_profit_pct: float = 0.03
    max_consecutive_losses: int = 3
    volatility_threshold: float = 0.02


def is_market_open_enhanced(symbol: str = "XAUUSD") -> bool:
    try:
        import MetaTrader5 as mt5  # type: ignore
    except Exception:
        mt5 = None

    if mt5 is not None:
        tick = mt5.symbol_info_tick(symbol)
        if tick is not None:
            now = time.time()
            if (now - tick.time) <= 300:
                return True

    now_utc = datetime.now(timezone.utc)
    weekday = now_utc.weekday()
    hour = now_utc.hour

    if weekday >= 5:
        if weekday == 6 and hour >= 22:
            return True
        return False

    if 0 <= hour < 22:
        return True

    return False
