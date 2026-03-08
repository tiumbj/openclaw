"""
Adaptive Volatility Manager for Dynamic Market Regime Detection and Execution

Features:
- ADX-Based Regime Detection: Ranging vs Trending market classification
- ATR-Based Dynamic SL/TP: Adaptive stops based on real-time volatility
- Continuous Re-Entry Support: Seamless trend following with adaptive parameters
- Enterprise-Grade Optimization: Vectorized calculations and zero silent failures
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from typing import Optional, Tuple, TypedDict
from enum import Enum
import logging
import time


class MarketRegime(Enum):
    """Market regime classification based on ADX"""
    RANGING = "ranging"      # ADX < 25 - Tight scalping mode
    TRENDING = "trending"    # ADX >= 25 - Wide momentum mode
    STRONG_TREND = "strong_trend"  # ADX >= 40 - Very strong trend


class AdaptiveSLTPResult(TypedDict):
    """Typed result for adaptive SL/TP calculation"""
    sl_price: float
    tp_price: float
    atr_value: float
    adx_value: float
    regime: MarketRegime
    regime_multiplier: float
    sl_distance_points: float
    tp_distance_points: float


class AdaptiveVolatilityManager:
    """
    Enterprise-grade adaptive volatility manager for dynamic execution
    
    Key Features:
    1. ADX-Based Regime Detection: Classifies market as ranging or trending
    2. ATR-Based Dynamic SL/TP: Adaptive stops based on real-time volatility
    3. Continuous Re-Entry Support: Seamless trend following capability
    4. Vectorized Calculations: Highly optimized pandas/numpy operations
    """
    
    def __init__(
        self,
        target_symbol: str = "GOLD",
        adx_period: int = 14,
        adx_timeframe: int = mt5.TIMEFRAME_H1,
        atr_period: int = 14,
        atr_timeframe: int = mt5.TIMEFRAME_H1,
        sl_multiplier: float = 1.5,
        tp_multiplier: float = 2.0,
        ranging_multiplier: float = 0.7,
        trending_multiplier: float = 1.2,
        strong_trend_multiplier: float = 1.5,
        max_retry_attempts: int = 3,
        retry_delay_seconds: float = 1.0
    ):
        """
        Initialize AdaptiveVolatilityManager with institutional configuration
        
        Args:
            target_symbol: Trading symbol (default: GOLD)
            adx_period: Period for ADX calculation
            adx_timeframe: Timeframe for ADX calculation
            atr_period: Period for ATR calculation
            atr_timeframe: Timeframe for ATR calculation
            sl_multiplier: Base multiplier for stop loss
            tp_multiplier: Base multiplier for take profit
            ranging_multiplier: Multiplier for ranging markets (ADX < 25)
            trending_multiplier: Multiplier for trending markets (ADX >= 25)
            strong_trend_multiplier: Multiplier for strong trends (ADX >= 40)
            max_retry_attempts: Maximum retry attempts for data fetching
            retry_delay_seconds: Delay between retry attempts
        """
        self.target_symbol = target_symbol
        self.adx_period = adx_period
        self.adx_timeframe = adx_timeframe
        self.atr_period = atr_period
        self.atr_timeframe = atr_timeframe
        self.sl_multiplier = sl_multiplier
        self.tp_multiplier = tp_multiplier
        self.ranging_multiplier = ranging_multiplier
        self.trending_multiplier = trending_multiplier
        self.strong_trend_multiplier = strong_trend_multiplier
        self.max_retries = max_retry_attempts
        self.retry_delay = retry_delay_seconds
        
        # ADX regime thresholds
        self.adx_thresholds = {
            MarketRegime.RANGING: 25.0,
            MarketRegime.TRENDING: 25.0,
            MarketRegime.STRONG_TREND: 40.0
        }
        
        # Setup enterprise logging
        self.logger = logging.getLogger("AdaptiveVolatilityManager")
        if not self.logger.handlers:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler("adaptive_volatility.log"),
                    logging.StreamHandler()
                ]
            )
        
        self.logger.info(
            f"AdaptiveVolatilityManager initialized for {target_symbol} | "
            f"ADX({adx_period}) | ATR({atr_period}) | SL Multiplier: {sl_multiplier}"
        )
    
    def _fetch_ohlc_data(self, timeframe: int, bars: int) -> Optional[pd.DataFrame]:
        """
        Fetch OHLC data with retry logic and robust error handling
        
        Args:
            timeframe: MT5 timeframe
            bars: Number of bars to fetch
            
        Returns:
            DataFrame with OHLC data or None if failed
        """
        for attempt in range(self.max_retries):
            try:
                rates = mt5.copy_rates_from_pos(
                    self.target_symbol, 
                    timeframe, 
                    0, 
                    bars
                )
                
                if rates is None or len(rates) == 0:
                    self.logger.warning(f"No data received (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(self.retry_delay)
                    continue
                
                # Convert to DataFrame with vectorized operations
                df = pd.DataFrame(rates)
                df['time'] = pd.to_datetime(df['time'], unit='s')
                df.set_index('time', inplace=True)
                
                return df
                
            except Exception as e:
                self.logger.error(f"Data fetch error (attempt {attempt + 1}): {e}")
                if attempt == self.max_retries - 1:
                    return None
                time.sleep(self.retry_delay)
        
        return None
    
    def _calculate_adx(self, bars: int = 100) -> Optional[float]:
        """
        Calculate ADX using vectorized pandas operations
        
        Args:
            bars: Number of bars for calculation
            
        Returns:
            Current ADX value or None if calculation fails
        """
        try:
            # Fetch OHLC data with buffer for indicator calculation
            df = self._fetch_ohlc_data(self.adx_timeframe, bars + self.adx_period * 2)
            if df is None or len(df) < self.adx_period + 1:
                self.logger.warning("Insufficient data for ADX calculation")
                return None
            
            # Vectorized True Range calculation
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift(1))
            low_close = np.abs(df['low'] - df['close'].shift(1))
            
            tr = np.maximum.reduce([high_low, high_close, low_close])
            
            # Vectorized Directional Movement
            up_move = df['high'] - df['high'].shift(1)
            down_move = df['low'].shift(1) - df['low']
            
            # Positive Directional Movement (+DM)
            pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
            
            # Negative Directional Movement (-DM)
            neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
            
            # Smooth TR, +DM, -DM using Wilder's smoothing
            tr_smooth = tr.rolling(window=self.adx_period).mean()
            pos_dm_smooth = pd.Series(pos_dm).rolling(window=self.adx_period).mean()
            neg_dm_smooth = pd.Series(neg_dm).rolling(window=self.adx_period).mean()
            
            # Calculate Directional Indicators
            pos_di = 100 * (pos_dm_smooth / tr_smooth)
            neg_di = 100 * (neg_dm_smooth / tr_smooth)
            
            # Calculate ADX
            dx = 100 * np.abs(pos_di - neg_di) / (pos_di + neg_di)
            adx = dx.rolling(window=self.adx_period).mean()
            
            current_adx = adx.iloc[-1]
            
            self.logger.debug(f"ADX calculated: {current_adx:.2f} for {self.target_symbol}")
            return current_adx
            
        except Exception as e:
            self.logger.error(f"ADX calculation error: {e}")
            return None
    
    def _calculate_atr(self, bars: int = 100) -> Optional[float]:
        """
        Calculate ATR using vectorized pandas operations
        
        Args:
            bars: Number of bars for calculation
            
        Returns:
            Current ATR value or None if calculation fails
        """
        try:
            df = self._fetch_ohlc_data(self.atr_timeframe, bars + self.atr_period)
            if df is None or len(df) < self.atr_period + 1:
                self.logger.warning("Insufficient data for ATR calculation")
                return None
            
            # Vectorized True Range calculation
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift(1))
            low_close = np.abs(df['low'] - df['close'].shift(1))
            
            tr = np.maximum.reduce([high_low, high_close, low_close])
            
            # Wilder's smoothing for ATR
            atr = tr.rolling(window=self.atr_period).mean()
            
            current_atr = atr.iloc[-1]
            
            self.logger.debug(f"ATR calculated: {current_atr:.4f} for {self.target_symbol}")
            return current_atr
            
        except Exception as e:
            self.logger.error(f"ATR calculation error: {e}")
            return None
    
    def _detect_market_regime(self, adx_value: float) -> Tuple[MarketRegime, float]:
        """
        Detect current market regime based on ADX value
        
        Args:
            adx_value: Current ADX value
            
        Returns:
            Tuple of (MarketRegime, regime_multiplier)
        """
        if adx_value >= self.adx_thresholds[MarketRegime.STRONG_TREND]:
            return MarketRegime.STRONG_TREND, self.strong_trend_multiplier
        elif adx_value >= self.adx_thresholds[MarketRegime.TRENDING]:
            return MarketRegime.TRENDING, self.trending_multiplier
        else:
            return MarketRegime.RANGING, self.ranging_multiplier
    
    def calculate_adaptive_sltp(
        self, 
        entry_price: float, 
        direction: int
    ) -> Optional[AdaptiveSLTPResult]:
        """
        Calculate adaptive SL/TP based on current market regime
        
        Args:
            entry_price: Entry price for the trade
            direction: Trade direction (mt5.ORDER_TYPE_BUY/SELL)
            
        Returns:
            AdaptiveSLTPResult with dynamic prices and regime info
        """
        try:
            # Calculate current ADX for regime detection
            adx_value = self._calculate_adx()
            if adx_value is None:
                self.logger.error("Failed to calculate ADX for regime detection")
                return None
            
            # Calculate current ATR for volatility measurement
            atr_value = self._calculate_atr()
            if atr_value is None:
                self.logger.error("Failed to calculate ATR for dynamic SL/TP")
                return None
            
            # Detect market regime and get multiplier
            regime, regime_multiplier = self._detect_market_regime(adx_value)
            
            # Calculate dynamic distances
            sl_distance = atr_value * self.sl_multiplier * regime_multiplier
            tp_distance = atr_value * self.tp_multiplier * regime_multiplier
            
            # Calculate SL/TP prices
            if direction == mt5.ORDER_TYPE_BUY:
                sl_price = entry_price - sl_distance
                tp_price = entry_price + tp_distance
            else:  # SELL position
                sl_price = entry_price + sl_distance
                tp_price = entry_price - tp_distance
            
            # Validate prices are within reasonable bounds
            symbol_info = mt5.symbol_info(self.target_symbol)
            if symbol_info:
                # Ensure SL/TP are not too close to current price
                min_distance = symbol_info.point * 10  # 10 points minimum
                if abs(entry_price - sl_price) < min_distance:
                    sl_price = entry_price - min_distance if direction == mt5.ORDER_TYPE_BUY else entry_price + min_distance
                
                if abs(tp_price - entry_price) < min_distance:
                    tp_price = entry_price + min_distance if direction == mt5.ORDER_TYPE_BUY else entry_price - min_distance
            
            result: AdaptiveSLTPResult = {
                "sl_price": round(sl_price, 2),
                "tp_price": round(tp_price, 2),
                "atr_value": atr_value,
                "adx_value": adx_value,
                "regime": regime,
                "regime_multiplier": regime_multiplier,
                "sl_distance_points": sl_distance / symbol_info.point if symbol_info else sl_distance,
                "tp_distance_points": tp_distance / symbol_info.point if symbol_info else tp_distance
            }
            
            self.logger.info(
                f"Adaptive SL/TP calculated | Regime: {regime.value} | "
                f"ADX: {adx_value:.1f} | ATR: {atr_value:.4f} | "
                f"Multiplier: {regime_multiplier}x | "
                f"Entry: {entry_price} | SL: {sl_price:.2f} | TP: {tp_price:.2f}"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Adaptive SL/TP calculation error: {e}")
            return None
    
    def should_allow_re_entry(
        self, 
        previous_direction: int, 
        current_direction: int,
        adx_value: Optional[float] = None
    ) -> bool:
        """
        Determine if continuous re-entry should be allowed based on trend strength
        
        Args:
            previous_direction: Direction of previous trade
            current_direction: Direction of potential new trade
            adx_value: Current ADX value (optional, will calculate if not provided)
            
        Returns:
            True if re-entry should be allowed, False otherwise
        """
        try:
            # Calculate ADX if not provided
            if adx_value is None:
                adx_value = self._calculate_adx()
                if adx_value is None:
                    return False
            
            # Only allow re-entry in trending markets
            if adx_value < self.adx_thresholds[MarketRegime.TRENDING]:
                self.logger.debug("Re-entry denied: Market is ranging (ADX < 25)")
                return False
            
            # Only allow re-entry in the same direction as previous trade
            if previous_direction != current_direction:
                self.logger.debug("Re-entry denied: Direction change detected")
                return False
            
            # Additional checks for strong trends
            if adx_value >= self.adx_thresholds[MarketRegime.STRONG_TREND]:
                self.logger.info("Re-entry allowed: Strong trend detected (ADX >= 40)")
                return True
            
            # For moderate trends, be more conservative
            self.logger.info("Re-entry allowed: Moderate trend continuation")
            return True
            
        except Exception as e:
            self.logger.error(f"Re-entry decision error: {e}")
            return False


def create_adaptive_volatility_manager() -> AdaptiveVolatilityManager:
    """
    Factory function to create configured AdaptiveVolatilityManager instance
    
    Returns:
        Configured AdaptiveVolatilityManager instance
    """
    return AdaptiveVolatilityManager(
        target_symbol="GOLD",
        adx_period=14,
        adx_timeframe=mt5.TIMEFRAME_H1,
        atr_period=14,
        atr_timeframe=mt5.TIMEFRAME_H1,
        sl_multiplier=1.5,           # 1.5 ATR for stop loss
        tp_multiplier=2.0,           # 2.0 ATR for take profit
        ranging_multiplier=0.7,      # 30% tighter in ranging markets
        trending_multiplier=1.2,     # 20% wider in trending markets
        strong_trend_multiplier=1.5, # 50% wider in strong trends
        max_retry_attempts=3,
        retry_delay_seconds=1.0
    )


# Example usage in trading system
if __name__ == "__main__":
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed")
        exit(1)
    
    # Create volatility manager
    volatility_manager = create_adaptive_volatility_manager()
    
    # Example: Calculate adaptive SL/TP for a trade
    entry_price = 2000.0
    direction = mt5.ORDER_TYPE_BUY
    
    sltp_result = volatility_manager.calculate_adaptive_sltp(entry_price, direction)
    if sltp_result:
        print(f"Market Regime: {sltp_result['regime'].value}")
        print(f"ADX: {sltp_result['adx_value']:.1f}")
        print(f"ATR: {sltp_result['atr_value']:.4f}")
        print(f"Regime Multiplier: {sltp_result['regime_multiplier']}x")
        print(f"Dynamic SL: {sltp_result['sl_price']}")
        print(f"Dynamic TP: {sltp_result['tp_price']}")
        print(f"SL Distance: {sltp_result['sl_distance_points']:.1f} points")
        print(f"TP Distance: {sltp_result['tp_distance_points']:.1f} points")
    
    # Example: Check re-entry permission
    re_entry_allowed = volatility_manager.should_allow_re_entry(
        mt5.ORDER_TYPE_BUY, 
        mt5.ORDER_TYPE_BUY,
        sltp_result['adx_value'] if sltp_result else None
    )
    print(f"Re-entry allowed: {re_entry_allowed}")
    
    mt5.shutdown()