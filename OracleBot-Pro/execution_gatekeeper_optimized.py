"""
Institutional-Grade Execution Gatekeeper for XAUUSD (GOLD)

Mathematically Optimized Parameters for XAUUSD:
- Minimum Distance: 300-500 points (3-5 USD) - Institutional grid/pyramid standard
- ATR Multiplier: 2.5x (accounts for Gold's high volatility)
- Time Cooldown: Strict same-candle blocking for M5/M15 timeframes

Key Features:
1. Strict Bar Delay: No trades within same candle (M5/M15 timeframe)
2. Normalized Distance Filter: Proper XAUUSD point interpretation
3. Volatility-Adaptive: ATR-based dynamic minimums
4. Enterprise Logging: Comprehensive audit trail
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from typing import Optional, Tuple, List, TypedDict
from enum import Enum
import logging
import time
from datetime import datetime, timedelta

from core.time_utils import MT5TimeConversionConfig, THAILAND_TZ, mt5_timestamp_to_thailand


_MT5_TIME_CFG = MT5TimeConversionConfig()


class GatekeeperDecision(Enum):
    """Execution gatekeeper decision outcomes"""
    APPROVED = "approved"
    REJECTED_COOLDOWN = "rejected_cooldown"
    REJECTED_PRICE_DISTANCE = "rejected_price_distance"
    REJECTED_SAME_DIRECTION = "rejected_same_direction"
    ERROR = "error"


class ExecutionState(TypedDict):
    """Execution state tracking structure"""
    last_trade_time: Optional[datetime]
    last_trade_price: Optional[float]
    last_trade_direction: Optional[int]
    last_trade_symbol: Optional[str]
    current_cooldown_end: Optional[datetime]
    last_candle_timestamp: Optional[datetime]


class InstitutionalExecutionGatekeeper:
    """
    Institutional-grade execution gatekeeper optimized for XAUUSD
    
    Mathematical Basis for XAUUSD Parameters:
    - Average Daily Range: 2000-3000 points (20-30 USD)
    - 5-min ATR: Typically 150-300 points (1.5-3.0 USD)
    - Institutional Grid Step: 300-500 points (3-5 USD)
    - Minimum Breathing Room: 2.5x ATR or 300 points (whichever larger)
    """
    
    def __init__(
        self,
        operational_timeframe: int = mt5.TIMEFRAME_M5,
        min_cooldown_seconds: int = 300,           # 5 minutes for M5
        min_distance_atr_multiplier: float = 2.5,  # 2.5x ATR for Gold volatility
        min_hardcoded_points: float = 300.0,        # 300 points institutional minimum
        max_retry_attempts: int = 3,
        retry_delay_seconds: float = 1.0
    ):
        """
        Initialize with XAUUSD-optimized institutional parameters
        
        Args:
            operational_timeframe: MT5 timeframe for strict candle blocking
            min_cooldown_seconds: Minimum seconds between executions
            min_distance_atr_multiplier: 2.5x ATR for Gold's high volatility
            min_hardcoded_points: 300 points institutional standard
        """
        self.operational_timeframe = operational_timeframe
        self.min_cooldown_seconds = min_cooldown_seconds
        self.min_distance_atr_multiplier = min_distance_atr_multiplier
        self.min_hardcoded_points = min_hardcoded_points
        self.max_retries = max_retry_attempts
        self.retry_delay = retry_delay_seconds
        
        # Execution state with candle tracking
        self.execution_state: ExecutionState = {
            "last_trade_time": None,
            "last_trade_price": None,
            "last_trade_direction": None,
            "last_trade_symbol": None,
            "current_cooldown_end": None,
            "last_candle_timestamp": None
        }
        
        # Setup enterprise logging
        self.logger = logging.getLogger("InstitutionalExecutionGatekeeper")
        if not self.logger.handlers:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler("institutional_gatekeeper.log"),
                    logging.StreamHandler()
                ]
            )
        
        self.logger.info(
            f"Institutional Gatekeeper initialized for XAUUSD | "
            f"Cooldown: {min_cooldown_seconds}s | "
            f"Min Distance: {min_distance_atr_multiplier}x ATR / {min_hardcoded_points} points"
        )
    
    def _get_current_candle_timestamp(self, symbol: str) -> Optional[datetime]:
        """
        Get timestamp of current candle's open time
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Current candle open timestamp or None
        """
        try:
            rates = mt5.copy_rates_from_pos(symbol, self.operational_timeframe, 0, 1)
            if rates is None or len(rates) == 0:
                return None

            return mt5_timestamp_to_thailand(rates[0]["time"], config=_MT5_TIME_CFG)
            
        except Exception as e:
            self.logger.error(f"Candle timestamp fetch error: {e}")
            return None

    def _get_current_server_time(self, symbol: str) -> Optional[datetime]:
        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None
            tick_time = getattr(tick, "time", None)
            if tick_time is None:
                return None
            return mt5_timestamp_to_thailand(tick_time, config=_MT5_TIME_CFG)
        except Exception as e:
            self.logger.error(f"Server time fetch error: {e}")
            return None
    
    def _is_same_candle(self, symbol: str, trade_time: datetime) -> bool:
        """
        Check if trade occurred in current candle
        
        Args:
            symbol: Trading symbol
            trade_time: Time of previous trade
            
        Returns:
            True if within same candle, False otherwise
        """
        current_candle_time = self._get_current_candle_timestamp(symbol)
        if not current_candle_time or not trade_time:
            return False
        
        timeframe_minutes = {
            mt5.TIMEFRAME_M1: 1,
            mt5.TIMEFRAME_M2: 2,
            mt5.TIMEFRAME_M3: 3,
            mt5.TIMEFRAME_M4: 4,
            mt5.TIMEFRAME_M5: 5,
            mt5.TIMEFRAME_M6: 6,
            mt5.TIMEFRAME_M10: 10,
            mt5.TIMEFRAME_M12: 12,
            mt5.TIMEFRAME_M15: 15,
            mt5.TIMEFRAME_M20: 20,
            mt5.TIMEFRAME_M30: 30,
            mt5.TIMEFRAME_H1: 60,
            mt5.TIMEFRAME_H2: 120,
            mt5.TIMEFRAME_H3: 180,
            mt5.TIMEFRAME_H4: 240,
        }
        candle_duration = timedelta(minutes=timeframe_minutes.get(self.operational_timeframe, 5))
        
        candle_end_time = current_candle_time + candle_duration
        
        return trade_time >= current_candle_time and trade_time < candle_end_time
    
    def _fetch_current_atr(self, symbol: str, timeframe: int = mt5.TIMEFRAME_H1) -> Optional[float]:
        """
        Fetch current ATR(14) value for dynamic distance calculation
        
        Args:
            symbol: Trading symbol
            timeframe: H1 for stable ATR calculation
            
        Returns:
            Current ATR value or None if failed
        """
        for attempt in range(self.max_retries):
            try:
                rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 100)
                if rates is None or len(rates) < 20:  # Minimum for stable ATR(14)
                    self.logger.warning(f"Insufficient data for ATR calculation (attempt {attempt + 1})")
                    time.sleep(self.retry_delay)
                    continue
                
                df = pd.DataFrame(rates)
                
                # Vectorized True Range calculation
                high_low = df['high'] - df['low']
                high_close = np.abs(df['high'] - df['close'].shift(1))
                low_close = np.abs(df['low'] - df['close'].shift(1))
                
                tr = np.maximum.reduce([high_low, high_close, low_close])
                
                # Wilder's smoothing for ATR(14)
                atr = tr.rolling(window=14).mean()
                current_atr = atr.iloc[-1]
                
                if pd.isna(current_atr):
                    self.logger.warning(f"ATR calculation returned NaN (attempt {attempt + 1})")
                    time.sleep(self.retry_delay)
                    continue
                
                return current_atr
                
            except Exception as e:
                self.logger.error(f"ATR fetch error (attempt {attempt + 1}): {e}")
                if attempt == self.max_retries - 1:
                    return None
                time.sleep(self.retry_delay)
        
        return None
    
    def _get_mt5_positions(self) -> List[mt5.TradePosition]:
        """
        Get current MT5 positions with robust error handling
        
        Returns:
            List of MT5 positions or empty list on error
        """
        for attempt in range(self.max_retries):
            try:
                positions = mt5.positions_get()
                if positions is None:
                    self.logger.warning(f"No positions received (attempt {attempt + 1})")
                    time.sleep(self.retry_delay)
                    continue
                
                return positions
                
            except Exception as e:
                self.logger.error(f"Position fetch error (attempt {attempt + 1}): {e}")
                if attempt == self.max_retries - 1:
                    return []
                time.sleep(self.retry_delay)
        
        return []
    
    def _update_execution_state(self):
        """
        Update execution state from current MT5 positions
        Includes strict candle-based tracking
        """
        try:
            positions = self._get_mt5_positions()
            
            if not positions:
                return
            
            # Find the most recently opened position
            latest_position = max(positions, key=lambda p: p.time_update)
            
            # Convert MT5 timestamp to datetime
            trade_time = mt5_timestamp_to_thailand(latest_position.time_update, config=_MT5_TIME_CFG)
            
            # Check if trade was in current candle
            current_candle_time = self._get_current_candle_timestamp(latest_position.symbol)
            
            self.execution_state.update({
                "last_trade_time": trade_time,
                "last_trade_price": latest_position.price_open,
                "last_trade_direction": latest_position.type,
                "last_trade_symbol": latest_position.symbol,
                "last_candle_timestamp": current_candle_time
            })
            
            # Calculate cooldown end time
            if trade_time:
                cooldown_end = trade_time + timedelta(seconds=self.min_cooldown_seconds)
                self.execution_state["current_cooldown_end"] = cooldown_end
            
            self.logger.debug(
                f"State updated | Last Trade: {trade_time} | "
                f"Price: {latest_position.price_open} | "
                f"Direction: {latest_position.type} | "
                f"Symbol: {latest_position.symbol} | "
                f"Current Candle: {current_candle_time}"
            )
            
        except Exception as e:
            self.logger.error(f"State update error: {e}")

    def record_execution(self, symbol: str, order_type: int, entry_price: float) -> None:
        try:
            now = self._get_current_server_time(symbol) or datetime.now(tz=THAILAND_TZ)
            self.execution_state.update({
                "last_trade_time": now,
                "last_trade_price": float(entry_price),
                "last_trade_direction": int(order_type),
                "last_trade_symbol": str(symbol),
                "last_candle_timestamp": self._get_current_candle_timestamp(symbol),
                "current_cooldown_end": now + timedelta(seconds=self.min_cooldown_seconds),
            })
        except Exception as e:
            self.logger.error(f"Execution record error: {e}")

    def _sanitize_state_times(self, current_time: datetime) -> None:
        last_trade_time = self.execution_state.get("last_trade_time")
        if not last_trade_time:
            return
        if last_trade_time > current_time:
            self.logger.warning(
                "Clock skew detected | "
                f"Last trade: {last_trade_time} | "
                f"Now: {current_time} | "
                f"Skew: {(last_trade_time - current_time).total_seconds():.1f}s"
            )
            self.execution_state["last_trade_time"] = current_time
            self.execution_state["current_cooldown_end"] = current_time + timedelta(seconds=self.min_cooldown_seconds)
            return
        cooldown_end = self.execution_state.get("current_cooldown_end")
        if cooldown_end and cooldown_end < last_trade_time:
            self.execution_state["current_cooldown_end"] = last_trade_time + timedelta(seconds=self.min_cooldown_seconds)
    
    def _check_strict_candle_cooldown(
        self,
        symbol: str,
        current_time: datetime,
        proposed_direction: Optional[int] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        STRICT CANDLE BLOCKING: No trades within same candle
        
        Args:
            symbol: Trading symbol
            current_time: Current datetime
            
        Returns:
            Tuple of (is_violated, rejection_reason)
        """
        if not self.execution_state["last_trade_time"]:
            return False, None  # No previous trade
        
        if not self.execution_state["last_candle_timestamp"]:
            return False, None  # No candle information
        
        if self.execution_state["last_trade_symbol"] != symbol:
            return False, None
        if (
            proposed_direction is not None and
            self.execution_state["last_trade_direction"] is not None and
            self.execution_state["last_trade_direction"] != proposed_direction
        ):
            return False, None
        # Check if last trade was in current candle
        if self._is_same_candle(symbol, self.execution_state["last_trade_time"]):
            rejection_reason = (
                f"STRICT CANDLE BLOCKING | "
                f"Last trade in current {self.operational_timeframe} candle | "
                f"Trade time: {self.execution_state['last_trade_time']} | "
                f"Candle start: {self.execution_state['last_candle_timestamp']}"
            )
            return True, rejection_reason
        
        return False, None
    
    def _check_time_cooldown(self, current_time: datetime) -> Tuple[bool, Optional[str]]:
        """
        Standard time-based cooldown check
        
        Args:
            current_time: Current datetime for comparison
            
        Returns:
            Tuple of (is_violated, rejection_reason)
        """
        if not self.execution_state["last_trade_time"]:
            return False, None
        
        if not self.execution_state["current_cooldown_end"]:
            return False, None
        
        time_since_last_trade = current_time - self.execution_state["last_trade_time"]
        
        if current_time < self.execution_state["current_cooldown_end"]:
            remaining_cooldown = self.execution_state["current_cooldown_end"] - current_time
            
            rejection_reason = (
                f"Time cooldown active | "
                f"Last trade: {self.execution_state['last_trade_time']} | "
                f"Time since: {time_since_last_trade.total_seconds():.1f}s | "
                f"Remaining: {remaining_cooldown.total_seconds():.1f}s"
            )
            
            return True, rejection_reason
        
        return False, None
    
    def _check_price_distance(
        self, 
        symbol: str, 
        proposed_price: float, 
        direction: int
    ) -> Tuple[bool, Optional[str]]:
        """
        Institutional-grade price distance check for XAUUSD
        
        Args:
            symbol: Trading symbol
            proposed_price: Proposed entry price
            direction: Trade direction
            
        Returns:
            Tuple of (is_violated, rejection_reason)
        """
        if not self.execution_state["last_trade_price"]:
            return False, None
        
        if self.execution_state["last_trade_symbol"] != symbol:
            return False, None
        
        if self.execution_state["last_trade_direction"] != direction:
            return False, None
        
        # Calculate price distance
        price_distance = abs(proposed_price - self.execution_state["last_trade_price"])
        
        # Get symbol info for proper point conversion
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            self.logger.error(f"Symbol info not available for {symbol}")
            return False, None
        
        # Convert to points (proper XAUUSD digit handling)
        distance_points = price_distance / symbol_info.point
        
        # Calculate dynamic minimum distance using ATR
        atr_value = self._fetch_current_atr(symbol)
        dynamic_min_distance = 0.0
        
        if atr_value:
            # Convert ATR to points for proper comparison
            dynamic_min_distance = atr_value * self.min_distance_atr_multiplier / symbol_info.point
        
        # Use the larger of dynamic or institutional hardcoded minimum
        required_min_distance = max(dynamic_min_distance, self.min_hardcoded_points)
        
        if distance_points < required_min_distance:
            rejection_reason = (
                f"Price distance violation | "
                f"Current: {distance_points:.1f} points | "
                f"Required: {required_min_distance:.1f} points | "
                f"Last price: {self.execution_state['last_trade_price']} | "
                f"Proposed: {proposed_price}"
            )
            
            if atr_value:
                rejection_reason += f" | ATR: {atr_value:.4f} ({dynamic_min_distance:.1f} points)"
            
            return True, rejection_reason
        
        return False, None
    
    def validate_execution(
        self, 
        symbol: str, 
        order_type: int, 
        entry_price: float
    ) -> Tuple[GatekeeperDecision, Optional[str]]:
        """
        Master validation function with STRICT candle blocking
        
        Args:
            symbol: Trading symbol
            order_type: MT5 order type
            entry_price: Proposed entry price
            
        Returns:
            Tuple of (decision, rejection_reason)
        """
        try:
            current_time = self._get_current_server_time(symbol) or datetime.now(tz=THAILAND_TZ)
            
            # Update state from current MT5 positions
            self._update_execution_state()
            self._sanitize_state_times(current_time)
            
            # Check 1: STRICT CANDLE BLOCKING (Highest priority)
            candle_violated, candle_reason = self._check_strict_candle_cooldown(
                symbol,
                current_time,
                order_type
            )
            if candle_violated:
                self.logger.warning(f"REJECTED: {candle_reason}")
                return GatekeeperDecision.REJECTED_COOLDOWN, candle_reason
            
            # Check 2: Standard time-based cooldown
            time_violated, time_reason = self._check_time_cooldown(current_time)
            if time_violated:
                self.logger.warning(f"REJECTED: {time_reason}")
                return GatekeeperDecision.REJECTED_COOLDOWN, time_reason
            
            # Check 3: Institutional price distance filter
            distance_violated, distance_reason = self._check_price_distance(
                symbol, entry_price, order_type
            )
            if distance_violated:
                self.logger.warning(f"REJECTED: {distance_reason}")
                return GatekeeperDecision.REJECTED_PRICE_DISTANCE, distance_reason
            
            # Check 4: Same direction additional protection
            if (self.execution_state["last_trade_direction"] == order_type and
                self.execution_state["last_trade_symbol"] == symbol):
                
                time_since_last = current_time - self.execution_state["last_trade_time"]
                if time_since_last.total_seconds() < 0:
                    time_since_last = timedelta(seconds=0)
                if time_since_last.total_seconds() < self.min_cooldown_seconds / 2:
                    rejection_reason = (
                        f"Same direction trade too soon | "
                        f"Time since: {time_since_last.total_seconds():.1f}s | "
                        f"Minimum: {self.min_cooldown_seconds / 2:.1f}s"
                    )
                    self.logger.warning(f"REJECTED: {rejection_reason}")
                    return GatekeeperDecision.REJECTED_SAME_DIRECTION, rejection_reason
            
            # All checks passed - execution approved
            approval_reason = (
                f"Execution approved | "
                f"Symbol: {symbol} | "
                f"Type: {order_type} | "
                f"Price: {entry_price} | "
                f"Strict candle blocking: PASSED"
            )
            
            self.logger.info(approval_reason)
            return GatekeeperDecision.APPROVED, approval_reason
            
        except Exception as e:
            error_msg = f"Validation error: {e}"
            self.logger.error(error_msg)
            return GatekeeperDecision.ERROR, error_msg
    
    def force_state_update(self):
        """Force update execution state from MT5 positions"""
        self._update_execution_state()
        self.logger.info("Execution state force-updated from MT5 positions")


def create_institutional_gatekeeper() -> InstitutionalExecutionGatekeeper:
    """
    Factory function for XAUUSD-optimized institutional gatekeeper
    
    Mathematical Basis:
    - XAUUSD Average 5-min ATR: ~150-300 points (1.5-3.0 USD)
    - 2.5x ATR Multiplier: 375-750 points dynamic minimum
    - Institutional Hardcoded Minimum: 300 points (3.0 USD)
    - Effective Minimum: MAX(2.5x ATR, 300 points)
    """
    return InstitutionalExecutionGatekeeper(
        operational_timeframe=mt5.TIMEFRAME_M5,
        min_cooldown_seconds=300,           # 5 minutes for M5
        min_distance_atr_multiplier=2.5,    # 2.5x ATR for Gold volatility
        min_hardcoded_points=300.0,         # 300 points institutional standard
        max_retry_attempts=3,
        retry_delay_seconds=1.0
    )


# Example usage and testing
if __name__ == "__main__":
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed")
        exit(1)
    
    # Create institutional gatekeeper
    gatekeeper = create_institutional_gatekeeper()
    
    # Test validation
    symbol = "XAUUSD"
    order_type = mt5.ORDER_TYPE_BUY
    entry_price = 2000.0
    
    decision, reason = gatekeeper.validate_execution(symbol, order_type, entry_price)
    
    print(f"Decision: {decision.value}")
    if reason:
        print(f"Reason: {reason}")
    
    # Force state update from current positions
    gatekeeper.force_state_update()
    
    mt5.shutdown()
