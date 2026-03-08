"""
Enterprise Trade Manager for Post-Trade Management and Capital Preservation

Features:
- Symbol Lock: Strictly manages only target symbol positions
- Auto Break-Even: Moves SL to entry price + buffer when profit threshold reached
- Dynamic Trailing Stop: ATR-based trailing stop that locks in profits
- MT5 Safe Modification: Robust error handling for MT5 order modifications
- Enterprise Logging: Comprehensive logging for audit and monitoring
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
import logging
import time


class TradeAction(Enum):
    """Trade modification actions"""
    NO_ACTION = "no_action"
    MOVE_TO_BREAKEVEN = "move_to_breakeven"
    TRAILING_STOP = "trailing_stop"
    ERROR = "error"


class TradeManager:
    """
    Enterprise-grade post-trade management system for MetaTrader 5
    
    Key Features:
    1. Symbol Verification: Only manages positions for specified target symbol
    2. Auto Break-Even: Moves SL to entry + spread when profit threshold reached
    3. Dynamic Trailing Stop: ATR-based trailing with profit locking
    4. MT5 Safe Modification: Robust error handling and requote management
    5. Enterprise Logging: Comprehensive audit trail and monitoring
    """
    
    def __init__(
        self,
        target_symbol: str = "GOLD",
        breakeven_threshold_points: float = 300.0,
        trailing_stop_atr_multiplier: float = 1.5,
        atr_period: int = 14,
        atr_timeframe: int = mt5.TIMEFRAME_H1,
        spread_buffer_points: float = 5.0,
        max_retry_attempts: int = 3,
        retry_delay_seconds: float = 1.0
    ):
        """
        Initialize TradeManager with enterprise configuration
        
        Args:
            target_symbol: Only manage positions for this symbol
            breakeven_threshold_points: Profit threshold for break-even activation (points)
            trailing_stop_atr_multiplier: ATR multiplier for trailing stop distance
            atr_period: Period for ATR calculation
            atr_timeframe: Timeframe for ATR calculation
            spread_buffer_points: Buffer to add above entry price for break-even
            max_retry_attempts: Maximum retry attempts for MT5 operations
            retry_delay_seconds: Delay between retry attempts
        """
        self.target_symbol = target_symbol
        self.breakeven_threshold = breakeven_threshold_points
        self.trailing_multiplier = trailing_stop_atr_multiplier
        self.atr_period = atr_period
        self.atr_timeframe = atr_timeframe
        self.spread_buffer = spread_buffer_points
        self.max_retries = max_retry_attempts
        self.retry_delay = retry_delay_seconds
        
        # Setup enterprise logging
        self.logger = logging.getLogger("TradeManager")
        if not self.logger.handlers:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler("trade_manager.log"),
                    logging.StreamHandler()
                ]
            )
        
        self.logger.info(f"TradeManager initialized for symbol: {target_symbol}")
    
    def _get_target_positions(self) -> List:
        """
        Get only positions for the target symbol with strict filtering
        
        Returns:
            List of MT5 position objects for target symbol only
        """
        try:
            all_positions = mt5.positions_get()
            if all_positions is None:
                return []
            
            # Strict symbol filtering - only exact matches
            target_positions = [
                pos for pos in all_positions 
                if pos.symbol == self.target_symbol
            ]
            
            return target_positions
            
        except Exception as e:
            self.logger.error(f"Error getting positions: {e}")
            return []
    
    def _calculate_atr(self, bars: int = 50) -> Optional[float]:
        """
        Calculate current ATR value for trailing stop distance
        
        Args:
            bars: Number of bars to use for ATR calculation
            
        Returns:
            ATR value in points or None if calculation fails
        """
        try:
            rates = mt5.copy_rates_from_pos(
                self.target_symbol, 
                self.atr_timeframe, 
                0, 
                bars + self.atr_period
            )
            
            if rates is None or len(rates) < self.atr_period + 1:
                self.logger.warning("Insufficient data for ATR calculation")
                return None
            
            df = pd.DataFrame(rates)
            df['high_low'] = df['high'] - df['low']
            df['high_close'] = abs(df['high'] - df['close'].shift(1))
            df['low_close'] = abs(df['low'] - df['close'].shift(1))
            df['true_range'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
            
            atr = df['true_range'].tail(self.atr_period).mean()
            return atr
            
        except Exception as e:
            self.logger.error(f"ATR calculation error: {e}")
            return None
    
    def _should_move_to_breakeven(self, position) -> bool:
        """
        Determine if position should be moved to break-even
        
        Args:
            position: MT5 position object
            
        Returns:
            True if break-even condition is met
        """
        try:
            # Get current price based on position type
            if position.type == mt5.ORDER_TYPE_BUY:
                current_price = mt5.symbol_info_tick(self.target_symbol).ask
                profit_points = current_price - position.price_open
            else:  # SELL position
                current_price = mt5.symbol_info_tick(self.target_symbol).bid
                profit_points = position.price_open - current_price
            
            # Check if profit exceeds break-even threshold
            return profit_points >= self.breakeven_threshold
            
        except Exception as e:
            self.logger.error(f"Break-even check error: {e}")
            return False
    
    def _calculate_new_sl_price(self, position, current_price: float) -> float:
        """
        Calculate new stop loss price for trailing or break-even
        
        Args:
            position: MT5 position object
            current_price: Current market price
            
        Returns:
            New stop loss price
        """
        if position.type == mt5.ORDER_TYPE_BUY:
            # For BUY positions, calculate ATR-based trailing stop
            atr_value = self._calculate_atr()
            if atr_value:
                new_sl = current_price - (atr_value * self.trailing_multiplier)
                # Ensure SL doesn't move backward (widening loss)
                new_sl = max(new_sl, position.sl) if position.sl > 0 else new_sl
            else:
                # Fallback: Use fixed trailing if ATR fails
                profit = current_price - position.price_open
                new_sl = position.price_open + (profit * 0.5)  # Trail 50% of profit
            
            # Add spread buffer for break-even
            symbol_info = mt5.symbol_info(self.target_symbol)
            if symbol_info:
                spread_points = symbol_info.spread * symbol_info.point
                new_sl = max(new_sl, position.price_open + spread_points + self.spread_buffer)
            
        else:  # SELL positions
            atr_value = self._calculate_atr()
            if atr_value:
                new_sl = current_price + (atr_value * self.trailing_multiplier)
                new_sl = min(new_sl, position.sl) if position.sl > 0 else new_sl
            else:
                profit = position.price_open - current_price
                new_sl = position.price_open - (profit * 0.5)
            
            symbol_info = mt5.symbol_info(self.target_symbol)
            if symbol_info:
                spread_points = symbol_info.spread * symbol_info.point
                new_sl = min(new_sl, position.price_open - spread_points - self.spread_buffer)
        
        return round(new_sl, 2)
    
    def _modify_position_sl(self, position, new_sl: float) -> bool:
        """
        Safely modify position stop loss with retry logic and error handling
        
        Args:
            position: MT5 position object to modify
            new_sl: New stop loss price
            
        Returns:
            True if modification successful, False otherwise
        """
        for attempt in range(self.max_retries):
            try:
                # Prepare modification request
                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": position.ticket,
                    "sl": new_sl,
                    "symbol": self.target_symbol,
                    "magic": position.magic,
                    "comment": f"TM_MOD_{datetime.now().strftime('%H%M%S')}"
                }
                
                # Send modification request
                result = mt5.order_send(request)
                
                if result.retcode == mt5.TRADE_RETCODE_DONE:
                    self.logger.info(
                        f"SL modified successfully: Ticket {position.ticket}, "
                        f"Old SL: {position.sl}, New SL: {new_sl}"
                    )
                    return True
                else:
                    self.logger.warning(
                        f"SL modification failed (attempt {attempt + 1}): "
                        f"Ticket {position.ticket}, Error: {result.retcode}, "
                        f"{mt5.last_error()}"
                    )
                    
                    # Handle specific error cases
                    if result.retcode in [mt5.TRADE_RETCODE_INVALID_STOPS, 
                                        mt5.TRADE_RETCODE_INVALID_PRICE]:
                        # Wait and retry with potentially updated prices
                        time.sleep(self.retry_delay)
                        continue
                    else:
                        # Unrecoverable error
                        break
                        
            except Exception as e:
                self.logger.error(f"SL modification exception: {e}")
                time.sleep(self.retry_delay)
                continue
        
        return False
    
    def manage_positions(self) -> Dict:
        """
        Main method to manage all open positions for target symbol
        
        Returns:
            Dictionary with management results and statistics
        """
        results = {
            "total_positions": 0,
            "managed_positions": 0,
            "breakeven_moves": 0,
            "trailing_moves": 0,
            "errors": 0,
            "actions_taken": []
        }
        
        try:
            # Get positions for target symbol only
            positions = self._get_target_positions()
            results["total_positions"] = len(positions)
            
            if not positions:
                self.logger.info("No positions found for management")
                return results
            
            self.logger.info(f"Managing {len(positions)} positions for {self.target_symbol}")
            
            for position in positions:
                try:
                    # Get current market price
                    tick = mt5.symbol_info_tick(self.target_symbol)
                    if not tick:
                        self.logger.error(f"Failed to get tick data for {self.target_symbol}")
                        continue
                    
                    current_price = tick.ask if position.type == mt5.ORDER_TYPE_BUY else tick.bid
                    
                    # Check break-even condition
                    if self._should_move_to_breakeven(position):
                        new_sl = self._calculate_new_sl_price(position, current_price)
                        if self._modify_position_sl(position, new_sl):
                            results["breakeven_moves"] += 1
                            results["actions_taken"].append({
                                "ticket": position.ticket,
                                "action": "breakeven",
                                "new_sl": new_sl
                            })
                    
                    # Check trailing stop condition (if SL already set)
                    elif position.sl > 0:
                        new_sl = self._calculate_new_sl_price(position, current_price)
                        
                        # Only modify if new SL provides better protection
                        if (position.type == mt5.ORDER_TYPE_BUY and new_sl > position.sl) or \
                           (position.type == mt5.ORDER_TYPE_SELL and new_sl < position.sl):
                            if self._modify_position_sl(position, new_sl):
                                results["trailing_moves"] += 1
                                results["actions_taken"].append({
                                    "ticket": position.ticket,
                                    "action": "trailing_stop",
                                    "new_sl": new_sl
                                })
                    
                    results["managed_positions"] += 1
                    
                except Exception as e:
                    self.logger.error(f"Error managing position {position.ticket}: {e}")
                    results["errors"] += 1
                    
        except Exception as e:
            self.logger.error(f"Fatal error in manage_positions: {e}")
            results["errors"] += 1
        
        return results


def create_trade_manager() -> TradeManager:
    """
    Factory function to create and configure TradeManager instance
    
    Returns:
        Configured TradeManager instance
    """
    return TradeManager(
        target_symbol="GOLD",
        breakeven_threshold_points=300.0,  # Move to BE at +300 points profit
        trailing_stop_atr_multiplier=1.5,   # 1.5 ATR trailing distance
        atr_period=14,
        atr_timeframe=mt5.TIMEFRAME_H1,
        spread_buffer_points=5.0,          # 5 points buffer above entry
        max_retry_attempts=3,
        retry_delay_seconds=1.0
    )


# Example usage in event loop
if __name__ == "__main__":
    # Initialize MT5 connection
    if not mt5.initialize():
        print("MT5 initialization failed")
        exit(1)
    
    # Create trade manager
    trade_manager = create_trade_manager()
    
    # Example event loop integration
    print("Starting Trade Manager event loop...")
    
    while True:
        try:
            # Manage positions every 30 seconds
            results = trade_manager.manage_positions()
            
            print(f"Managed {results['managed_positions']} positions | "
                  f"BE moves: {results['breakeven_moves']} | "
                  f"Trailing moves: {results['trailing_moves']}")
            
            # Sleep for 30 seconds
            time.sleep(30)
            
        except KeyboardInterrupt:
            print("\nShutting down Trade Manager...")
            break
        except Exception as e:
            print(f"Error in event loop: {e}")
            time.sleep(60)  # Wait longer on error
    
    mt5.shutdown()