import MetaTrader5 as mt5
import logging
import math
from typing import Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass

class TradeDirection(Enum):
    BUY = 0
    SELL = 1

class RiskAssessmentResult(Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

@dataclass
class RiskAssessment:
    result: RiskAssessmentResult
    reason: str
    current_positions: int
    margin_level: float
    recommended_action: Optional[str] = None

class RiskFirewall:
    """
    Enterprise-Grade Risk Management Firewall.
    Designed for high-volatility assets like XAUUSD to strictly enforce capital preservation.
    """
    def __init__(self, max_open_trades: int = 4, max_risk_usd: float = 200.0, min_distance_points: float = 400.0):
        self.max_open_trades = max_open_trades
        self.max_risk_usd = max_risk_usd
        self.min_distance_points = min_distance_points  # ระยะห่างขั้นต่ำเพื่อป้องกันการยิงออเดอร์กระจุกตัว
        
        # Setup Enterprise Logging
        self.logger = logging.getLogger("RiskFirewall")
        if not self.logger.handlers:
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    def _calculate_safe_lot_size(self, symbol: str, order_type: int, entry_price: float, sl_price: float) -> float:
        """คำนวณ Lot Size ตามความเสี่ยง (Risk Amount) โดยดึงสเปคจริงจาก Broker"""
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            self.logger.error(f"Symbol {symbol} not found.")
            return 0.0

        step = float(getattr(symbol_info, "volume_step", 0.01) or 0.01)
        volume_min = float(getattr(symbol_info, "volume_min", 0.01) or 0.01)
        volume_max = float(getattr(symbol_info, "volume_max", 100.0) or 100.0)
        tick_size = float(getattr(symbol_info, "trade_tick_size", 0.0) or 0.0)
        tick_value = float(getattr(symbol_info, "trade_tick_value", 0.0) or 0.0)

        sl_distance_price = abs(entry_price - sl_price)
        if sl_distance_price == 0:
            return 0.0

        risk_per_standard_lot = None
        try:
            calc_profit = mt5.order_calc_profit(order_type, symbol, 1.0, float(entry_price), float(sl_price))
            if calc_profit is not None:
                risk_per_standard_lot = abs(float(calc_profit))
        except Exception:
            risk_per_standard_lot = None

        if risk_per_standard_lot is None:
            if tick_size <= 0 or tick_value <= 0:
                return 0.0
            ticks_at_risk = sl_distance_price / tick_size
            risk_per_standard_lot = ticks_at_risk * tick_value

        if risk_per_standard_lot <= 0:
            return 0.0

        raw_lot_size = float(self.max_risk_usd) / float(risk_per_standard_lot)
        if step <= 0:
            step = 0.01

        normalized_lot = math.floor(raw_lot_size / step) * step
        final_lot = max(volume_min, min(normalized_lot, volume_max))

        step_text = f"{step:.10f}".rstrip("0").rstrip(".")
        decimals = 0
        if "." in step_text:
            decimals = len(step_text.split(".", 1)[1])
        final_lot = math.floor(final_lot / step) * step
        return round(final_lot, decimals)

    def validate_signal(self, symbol: str, order_type: int, entry_price: float, sl_price: float) -> Dict[str, Any]:
        """
        The Master Gatekeeper.
        นำสัญญาณเทรดมาผ่านฟังก์ชันนี้ก่อนส่งคำสั่ง execution เสมอ
        Returns: Dict containing 'is_valid' (bool), 'lot_size' (float), and 'reason' (str)
        """
        # 1. Check Max Open Positions (The Broker Block Fix)
        positions = mt5.positions_get(symbol=symbol)
        if positions is None:
            self.logger.error("Failed to retrieve positions from MT5. Aborting trade for safety.")
            return {"is_valid": False, "lot_size": 0.0, "reason": "MT5 API Error (positions_get)"}
            
        current_positions_count = len(positions)
        if current_positions_count >= self.max_open_trades:
            self.logger.warning(f"REJECTED: Max open trades reached ({current_positions_count}/{self.max_open_trades}).")
            return {"is_valid": False, "lot_size": 0.0, "reason": "Max Positions Limit Hit"}

        # 2. Anti-Clustering (Distance Filter)
        # ตรวจสอบว่ามีออเดอร์ที่เปิดอยู่ใกล้กับราคาปัจจุบันเกินไปหรือไม่
        for pos in positions:
            if pos.type == order_type: # เทียบเฉพาะฝั่งเดียวกัน (Buy เทียบ Buy, Sell เทียบ Sell)
                distance = abs(entry_price - pos.price_open) / mt5.symbol_info(symbol).point
                if distance < self.min_distance_points:
                    self.logger.warning(f"REJECTED: Signal too close to existing position (Distance: {distance} points).")
                    return {"is_valid": False, "lot_size": 0.0, "reason": "Clustering / Distance Filter"}

        # 3. Calculate Lot Size Based on Risk
        lot_size = self._calculate_safe_lot_size(symbol, order_type, entry_price, sl_price)
        if lot_size <= 0:
            self.logger.warning("REJECTED: Calculated Lot Size is 0 or invalid.")
            return {"is_valid": False, "lot_size": 0.0, "reason": "Invalid Lot Size Calculation"}

        # 4. Final Margin Validation (Enterprise Check)
        # เช็คให้ชัวร์ว่า Margin ในพอร์ตมีพอให้เปิด Lot Size ที่คำนวณมาได้หรือไม่
        account_info = mt5.account_info()
        margin_required = mt5.order_calc_margin(order_type, symbol, lot_size, entry_price)
        
        if account_info is None or margin_required is None:
            self.logger.error("Failed to calculate margin requirements.")
            return {"is_valid": False, "lot_size": 0.0, "reason": "Margin Calculation Failed"}

        if margin_required > account_info.margin_free:
            self.logger.warning(f"REJECTED: Insufficient Free Margin. Required: {margin_required}, Free: {account_info.margin_free}")
            return {"is_valid": False, "lot_size": 0.0, "reason": "Insufficient Margin"}

        # หากผ่านทุกด่าน
        self.logger.info(f"SIGNAL APPROVED: {symbol}, Type: {order_type}, Lot: {lot_size}, Risk: ~${self.max_risk_usd}")
        return {"is_valid": True, "lot_size": lot_size, "reason": "Approved"}

    def assess_trade_risk(self, symbol: str, direction: TradeDirection, volume: float, price: Optional[float] = None) -> RiskAssessment:
        """
        Comprehensive risk assessment for trade execution
        """
        # For compatibility with existing code
        positions = mt5.positions_get()
        current_positions = len(positions) if positions else 0
        
        account_info = mt5.account_info()
        margin_level = (account_info.equity / account_info.margin) * 100 if account_info and account_info.margin > 0 else 0
        
        # Check max open trades
        if current_positions >= self.max_open_trades:
            return RiskAssessment(
                result=RiskAssessmentResult.REJECTED,
                reason=f"Max open trades reached ({current_positions}/{self.max_open_trades})",
                current_positions=current_positions,
                margin_level=margin_level
            )
        
        return RiskAssessment(
            result=RiskAssessmentResult.APPROVED,
            reason="Approved",
            current_positions=current_positions,
            margin_level=margin_level
        )
