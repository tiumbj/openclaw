#!/usr/bin/env python3
"""
Advanced Live Trading Script with Volatility Management System
Enhanced version with Market Regime Detection and Adaptive Strategies
"""

import argparse
import csv
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Literal

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

# Import Advanced Volatility Management System
from advanced_volatility_system import AdvancedVolatilitySystem

# Import Institutional Execution Gatekeeper for XAUUSD
from execution_gatekeeper_optimized import GatekeeperDecision, InstitutionalExecutionGatekeeper
from oraclebot_pro_runtime import (
    TelegramNotifier,
    load_dotenv_file,
    load_trading_config,
)
from oraclebot_pro_runtime import (
    is_market_open_enhanced as runtime_is_market_open_enhanced,
)

# Import RiskFirewall for enterprise-grade risk management
from risk_firewall import RiskFirewall

# Global instances
RISK_FIREWALL = None
EXECUTION_GATEKEEPER = None
VOLATILITY_SYSTEM = None
load_dotenv_file()
CONFIG: Dict = load_trading_config()
TELEGRAM = TelegramNotifier.from_env_and_config(CONFIG)
EXECUTION_CANDLE_GUARD: Dict[str, int] = {}
EXECUTION_BAR_COOLDOWN_GUARD: Dict[str, int] = {}
LOG_DIR = Path(__file__).resolve().parent
SIGNAL_LOG_PATH = str(LOG_DIR / "advanced_signals_log.csv")
EVENT_LOG_PATH = str(LOG_DIR / "advanced_events_log.csv")

TIMEFRAME_NAME_TO_MT5: Dict[str, int] = {
    "M1": mt5.TIMEFRAME_M1,
    "M2": mt5.TIMEFRAME_M2,
    "M3": mt5.TIMEFRAME_M3,
    "M4": mt5.TIMEFRAME_M4,
    "M5": mt5.TIMEFRAME_M5,
    "M6": mt5.TIMEFRAME_M6,
    "M10": mt5.TIMEFRAME_M10,
    "M12": mt5.TIMEFRAME_M12,
    "M15": mt5.TIMEFRAME_M15,
    "M20": mt5.TIMEFRAME_M20,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H2": mt5.TIMEFRAME_H2,
    "H3": mt5.TIMEFRAME_H3,
    "H4": mt5.TIMEFRAME_H4,
}

MTF_WEIGHTS: Dict[int, float] = {}
_mtf_cfg = CONFIG.get("mtf", {}) if isinstance(CONFIG.get("mtf"), dict) else {}
for tf_name, weight in (_mtf_cfg.get("weights", {}) if isinstance(_mtf_cfg.get("weights"), dict) else {}).items():
    tf_mt5 = TIMEFRAME_NAME_TO_MT5.get(str(tf_name).upper())
    if tf_mt5 is not None:
        MTF_WEIGHTS[tf_mt5] = float(weight)
if not MTF_WEIGHTS:
    MTF_WEIGHTS = {
        mt5.TIMEFRAME_M5: 0.20,
        mt5.TIMEFRAME_M15: 0.25,
        mt5.TIMEFRAME_M30: 0.25,
        mt5.TIMEFRAME_H1: 0.30,
    }

SIGNAL_SCAN_TIMEFRAMES: List[int] = []
for tf_name in (_mtf_cfg.get("scan_timeframes", []) if isinstance(_mtf_cfg.get("scan_timeframes"), list) else []):
    tf_mt5 = TIMEFRAME_NAME_TO_MT5.get(str(tf_name).upper())
    if tf_mt5 is not None:
        SIGNAL_SCAN_TIMEFRAMES.append(tf_mt5)
if not SIGNAL_SCAN_TIMEFRAMES:
    SIGNAL_SCAN_TIMEFRAMES = [mt5.TIMEFRAME_M5, mt5.TIMEFRAME_M15, mt5.TIMEFRAME_M30, mt5.TIMEFRAME_H1]

TIMEFRAME_RISK_PROFILE: Dict[int, Dict[str, float]] = {}
_sl_tp_cfg = CONFIG.get("sl_tp", {}) if isinstance(CONFIG.get("sl_tp"), dict) else {}
_profiles = _sl_tp_cfg.get("timeframe_profiles", {}) if isinstance(_sl_tp_cfg.get("timeframe_profiles"), dict) else {}
for tf_name, profile in _profiles.items():
    tf_mt5 = TIMEFRAME_NAME_TO_MT5.get(str(tf_name).upper())
    if tf_mt5 is None or not isinstance(profile, dict):
        continue
    TIMEFRAME_RISK_PROFILE[tf_mt5] = {
        "sl_atr_multiplier": float(profile.get("sl_atr_multiplier", 1.0)),
        "rr_ratio": float(profile.get("rr_ratio", 1.7)),
        "sl_min_points": float(profile.get("sl_min_points", 50.0)),
        "sl_max_points": float(profile.get("sl_max_points", 180.0)),
    }
if not TIMEFRAME_RISK_PROFILE:
    TIMEFRAME_RISK_PROFILE = {
        mt5.TIMEFRAME_M5: {"sl_atr_multiplier": 0.75, "rr_ratio": 1.4, "sl_min_points": 30.0, "sl_max_points": 120.0},
        mt5.TIMEFRAME_M15: {"sl_atr_multiplier": 1.00, "rr_ratio": 1.7, "sl_min_points": 50.0, "sl_max_points": 180.0},
        mt5.TIMEFRAME_M30: {"sl_atr_multiplier": 1.25, "rr_ratio": 2.0, "sl_min_points": 80.0, "sl_max_points": 260.0},
        mt5.TIMEFRAME_H1: {"sl_atr_multiplier": 1.50, "rr_ratio": 2.2, "sl_min_points": 110.0, "sl_max_points": 360.0},
    }

def get_sensitivity_level() -> int:
    sensitivity_cfg = CONFIG.get("sensitivity", {}) if isinstance(CONFIG.get("sensitivity"), dict) else {}
    level = int(sensitivity_cfg.get("level", 2))
    return max(0, min(3, level))

def timeframe_label(timeframe: int) -> str:
    for name, tf_mt5 in TIMEFRAME_NAME_TO_MT5.items():
        if tf_mt5 == timeframe:
            return name
    return str(timeframe)

def get_timeframe_atr(symbol: str, timeframe: int) -> Optional[float]:
    df = get_market_data(symbol=symbol, timeframe=timeframe, bars=150)
    if df is None or len(df) < 30:
        return None
    return calculate_atr(df, period=14)

def get_adaptive_confluence_threshold(signal: Dict) -> float:
    sensitivity = get_sensitivity_level()
    timeframe = signal.get("source_timeframe", mt5.TIMEFRAME_M15)
    regime = signal.get("regime", "TRENDING")
    thresholds_cfg = CONFIG.get("confluence_thresholds", {}) if isinstance(CONFIG.get("confluence_thresholds"), dict) else {}
    base_by_tf = thresholds_cfg.get("base_by_timeframe", {}) if isinstance(thresholds_cfg.get("base_by_timeframe"), dict) else {}
    default_threshold = float(thresholds_cfg.get("default", 42.0))
    base_map: Dict[int, float] = {}
    for tf_name, v in base_by_tf.items():
        tf_mt5 = TIMEFRAME_NAME_TO_MT5.get(str(tf_name).upper())
        if tf_mt5 is not None:
            base_map[tf_mt5] = float(v)
    threshold = float(base_map.get(timeframe, default_threshold))

    regime_adj = thresholds_cfg.get("regime_adjustments", {}) if isinstance(thresholds_cfg.get("regime_adjustments"), dict) else {}
    if isinstance(regime, str) and regime in regime_adj:
        threshold += float(regime_adj.get(regime, 0.0))

    sensitivity_cfg = CONFIG.get("sensitivity", {}) if isinstance(CONFIG.get("sensitivity"), dict) else {}
    threshold -= float(sensitivity_cfg.get("confluence_threshold_delta_per_level", 4.0)) * float(sensitivity)

    floor_by_regime = thresholds_cfg.get("floor_by_regime", {}) if isinstance(thresholds_cfg.get("floor_by_regime"), dict) else {}
    default_floors = {
        "QUIET": 38.0,
        "MEAN_REVERTING": 34.0,
        "TRENDING": 32.0,
        "VOLATILE_CHAOS": 42.0,
        "LIQUIDITY_CRISIS": 46.0,
    }
    floor_value = None
    if isinstance(regime, str):
        floor_value = floor_by_regime.get(regime)
        if floor_value is None:
            floor_value = default_floors.get(regime)
    if floor_value is not None:
        try:
            threshold = max(float(threshold), float(floor_value))
        except Exception:
            pass

    min_v = float(thresholds_cfg.get("min", 30.0))
    max_v = float(thresholds_cfg.get("max", 58.0))
    return max(min_v, min(max_v, threshold))

def get_primary_symbol() -> str:
    runtime_cfg = CONFIG.get("runtime", {}) if isinstance(CONFIG.get("runtime"), dict) else {}
    preferred = str(runtime_cfg.get("default_symbol", "XAUUSD")).strip() or "XAUUSD"
    configured = runtime_cfg.get("symbol_aliases", [])
    aliases = configured if isinstance(configured, list) else []
    candidates: List[str] = [preferred, "XAUUSD", "GOLD", "XAUUSDm"]
    for alias in aliases:
        value = str(alias).strip()
        if value:
            candidates.append(value)

    deduped: List[str] = []
    for c in candidates:
        value = str(c).strip()
        if value and value not in deduped:
            deduped.append(value)

    for s in deduped:
        info = mt5.symbol_info(s)
        if info is None:
            continue
        if not info.visible:
            mt5.symbol_select(s, True)
            info = mt5.symbol_info(s)
        if info is not None and info.trade_mode != mt5.SYMBOL_TRADE_MODE_DISABLED:
            return s

    universe = mt5.symbols_get()
    if universe:
        for s in deduped:
            key = "".join(ch for ch in s.upper() if ch.isalnum())
            if not key:
                continue
            for symbol_info in universe:
                name = str(getattr(symbol_info, "name", "")).strip()
                normalized = "".join(ch for ch in name.upper() if ch.isalnum())
                if key in normalized:
                    mt5.symbol_select(name, True)
                    info = mt5.symbol_info(name)
                    if info is not None and info.trade_mode != mt5.SYMBOL_TRADE_MODE_DISABLED:
                        return name
    return deduped[0] if deduped else "XAUUSD"

def calculate_atr(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    if df is None or len(df) < period + 1:
        return None
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_series = tr.rolling(period).mean()
    value = float(atr_series.iloc[-1])
    if np.isnan(value):
        return None
    return value

def get_multi_tf_atr(symbol: str) -> Optional[float]:
    timeframes = [
        mt5.TIMEFRAME_M5,
        mt5.TIMEFRAME_M15,
        mt5.TIMEFRAME_M30,
        mt5.TIMEFRAME_H1,
    ]
    atr_values: List[float] = []
    for tf in timeframes:
        df = get_market_data(symbol=symbol, timeframe=tf, bars=120)
        if df is None or len(df) < 30:
            continue
        atr = calculate_atr(df, period=14)
        if atr is not None and atr > 0:
            atr_values.append(atr)
    if not atr_values:
        return None
    return float(np.median(atr_values))

def evaluate_mtf_confluence(symbol: str, direction: str) -> Tuple[float, Dict[str, float]]:
    aligned_score = 0.0
    total_weight = 0.0
    details: Dict[str, float] = {}
    for tf, weight in MTF_WEIGHTS.items():
        df = get_market_data(symbol=symbol, timeframe=tf, bars=120)
        if df is None or len(df) < 60:
            continue
        close = df["close"]
        ema_fast = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_slow = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
        recent_move = float(close.iloc[-1] - close.iloc[-6]) if len(close) >= 6 else float(close.diff().tail(5).sum())
        atr_value = calculate_atr(df, period=14)
        if atr_value is None or atr_value <= 0:
            continue
        ema_diff = ema_fast - ema_slow
        close_last = float(close.iloc[-1])
        sep_den = max(float(atr_value) * 0.5, abs(close_last) * 0.0005, 1e-9)
        separation = min(abs(ema_diff) / sep_den, 1.0)
        move_units = min(abs(recent_move) / max(float(atr_value), 1e-9), 1.0)
        is_aligned = (
            (direction == "BUY" and ema_diff > 0)
            or (direction == "SELL" and ema_diff < 0)
        )
        directional_momentum = 0.0
        if direction == "BUY":
            directional_momentum = max(0.0, min(1.0, recent_move / max(float(atr_value), 1e-9)))
        else:
            directional_momentum = max(0.0, min(1.0, (-recent_move) / max(float(atr_value), 1e-9)))
        strength = (0.65 * separation) + (0.20 * move_units) + (0.15 * directional_momentum)
        tf_score = (strength * 100.0) if is_aligned else 0.0
        if is_aligned:
            aligned_score += weight * tf_score
            total_weight += weight
        details[str(tf)] = round(tf_score, 2)
    if total_weight == 0:
        return 0.0, details
    return aligned_score / total_weight, details

def log_advanced_signal(signal: Dict):
    runtime_cfg = CONFIG.get("runtime", {}) if isinstance(CONFIG.get("runtime"), dict) else {}
    if not bool(runtime_cfg.get("enable_signal_csv_log", True)):
        return
    filepath = SIGNAL_LOG_PATH
    file_exists = os.path.isfile(filepath)
    fieldnames = [
        "timestamp",
        "symbol",
        "signal",
        "strategy",
        "exposure",
        "urgency",
        "regime",
        "mtf_confluence_score"
    ]
    urgency_value = signal.get("urgency", "")
    if hasattr(urgency_value, "name"):
        urgency_value = urgency_value.name
    with open(filepath, mode="a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": signal.get("symbol", ""),
            "signal": signal.get("signal", ""),
            "strategy": signal.get("strategy", ""),
            "exposure": signal.get("exposure", ""),
            "urgency": urgency_value,
            "regime": signal.get("regime", ""),
            "mtf_confluence_score": signal.get("mtf_confluence_score", "")
        })

def log_advanced_event(event_type: str, signal: Optional[Dict] = None, **extra: object) -> None:
    runtime_cfg = CONFIG.get("runtime", {}) if isinstance(CONFIG.get("runtime"), dict) else {}
    if not bool(runtime_cfg.get("enable_signal_csv_log", True)):
        return
    filepath = EVENT_LOG_PATH
    file_exists = os.path.isfile(filepath)
    fieldnames = [
        "timestamp",
        "event_type",
        "cid",
        "symbol",
        "direction",
        "source_tf",
        "strategy",
        "regime",
        "mtf_score",
        "mtf_threshold",
        "price",
        "sl",
        "tp",
        "volume",
        "reason",
        "details_json",
    ]
    base: Dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "cid": "",
        "symbol": "",
        "direction": "",
        "source_tf": "",
        "strategy": "",
        "regime": "",
        "mtf_score": "",
        "mtf_threshold": "",
        "price": "",
        "sl": "",
        "tp": "",
        "volume": "",
        "reason": "",
        "details_json": "",
    }
    if isinstance(signal, dict):
        base.update({
            "cid": signal.get("cid", ""),
            "symbol": signal.get("symbol", ""),
            "direction": signal.get("signal", ""),
            "source_tf": timeframe_label(int(signal.get("source_timeframe", mt5.TIMEFRAME_M15))),
            "strategy": signal.get("strategy", ""),
            "regime": signal.get("regime", ""),
            "mtf_score": signal.get("mtf_confluence_score", ""),
            "mtf_threshold": signal.get("mtf_confluence_threshold", ""),
        })
    reason = extra.pop("reason", "")
    base["reason"] = reason
    for k in ("price", "sl", "tp", "volume"):
        if k in extra:
            base[k] = extra.pop(k)
    if extra:
        try:
            base["details_json"] = json.dumps(extra, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            base["details_json"] = str(extra)
    with open(filepath, mode="a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(base)

def is_market_open_enhanced(symbol: str = "XAUUSD") -> bool:
    return runtime_is_market_open_enhanced(symbol)

def initialize_mt5() -> bool:
    """Initialize MT5 connection for live trading"""
    print("🔗 Initializing MT5 for Advanced Live Trading...")

    # Try to initialize MT5
    if not mt5.initialize():
        print("❌ MT5 Initialize failed")
        print("   Error:", mt5.last_error())
        return False

    print("✅ MT5 initialized successfully")

    # Try to login with any available account
    mt5.login()  # Use default credentials for new broker

    # Get account info regardless of login status
    account_info = mt5.account_info()
    sensitivity = get_sensitivity_level()
    sensitivity_cfg = CONFIG.get("sensitivity", {}) if isinstance(CONFIG.get("sensitivity"), dict) else {}

    dist_cfg = sensitivity_cfg.get("min_distance_points", {}) if isinstance(sensitivity_cfg.get("min_distance_points"), dict) else {}
    risk_min_distance = max(
        int(dist_cfg.get("min", 20)),
        int(dist_cfg.get("base", 50)) - (int(sensitivity) * int(dist_cfg.get("per_level_delta", 10))),
    )

    cd_cfg = sensitivity_cfg.get("gatekeeper_cooldown_seconds", {}) if isinstance(sensitivity_cfg.get("gatekeeper_cooldown_seconds"), dict) else {}
    gatekeeper_cooldown = max(
        int(cd_cfg.get("min", 60)),
        int(cd_cfg.get("base", 120)) - (int(sensitivity) * int(cd_cfg.get("per_level_delta", 30))),
    )

    atr_cfg = sensitivity_cfg.get("gatekeeper_atr_multiplier", {}) if isinstance(sensitivity_cfg.get("gatekeeper_atr_multiplier"), dict) else {}
    gatekeeper_atr = max(
        float(atr_cfg.get("min", 1.2)),
        float(atr_cfg.get("base", 1.6)) - (float(sensitivity) * float(atr_cfg.get("per_level_delta", 0.15))),
    )

    hard_cfg = sensitivity_cfg.get("gatekeeper_min_points", {}) if isinstance(sensitivity_cfg.get("gatekeeper_min_points"), dict) else {}
    gatekeeper_hard_points = max(
        float(hard_cfg.get("min", 80.0)),
        float(hard_cfg.get("base", 120.0)) - (float(sensitivity) * float(hard_cfg.get("per_level_delta", 20.0))),
    )

    if account_info is not None:
        print("✅ Connected to MT5 Account Successfully")
        print(f"   Account: {account_info.login}")
        print(f"   Balance: ${account_info.balance:.2f}")
        print(f"   Equity: ${account_info.equity:.2f}")
        print(f"   Broker: {account_info.server}")
        print(f"   Trade Allowed: {account_info.trade_allowed}")
        print(f"   Trade Expert: {account_info.trade_expert}")

        # Initialize RiskFirewall
        global RISK_FIREWALL
        risk_cfg = CONFIG.get("risk", {}) if isinstance(CONFIG.get("risk"), dict) else {}
        RISK_FIREWALL = RiskFirewall(
            max_open_trades=int(risk_cfg.get("max_open_trades", 4)),
            max_risk_usd=float(risk_cfg.get("max_risk_usd", 200.0)),
            min_distance_points=risk_min_distance
        )
        print(f"✅ RiskFirewall initialized successfully | Sensitivity: {sensitivity} | Min distance: {risk_min_distance}")

        # Initialize Institutional Execution Gatekeeper
        global EXECUTION_GATEKEEPER
        EXECUTION_GATEKEEPER = InstitutionalExecutionGatekeeper(
            operational_timeframe=mt5.TIMEFRAME_M5,
            min_cooldown_seconds=gatekeeper_cooldown,
            min_distance_atr_multiplier=gatekeeper_atr,
            min_hardcoded_points=gatekeeper_hard_points,
            max_retry_attempts=3,
            retry_delay_seconds=1.0
        )
        print(
            f"✅ Institutional Execution Gatekeeper initialized successfully | "
            f"Cooldown: {gatekeeper_cooldown}s | ATR: {gatekeeper_atr:.2f}x | "
            f"Min points: {gatekeeper_hard_points:.0f}"
        )

        # Initialize Advanced Volatility System
        global VOLATILITY_SYSTEM
        VOLATILITY_SYSTEM = AdvancedVolatilitySystem()
        print("✅ Advanced Volatility System initialized successfully")

        return True
    else:
        print("⚠️  Cannot get account info")
        print("   Error:", mt5.last_error())

        try:
            fallback_symbol = get_primary_symbol()
            rates = mt5.copy_rates_from_pos(fallback_symbol, mt5.TIMEFRAME_M5, 0, 1)
            if rates is not None:
                print("✅ Market data accessible (demo mode)")
                return True
        except Exception as e:
            print(f"❌ Market data error: {e}")
            return False

def send_telegram_message(message: str) -> bool:
    ok = TELEGRAM.send_html(message)
    if not ok:
        print("⚠️ Telegram send failed (check .env TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")
    return ok

def send_system_startup_notification():
    """Send advanced system startup notification"""
    try:
        telegram_cfg = CONFIG.get("telegram", {}) if isinstance(CONFIG.get("telegram"), dict) else {}
        if not bool(telegram_cfg.get("startup_notify", True)):
            print("INFO: Telegram startup_notify disabled in config")
            return

        symbol = get_primary_symbol()
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 1)
        current_price = None
        if rates is not None and len(rates) > 0:
            current_price = rates[0]["close"]

        account_info = mt5.account_info()
        mt5_status = "✅ MT5: Connected (เชื่อมต่อเรียบร้อย)" if account_info is not None else "⚠️ MT5: Not connected (ยังไม่เชื่อมต่อ)"

        telegram_status = "✅ Telegram: Enabled (ส่งสัญญาณได้)" if TELEGRAM.enabled and TELEGRAM.token and TELEGRAM.chat_id else "⚠️ Telegram: Disabled/Not configured (ยังไม่ได้ตั้งค่า)"

        ai_api_status = "INFO: AI API: N/A (โหมดนี้ยังไม่ใช้ AI ภายนอก)"

        bot_health = "💚 Bot Health: OK (ระบบผ่านขั้นตอนเริ่มต้นแล้ว)" if account_info is not None else "⚠️ Bot Health: CHECK (ตรวจสอบการเชื่อมต่อ MT5)"

        runtime_cfg = CONFIG.get("runtime", {}) if isinstance(CONFIG.get("runtime"), dict) else {}
        interval = int(runtime_cfg.get("trade_check_interval_seconds", 30))
        filters_cfg = CONFIG.get("market_filters", {}) if isinstance(CONFIG.get("market_filters"), dict) else {}
        max_spread_points = int(filters_cfg.get("max_spread_points", 200))
        mtf_cfg = CONFIG.get("mtf", {}) if isinstance(CONFIG.get("mtf"), dict) else {}
        min_tfs = int(mtf_cfg.get("min_timeframes_required", 2))

        price_line = f"💰 <b>Current GOLD (ราคาปัจจุบัน):</b> {current_price:.2f}\n" if isinstance(current_price, (int, float)) else ""
        tf_scan = ", ".join(timeframe_label(tf) for tf in SIGNAL_SCAN_TIMEFRAMES)
        mode_label = CONFIG.get("profile_name", "N/A")
        message = (
            f"🎯 <b>ADVANCED ORACLEBOT LIVE TRADING STARTED</b>\n\n"
            f"📊 <b>System Status / สถานะระบบ:</b> Advanced Volatility Management Online\n"
            f"{bot_health}\n"
            f"{mt5_status}\n"
            f"{telegram_status}\n"
            f"{ai_api_status}\n\n"
            f"{price_line}"
            f"⚡ <b>Strategy / กลยุทธ์:</b> Hybrid Adaptive System\n"
            f"🧭 <b>Trading Mode:</b> {mode_label} (โหมดการเทรดจาก config.json)\n"
            f"🔁 <b>Check Interval (รอบตรวจสัญญาณ):</b> {interval}s\n"
            f"🧭 <b>MTF Scan:</b> {tf_scan}\n"
            f"🧩 <b>MTF Min TF:</b> {min_tfs} (จำนวน TF ขั้นต่ำที่ต้อง align)\n"
            f"🛡️ <b>Spread Guard:</b> ≤ {max_spread_points} points (ถ้าสเปรดเกินจะไม่เข้าเทรด)\n\n"
            f"<b>Mentor Notes (คำอธิบายสำหรับมือใหม่)</b>\n"
            f"• ถ้า spread สูงเกิน limit ระบบจะพักการเข้าออเดอร์อัตโนมัติ\n"
            f"• ถ้าข้อมูล MTF ไม่ครบ ระบบจะข้ามสัญญาณเพื่อลด false signal\n"
            f"• ถ้า Regime เป็น VOLATILE_CHAOS/LIQUIDITY_CRISIS ค่าความเข้มงวดของ confluence จะถูกปรับอัตโนมัติให้ระมัดระวังมากขึ้น"
        )
        ok = send_telegram_message(message)
        if ok:
            print("✅ Telegram startup notification sent")
    except Exception as e:
        print(f"❌ Startup notification error: {e}")

def get_market_data(symbol: Optional[str] = None, timeframe: int = mt5.TIMEFRAME_M5, bars: int = 100) -> Optional[pd.DataFrame]:
    """Get market data for volatility analysis"""
    try:
        if symbol is None:
            symbol = get_primary_symbol()
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
        if rates is None:
            return None

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df
    except Exception as e:
        print(f"❌ Market data error: {e}")
        return None

def get_tick_data(symbol: Optional[str] = None) -> Dict:
    """Get current tick data for order flow analysis"""
    try:
        if symbol is None:
            symbol = get_primary_symbol()
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {}

        return {
            'time': tick.time,
            'bid': tick.bid,
            'ask': tick.ask,
            'last': tick.last,
            'volume': tick.volume,
            'spread': tick.ask - tick.bid
        }
    except Exception as e:
        print(f"❌ Tick data error: {e}")
        return {}

M15Bias = Literal["BULLISH", "BEARISH", "NEUTRAL"]


def _m15_ema_warning(m15_df: pd.DataFrame) -> M15Bias:
    if m15_df is None or len(m15_df) < 60:
        return "NEUTRAL"
    close = m15_df["close"]
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    last_close = float(close.iloc[-1])
    e20 = float(ema20.iloc[-1])
    e50 = float(ema50.iloc[-1])
    if e20 > e50 and last_close > e20:
        return "BULLISH"
    if e20 < e50 and last_close < e20:
        return "BEARISH"
    return "NEUTRAL"


def _m15_structure_bias(
    m15_df: pd.DataFrame,
    *,
    bars: int = 220,
    pivot_lookback: int = 2,
) -> M15Bias:
    if m15_df is None or len(m15_df) < 80:
        return "NEUTRAL"
    lookback = max(1, int(pivot_lookback))
    view = m15_df.tail(int(bars)).copy() if len(m15_df) > bars else m15_df.copy()
    if len(view) < (lookback * 2 + 5):
        return "NEUTRAL"
    highs = view["high"].to_list()
    lows = view["low"].to_list()
    n = len(view)

    swing_highs: List[float] = []
    swing_lows: List[float] = []
    for i in range(lookback, n - lookback):
        h = float(highs[i])
        low_val = float(lows[i])
        left_h = highs[i - lookback : i]
        right_h = highs[i + 1 : i + 1 + lookback]
        left_l = lows[i - lookback : i]
        right_l = lows[i + 1 : i + 1 + lookback]
        if h > max(left_h) and h > max(right_h):
            swing_highs.append(h)
        if low_val < min(left_l) and low_val < min(right_l):
            swing_lows.append(low_val)
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "NEUTRAL"

    prev_high, last_high = float(swing_highs[-2]), float(swing_highs[-1])
    prev_low, last_low = float(swing_lows[-2]), float(swing_lows[-1])
    if last_high > prev_high and last_low > prev_low:
        return "BULLISH"
    if last_high < prev_high and last_low < prev_low:
        return "BEARISH"
    return "NEUTRAL"


def advanced_trade_decision(symbol: Optional[str] = None) -> Optional[Dict]:
    """Make advanced trading decision using volatility system"""
    try:
        def _higher_tf_alignment_ok(signal: Dict) -> bool:
            regime = signal.get("regime", "")
            strategy = str(signal.get("strategy", "")).lower()
            if "mean" in strategy or regime == "MEAN_REVERTING":
                return True
            if regime in {"TRENDING", "VOLATILE_CHAOS", "LIQUIDITY_CRISIS"}:
                details = signal.get("mtf_confluence_details", {})
                if not isinstance(details, dict):
                    return False
                h1 = float(details.get(str(mt5.TIMEFRAME_H1), 0.0) or 0.0)
                m30 = float(details.get(str(mt5.TIMEFRAME_M30), 0.0) or 0.0)
                return (h1 > 0.0) or (m30 > 0.0)
            return True

        market_symbol = symbol or get_primary_symbol()
        symbol_info = mt5.symbol_info(market_symbol)
        filters_cfg = CONFIG.get("market_filters", {}) if isinstance(CONFIG.get("market_filters"), dict) else {}
        max_spread_points = int(filters_cfg.get("max_spread_points", 200))

        tick_data = get_tick_data(symbol=market_symbol)
        if symbol_info is not None and symbol_info.point and tick_data.get("spread") is not None:
            spread_points = float(tick_data["spread"]) / float(symbol_info.point)
            tick_data["spread_points"] = spread_points
            if spread_points > max_spread_points:
                print(f"⏸️ Spread too high: {spread_points:.0f} > {max_spread_points} points")
                log_advanced_event(
                    "MARKET_REJECTED",
                    {"symbol": market_symbol, "signal": "", "source_timeframe": mt5.TIMEFRAME_M15},
                    reason="spread_too_high",
                    spread_points=spread_points,
                    max_spread_points=max_spread_points,
                )
                return None
        candidate_signals: List[Dict] = []
        mtf_cfg = CONFIG.get("mtf", {}) if isinstance(CONFIG.get("mtf"), dict) else {}
        min_tfs = int(mtf_cfg.get("min_timeframes_required", 2))
        primary_tf_name = str(mtf_cfg.get("primary_timeframe", "M15")).upper()
        primary_tf = TIMEFRAME_NAME_TO_MT5.get(primary_tf_name, mt5.TIMEFRAME_M15)
        require_primary_alignment = bool(mtf_cfg.get("require_primary_alignment", True))
        structure_gate_cfg = mtf_cfg.get("structure_gate", {}) if isinstance(mtf_cfg.get("structure_gate"), dict) else {}
        structure_gate_enabled = bool(structure_gate_cfg.get("enabled", True))
        structure_gate_tf_name = str(structure_gate_cfg.get("timeframe", primary_tf_name)).upper()
        structure_gate_tf = TIMEFRAME_NAME_TO_MT5.get(structure_gate_tf_name, primary_tf)
        structure_gate_bars = int(structure_gate_cfg.get("bars", 220))
        structure_gate_pivot = int(structure_gate_cfg.get("pivot_lookback", 2))
        structure_gate_bypass_mean = bool(structure_gate_cfg.get("bypass_for_mean_reversion", True))
        m15_df = get_market_data(symbol=market_symbol, timeframe=structure_gate_tf, bars=max(260, structure_gate_bars))
        m15_bias = _m15_structure_bias(m15_df, bars=structure_gate_bars, pivot_lookback=structure_gate_pivot)
        m15_ema = _m15_ema_warning(m15_df)
        for tf in SIGNAL_SCAN_TIMEFRAMES:
            market_data = get_market_data(symbol=market_symbol, timeframe=tf, bars=250)
            if market_data is None or len(market_data) < 50:
                print(f"INFO: Skip {timeframe_label(tf)} no market data or insufficient bars ({0 if market_data is None else len(market_data)})")
                continue
            trade_signal = VOLATILITY_SYSTEM.orchestrator.execute_hybrid_strategy(market_data, tick_data)
            if not trade_signal:
                print(f"INFO: Skip {timeframe_label(tf)} no signal from volatility system")
                continue
            trade_signal["symbol"] = market_symbol
            trade_signal["source_timeframe"] = tf
            trade_signal["source_timeframe_label"] = timeframe_label(tf)
            confluence_score, confluence_details = evaluate_mtf_confluence(
                market_symbol,
                trade_signal["signal"]
            )
            trade_signal["mtf_confluence_score"] = round(confluence_score, 2)
            trade_signal["mtf_confluence_details"] = confluence_details
            trade_signal["m15_structure_bias"] = m15_bias
            trade_signal["m15_ema_warning"] = m15_ema
            if require_primary_alignment:
                primary_score = float(confluence_details.get(str(primary_tf), 0.0) or 0.0) if isinstance(confluence_details, dict) else 0.0
                if primary_score <= 0.0:
                    print(f"⏸️ Skip {trade_signal['source_timeframe_label']} not aligned with primary {primary_tf_name}")
                    log_advanced_event(
                        "SIGNAL_REJECTED",
                        trade_signal,
                        reason="primary_tf_misaligned",
                        primary_timeframe=primary_tf_name,
                    )
                    continue
            strategy = str(trade_signal.get("strategy", "")).lower()
            regime = str(trade_signal.get("regime", ""))
            if structure_gate_enabled and not (structure_gate_bypass_mean and ("mean" in strategy or regime == "MEAN_REVERTING")):
                if trade_signal["signal"] == "BUY" and m15_bias != "BULLISH":
                    print(f"⏸️ Skip {trade_signal['source_timeframe_label']} BUY blocked by M15 HH/HL gate ({m15_bias})")
                    log_advanced_event(
                        "SIGNAL_REJECTED",
                        trade_signal,
                        reason="m15_structure_gate",
                        m15_bias=m15_bias,
                        m15_ema_warning=m15_ema,
                    )
                    continue
                if trade_signal["signal"] == "SELL" and m15_bias != "BEARISH":
                    print(f"⏸️ Skip {trade_signal['source_timeframe_label']} SELL blocked by M15 HH/HL gate ({m15_bias})")
                    log_advanced_event(
                        "SIGNAL_REJECTED",
                        trade_signal,
                        reason="m15_structure_gate",
                        m15_bias=m15_bias,
                        m15_ema_warning=m15_ema,
                    )
                    continue
            threshold = get_adaptive_confluence_threshold(trade_signal)
            trade_signal["mtf_confluence_threshold"] = threshold
            used_tfs = len(confluence_details) if isinstance(confluence_details, dict) else 0
            trade_signal["mtf_timeframes_used"] = used_tfs
            print(
                f"INFO: MTF debug {trade_signal['source_timeframe_label']} "
                f"dir {trade_signal['signal']} "
                f"score {confluence_score:.1f} "
                f"thr {threshold:.1f} "
                f"tfs {used_tfs}"
            )
            if used_tfs < min_tfs:
                print(f"⏸️ Skip {trade_signal['source_timeframe_label']} insufficient MTF data {used_tfs}/{min_tfs}")
                log_advanced_event(
                    "SIGNAL_REJECTED",
                    trade_signal,
                    reason="mtf_insufficient_tfs",
                    used_tfs=used_tfs,
                    min_tfs=min_tfs,
                )
                continue
            if not _higher_tf_alignment_ok(trade_signal):
                print(f"⏸️ Skip {trade_signal['source_timeframe_label']} higher-TF misaligned")
                log_advanced_event(
                    "SIGNAL_REJECTED",
                    trade_signal,
                    reason="higher_tf_misaligned",
                )
                continue
            if confluence_score < threshold:
                print(
                    f"⏸️ Skip {trade_signal['source_timeframe_label']} "
                    f"score {confluence_score:.1f}/{threshold:.1f}"
                )
                log_advanced_event(
                    "SIGNAL_REJECTED",
                    trade_signal,
                    reason="mtf_below_threshold",
                    score=float(confluence_score),
                    threshold=float(threshold),
                )
                continue
            candidate_signals.append(trade_signal)
        if not candidate_signals:
            return None
        best_signal = max(
            candidate_signals,
            key=lambda x: (x.get("mtf_confluence_score", 0.0), x.get("exposure", 0.0))
        )
        best_signal["cid"] = uuid.uuid4().hex[:12]
        log_advanced_signal(best_signal)
        log_advanced_event("SIGNAL_SELECTED", best_signal, reason="selected")
        print(f"🎯 Advanced Signal: {best_signal}")
        return best_signal

    except Exception as e:
        print(f"❌ Advanced decision error: {e}")
        return None

def execute_advanced_trade(signal: Dict) -> bool:
    """Execute trade based on advanced signal"""
    try:
        if "cid" not in signal:
            signal["cid"] = uuid.uuid4().hex[:12]
        symbol = signal.get("symbol") or get_primary_symbol()
        symbol = str(symbol).strip() if symbol is not None else ""
        if not symbol:
            symbol = get_primary_symbol()
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is not None and not symbol_info.visible:
            mt5.symbol_select(symbol, True)
            symbol_info = mt5.symbol_info(symbol)
        selected_symbol = symbol
        if symbol_info is None:
            selected_symbol = get_primary_symbol()
            symbol_info = mt5.symbol_info(selected_symbol)
        symbol = selected_symbol
        trade_type = mt5.ORDER_TYPE_BUY if signal['signal'] == 'BUY' else mt5.ORDER_TYPE_SELL

        if symbol_info is None:
            print("❌ Cannot get symbol info")
            log_advanced_event("EXECUTION_REJECTED", signal, reason="symbol_info_missing")
            return False

        source_timeframe = signal.get("source_timeframe", mt5.TIMEFRAME_M15)
        exec_filters_cfg = CONFIG.get("execution_filters", {}) if isinstance(CONFIG.get("execution_filters"), dict) else {}
        one_trade_per_candle = bool(exec_filters_cfg.get("one_trade_per_candle", True))
        momentum_guard = bool(exec_filters_cfg.get("momentum_candle_guard", True))
        momentum_atr_ratio = float(exec_filters_cfg.get("momentum_candle_atr_ratio", 0.55))
        min_bars_cfg = exec_filters_cfg.get("min_bars_between_trades_by_timeframe", {}) if isinstance(exec_filters_cfg.get("min_bars_between_trades_by_timeframe"), dict) else {}
        min_bars_between = int(min_bars_cfg.get(timeframe_label(int(source_timeframe)), 1) or 1)
        tf_seconds_map = {
            mt5.TIMEFRAME_M1: 60,
            mt5.TIMEFRAME_M5: 300,
            mt5.TIMEFRAME_M15: 900,
            mt5.TIMEFRAME_M30: 1800,
            mt5.TIMEFRAME_H1: 3600,
            mt5.TIMEFRAME_H4: 14400,
            mt5.TIMEFRAME_D1: 86400,
        }
        tf_seconds = int(tf_seconds_map.get(int(source_timeframe), 60))
        candle_guard_key = f"{symbol}:{int(source_timeframe)}:{int(trade_type)}"
        current_candle_ts: Optional[int] = None
        guard_df = get_market_data(symbol=symbol, timeframe=source_timeframe, bars=60)
        if guard_df is not None and len(guard_df) >= 20:
            current_candle_ts = int(pd.Timestamp(guard_df["time"].iloc[-1]).timestamp())
            if one_trade_per_candle and EXECUTION_CANDLE_GUARD.get(candle_guard_key) == current_candle_ts:
                print(f"⏸️ Skip {symbol} {timeframe_label(source_timeframe)} already executed this candle")
                log_advanced_event("EXECUTION_REJECTED", signal, reason="one_trade_per_candle")
                return False
            if min_bars_between > 1:
                last_ts = EXECUTION_BAR_COOLDOWN_GUARD.get(candle_guard_key)
                if isinstance(last_ts, int) and last_ts > 0:
                    if (current_candle_ts - last_ts) < int(min_bars_between * tf_seconds):
                        print(f"⏸️ Skip {symbol} {timeframe_label(source_timeframe)} cooldown {min_bars_between} bars")
                        log_advanced_event(
                            "EXECUTION_REJECTED",
                            signal,
                            reason="min_bars_cooldown",
                            min_bars=min_bars_between,
                            timeframe=timeframe_label(source_timeframe),
                        )
                        return False

            if momentum_guard and len(guard_df) >= 16:
                closed_df = guard_df.iloc[:-1]
                last_candle = closed_df.iloc[-1]
                last_open = float(last_candle["open"])
                last_close = float(last_candle["close"])
                body = abs(last_close - last_open)
                atr_guard = calculate_atr(closed_df, period=14)
                if atr_guard is not None and atr_guard > 0:
                    body_ratio = body / float(atr_guard)
                    if body_ratio >= momentum_atr_ratio:
                        if trade_type == mt5.ORDER_TYPE_BUY and last_close < last_open:
                            print(f"⏸️ Skip BUY against strong bearish candle {body_ratio:.2f} ATR")
                            log_advanced_event(
                                "EXECUTION_REJECTED",
                                signal,
                                reason="momentum_guard_bearish",
                                body_ratio=body_ratio,
                                threshold=momentum_atr_ratio,
                            )
                            return False
                        if trade_type == mt5.ORDER_TYPE_SELL and last_close > last_open:
                            print(f"⏸️ Skip SELL against strong bullish candle {body_ratio:.2f} ATR")
                            log_advanced_event(
                                "EXECUTION_REJECTED",
                                signal,
                                reason="momentum_guard_bullish",
                                body_ratio=body_ratio,
                                threshold=momentum_atr_ratio,
                            )
                            return False

        price = symbol_info.ask if trade_type == mt5.ORDER_TYPE_BUY else symbol_info.bid
        digits = getattr(symbol_info, "digits", 2) or 2
        point = float(symbol_info.point)
        price = round(float(price), digits)
        spread_points = 0.0
        tick = mt5.symbol_info_tick(symbol)
        if tick is not None and point > 0:
            spread_points = float(tick.ask - tick.bid) / point

        tf_profile = TIMEFRAME_RISK_PROFILE.get(source_timeframe, TIMEFRAME_RISK_PROFILE[mt5.TIMEFRAME_M15])
        rr_ratio = float(tf_profile["rr_ratio"])
        strategy = str(signal.get("strategy", "")).lower()
        regime = str(signal.get("regime", ""))
        if "quiet" in strategy or regime == "QUIET":
            rr_ratio = min(rr_ratio, 1.2)
        sltp_cfg = CONFIG.get("sl_tp", {}) if isinstance(CONFIG.get("sl_tp"), dict) else {}
        confirm_cfg = sltp_cfg.get("confirmation_adjustments", {}) if isinstance(sltp_cfg.get("confirmation_adjustments"), dict) else {}
        structure_sl_factor = float(confirm_cfg.get("structure_sl_atr_multiplier_factor", 1.0))
        structure_rr = float(confirm_cfg.get("structure_rr_ratio", rr_ratio))
        ema_sl_factor = float(confirm_cfg.get("ema_sl_atr_multiplier_factor", 1.0))
        ema_rr = float(confirm_cfg.get("ema_rr_ratio", rr_ratio))
        m15_bias = str(signal.get("m15_structure_bias", "NEUTRAL")).upper()
        m15_ema = str(signal.get("m15_ema_warning", "NEUTRAL")).upper()
        direction_str = "BUY" if trade_type == mt5.ORDER_TYPE_BUY else "SELL"
        sl_mult_factor = 1.0
        if (direction_str == "BUY" and m15_bias == "BULLISH") or (direction_str == "SELL" and m15_bias == "BEARISH"):
            sl_mult_factor = structure_sl_factor
            rr_ratio = max(rr_ratio, structure_rr)
        else:
            sl_mult_factor = ema_sl_factor
            rr_ratio = min(rr_ratio, ema_rr)
        signal["sltp_mode"] = "STRUCTURE" if sl_mult_factor == structure_sl_factor else "EMA"
        signal["m15_ema_warning"] = m15_ema
        broker_stops_level_points = float(getattr(symbol_info, "stops_level", 0) or 0)
        min_stop_points = float(tf_profile["sl_min_points"])
        filters_cfg = CONFIG.get("market_filters", {}) if isinstance(CONFIG.get("market_filters"), dict) else {}
        spread_factor = float(filters_cfg.get("sl_tp_spread_factor", 1.5))
        pip_size_points = max(float(filters_cfg.get("gold_pip_size_points", 10.0)), 1.0)
        noise_pips = max(float(filters_cfg.get("gold_noise_pips", 20.0)), 0.0)
        buffer_pips = max(float(filters_cfg.get("sl_tp_buffer_pips", 10.0)), 0.0)
        hard_min_points = max(float(filters_cfg.get("sl_min_points_hard", 300.0)), 1.0)
        hard_max_points = max(float(filters_cfg.get("sl_max_points_hard", 1200.0)), hard_min_points)
        atr_guard_min_points = max(float(filters_cfg.get("atr_min_points_guard", 80.0)), 1.0)
        atr_guard_spread_multiplier = max(float(filters_cfg.get("atr_min_spread_multiplier", 6.0)), 0.0)
        tp_min_sl_ratio = max(float(filters_cfg.get("tp_min_sl_ratio", 1.2)), 1.0)
        min_stop_points = max(min_stop_points, hard_min_points)
        if spread_points > 0.0:
            min_stop_points = max(min_stop_points, spread_points * spread_factor)
        spread_pips = spread_points / pip_size_points if spread_points > 0.0 else 0.0
        noise_floor_points = (noise_pips + spread_pips + buffer_pips) * pip_size_points
        min_stop_points = max(min_stop_points, noise_floor_points)
        if broker_stops_level_points > 0:
            min_stop_points = max(min_stop_points, broker_stops_level_points)
        base_atr = get_timeframe_atr(symbol, source_timeframe)
        if base_atr is None:
            base_atr = get_multi_tf_atr(symbol)
        if base_atr is not None and point > 0:
            atr_points = float(base_atr) / point
            atr_floor_points = atr_guard_min_points
            if spread_points > 0:
                atr_floor_points = max(atr_floor_points, spread_points * atr_guard_spread_multiplier)
            atr_points = max(atr_points, atr_floor_points)
            stop_loss_points = atr_points * tf_profile["sl_atr_multiplier"] * sl_mult_factor
            max_stop_points = max(float(tf_profile["sl_max_points"]), hard_max_points, min_stop_points)
            stop_loss_points = max(
                min(stop_loss_points, max_stop_points),
                min_stop_points
            )
            take_profit_points = max(
                stop_loss_points * rr_ratio,
                min_stop_points * tp_min_sl_ratio
            )
        else:
            stop_loss_points = min_stop_points
            take_profit_points = max(
                stop_loss_points * rr_ratio,
                min_stop_points * tp_min_sl_ratio
            )
        signal["computed_sl_points"] = float(stop_loss_points)
        signal["computed_tp_points"] = float(take_profit_points)
        signal["symbol"] = symbol
        stop_loss_price = price - (stop_loss_points * point) if trade_type == mt5.ORDER_TYPE_BUY else price + (stop_loss_points * point)
        take_profit_price = price + (take_profit_points * point) if trade_type == mt5.ORDER_TYPE_BUY else price - (take_profit_points * point)
        stop_loss_price = round(float(stop_loss_price), digits)
        take_profit_price = round(float(take_profit_price), digits)
        actual_sl_points = abs(float(price) - float(stop_loss_price)) / point if point > 0 else 0.0
        if actual_sl_points < min_stop_points:
            adjusted_sl_points = min_stop_points
            stop_loss_price = round(
                float(price - (adjusted_sl_points * point) if trade_type == mt5.ORDER_TYPE_BUY else price + (adjusted_sl_points * point)),
                digits
            )
            signal["computed_sl_points"] = float(adjusted_sl_points)
        actual_tp_points = abs(float(take_profit_price) - float(price)) / point if point > 0 else 0.0
        min_tp_points = max(min_stop_points * tp_min_sl_ratio, min_stop_points)
        if actual_tp_points < min_tp_points:
            adjusted_tp_points = min_tp_points
            take_profit_price = round(
                float(price + (adjusted_tp_points * point) if trade_type == mt5.ORDER_TYPE_BUY else price - (adjusted_tp_points * point)),
                digits
            )
            signal["computed_tp_points"] = float(adjusted_tp_points)
        if trade_type == mt5.ORDER_TYPE_BUY:
            if stop_loss_price >= price:
                stop_loss_price = round(float(price - (min_stop_points * point)), digits)
            if take_profit_price <= price:
                take_profit_price = round(float(price + (min_tp_points * point)), digits)
        else:
            if stop_loss_price <= price:
                stop_loss_price = round(float(price + (min_stop_points * point)), digits)
            if take_profit_price >= price:
                take_profit_price = round(float(price - (min_tp_points * point)), digits)
        validation = RISK_FIREWALL.validate_signal(
            symbol=symbol,
            order_type=trade_type,
            entry_price=price,
            sl_price=stop_loss_price
        )
        if not validation["is_valid"]:
            print(f"❌ Trade rejected by RiskFirewall: {validation['reason']}")
            log_advanced_event(
                "EXECUTION_REJECTED",
                signal,
                reason=f"risk_firewall:{validation['reason']}",
                price=price,
                sl=stop_loss_price,
                tp=take_profit_price,
            )
            return False
        lot_size = float(validation["lot_size"])
        volume_min = float(getattr(symbol_info, "volume_min", 0.01) or 0.01)
        lot_size = max(volume_min, lot_size)
        risk_cfg = CONFIG.get("risk", {}) if isinstance(CONFIG.get("risk"), dict) else {}
        max_lot = float(risk_cfg.get("max_lot", 0.01))
        lot_size = min(lot_size, max(volume_min, max_lot))
        gatekeeper_decision, gatekeeper_reason = EXECUTION_GATEKEEPER.validate_execution(
            symbol=symbol,
            order_type=trade_type,
            entry_price=price
        )
        if gatekeeper_decision != GatekeeperDecision.APPROVED:
            print(f"❌ Trade rejected by Gatekeeper: {gatekeeper_reason}")
            log_advanced_event(
                "EXECUTION_REJECTED",
                signal,
                reason=f"gatekeeper:{gatekeeper_reason}",
                price=price,
                sl=stop_loss_price,
                tp=take_profit_price,
                volume=lot_size,
            )
            return False

        telegram_cfg = CONFIG.get("telegram", {}) if isinstance(CONFIG.get("telegram"), dict) else {}
        if bool(telegram_cfg.get("order_notify", True)):
            direction_label = "BUY" if trade_type == mt5.ORDER_TYPE_BUY else "SELL"
            mtf_score = float(signal.get("mtf_confluence_score", 0.0) or 0.0)
            confidence_pct = max(0.0, min(100.0, mtf_score))
            mentor_pre = (
                f"🧠 <b>ORDER READY</b>\n\n"
                f"📌 <b>Symbol:</b> {symbol}\n"
                f"🧭 <b>Direction:</b> {direction_label} (ทิศทาง{ 'ซื้อ' if direction_label == 'BUY' else 'ขาย' })\n"
                f"🕒 <b>Timeframe:</b> {timeframe_label(source_timeframe)}\n"
                f"🧩 <b>Regime:</b> {signal.get('regime', 'N/A')}\n"
                f"🧠 <b>Strategy:</b> {signal.get('strategy', 'Adaptive')}\n"
                f"📈 <b>MTF:</b> {mtf_score:.2f}/{signal.get('mtf_confluence_threshold', 'N/A')} | ความมั่นใจ ~{confidence_pct:.1f}%\n"
                f"🛑 <b>SL:</b> {stop_loss_price:.2f} ({stop_loss_points:.0f} pts)\n"
                f"🎯 <b>TP:</b> {take_profit_price:.2f} ({take_profit_points:.0f} pts)"
            )
            send_telegram_message(mentor_pre)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot_size,
            "type": trade_type,
            "price": price,
            "sl": stop_loss_price,
            "tp": take_profit_price,
            "deviation": 20,
            "magic": 234000,
            "comment": f"Advanced_{signal.get('strategy', 'Adaptive')}_{timeframe_label(source_timeframe)}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        max_retries = 3
        delay_seconds = 0.7
        trade_context_busy_code = getattr(mt5, "TRADE_RETCODE_TRADE_CONTEXT_BUSY", 10016)
        result = None
        for attempt in range(max_retries):
            result = mt5.order_send(request)
            if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
                break
            retcode = result.retcode if result is not None else "None"
            if retcode == trade_context_busy_code and attempt < max_retries - 1:
                print(f"⚠️ Trade context busy (10016), retry {attempt + 1}/{max_retries - 1}")
                time.sleep(delay_seconds)
                continue
            print(f"❌ Trade execution failed: {retcode}")
            log_advanced_event(
                "ORDER_FAILED",
                signal,
                reason=f"retcode:{retcode}",
                price=price,
                sl=stop_loss_price,
                tp=take_profit_price,
                volume=lot_size,
            )
            if bool(telegram_cfg.get("order_notify", True)):
                send_telegram_message(
                    f"❌ <b>ORDER FAILED</b>\n\n"
                    f"📌 <b>Symbol:</b> {symbol}\n"
                    f"🧭 <b>Direction:</b> {direction_label}\n"
                    f"🕒 <b>Timeframe:</b> {timeframe_label(source_timeframe)}\n"
                    f"⚠️ <b>Retcode:</b> {retcode}"
                )
            return False

        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            retcode = result.retcode if result is not None else "None"
            print(f"❌ Trade execution failed: {retcode}")
            log_advanced_event(
                "ORDER_FAILED",
                signal,
                reason=f"retcode:{retcode}",
                price=price,
                sl=stop_loss_price,
                tp=take_profit_price,
                volume=lot_size,
            )
            if bool(telegram_cfg.get("order_notify", True)):
                send_telegram_message(
                    f"❌ <b>ORDER FAILED</b>\n\n"
                    f"📌 <b>Symbol:</b> {symbol}\n"
                    f"🧭 <b>Direction:</b> {direction_label}\n"
                    f"🕒 <b>Timeframe:</b> {timeframe_label(source_timeframe)}\n"
                    f"⚠️ <b>Retcode:</b> {retcode}"
                )
            return False

        print(f"✅ Advanced trade executed: {signal['signal']} {lot_size:.2f} lots")
        log_advanced_event(
            "EXECUTED",
            signal,
            reason="done",
            price=float(getattr(result, "price", price) or price),
            sl=stop_loss_price,
            tp=take_profit_price,
            volume=float(getattr(result, "volume", lot_size) or lot_size),
            order=int(getattr(result, "order", 0) or 0),
            deal=int(getattr(result, "deal", 0) or 0),
        )
        if current_candle_ts is not None:
            EXECUTION_CANDLE_GUARD[candle_guard_key] = current_candle_ts
            EXECUTION_BAR_COOLDOWN_GUARD[candle_guard_key] = current_candle_ts
        try:
            if hasattr(EXECUTION_GATEKEEPER, "record_execution"):
                EXECUTION_GATEKEEPER.record_execution(symbol, trade_type, price)
        except Exception as e:
            print(f"⚠️ Gatekeeper record_execution warning: {e}")

        # Send notification
        send_advanced_trade_notification(signal, result, request['sl'], request['tp'])

        return True

    except Exception as e:
        print(f"❌ Advanced trade execution error: {e}")
        return False

def send_advanced_trade_notification(signal: Dict, result, stop_loss: float, take_profit: float):
    """Send advanced trade notification"""
    try:
        telegram_cfg = CONFIG.get("telegram", {}) if isinstance(CONFIG.get("telegram"), dict) else {}
        if not bool(telegram_cfg.get("order_notify", True)):
            return

        strategy_name = signal.get("strategy", "Advanced")
        urgency = signal.get("urgency", "NORMAL")
        tf_label = signal.get("source_timeframe_label", timeframe_label(signal.get("source_timeframe", mt5.TIMEFRAME_M15)))
        confluence_score = signal.get("mtf_confluence_score", "N/A")
        confluence_threshold = signal.get("mtf_confluence_threshold", "N/A")
        used_tfs = signal.get("mtf_timeframes_used", "N/A")
        sl_pts = signal.get("computed_sl_points")
        tp_pts = signal.get("computed_tp_points")

        symbol = signal.get("symbol", "")
        action = signal.get("signal", "")
        action_th = "ซื้อ (BUY)" if str(action).upper() == "BUY" else "ขาย (SELL)" if action else ""
        regime = signal.get("regime", "N/A")

        sl_detail = f"{stop_loss:.2f}"
        if isinstance(sl_pts, (int, float)):
            sl_detail += f" ({sl_pts:.0f} pts)"
        tp_detail = f"{take_profit:.2f}"
        if isinstance(tp_pts, (int, float)):
            tp_detail += f" ({tp_pts:.0f} pts)"

        message = (
            f"🚀 <b>ADVANCED ORDER EXECUTED</b>\n\n"
            f"📌 <b>Symbol:</b> {symbol} | สินทรัพย์ที่เทรด\n"
            f"🧭 <b>Action:</b> {action} | ฝั่ง {action_th}\n"
            f"🕒 <b>Source TF:</b> {tf_label} | กรอบเวลาที่ใช้ตัดสินใจ\n"
            f"🧠 <b>Strategy:</b> {strategy_name} | แผนการเทรดที่ระบบเลือก\n"
            f"🧩 <b>Regime:</b> {regime} | สภาพตลาดที่ระบบประเมิน\n"
            f"⚡ <b>Urgency:</b> {urgency} | ความเร่งด่วนของการเข้าออเดอร์\n\n"
            f"✅ <b>Why entered / ทำไมระบบเข้าออเดอร์นี้</b>\n"
            f"• MTF confluence {confluence_score}/{confluence_threshold} (TF used: {used_tfs}) → หลายกรอบเวลาไปทิศทางเดียวกัน\n"
            f"• Regime matched strategy routing (HybridStrategyOrchestrator) → กลยุทธ์ที่ใช้เหมาะกับสภาพตลาดตอนนี้\n\n"
            f"💰 <b>Fill Price:</b> {result.price:.2f} | ราคาที่ได้จริง\n"
            f"📦 <b>Size:</b> {result.volume:.2f} lots | ขนาดออเดอร์ (lot)\n"
            f"🛑 <b>SL:</b> {sl_detail}\n"
            f"🎯 <b>TP:</b> {tp_detail}\n\n"
            f"<b>คำอธิบายแบบภาษาคน (อ่านทีเดียวจบ)</b>\n"
            f"• <b>SL</b> คือเส้นตัดขาดทุน: ถ้าราคาไปถึง แปลว่าไอเดียนี้ผิดทางแล้ว ให้จบไม้เพื่อหยุดความเสียหาย\n"
            f"• <b>TP</b> คือเป้ากำไร: ถ้าราคาไปถึง คือได้กำไรตามแผนที่ระบบประเมินไว้\n"
            f"• <b>ความมั่นใจ (MTF)</b> คือภาพรวมหลายกรอบเวลาไปทางเดียวกันมากแค่ไหน ไม่ใช่การันตีว่าจะชนะ\n\n"
            f"<b>⚠️ ระวัง “ตลาดกลับตัวเร็ว”</b>\n"
            f"• ถ้าเพิ่งเข้าแล้วราคากลับสวนแรงใน 1-3 แท่ง M5 (กลับเข้ากรอบเดิมเร็ว) → มักเป็น whipsaw/false break\n"
            f"• ถ้า spread กว้างผิดปกติช่วงข่าว/rollover → ราคาอาจกระชากไปมาและโดน SL ได้ง่ายขึ้น\n"
            f"• ถ้าเริ่มมีสัญญาณฝั่งตรงข้ามที่ MTF สูงกว่าอย่างชัดเจน → โอกาสกลับตัวเพิ่มขึ้น\n"
            f"• <b>ต้องทำอะไร</b>: ห้ามเพิ่มไม้/เฉลี่ยขาดทุน และห้ามขยับ SL ให้ไกลกว่าเดิม; ถ้าจะจัดการให้ทำเพื่อ “ลดความเสี่ยง” เท่านั้น (ปิดบางส่วน/ปิดทั้งไม้) แล้วรอระบบประเมินใหม่"
        )

        send_telegram_message(message)

    except Exception as e:
        print(f"❌ Advanced notification error: {e}")

def main():
    """Main advanced trading loop"""

    # Initialize MT5
    if not initialize_mt5():
        print("❌ MT5 initialization failed - exiting")
        return

    send_system_startup_notification()

    symbol = get_primary_symbol()
    runtime_cfg = CONFIG.get("runtime", {}) if isinstance(CONFIG.get("runtime"), dict) else {}
    interval = int(runtime_cfg.get("trade_check_interval_seconds", 30))
    print("\n🎯 ADVANCED TRADING SYSTEM ACTIVE")
    print(f"📊 Monitoring {symbol} with Volatility Management")
    print("⚡ Features: Regime Detection + Adaptive Strategies")
    print(f"🔁 Checking every {interval} seconds...\n")

    # Main trading loop
    while True:
        try:
            symbol = get_primary_symbol()
            if not is_market_open_enhanced(symbol):
                print("⏸️  Market closed - waiting...")
                time.sleep(300)  # Wait 5 minutes
                continue

            trade_signal = advanced_trade_decision(symbol)

            if trade_signal:
                print(f"🎯 Advanced signal detected: {trade_signal}")

                # Execute advanced trade
                success = execute_advanced_trade(trade_signal)

                if success:
                    print("✅ Advanced trade executed successfully")
                else:
                    print("❌ Advanced trade execution failed")

            # Wait for next check
            time.sleep(interval)

        except KeyboardInterrupt:
            print("\n🛑 Advanced trading stopped by user")
            break
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backtest-hours", type=float, default=0.0)
    parser.add_argument("--symbol", type=str, default="")
    parser.add_argument("--spread-points", type=float, default=50.0)
    parser.add_argument("--warmup-hours", type=float, default=36.0)
    parser.add_argument("--compare-live", action="store_true")
    args = parser.parse_args()

    def _fetch_rates_df(symbol: str, timeframe: int, bars: int) -> Optional[pd.DataFrame]:
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, int(bars))
        if rates is None or len(rates) == 0:
            return None
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert(None)
        return df

    def _slice_asof(df: pd.DataFrame, as_of_ts: pd.Timestamp, bars: int) -> pd.DataFrame:
        view = df[df["time"] <= as_of_ts]
        if len(view) <= bars:
            return view
        return view.iloc[-bars:]

    def _timeframe_seconds(timeframe: int) -> int:
        tf_seconds = {
            mt5.TIMEFRAME_M1: 60,
            mt5.TIMEFRAME_M5: 300,
            mt5.TIMEFRAME_M15: 900,
            mt5.TIMEFRAME_M30: 1800,
            mt5.TIMEFRAME_H1: 3600,
            mt5.TIMEFRAME_H4: 14400,
            mt5.TIMEFRAME_D1: 86400,
        }
        return int(tf_seconds.get(timeframe, 60))

    def _candle_open_ts(as_of_ts: pd.Timestamp, timeframe: int) -> int:
        sec = _timeframe_seconds(timeframe)
        ts = int(as_of_ts.timestamp())
        return int(ts // sec) * sec

    def _slice_closed_asof(df: pd.DataFrame, as_of_ts: pd.Timestamp, timeframe: int, bars: int) -> pd.DataFrame:
        sec = _timeframe_seconds(timeframe)
        cutoff_open_ts = _candle_open_ts(as_of_ts, timeframe) - sec
        if cutoff_open_ts <= 0:
            return df.iloc[:0]
        cutoff = pd.Timestamp.fromtimestamp(int(cutoff_open_ts))
        view = df[df["time"] <= cutoff]
        if len(view) <= bars:
            return view
        return view.iloc[-bars:]

    def _evaluate_mtf_confluence_asof(
        direction: str,
        history_by_tf: Dict[int, pd.DataFrame],
        as_of_ts: pd.Timestamp,
    ) -> Tuple[float, Dict[str, float]]:
        aligned_score = 0.0
        total_weight = 0.0
        details: Dict[str, float] = {}
        for tf, weight in MTF_WEIGHTS.items():
            df = history_by_tf.get(tf)
            if df is None:
                continue
            window = _slice_closed_asof(df, as_of_ts, tf, 120)
            if window is None or len(window) < 60:
                continue
            close = window["close"]
            ema_fast = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
            ema_slow = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
            recent_move = float(close.iloc[-1] - close.iloc[-6]) if len(close) >= 6 else float(close.diff().tail(5).sum())
            atr_value = calculate_atr(window, period=14)
            if atr_value is None or atr_value <= 0:
                continue
            ema_diff = ema_fast - ema_slow
            close_last = float(close.iloc[-1])
            sep_den = max(float(atr_value) * 0.5, abs(close_last) * 0.0005, 1e-9)
            separation = min(abs(ema_diff) / sep_den, 1.0)
            move_units = min(abs(recent_move) / max(float(atr_value), 1e-9), 1.0)
            is_aligned = ((direction == "BUY" and ema_diff > 0) or (direction == "SELL" and ema_diff < 0))
            directional_momentum = 0.0
            if direction == "BUY":
                directional_momentum = max(0.0, min(1.0, recent_move / max(float(atr_value), 1e-9)))
            else:
                directional_momentum = max(0.0, min(1.0, (-recent_move) / max(float(atr_value), 1e-9)))
            strength = (0.65 * separation) + (0.20 * move_units) + (0.15 * directional_momentum)
            tf_score = (strength * 100.0) if is_aligned else 0.0
            if is_aligned:
                aligned_score += float(weight) * tf_score
                total_weight += float(weight)
            details[str(tf)] = round(tf_score, 2)
        if total_weight == 0:
            return 0.0, details
        return aligned_score / total_weight, details

    def _execution_filters_allow(
        symbol: str,
        trade_type: int,
        source_timeframe: int,
        as_of_ts: pd.Timestamp,
        history_by_tf: Dict[int, pd.DataFrame],
    ) -> bool:
        exec_filters_cfg = CONFIG.get("execution_filters", {}) if isinstance(CONFIG.get("execution_filters"), dict) else {}
        one_trade_per_candle = bool(exec_filters_cfg.get("one_trade_per_candle", True))
        momentum_guard = bool(exec_filters_cfg.get("momentum_candle_guard", True))
        momentum_atr_ratio = float(exec_filters_cfg.get("momentum_candle_atr_ratio", 0.55))
        streak_guard = bool(exec_filters_cfg.get("countertrend_streak_guard", True))
        streak_bars = int(exec_filters_cfg.get("countertrend_streak_bars", 3))
        candle_guard_key = f"{symbol}:{int(source_timeframe)}:{int(trade_type)}"
        current_candle_ts = _candle_open_ts(as_of_ts, source_timeframe)
        if one_trade_per_candle and EXECUTION_CANDLE_GUARD.get(candle_guard_key) == current_candle_ts:
            return False
        guard_df = history_by_tf.get(source_timeframe)
        if guard_df is None or len(guard_df) < 20:
            return True
        window = _slice_closed_asof(guard_df, as_of_ts, source_timeframe, 60)
        if window is None or len(window) < 20:
            return True
        if streak_guard and streak_bars >= 2 and len(window) >= streak_bars:
            tail = window.tail(int(streak_bars))
            up_streak = bool((tail["close"] > tail["open"]).all())
            down_streak = bool((tail["close"] < tail["open"]).all())
            if trade_type == mt5.ORDER_TYPE_SELL and up_streak:
                return False
            if trade_type == mt5.ORDER_TYPE_BUY and down_streak:
                return False
        if not momentum_guard:
            return True
        last_candle = window.iloc[-1]
        last_open = float(last_candle["open"])
        last_close = float(last_candle["close"])
        body = abs(last_close - last_open)
        atr_guard = calculate_atr(window, period=14)
        if atr_guard is None or atr_guard <= 0:
            return True
        body_ratio = body / float(atr_guard)
        if body_ratio < momentum_atr_ratio:
            return True
        if trade_type == mt5.ORDER_TYPE_BUY and last_close < last_open:
            return False
        if trade_type == mt5.ORDER_TYPE_SELL and last_close > last_open:
            return False
        return True

    def _gatekeeper_allows(
        *,
        entry_price: float,
        symbol_info,
        trade_type: int,
        state: Dict[str, object],
        as_of_dt: datetime,
        as_of_ts: pd.Timestamp,
        history_by_tf: Dict[int, pd.DataFrame],
        cooldown_seconds: int,
        min_distance_atr_multiplier: float,
        min_hardcoded_points: float,
        atr_timeframe: int = mt5.TIMEFRAME_H1,
        operational_timeframe: int = mt5.TIMEFRAME_M5,
    ) -> Tuple[bool, str]:
        point = float(getattr(symbol_info, "point", 0.0) or 0.0)
        if point <= 0:
            return False, "invalid_point"
        last_trade_time = state.get("last_trade_time")
        if isinstance(last_trade_time, datetime):
            if (last_trade_time + timedelta(seconds=int(cooldown_seconds))) > as_of_dt:
                return False, "cooldown"
        last_candle_ts = state.get("last_candle_ts")
        current_candle_ts = _candle_open_ts(as_of_ts, operational_timeframe)
        if isinstance(last_candle_ts, int):
            if last_candle_ts == int(current_candle_ts) and operational_timeframe == mt5.TIMEFRAME_M5:
                return False, "same_candle"
        last_trade_price = state.get("last_trade_price")
        last_trade_type = state.get("last_trade_type")
        if isinstance(last_trade_time, datetime) and isinstance(last_trade_type, int):
            if int(last_trade_type) == int(trade_type):
                if (as_of_dt - last_trade_time).total_seconds() < (float(cooldown_seconds) / 2.0):
                    return False, "same_direction"
        if isinstance(last_trade_price, (int, float)) and isinstance(last_trade_type, int):
            if int(last_trade_type) == int(trade_type):
                distance_points = abs(float(entry_price) - float(last_trade_price)) / point
                atr_df = history_by_tf.get(atr_timeframe)
                atr_value = None
                if atr_df is not None:
                    atr_window = _slice_closed_asof(atr_df, as_of_ts, atr_timeframe, 100)
                    if atr_window is not None and len(atr_window) >= 20:
                        atr_value = calculate_atr(atr_window, period=14)
                dynamic_min_distance = 0.0
                if atr_value is not None and atr_value > 0:
                    dynamic_min_distance = float(atr_value) * float(min_distance_atr_multiplier) / point
                required_min_distance = max(float(dynamic_min_distance), float(min_hardcoded_points))
                if distance_points < required_min_distance:
                    return False, "price_distance"
        return True, "approved"

    def _build_tick_from_bar(bar: pd.Series, spread_points: float, point: float, as_of_ts: pd.Timestamp) -> Dict:
        close_price = float(bar["close"])
        open_price = float(bar["open"])
        volume = float(bar.get("tick_volume", 0.0) or 0.0)
        ts = int(as_of_ts.timestamp())
        spread_price = float(spread_points) * float(point)
        bid = float(close_price)
        ask = float(close_price) + spread_price
        bid_volume = volume if close_price <= open_price else 0.0
        ask_volume = volume if close_price > open_price else 0.0
        return {
            "time": ts,
            "bid": bid,
            "ask": ask,
            "last": bid,
            "volume": volume,
            "bid_volume": bid_volume,
            "ask_volume": ask_volume,
            "spread": ask - bid,
            "spread_points": float(spread_points),
        }

    def _backtest_trade_decision(
        symbol: str,
        as_of_ts: pd.Timestamp,
        history_by_tf: Dict[int, pd.DataFrame],
        tick_data: Dict,
        metrics: Dict[str, int],
        rejects: Dict[str, int],
    ) -> Optional[Dict]:
        metrics["decision_calls"] = int(metrics.get("decision_calls", 0)) + 1
        def _higher_tf_alignment_ok(signal: Dict) -> bool:
            regime = signal.get("regime", "")
            strategy = str(signal.get("strategy", "")).lower()
            if "mean" in strategy or regime == "MEAN_REVERTING":
                return True
            if regime in {"TRENDING", "VOLATILE_CHAOS", "LIQUIDITY_CRISIS"}:
                details = signal.get("mtf_confluence_details", {})
                if not isinstance(details, dict):
                    return False
                h1 = float(details.get(str(mt5.TIMEFRAME_H1), 0.0) or 0.0)
                m30 = float(details.get(str(mt5.TIMEFRAME_M30), 0.0) or 0.0)
                return (h1 > 0.0) or (m30 > 0.0)
            return True

        filters_cfg = CONFIG.get("market_filters", {}) if isinstance(CONFIG.get("market_filters"), dict) else {}
        max_spread_points = int(filters_cfg.get("max_spread_points", 200))
        spread_points = float(tick_data.get("spread_points") or 0.0)
        if spread_points > max_spread_points:
            rejects["spread_too_high"] = int(rejects.get("spread_too_high", 0)) + 1
            return None

        candidate_signals: List[Dict] = []
        mtf_cfg = CONFIG.get("mtf", {}) if isinstance(CONFIG.get("mtf"), dict) else {}
        min_tfs = int(mtf_cfg.get("min_timeframes_required", 2))

        for tf in SIGNAL_SCAN_TIMEFRAMES:
            df = history_by_tf.get(tf)
            if df is None:
                rejects["tf_missing"] = int(rejects.get("tf_missing", 0)) + 1
                continue
            market_data = _slice_closed_asof(df, as_of_ts, tf, 250)
            if market_data is None or len(market_data) < 50:
                rejects["tf_insufficient_data"] = int(rejects.get("tf_insufficient_data", 0)) + 1
                continue
            trade_signal = VOLATILITY_SYSTEM.orchestrator.execute_hybrid_strategy(market_data, tick_data)
            if not trade_signal:
                rejects["no_raw_signal"] = int(rejects.get("no_raw_signal", 0)) + 1
                continue
            metrics["raw_signals"] = int(metrics.get("raw_signals", 0)) + 1
            trade_signal["symbol"] = symbol
            trade_signal["source_timeframe"] = tf
            trade_signal["source_timeframe_label"] = timeframe_label(tf)
            confluence_score, confluence_details = _evaluate_mtf_confluence_asof(
                trade_signal["signal"],
                history_by_tf,
                as_of_ts,
            )
            trade_signal["mtf_confluence_score"] = round(confluence_score, 2)
            trade_signal["mtf_confluence_details"] = confluence_details
            primary_tf_name = str(mtf_cfg.get("primary_timeframe", "M15")).upper()
            primary_tf = TIMEFRAME_NAME_TO_MT5.get(primary_tf_name, mt5.TIMEFRAME_M15)
            require_primary_alignment = bool(mtf_cfg.get("require_primary_alignment", True))
            if require_primary_alignment:
                primary_score = float(confluence_details.get(str(primary_tf), 0.0) or 0.0) if isinstance(confluence_details, dict) else 0.0
                if primary_score <= 0.0:
                    rejects["primary_tf_misaligned"] = int(rejects.get("primary_tf_misaligned", 0)) + 1
                    continue
            threshold = get_adaptive_confluence_threshold(trade_signal)
            trade_signal["mtf_confluence_threshold"] = threshold
            used_tfs = len(confluence_details) if isinstance(confluence_details, dict) else 0
            trade_signal["mtf_timeframes_used"] = used_tfs
            if used_tfs < min_tfs:
                rejects["mtf_insufficient_tfs"] = int(rejects.get("mtf_insufficient_tfs", 0)) + 1
                continue
            if not _higher_tf_alignment_ok(trade_signal):
                rejects["higher_tf_misaligned"] = int(rejects.get("higher_tf_misaligned", 0)) + 1
                continue
            if confluence_score < threshold:
                rejects["mtf_below_threshold"] = int(rejects.get("mtf_below_threshold", 0)) + 1
                continue
            trade_type = mt5.ORDER_TYPE_BUY if trade_signal["signal"] == "BUY" else mt5.ORDER_TYPE_SELL
            if not _execution_filters_allow(symbol, trade_type, tf, as_of_ts, history_by_tf):
                rejects["execution_filters"] = int(rejects.get("execution_filters", 0)) + 1
                continue
            candidate_signals.append(trade_signal)
            metrics["mtf_passed"] = int(metrics.get("mtf_passed", 0)) + 1

        if not candidate_signals:
            return None
        best_signal = max(candidate_signals, key=lambda x: (x.get("mtf_confluence_score", 0.0), x.get("exposure", 0.0)))
        metrics["selected_signals"] = int(metrics.get("selected_signals", 0)) + 1
        return best_signal

    def _simulate_fill_and_sl_tp(
        symbol: str,
        signal: Dict,
        tick_data: Dict,
        history_by_tf: Dict[int, pd.DataFrame],
        as_of_ts: pd.Timestamp,
    ) -> Optional[Dict]:
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return None
        trade_type = mt5.ORDER_TYPE_BUY if signal["signal"] == "BUY" else mt5.ORDER_TYPE_SELL
        price = float(tick_data["ask"] if trade_type == mt5.ORDER_TYPE_BUY else tick_data["bid"])
        digits = getattr(symbol_info, "digits", 2) or 2
        point = float(symbol_info.point)
        price = round(float(price), digits)
        spread_points = float(tick_data.get("spread_points") or 0.0)
        source_timeframe = signal.get("source_timeframe", mt5.TIMEFRAME_M15)
        tf_profile = TIMEFRAME_RISK_PROFILE.get(source_timeframe, TIMEFRAME_RISK_PROFILE[mt5.TIMEFRAME_M15])
        rr_ratio = float(tf_profile["rr_ratio"])
        strategy = str(signal.get("strategy", "")).lower()
        regime = str(signal.get("regime", ""))
        if "quiet" in strategy or regime == "QUIET":
            rr_ratio = min(rr_ratio, 1.2)
        broker_stops_level_points = float(getattr(symbol_info, "stops_level", 0) or 0)
        min_stop_points = float(tf_profile["sl_min_points"])
        filters_cfg = CONFIG.get("market_filters", {}) if isinstance(CONFIG.get("market_filters"), dict) else {}
        spread_factor = float(filters_cfg.get("sl_tp_spread_factor", 1.5))
        pip_size_points = max(float(filters_cfg.get("gold_pip_size_points", 10.0)), 1.0)
        noise_pips = max(float(filters_cfg.get("gold_noise_pips", 20.0)), 0.0)
        buffer_pips = max(float(filters_cfg.get("sl_tp_buffer_pips", 10.0)), 0.0)
        hard_min_points = max(float(filters_cfg.get("sl_min_points_hard", 300.0)), 1.0)
        hard_max_points = max(float(filters_cfg.get("sl_max_points_hard", 1200.0)), hard_min_points)
        atr_guard_min_points = max(float(filters_cfg.get("atr_min_points_guard", 80.0)), 1.0)
        atr_guard_spread_multiplier = max(float(filters_cfg.get("atr_min_spread_multiplier", 6.0)), 0.0)
        tp_min_sl_ratio = max(float(filters_cfg.get("tp_min_sl_ratio", 1.2)), 1.0)
        min_stop_points = max(min_stop_points, hard_min_points)
        if spread_points > 0.0:
            min_stop_points = max(min_stop_points, spread_points * spread_factor)
        spread_pips = spread_points / pip_size_points if spread_points > 0.0 else 0.0
        noise_floor_points = (noise_pips + spread_pips + buffer_pips) * pip_size_points
        min_stop_points = max(min_stop_points, noise_floor_points)
        if broker_stops_level_points > 0:
            min_stop_points = max(min_stop_points, broker_stops_level_points)

        base_atr = None
        src_df = history_by_tf.get(source_timeframe)
        if src_df is not None:
            src_window = _slice_closed_asof(src_df, as_of_ts, int(source_timeframe), 150)
            if src_window is not None and len(src_window) >= 30:
                base_atr = calculate_atr(src_window, period=14)
        if base_atr is None:
            base_atr = get_multi_tf_atr(symbol)
        if base_atr is not None and point > 0:
            atr_points = float(base_atr) / point
            atr_floor_points = atr_guard_min_points
            if spread_points > 0:
                atr_floor_points = max(atr_floor_points, spread_points * atr_guard_spread_multiplier)
            atr_points = max(atr_points, atr_floor_points)
            stop_loss_points = atr_points * tf_profile["sl_atr_multiplier"]
            max_stop_points = max(float(tf_profile["sl_max_points"]), hard_max_points, min_stop_points)
            stop_loss_points = max(min(stop_loss_points, max_stop_points), min_stop_points)
            take_profit_points = max(stop_loss_points * rr_ratio, min_stop_points * tp_min_sl_ratio)
        else:
            stop_loss_points = min_stop_points
            take_profit_points = max(stop_loss_points * rr_ratio, min_stop_points * tp_min_sl_ratio)

        stop_loss_price = price - (stop_loss_points * point) if trade_type == mt5.ORDER_TYPE_BUY else price + (stop_loss_points * point)
        take_profit_price = price + (take_profit_points * point) if trade_type == mt5.ORDER_TYPE_BUY else price - (take_profit_points * point)
        stop_loss_price = round(float(stop_loss_price), digits)
        take_profit_price = round(float(take_profit_price), digits)

        return {
            "trade_type": trade_type,
            "entry_price": price,
            "sl_price": stop_loss_price,
            "tp_price": take_profit_price,
            "sl_points": float(stop_loss_points),
            "tp_points": float(take_profit_points),
            "digits": int(digits),
            "point": float(point),
        }

    def _fetch_live_history(symbol: str, start_dt: datetime, end_dt: datetime) -> Dict[str, List[Dict]]:
        magic = 234000
        orders = mt5.history_orders_get(start_dt, end_dt)
        deals = mt5.history_deals_get(start_dt, end_dt)
        out_orders: List[Dict] = []
        out_deals: List[Dict] = []
        if orders is not None:
            for o in orders:
                if getattr(o, "magic", None) != magic:
                    continue
                if symbol and getattr(o, "symbol", "") != symbol:
                    continue
                comment = str(getattr(o, "comment", "") or "")
                if not comment.startswith("Advanced_"):
                    continue
                out_orders.append(
                    {
                        "time_setup": int(getattr(o, "time_setup", 0) or 0),
                        "symbol": str(getattr(o, "symbol", "") or ""),
                        "type": int(getattr(o, "type", 0) or 0),
                        "state": int(getattr(o, "state", 0) or 0),
                        "price_open": float(getattr(o, "price_open", 0.0) or 0.0),
                        "volume_initial": float(getattr(o, "volume_initial", 0.0) or 0.0),
                        "comment": comment,
                        "ticket": int(getattr(o, "ticket", 0) or 0),
                    }
                )
        if deals is not None:
            for d in deals:
                if getattr(d, "magic", None) != magic:
                    continue
                if symbol and getattr(d, "symbol", "") != symbol:
                    continue
                comment = str(getattr(d, "comment", "") or "")
                if not comment.startswith("Advanced_"):
                    continue
                out_deals.append(
                    {
                        "time": int(getattr(d, "time", 0) or 0),
                        "symbol": str(getattr(d, "symbol", "") or ""),
                        "type": int(getattr(d, "type", 0) or 0),
                        "entry": int(getattr(d, "entry", 0) or 0),
                        "price": float(getattr(d, "price", 0.0) or 0.0),
                        "volume": float(getattr(d, "volume", 0.0) or 0.0),
                        "profit": float(getattr(d, "profit", 0.0) or 0.0),
                        "comment": comment,
                        "ticket": int(getattr(d, "ticket", 0) or 0),
                    }
                )
        out_orders.sort(key=lambda x: x["time_setup"])
        out_deals.sort(key=lambda x: x["time"])
        return {"orders": out_orders, "deals": out_deals}

    def run_quick_backtest():
        hours = float(args.backtest_hours)
        symbol = (args.symbol or get_primary_symbol()).strip()
        if not symbol:
            symbol = get_primary_symbol()

        if not initialize_mt5():
            print("❌ MT5 initialization failed - exiting")
            return

        rates_last = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 1)
        if rates_last is not None and len(rates_last) > 0:
            end_dt = datetime.fromtimestamp(int(rates_last[0]["time"]), tz=timezone.utc).replace(tzinfo=None) + timedelta(
                minutes=5
            )
        else:
            end_dt = datetime.now()
        start_dt = end_dt - timedelta(hours=hours)

        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            print("❌ Cannot get symbol info")
            return
        if not symbol_info.visible:
            mt5.symbol_select(symbol, True)
            symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            print("❌ Cannot get symbol info after select")
            return

        all_tfs = set(SIGNAL_SCAN_TIMEFRAMES) | set(MTF_WEIGHTS.keys()) | {mt5.TIMEFRAME_M5, mt5.TIMEFRAME_H1}
        history_by_tf: Dict[int, pd.DataFrame] = {}
        hours_total = float(hours) + float(args.warmup_hours)
        for tf in sorted(all_tfs):
            tf_sec = _timeframe_seconds(int(tf))
            bars_needed = int((hours_total * 3600.0) / float(tf_sec)) + 300
            df = _fetch_rates_df(symbol, tf, bars_needed)
            if df is not None and len(df) > 0:
                history_by_tf[tf] = df

        base_df = history_by_tf.get(mt5.TIMEFRAME_M5)
        if base_df is None or len(base_df) < 50:
            print("❌ Insufficient M5 data for backtest")
            return

        base_tf_sec = _timeframe_seconds(mt5.TIMEFRAME_M5)
        bt_df = base_df[
            (base_df["time"] >= (pd.Timestamp(start_dt) - pd.Timedelta(seconds=base_tf_sec)))
            & (base_df["time"] <= (pd.Timestamp(end_dt) - pd.Timedelta(seconds=base_tf_sec)))
        ]
        if bt_df is None or len(bt_df) < 10:
            print("❌ Insufficient data in backtest window")
            return

        risk_cfg = CONFIG.get("risk", {}) if isinstance(CONFIG.get("risk"), dict) else {}
        max_open_trades = int(risk_cfg.get("max_open_trades", 4))

        sensitivity = get_sensitivity_level()
        sensitivity_cfg = CONFIG.get("sensitivity", {}) if isinstance(CONFIG.get("sensitivity"), dict) else {}
        cd_cfg = sensitivity_cfg.get("gatekeeper_cooldown_seconds", {}) if isinstance(sensitivity_cfg.get("gatekeeper_cooldown_seconds"), dict) else {}
        gatekeeper_cooldown = max(
            int(cd_cfg.get("min", 60)),
            int(cd_cfg.get("base", 120)) - (int(sensitivity) * int(cd_cfg.get("per_level_delta", 30))),
        )
        atr_cfg = sensitivity_cfg.get("gatekeeper_atr_multiplier", {}) if isinstance(sensitivity_cfg.get("gatekeeper_atr_multiplier"), dict) else {}
        gatekeeper_atr = max(
            float(atr_cfg.get("min", 1.2)),
            float(atr_cfg.get("base", 1.6)) - (float(sensitivity) * float(atr_cfg.get("per_level_delta", 0.15))),
        )
        hard_cfg = sensitivity_cfg.get("gatekeeper_min_points", {}) if isinstance(sensitivity_cfg.get("gatekeeper_min_points"), dict) else {}
        gatekeeper_hard_points = max(
            float(hard_cfg.get("min", 80.0)),
            float(hard_cfg.get("base", 120.0)) - (float(sensitivity) * float(hard_cfg.get("per_level_delta", 20.0))),
        )

        gatekeeper_state: Dict[str, object] = {"last_trade_time": None, "last_trade_price": None, "last_trade_type": None, "last_candle_ts": None}

        open_trades: List[Dict] = []
        closed_trades: List[Dict] = []
        metrics: Dict[str, int] = {}
        rejects: Dict[str, int] = {}
        spread_points = max(0.0, float(args.spread_points))
        point = float(getattr(symbol_info, "point", 0.0) or 0.0)

        for _, row in bt_df.iterrows():
            metrics["bars_processed"] = int(metrics.get("bars_processed", 0)) + 1
            bar_open_ts = pd.Timestamp(row["time"])
            as_of_ts = bar_open_ts + pd.Timedelta(seconds=base_tf_sec)
            as_of_dt = as_of_ts.to_pydatetime()

            new_open: List[Dict] = []
            for t in open_trades:
                if t.get("status") != "OPEN":
                    continue
                trade_type = int(t["trade_type"])
                sl_price = float(t["sl_price"])
                tp_price = float(t["tp_price"])
                high = float(row["high"])
                low = float(row["low"])
                hit_sl = (low <= sl_price) if trade_type == mt5.ORDER_TYPE_BUY else (high >= sl_price)
                hit_tp = (high >= tp_price) if trade_type == mt5.ORDER_TYPE_BUY else (low <= tp_price)
                if hit_sl or hit_tp:
                    exit_price = sl_price if (hit_sl and hit_tp) else (sl_price if hit_sl else tp_price)
                    pnl_points = (exit_price - float(t["entry_price"])) / point if point > 0 else 0.0
                    if trade_type == mt5.ORDER_TYPE_SELL:
                        pnl_points = -pnl_points
                    t["exit_time"] = as_of_dt
                    t["exit_price"] = float(exit_price)
                    t["pnl_points"] = float(pnl_points)
                    t["result"] = "WIN" if pnl_points > 0 else "LOSS"
                    t["status"] = "CLOSED"
                    closed_trades.append(t)
                else:
                    new_open.append(t)
            open_trades = new_open

            if len(open_trades) >= max_open_trades:
                rejects["max_open_trades"] = int(rejects.get("max_open_trades", 0)) + 1
                continue

            tick_data = _build_tick_from_bar(row, spread_points, point, as_of_ts)
            signal = _backtest_trade_decision(symbol, as_of_ts, history_by_tf, tick_data, metrics, rejects)
            if not signal:
                continue
            signal["as_of_time"] = as_of_dt

            trade_type = mt5.ORDER_TYPE_BUY if signal["signal"] == "BUY" else mt5.ORDER_TYPE_SELL
            allow, reason = _gatekeeper_allows(
                entry_price=float(tick_data["ask"] if trade_type == mt5.ORDER_TYPE_BUY else tick_data["bid"]),
                symbol_info=symbol_info,
                trade_type=trade_type,
                state=gatekeeper_state,
                as_of_dt=as_of_dt,
                as_of_ts=as_of_ts,
                history_by_tf=history_by_tf,
                cooldown_seconds=gatekeeper_cooldown,
                min_distance_atr_multiplier=gatekeeper_atr,
                min_hardcoded_points=gatekeeper_hard_points,
            )
            if not allow:
                rejects[f"gatekeeper_{reason}"] = int(rejects.get(f"gatekeeper_{reason}", 0)) + 1
                continue

            fill = _simulate_fill_and_sl_tp(symbol, signal, tick_data, history_by_tf, as_of_ts)
            if not fill:
                rejects["fill_failed"] = int(rejects.get("fill_failed", 0)) + 1
                continue

            candle_guard_key = f"{symbol}:{int(signal.get('source_timeframe', mt5.TIMEFRAME_M15))}:{int(trade_type)}"
            EXECUTION_CANDLE_GUARD[candle_guard_key] = _candle_open_ts(
                as_of_ts,
                int(signal.get("source_timeframe", mt5.TIMEFRAME_M15)),
            )

            trade = {
                "status": "OPEN",
                "open_time": as_of_dt,
                "symbol": symbol,
                "trade_type": int(fill["trade_type"]),
                "direction": "BUY" if int(fill["trade_type"]) == mt5.ORDER_TYPE_BUY else "SELL",
                "source_tf": timeframe_label(int(signal.get("source_timeframe", mt5.TIMEFRAME_M15))),
                "strategy": str(signal.get("strategy", "")),
                "regime": str(signal.get("regime", "")),
                "mtf_score": float(signal.get("mtf_confluence_score", 0.0) or 0.0),
                "mtf_threshold": float(signal.get("mtf_confluence_threshold", 0.0) or 0.0),
                "entry_price": float(fill["entry_price"]),
                "sl_price": float(fill["sl_price"]),
                "tp_price": float(fill["tp_price"]),
                "sl_points": float(fill["sl_points"]),
                "tp_points": float(fill["tp_points"]),
                "gatekeeper_reason": str(reason),
            }
            open_trades.append(trade)
            metrics["executed_trades"] = int(metrics.get("executed_trades", 0)) + 1
            gatekeeper_state["last_trade_time"] = as_of_dt
            gatekeeper_state["last_trade_price"] = float(fill["entry_price"])
            gatekeeper_state["last_trade_type"] = int(trade_type)
            gatekeeper_state["last_candle_ts"] = _candle_open_ts(as_of_ts, mt5.TIMEFRAME_M5)

        total = len(closed_trades)
        wins = sum(1 for t in closed_trades if t.get("result") == "WIN")
        losses = sum(1 for t in closed_trades if t.get("result") == "LOSS")
        winrate = (wins / total * 100.0) if total > 0 else 0.0
        avg_pnl_points = float(np.mean([t.get("pnl_points", 0.0) for t in closed_trades])) if total > 0 else 0.0
        sum_pnl_points = float(np.sum([t.get("pnl_points", 0.0) for t in closed_trades])) if total > 0 else 0.0

        print("\n📊 BACKTEST SUMMARY (approx)")
        print(f"Symbol: {symbol}")
        print(f"Window: {start_dt} -> {end_dt} (~{hours} hours)")
        print(f"Trades closed: {total} | Wins: {wins} | Losses: {losses} | Winrate: {winrate:.1f}%")
        print(f"PnL points: sum {sum_pnl_points:.1f} | avg/trade {avg_pnl_points:.1f}")
        print(f"Trades still open at end: {len(open_trades)}")
        if closed_trades:
            print("\nClosed trades (last 10):")
            for t in closed_trades[-10:]:
                ot = t.get("open_time")
                et = t.get("exit_time")
                ot_s = ot.isoformat(sep=" ", timespec="seconds") if isinstance(ot, datetime) else str(ot)
                et_s = et.isoformat(sep=" ", timespec="seconds") if isinstance(et, datetime) else str(et)
                print(
                    f"- {ot_s} -> {et_s} {t.get('direction')} "
                    f"pnl_pts={float(t.get('pnl_points', 0.0) or 0.0):.1f} "
                    f"tf={t.get('source_tf')} strat={t.get('strategy')} reg={t.get('regime')} "
                    f"mtf={float(t.get('mtf_score', 0.0) or 0.0):.1f}/{float(t.get('mtf_threshold', 0.0) or 0.0):.1f}"
                )
        if metrics:
            keys = [
                "bars_processed",
                "decision_calls",
                "raw_signals",
                "mtf_passed",
                "selected_signals",
                "executed_trades",
            ]
            parts = [f"{k}={int(metrics.get(k, 0))}" for k in keys]
            print("Metrics:", " | ".join(parts))
        if rejects:
            top = sorted(rejects.items(), key=lambda kv: kv[1], reverse=True)[:10]
            top_str = " | ".join(f"{k}={v}" for k, v in top)
            print("Top rejects:", top_str)

        if bool(args.compare_live):
            history = _fetch_live_history(symbol, start_dt, end_dt)
            print("\n🧾 LIVE HISTORY (MT5)")
            print(f"Orders (magic=234000, Advanced_*): {len(history['orders'])}")
            print(f"Deals  (magic=234000, Advanced_*): {len(history['deals'])}")
            deals = history["deals"]
            deals_symbol = [d for d in deals if str(d.get("symbol", "") or "") == str(symbol)]
            entry_deals = [d for d in deals_symbol if int(d.get("entry", 0)) == 0]
            exit_deals = [d for d in deals_symbol if int(d.get("entry", 0)) != 0]
            profit_sum = (
                float(np.sum([float(d.get("profit", 0.0) or 0.0) for d in deals_symbol])) if deals_symbol else 0.0
            )
            print(f"Deal entries/exits: {len(entry_deals)}/{len(exit_deals)} | Profit sum: {profit_sum:.2f}")

            def _dir_from_deal_type(deal_type: int) -> str:
                if int(deal_type) == 0:
                    return "BUY"
                if int(deal_type) == 1:
                    return "SELL"
                return "UNKNOWN"

            def _bucket_ts(ts: int, tf_sec: int) -> int:
                return int(ts // tf_sec) * tf_sec

            def _dt_to_epoch_seconds(dt: datetime) -> int:
                if dt.tzinfo is None:
                    return int(dt.replace(tzinfo=timezone.utc).timestamp())
                return int(dt.astimezone(timezone.utc).timestamp())

            def _as_naive_dt(x: object) -> datetime | None:
                if isinstance(x, datetime):
                    if x.tzinfo is None:
                        return x
                    return x.astimezone(timezone.utc).replace(tzinfo=None)
                if isinstance(x, pd.Timestamp):
                    return x.to_pydatetime().replace(tzinfo=None)
                return None

            m15_sec = _timeframe_seconds(mt5.TIMEFRAME_M15)
            live_buckets: Dict[Tuple[int, str], int] = {}
            for d in entry_deals:
                ts = int(d.get("time", 0) or 0)
                key = (_bucket_ts(ts, m15_sec), _dir_from_deal_type(int(d.get("type", -1))))
                live_buckets[key] = int(live_buckets.get(key, 0)) + 1

            bt_buckets: Dict[Tuple[int, str], int] = {}
            for t in (closed_trades + open_trades):
                ot = _as_naive_dt(t.get("open_time"))
                if ot is None:
                    continue
                ts = _dt_to_epoch_seconds(ot)
                key = (_bucket_ts(ts, m15_sec), str(t.get("direction", "UNKNOWN")))
                bt_buckets[key] = int(bt_buckets.get(key, 0)) + 1

            live_bucket_times = [int(k[0]) for k in live_buckets.keys()]
            live_min_bucket = min(live_bucket_times) if live_bucket_times else None
            live_max_bucket = max(live_bucket_times) if live_bucket_times else None
            if live_min_bucket is not None and live_max_bucket is not None:
                bt_buckets_overlap = {
                    k: v for k, v in bt_buckets.items() if live_min_bucket <= int(k[0]) <= live_max_bucket
                }
            else:
                bt_buckets_overlap = {}

            match = 0
            for key, bt_count in bt_buckets.items():
                live_count = int(live_buckets.get(key, 0))
                match += min(int(bt_count), live_count)

            overlap_match = 0
            for key, bt_count in bt_buckets_overlap.items():
                live_count = int(live_buckets.get(key, 0))
                overlap_match += min(int(bt_count), live_count)

            live_by_time: Dict[int, int] = {}
            for (bucket_ts, _dir), count in live_buckets.items():
                live_by_time[int(bucket_ts)] = int(live_by_time.get(int(bucket_ts), 0)) + int(count)
            bt_by_time: Dict[int, int] = {}
            for (bucket_ts, _dir), count in bt_buckets.items():
                bt_by_time[int(bucket_ts)] = int(bt_by_time.get(int(bucket_ts), 0)) + int(count)

            time_only_match = 0
            for bucket_ts, bt_count in bt_by_time.items():
                time_only_match += min(int(bt_count), int(live_by_time.get(int(bucket_ts), 0)))

            bt_total = sum(bt_buckets.values())
            live_total = sum(live_buckets.values())
            overlap_total = sum(bt_buckets_overlap.values())
            window_str = (
                f"{datetime.fromtimestamp(live_min_bucket, tz=timezone.utc).replace(tzinfo=None)}"
                f" -> {datetime.fromtimestamp(live_max_bucket, tz=timezone.utc).replace(tzinfo=None)}"
                if (live_min_bucket is not None and live_max_bucket is not None)
                else "n/a"
            )
            print(f"Approx M15 entry match (time+dir): {match} | bt={bt_total} live={live_total}")
            print(f"Approx M15 entry match (overlap): {overlap_match} | bt={overlap_total} live={live_total} | window={window_str}")
            print(f"Approx M15 entry match (time only): {time_only_match} | bt={sum(bt_by_time.values())} live={sum(live_by_time.values())}")

            def _counts_by_bucket_dir(buckets: Dict[Tuple[int, str], int]) -> Dict[int, Dict[str, int]]:
                out: Dict[int, Dict[str, int]] = {}
                for (bucket_ts, direction), count in buckets.items():
                    b = int(bucket_ts)
                    d = str(direction)
                    if b not in out:
                        out[b] = {}
                    out[b][d] = int(out[b].get(d, 0)) + int(count)
                return out

            if live_min_bucket is not None and live_max_bucket is not None:
                live_by_bucket_dir = _counts_by_bucket_dir(live_buckets)
                bt_by_bucket_dir = _counts_by_bucket_dir(bt_buckets)
                bucket_ts_union = sorted(
                    {
                        int(b)
                        for b in set(live_by_bucket_dir.keys()).union(set(bt_by_bucket_dir.keys()))
                        if live_min_bucket <= int(b) <= live_max_bucket
                    }
                )

                diffs: List[Tuple[int, int, int, int, int, int]] = []
                for b in bucket_ts_union:
                    live_counts = live_by_bucket_dir.get(b, {})
                    bt_counts = bt_by_bucket_dir.get(b, {})
                    l_buy = int(live_counts.get("BUY", 0))
                    l_sell = int(live_counts.get("SELL", 0))
                    bt_buy = int(bt_counts.get("BUY", 0))
                    bt_sell = int(bt_counts.get("SELL", 0))
                    if (l_buy != bt_buy) or (l_sell != bt_sell):
                        diffs.append((b, bt_buy, bt_sell, l_buy, l_sell, abs((bt_buy + bt_sell) - (l_buy + l_sell))))

                diffs = sorted(diffs, key=lambda x: (x[5], abs((x[1] - x[3])) + abs((x[2] - x[4]))), reverse=True)[:10]
                if diffs:
                    print("Top M15 bucket diffs (overlap, BUY/SELL):")
                    for b, bt_buy, bt_sell, l_buy, l_sell, _d in diffs:
                        dt = datetime.fromtimestamp(int(b), tz=timezone.utc).replace(tzinfo=None)
                        print(f"- {dt} | bt BUY/SELL={bt_buy}/{bt_sell} | live BUY/SELL={l_buy}/{l_sell}")

            bt_windows: List[Tuple[datetime, datetime | None, str, str, str]] = []
            for t in closed_trades:
                ot = _as_naive_dt(t.get("open_time"))
                ct = _as_naive_dt(t.get("exit_time"))
                if ot is not None:
                    bt_windows.append(
                        (
                            ot,
                            ct,
                            str(t.get("direction", "UNKNOWN")),
                            str(t.get("strategy", "")),
                            str(t.get("source_tf", "") or ""),
                        )
                    )
            for t in open_trades:
                ot = _as_naive_dt(t.get("open_time"))
                if ot is not None:
                    bt_windows.append(
                        (ot, None, str(t.get("direction", "UNKNOWN")), str(t.get("strategy", "")), str(t.get("source_tf", "") or ""))
                    )

            if bt_windows and entry_deals:
                print("Live entry vs backtest state (nearest/open):")
                entry_deals_sorted = sorted(entry_deals, key=lambda d: int(d.get("time", 0) or 0))
                for d in entry_deals_sorted[:10]:
                    live_ts = int(d.get("time", 0) or 0)
                    live_dt = datetime.fromtimestamp(live_ts, tz=timezone.utc).replace(tzinfo=None)
                    live_dir = _dir_from_deal_type(int(d.get("type", -1)))

                    open_now = [
                        w
                        for w in bt_windows
                        if w[0] <= live_dt and (w[1] is None or live_dt <= w[1])
                    ]
                    nearest = min(
                        bt_windows,
                        key=lambda w: abs((live_dt - w[0]).total_seconds()),
                    )
                    nearest_delta_s = int((live_dt - nearest[0]).total_seconds())

                    if open_now:
                        w0 = open_now[0]
                        w0_end = w0[1] if w0[1] is not None else live_dt
                        print(
                            f"- {live_dt} live={live_dir} | bt_open={len(open_now)} "
                            f"sample={w0[2]} {w0[0]}->{w0_end} tf={w0[4]} strat={w0[3]} | "
                            f"nearest={nearest[2]} Δs={nearest_delta_s}"
                        )
                    else:
                        print(f"- {live_dt} live={live_dir} | bt_open=0 | nearest={nearest[2]} Δs={nearest_delta_s}")

            for d in deals_symbol[-10:]:
                ts = datetime.fromtimestamp(int(d["time"]), tz=timezone.utc).replace(tzinfo=None)
                sym = str(d.get("symbol", "") or "")
                comment = str(d.get("comment", "") or "")
                print(
                    f"Deal {d['ticket']} {ts} sym={sym} type={d['type']} entry={d['entry']} "
                    f"price={d['price']:.2f} profit={d['profit']:.2f} comment={comment}"
                )

    if float(args.backtest_hours) > 0:
        run_quick_backtest()
    else:
        main()
