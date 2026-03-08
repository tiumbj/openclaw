"""
Execution Gatekeeper - Enterprise Signal Clustering Prevention

Features:
- Time-Based Cooldown: Prevents execution spam within same candle/bar
- Dynamic Price Distance Filter: ATR-based minimum distance enforcement
- State Tracking: Robust MT5 position-based state management
- Zero Silent Failures: Comprehensive validation and logging
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from typing import Optional, Tuple, List, TypedDict
from enum import Enum
import logging
import time
from datetime import datetime, timedelta


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


class ExecutionGatekeeper:
    """
    Enterprise-grade execution gatekeeper to prevent signal clustering
    
    Key Features:
    1. Time-Based Cooldown: Prevents execution within same operational timeframe
    2. Dynamic Price Distance: ATR-based minimum distance enforcement
    3. State Tracking: Robust MT5 position-based state management
    4. Zero Silent Failures: Comprehensive validation and logging
    """
    
    def __init__(
        self,
        operational_timeframe: int = mt5.TIMEFRAME_M5,
        min_cooldown_seconds: int = 300,  # 5 minutes for M5
        min_distance_atr_multiplier: float = 1.5,
        min_hardcoded_points: float = 50.0,
        max_retry_attempts: int = 3,
        retry_delay_seconds: float = 1.0
    ):
        """
        Initialize ExecutionGatekeeper with institutional configuration
        
        Args:
            operational_timeframe: MT5 timeframe for cooldown calculation
            min_cooldown_seconds: Minimum seconds between executions
            min_distance_atr_multiplier: ATR multiplier for dynamic distance
            min_hardcoded_points: Hardcoded minimum point distance
            max_retry_attempts: Maximum retry attempts for MT5 operations
            retry_delay_seconds: Delay between retry attempts
        """
        self.operational_timeframe = operational_timeframe
        self.min_cooldown_seconds = min_cooldown_seconds
        self.min_distance_atr_multiplier = min_distance_atr_multiplier
        self.min_hardcoded_points = min_hardcoded_points
        self.max_retries = max_retry_attempts
        self.retry_delay = retry_delay_seconds
        
        # Execution state
        self.execution_state: ExecutionState = {
            "last_trade_time": None,
            "last_trade_price": None,
            "last_trade_direction": None,
            "last_trade_symbol": None,
            "current_cooldown_end": None
        }
        
        # Setup enterprise logging
        self.logger = logging.getLogger("ExecutionGatekeeper")
        if not self.logger.handlers:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler("execution_gatekeeper.log"),
                    logging.StreamHandler()
                ]
            )
        
        self.logger.info(
            f"ExecutionGatekeeper initialized | "
            f"Cooldown: {min_cooldown_seconds}s | "
            f"Min Distance: {min_distance_atr_multiplier} ATR / {min_hardcoded_points} points"
        )
    
    def _fetch_current_atr(self, symbol: str, timeframe: int = mt5.TIMEFRAME_H1) -> Optional[float]:
        """
        Fetch current ATR value for dynamic distance calculation
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe for ATR calculation
            
        Returns:
            Current ATR value or None if failed
        """
        for attempt in range(self.max_retries):
            try:
                rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 100)
                if rates is None or len(rates) < 15:  # Minimum for ATR(14)
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
        Robust state tracking that survives bot restarts
        """
        try:
            positions = self._get_mt5_positions()
            
            if not positions:
                # No open positions, reset state
                self.execution_state = {
                    "last_trade_time": None,
                    "last_trade_price": None,
                    "last_trade_direction": None,
                    "last_trade_symbol": None,
                    "current_cooldown_end": None
                }
                return
            
            # Find the most recently opened position
            latest_position = max(positions, key=lambda p: p.time_update)
            
            # Convert MT5 timestamp to datetime
            trade_time = datetime.fromtimestamp(latest_position.time_update)
            
            self.execution_state.update({
                "last_trade_time": trade_time,
                "last_trade_price": latest_position.price_open,
                "last_trade_direction": latest_position.type,
                "last_trade_symbol": latest_position.symbol
            })
            
            # Calculate cooldown end time
            if trade_time:
                cooldown_end = trade_time + timedelta(seconds=self.min_cooldown_seconds)
                self.execution_state["current_cooldown_end"] = cooldown_end
            
            self.logger.debug(
                f"State updated | Last Trade: {trade_time} | "
                f"Price: {latest_position.price_open} | "
                f"Direction: {latest_position.type} | "
                f"Symbol: {latest_position.symbol}"
            )
            
        except Exception as e:
            self.logger.error(f"State update error: {e}")
    
    def _check_time_cooldown(self, current_time: datetime) -> Tuple[bool, Optional[str]]:
        """
        Check if time-based cooldown is active
        
        Args:
            current_time: Current datetime for comparison
            
        Returns:
            Tuple of (is_violated, rejection_reason)
        """
        if not self.execution_state["last_trade_time"]:
            return False, None  # No previous trade, cooldown not applicable
        
        if not self.execution_state["current_cooldown_end"]:
            return False, None  # No active cooldown
        
        time_since_last_trade = current_time - self.execution_state["last_trade_time"]
        
        if current_time < self.execution_state["current_cooldown_end"]:
            remaining_cooldown = self.execution_state["current_cooldown_end"] - current_time
            
            rejection_reason = (
                f"Cooldown active | "
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
        Check if proposed price meets minimum distance requirements
        
        Args:
            symbol: Trading symbol
            proposed_price: Proposed entry price
            direction: Trade direction
            
        Returns:
            Tuple of (is_violated, rejection_reason)
        """
        if not self.execution_state["last_trade_price"]:
            return False, None  # No previous trade price
        
        if self.execution_state["last_trade_symbol"] != symbol:
            return False, None  # Different symbol, distance not applicable
        
        if self.execution_state["last_trade_direction"] != direction:
            return False, None  # Different direction, distance not applicable
        
        # Calculate price distance
        price_distance = abs(proposed_price - self.execution_state["last_trade_price"])
        
        # Get symbol info for point conversion
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            self.logger.error(f"Symbol info not available for {symbol}")
            return False, None
        
        # Convert to points
        distance_points = price_distance / symbol_info.point
        
        # Calculate dynamic minimum distance
        atr_value = self._fetch_current_atr(symbol)
        dynamic_min_distance = 0.0
        
        if atr_value:
            dynamic_min_distance = atr_value * self.min_distance_atr_multiplier / symbol_info.point
        
        # Use the larger of dynamic or hardcoded minimum
        required_min_distance = max(dynamic_min_distance, self.min_hardcoded_points)
        
        if distance_points < required_min_distance:
            rejection_reason = (
                f"Price too close to existing position | "
                f"Current distance: {distance_points:.1f} points | "
                f"Required minimum: {required_min_distance:.1f} points | "
                f"Last trade price: {self.execution_state['last_trade_price']} | "
                f"Proposed price: {proposed_price}"
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
        Master validation function - must be called before every execution
        
        Args:
            symbol: Trading symbol
            order_type: MT5 order type (ORDER_TYPE_BUY/ORDER_TYPE_SELL)
            entry_price: Proposed entry price
            
        Returns:
            Tuple of (decision, rejection_reason)
        """
        try:
            current_time = datetime.now()
            
            # Update state from current MT5 positions
            self._update_execution_state()
            
            # Check 1: Time-based cooldown
            cooldown_violated, cooldown_reason = self._check_time_cooldown(current_time)
            if cooldown_violated:
                self.logger.warning(f"REJECTED: {cooldown_reason}")
                return GatekeeperDecision.REJECTED_COOLDOWN, cooldown_reason
            
            # Check 2: Price distance filter
            distance_violated, distance_reason = self._check_price_distance(
                symbol, entry_price, order_type
            )
            if distance_violated:
                self.logger.warning(f"REJECTED: {distance_reason}")
                return GatekeeperDecision.REJECTED_PRICE_DISTANCE, distance_reason
            
            # Check 3: Same direction validation (additional protection)
            if (self.execution_state["last_trade_direction"] == order_type and
                self.execution_state["last_trade_symbol"] == symbol):
                
                # Even if distance passes, ensure we're not spamming same direction
                time_since_last = current_time - self.execution_state["last_trade_time"]
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
                f"Price: {entry_price}"
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


def create_execution_gatekeeper() -> ExecutionGatekeeper:
    """
    Factory function to create configured ExecutionGatekeeper instance
    
    Returns:
        Configured ExecutionGatekeeper instance
    """
    return ExecutionGatekeeper(
        operational_timeframe=mt5.TIMEFRAME_M5,
        min_cooldown_seconds=300,           # 5 minutes for M5 timeframe
        min_distance_atr_multiplier=2.0,    # 2.0 ATR minimum distance for better precision
        min_hardcoded_points=75.0,         # 75 points absolute minimum for better filtering
        max_retry_attempts=3,
        retry_delay_seconds=1.0
    )


# Example usage in trading system
if __name__ == "__main__":
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed")
        exit(1)
    
    # Create execution gatekeeper
    gatekeeper = create_execution_gatekeeper()
    
    # Example: Validate execution
    symbol = "GOLD"
    order_type = mt5.ORDER_TYPE_BUY
    entry_price = 2000.0
    
    decision, reason = gatekeeper.validate_execution(symbol, order_type, entry_price)
    
    print(f"Decision: {decision.value}")
    if reason:
        print(f"Reason: {reason}")
    
    # Force state update from current positions
    gatekeeper.force_state_update()
    
    mt5.shutdown()