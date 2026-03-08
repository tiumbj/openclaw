"""
Dynamic Execution Manager for Volatility-Adjusted Trading and Swap Avoidance

Features:
- ATR-Based Dynamic SL/TP: Adjusts stops based on market volatility
- EOD Force Close: Avoids overnight swap fees with precise timing
- Capital Velocity Optimization: Adapts to ranging vs trending markets
- Enterprise-Grade MT5 Integration: Robust error handling and retry logic
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, Optional, TypedDict
from enum import Enum
import logging
import time


class ExecutionMode(Enum):
    """Trading execution modes based on volatility regime"""
    RANGING = "ranging"      # Tight SL/TP for scalping
    TRENDING = "trending"    # Wide SL/TP for momentum
    BREAKOUT = "breakout"    # Very wide SL/TP for volatility expansion


class DynamicSLTPResult(TypedDict):
    """Typed result for dynamic SL/TP calculation"""
    sl_price: float
    tp_price: float
    atr_value: float
    execution_mode: ExecutionMode
    risk_reward_ratio: float


class DynamicExecutionManager:
    """
    Enterprise-grade dynamic execution manager for volatility-adjusted trading
    
    Key Features:
    1. ATR-Based Dynamic SL/TP: Adaptive stops based on market volatility
    2. EOD Force Close: Precise swap avoidance before daily rollover
    3. Volatility Regime Detection: Ranging vs trending market adaptation
    4. Capital Velocity Optimization: Maximizes trade frequency in low volatility
    """
    
    def __init__(
        self,
        target_symbol: str = "GOLD",
        atr_period: int = 14,
        atr_timeframe: int = mt5.TIMEFRAME_H1,
        risk_reward_ratio: float = 1.5,
        swap_avoidance_time: dt_time = dt_time(23, 55),  # 23:55 for daily rollover
        swap_avoidance_buffer_minutes: int = 5,
        max_retry_attempts: int = 3,
        retry_delay_seconds: float = 1.0
    ):
        """
        Initialize DynamicExecutionManager with institutional configuration
        
        Args:
            target_symbol: Trading symbol (default: GOLD)
            atr_period: Period for ATR calculation
            atr_timeframe: Timeframe for ATR calculation
            risk_reward_ratio: Target R:R ratio for TP calculation
            swap_avoidance_time: Time to force close positions before swap
            swap_avoidance_buffer_minutes: Buffer minutes before swap time
            max_retry_attempts: Maximum retry attempts for MT5 operations
            retry_delay_seconds: Delay between retry attempts
        """
        self.target_symbol = target_symbol
        self.atr_period = atr_period
        self.atr_timeframe = atr_timeframe
        self.risk_reward_ratio = risk_reward_ratio
        self.swap_avoidance_time = swap_avoidance_time
        self.swap_buffer_minutes = swap_avoidance_buffer_minutes
        self.max_retries = max_retry_attempts
        self.retry_delay = retry_delay_seconds
        
        # Volatility regime thresholds (ATR multiples)
        self.regime_thresholds = {
            ExecutionMode.RANGING: 0.5,    # 0.5x ATR for tight ranges
            ExecutionMode.TRENDING: 1.0,   # 1.0x ATR for normal trends
            ExecutionMode.BREAKOUT: 2.0     # 2.0x ATR for high volatility
        }
        
        # Setup enterprise logging
        self.logger = logging.getLogger("DynamicExecutionManager")
        if not self.logger.handlers:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler("dynamic_execution.log"),
                    logging.StreamHandler()
                ]
            )
        
        self.logger.info(
            f"DynamicExecutionManager initialized for {target_symbol} | "
            f"RR: {risk_reward_ratio} | Swap Avoidance: {swap_avoidance_time}"
        )
    
    def _calculate_atr(self, bars: int = 100) -> Optional[float]:
        """
        Calculate current ATR value using vectorized pandas operations
        
        Args:
            bars: Number of bars for ATR calculation
            
        Returns:
            Current ATR value or None if calculation fails
        """
        try:
            # Fetch historical data with buffer for ATR calculation
            rates = mt5.copy_rates_from_pos(
                self.target_symbol, 
                self.atr_timeframe, 
                0, 
                bars + self.atr_period
            )
            
            if rates is None or len(rates) < self.atr_period + 1:
                self.logger.warning("Insufficient data for ATR calculation")
                return None
            
            # Convert to DataFrame for vectorized operations
            df = pd.DataFrame(rates)
            
            # Vectorized True Range calculation
            high_low = df['high'] - df['low']
            high_close = abs(df['high'] - df['close'].shift(1))
            low_close = abs(df['low'] - df['close'].shift(1))
            
            # Element-wise maximum for True Range
            true_range = np.maximum.reduce([high_low, high_close, low_close])
            
            # SMA of True Range for ATR
            atr = true_range.rolling(window=self.atr_period).mean().iloc[-1]
            
            self.logger.debug(f"ATR calculated: {atr:.4f} for {self.target_symbol}")
            return atr
            
        except Exception as e:
            self.logger.error(f"ATR calculation error: {e}")
            return None
    
    def _detect_volatility_regime(self, atr_value: float) -> ExecutionMode:
        """
        Detect current market volatility regime based on ATR percentiles
        
        Args:
            atr_value: Current ATR value
            
        Returns:
            ExecutionMode indicating current market regime
        """
        try:
            # Get historical ATR values for percentile calculation
            rates = mt5.copy_rates_from_pos(
                self.target_symbol, 
                self.atr_timeframe, 
                0, 
                500  # Sufficient data for percentile calculation
            )
            
            if rates is None or len(rates) < 100:
                self.logger.warning("Insufficient data for regime detection")
                return ExecutionMode.TRENDING
            
            df = pd.DataFrame(rates)
            
            # Calculate historical True Range
            high_low = df['high'] - df['low']
            high_close = abs(df['high'] - df['close'].shift(1))
            low_close = abs(df['low'] - df['close'].shift(1))
            true_range = np.maximum.reduce([high_low, high_close, low_close])
            
            # Calculate ATR percentiles
            atr_series = true_range.rolling(window=self.atr_period).mean()
            atr_series = atr_series.dropna()
            
            if len(atr_series) < 50:
                return ExecutionMode.TRENDING
            
            current_percentile = (atr_series < atr_value).mean()
            
            # Determine regime based on percentile
            if current_percentile < 0.3:
                return ExecutionMode.RANGING
            elif current_percentile > 0.7:
                return ExecutionMode.BREAKOUT
            else:
                return ExecutionMode.TRENDING
                
        except Exception as e:
            self.logger.error(f"Regime detection error: {e}")
            return ExecutionMode.TRENDING
    
    def calculate_dynamic_sltp(
        self, 
        entry_price: float, 
        direction: int,
        risk_per_trade: float = 0.01
    ) -> Optional[DynamicSLTPResult]:
        """
        Calculate dynamic SL/TP based on current volatility regime
        
        Args:
            entry_price: Entry price for the trade
            direction: Trade direction (mt5.ORDER_TYPE_BUY/SELL)
            risk_per_trade: Risk percentage per trade
            
        Returns:
            DynamicSLTPResult with calculated prices and regime info
        """
        try:
            # Calculate current ATR
            atr_value = self._calculate_atr()
            if atr_value is None:
                self.logger.error("Failed to calculate ATR for dynamic SL/TP")
                return None
            
            # Detect volatility regime
            regime = self._detect_volatility_regime(atr_value)
            atr_multiplier = self.regime_thresholds[regime]
            
            # Calculate SL distance based on regime
            sl_distance = atr_value * atr_multiplier
            
            # Calculate SL price
            if direction == mt5.ORDER_TYPE_BUY:
                sl_price = entry_price - sl_distance
                tp_price = entry_price + (sl_distance * self.risk_reward_ratio)
            else:  # SELL position
                sl_price = entry_price + sl_distance
                tp_price = entry_price - (sl_distance * self.risk_reward_ratio)
            
            # Validate prices are within reasonable bounds
            symbol_info = mt5.symbol_info(self.target_symbol)
            if symbol_info:
                # Ensure SL/TP are not too close to current price
                min_distance = symbol_info.point * 10  # 10 points minimum
                if abs(entry_price - sl_price) < min_distance:
                    sl_price = entry_price - min_distance if direction == mt5.ORDER_TYPE_BUY else entry_price + min_distance
                
                if abs(tp_price - entry_price) < min_distance:
                    tp_price = entry_price + min_distance if direction == mt5.ORDER_TYPE_BUY else entry_price - min_distance
            
            result: DynamicSLTPResult = {
                "sl_price": round(sl_price, 2),
                "tp_price": round(tp_price, 2),
                "atr_value": atr_value,
                "execution_mode": regime,
                "risk_reward_ratio": self.risk_reward_ratio
            }
            
            self.logger.info(
                f"Dynamic SL/TP calculated | Mode: {regime.value} | "
                f"Entry: {entry_price} | SL: {sl_price:.2f} | TP: {tp_price:.2f} | "
                f"ATR: {atr_value:.4f} | RR: {self.risk_reward_ratio}"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Dynamic SL/TP calculation error: {e}")
            return None
    
    def _should_force_close_for_swap(self) -> bool:
        """
        Check if current time requires force close to avoid swap fees
        
        Returns:
            True if positions should be force closed, False otherwise
        """
        try:
            # Get current broker server time
            server_time = mt5.time_trade_server()
            if server_time is None:
                self.logger.warning("Failed to get server time")
                return False
            
            current_time = datetime.fromtimestamp(server_time).time()
            
            # Calculate swap avoidance window
            swap_time = self.swap_avoidance_time
            buffer_time = timedelta(minutes=self.swap_buffer_minutes)
            
            swap_start = datetime.combine(datetime.today(), swap_time) - buffer_time
            swap_end = datetime.combine(datetime.today(), swap_time) + buffer_time
            
            current_datetime = datetime.combine(datetime.today(), current_time)
            
            # Check if current time is within swap avoidance window
            return swap_start <= current_datetime <= swap_end
            
        except Exception as e:
            self.logger.error(f"Swap time check error: {e}")
            return False
    
    def _force_close_positions(self) -> Dict[str, int]:
        """
        Force close all open positions for target symbol to avoid swap fees
        
        Returns:
            Dictionary with force close results
        """
        results = {
            "total_positions": 0,
            "closed_positions": 0,
            "errors": 0,
            "closed_tickets": []
        }
        
        try:
            # Get all positions for target symbol
            positions = mt5.positions_get(symbol=self.target_symbol)
            if positions is None:
                self.logger.info("No positions found for force close")
                return results
            
            results["total_positions"] = len(positions)
            
            if not positions:
                self.logger.info("No positions to force close")
                return results
            
            self.logger.warning(
                f"Initiating force close for {len(positions)} positions "
                f"to avoid swap fees at {self.swap_avoidance_time}"
            )
            
            for position in positions:
                for attempt in range(self.max_retries):
                    try:
                        # Prepare close request
                        tick = mt5.symbol_info_tick(self.target_symbol)
                        if not tick:
                            self.logger.error(f"Failed to get tick data for {self.target_symbol}")
                            continue
                        
                        price = tick.ask if position.type == mt5.ORDER_TYPE_BUY else tick.bid
                        
                        request = {
                            "action": mt5.TRADE_ACTION_DEAL,
                            "position": position.ticket,
                            "symbol": self.target_symbol,
                            "volume": position.volume,
                            "type": mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
                            "price": price,
                            "deviation": 20,
                            "magic": position.magic,
                            "comment": f"SWAP_AVOIDANCE_{datetime.now().strftime('%H%M%S')}",
                            "type_time": mt5.ORDER_TIME_SPECIFIED,
                            "type_filling": mt5.ORDER_FILLING_FOK
                        }
                        
                        # Send close order
                        result = mt5.order_send(request)
                        
                        if result.retcode == mt5.TRADE_RETCODE_DONE:
                            results["closed_positions"] += 1
                            results["closed_tickets"].append(position.ticket)
                            
                            self.logger.info(
                                f"Force closed position {position.ticket} | "
                                f"P/L: ${position.profit:.2f} | "
                                f"Volume: {position.volume:.2f} lots"
                            )
                            break
                        
                        else:
                            self.logger.warning(
                                f"Force close failed (attempt {attempt + 1}): "
                                f"Ticket {position.ticket}, Error: {result.retcode}"
                            )
                            
                            if attempt == self.max_retries - 1:
                                results["errors"] += 1
                            
                            time.sleep(self.retry_delay)
                            
                    except Exception as e:
                        self.logger.error(f"Force close error for ticket {position.ticket}: {e}")
                        if attempt == self.max_retries - 1:
                            results["errors"] += 1
                        time.sleep(self.retry_delay)
            
            self.logger.info(
                f"Force close completed: {results['closed_positions']}/"
                f"{results['total_positions']} positions closed"
            )
            
            return results
            
        except Exception as e:
            self.logger.error(f"Fatal error in force close: {e}")
            results["errors"] += 1
            return results
    
    def execute_swap_avoidance(self) -> Dict[str, int]:
        """
        Execute swap avoidance procedure if within swap avoidance window
        
        Returns:
            Dictionary with execution results
        """
        if self._should_force_close_for_swap():
            return self._force_close_positions()
        else:
            self.logger.debug("Not within swap avoidance time window")
            return {"total_positions": 0, "closed_positions": 0, "errors": 0, "closed_tickets": []}


def create_dynamic_execution_manager() -> DynamicExecutionManager:
    """
    Factory function to create configured DynamicExecutionManager instance
    
    Returns:
        Configured DynamicExecutionManager instance
    """
    return DynamicExecutionManager(
        target_symbol="GOLD",
        atr_period=14,
        atr_timeframe=mt5.TIMEFRAME_H1,
        risk_reward_ratio=1.5,
        swap_avoidance_time=time(23, 55),  # Force close at 23:55
        swap_avoidance_buffer_minutes=5,    # 5 minutes buffer
        max_retry_attempts=3,
        retry_delay_seconds=1.0
    )


# Example usage in trading system
if __name__ == "__main__":
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed")
        exit(1)
    
    # Create execution manager
    execution_manager = create_dynamic_execution_manager()
    
    # Example: Calculate dynamic SL/TP for a trade
    entry_price = 2000.0
    direction = mt5.ORDER_TYPE_BUY
    
    sltp_result = execution_manager.calculate_dynamic_sltp(entry_price, direction)
    if sltp_result:
        print(f"Dynamic SL: {sltp_result['sl_price']}")
        print(f"Dynamic TP: {sltp_result['tp_price']}")
        print(f"Volatility Regime: {sltp_result['execution_mode'].value}")
    
    # Example: Check and execute swap avoidance
    swap_results = execution_manager.execute_swap_avoidance()
    print(f"Swap avoidance: {swap_results['closed_positions']} positions closed")
    
    mt5.shutdown()
