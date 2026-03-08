"""
Multi-Timeframe Analyzer for OracleBot-Pro
Analyzes market confluence across multiple timeframes
"""

import MetaTrader5 as mt5
import pandas as pd
from typing import Dict
from dataclasses import dataclass

@dataclass
class MTFSignal:
    """Multi-timeframe signal container"""
    timeframe: str
    trend_direction: str  # 'bullish', 'bearish', 'neutral'
    trend_strength: float  # 0-100
    signal_strength: float  # 0-100
    indicators: Dict
    
class MultiTimeframeAnalyzer:
    def __init__(self):
        self.timeframes = {
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15, 
            'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1
        }
        
        # Weighting for different timeframes
        self.timeframe_weights = {
            'M5': 0.1,   # 10%
            'M15': 0.15, # 15% 
            'H1': 0.2,   # 20%
            'H4': 0.3,   # 30%
            'D1': 0.25   # 25%
        }
    
    def download_mtf_data(self, symbol: str, bars_per_tf: int = 100) -> Dict[str, pd.DataFrame]:
        """Download data for all timeframes"""
        mtf_data = {}
        
        for tf_name, tf_value in self.timeframes.items():
            print(f"📥 Downloading {symbol} {tf_name} data...")
            
            rates = mt5.copy_rates_from_pos(symbol, tf_value, 0, bars_per_tf)
            if rates is not None and len(rates) > 0:
                df = pd.DataFrame(rates)
                df['time'] = pd.to_datetime(df['time'], unit='s')
                df.set_index('time', inplace=True)
                mtf_data[tf_name] = df
                print(f"✅ {tf_name}: {len(df)} bars")
            else:
                print(f"❌ Failed to download {tf_name} data")
        
        return mtf_data
    
    def calculate_tf_indicators(self, df: pd.DataFrame) -> Dict:
        """Calculate indicators for a single timeframe"""
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        # MACD
        exp12 = df['close'].ewm(span=12).mean()
        exp26 = df['close'].ewm(span=26).mean()
        macd = exp12 - exp26
        macd_signal = macd.ewm(span=9).mean()
        
        # Simple trend detection
        sma20 = df['close'].rolling(window=20).mean()
        sma50 = df['close'].rolling(window=50).mean()
        
        # Trend strength (absolute price change over 20 periods)
        trend_strength = abs((df['close'].iloc[-1] / df['close'].iloc[-20] - 1) * 100) if len(df) >= 20 else 0
        
        return {
            'rsi': rsi.iloc[-1] if not rsi.empty else 50,
            'macd': macd.iloc[-1] if not macd.empty else 0,
            'macd_signal': macd_signal.iloc[-1] if not macd_signal.empty else 0,
            'sma20': sma20.iloc[-1] if not sma20.empty else df['close'].iloc[-1],
            'sma50': sma50.iloc[-1] if not sma50.empty else df['close'].iloc[-1],
            'trend_strength': trend_strength,
            'price': df['close'].iloc[-1]
        }
    
    def analyze_timeframe(self, df: pd.DataFrame, timeframe: str) -> MTFSignal:
        """Analyze a single timeframe"""
        indicators = self.calculate_tf_indicators(df)
        
        # Determine trend direction
        price = indicators['price']
        sma20 = indicators['sma20']
        sma50 = indicators['sma50']
        
        if price > sma20 > sma50:
            trend_direction = 'bullish'
        elif price < sma20 < sma50:
            trend_direction = 'bearish'
        else:
            trend_direction = 'neutral'
        
        # Calculate signal strength
        rsi = indicators['rsi']
        macd_diff = indicators['macd'] - indicators['macd_signal']
        
        # Bullish signal strength
        if trend_direction == 'bullish':
            signal_strength = 0
            if rsi < 40:
                signal_strength += 30
            if macd_diff > 0:
                signal_strength += 40
            if indicators['trend_strength'] > 2:
                signal_strength += 30
            
        # Bearish signal strength  
        elif trend_direction == 'bearish':
            signal_strength = 0
            if rsi > 60:
                signal_strength += 30
            if macd_diff < 0:
                signal_strength += 40
            if indicators['trend_strength'] > 2:
                signal_strength += 30
            
        else:
            signal_strength = 0
        
        signal_strength = min(signal_strength, 100)
        
        return MTFSignal(
            timeframe=timeframe,
            trend_direction=trend_direction,
            trend_strength=indicators['trend_strength'],
            signal_strength=signal_strength,
            indicators=indicators
        )
    
    def get_mtf_confluence(self, symbol: str) -> Dict:
        """Get multi-timeframe confluence analysis"""
        print(f"\n🎯 Analyzing Multi-Timeframe Confluence for {symbol}")
        print("=" * 60)
        
        # Download data for all timeframes
        mtf_data = self.download_mtf_data(symbol)
        
        if not mtf_data:
            print("❌ No data available for analysis")
            return {}
        
        # Analyze each timeframe
        signals = {}
        for tf_name, df in mtf_data.items():
            signal = self.analyze_timeframe(df, tf_name)
            signals[tf_name] = signal
            
            print(f"\n{tf_name}:")
            print(f"  Trend: {signal.trend_direction.upper()} (Strength: {signal.trend_strength:.1f}%)")
            print(f"  Signal: {signal.signal_strength:.1f}/100")
            print(f"  RSI: {signal.indicators['rsi']:.1f}, MACD: {signal.indicators['macd']:.3f}")
            print(f"  Price: {signal.indicators['price']:.2f}, SMA20: {signal.indicators['sma20']:.2f}")
        
        # Calculate overall confluence
        overall_score = 0
        bullish_weight = 0
        bearish_weight = 0
        
        for tf_name, signal in signals.items():
            weight = self.timeframe_weights.get(tf_name, 0.1)
            
            if signal.trend_direction == 'bullish':
                bullish_weight += weight * signal.signal_strength / 100
            elif signal.trend_direction == 'bearish':
                bearish_weight += weight * signal.signal_strength / 100
        
        overall_direction = 'BULLISH' if bullish_weight > bearish_weight else 'BEARISH'
        overall_score = max(bullish_weight, bearish_weight) * 100
        
        confluence = {
            'overall_direction': overall_direction,
            'overall_score': overall_score,
            'bullish_weight': bullish_weight * 100,
            'bearish_weight': bearish_weight * 100,
            'signals': signals,
            'recommendation': self.generate_recommendation(overall_direction, overall_score)
        }
        
        print(f"\n🎯 OVERALL CONFLUENCE: {overall_direction} ({overall_score:.1f}/100)")
        print(f"📊 Bullish: {bullish_weight * 100:.1f}%, Bearish: {bearish_weight * 100:.1f}%")
        print(f"💡 Recommendation: {confluence['recommendation']}")
        
        return confluence
    
    def generate_recommendation(self, direction: str, score: float) -> str:
        """Generate trading recommendation"""
        if score >= 70:
            strength = "STRONG"
        elif score >= 50:
            strength = "MODERATE" 
        elif score >= 30:
            strength = "WEAK"
        else:
            return "NO CLEAR DIRECTION - WAIT"
        
        if direction == 'BULLISH':
            return f"{strength} BUY SIGNAL"
        else:
            return f"{strength} SELL SIGNAL"

# Example usage
if __name__ == "__main__":
    # Initialize MT5
    if not mt5.initialize():
        print("❌ MT5 Initialize failed")
    else:
        # Create analyzer
        analyzer = MultiTimeframeAnalyzer()
        
        # Get confluence analysis
        confluence = analyzer.get_mtf_confluence("GOLD")
        
        mt5.shutdown()
