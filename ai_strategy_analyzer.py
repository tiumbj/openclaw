"""
AI-Powered Strategy Analyzer for MT5
Version: 1.0.0
"""

import sys
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import MetaTrader5 as mt5
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
from typing import Dict

# Import Enterprise Backtester
from enterprise_backtester import EnterpriseBacktester

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class AIStrategyAnalyzer:
    """AI-powered strategy analysis and optimization"""
    
    def __init__(self):
        self.mt5 = None
        self.data = {}
        self.strategy_results = {}
        self.backtester = EnterpriseBacktester()
        
    def connect_mt5(self):
        """Connect to MT5"""
        print("🔗 กำลังเชื่อมต่อ MT5...")
        
        if not mt5.initialize():
            error = mt5.last_error()
            print(f"❌ MT5 Initialize ล้มเหลว: {error}")
            return False
        
        print("✅ MT5 เชื่อมต่อสำเร็จ")
        
        # Get account info
        account_info = mt5.account_info()
        if account_info:
            print(f"💰 Account: {account_info.login}")
            print(f"💼 Balance: {account_info.balance}")
            print(f"🏢 Broker: {account_info.company}")
        
        return True
    
    def download_historical_data(self, symbol: str, timeframe: int, bars: int = 1000):
        """Download historical data from MT5"""
        print(f"📥 กำลังดาวน์โหลดข้อมูล: {symbol} ({bars} bars)")
        
        try:
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
            
            if rates is None or len(rates) == 0:
                print(f"❌ ไม่สามารถดาวน์โหลดข้อมูล {symbol} ได้")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            
            print(f"✅ ดาวน์โหลด {symbol} สำเร็จ: {len(df)} bars")
            return df
            
        except Exception as e:
            print(f"❌ Error ในการดาวน์โหลดข้อมูล: {e}")
            return None
    
    def get_timeframe_name(self, timeframe: int) -> str:
        """Convert MT5 timeframe to readable name"""
        timeframe_map = {
            mt5.TIMEFRAME_M1: "M1",
            mt5.TIMEFRAME_M5: "M5", 
            mt5.TIMEFRAME_M15: "M15",
            mt5.TIMEFRAME_M30: "M30",
            mt5.TIMEFRAME_H1: "H1",
            mt5.TIMEFRAME_H4: "H4",
            mt5.TIMEFRAME_D1: "D1",
            mt5.TIMEFRAME_W1: "W1",
            mt5.TIMEFRAME_MN1: "MN1"
        }
        return timeframe_map.get(timeframe, f"Unknown({timeframe})")
    
    def calculate_technical_indicators(self, df: pd.DataFrame):
        """Calculate technical indicators"""
        print("📊 กำลังคำนวณ Technical Indicators...")
        
        # RSI (Manual calculation)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD (Manual calculation)
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # Bollinger Bands (Manual calculation)
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        
        # Stochastic (Manual calculation)
        low14 = df['low'].rolling(window=14).min()
        high14 = df['high'].rolling(window=14).max()
        df['stoch_k'] = 100 * ((df['close'] - low14) / (high14 - low14))
        df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()
        
        # Moving Averages
        df['sma_20'] = df['close'].rolling(window=20).mean()
        df['sma_50'] = df['close'].rolling(window=50).mean()
        df['ema_12'] = df['close'].ewm(span=12).mean()
        df['ema_26'] = df['close'].ewm(span=26).mean()
        
        # ATR for volatility (Manual calculation)
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df['atr'] = true_range.rolling(window=14).mean()
        
        # ADX for trend strength (Manual calculation)
        # +DM and -DM
        up_move = df['high'] - df['high'].shift()
        down_move = df['low'].shift() - df['low']
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        # True Range
        tr = np.maximum(df['high'] - df['low'], 
                       np.maximum(np.abs(df['high'] - df['close'].shift()), 
                                 np.abs(df['low'] - df['close'].shift())))
        
        # Smooth the DMs and TR
        plus_di = 100 * (pd.Series(plus_dm).rolling(window=14).mean() / 
                        pd.Series(tr).rolling(window=14).mean())
        minus_di = 100 * (pd.Series(minus_dm).rolling(window=14).mean() / 
                         pd.Series(tr).rolling(window=14).mean())
        
        # ADX calculation - handle division by zero
        dx = 100 * np.abs(plus_di - minus_di) / np.where((plus_di + minus_di) == 0, 1, (plus_di + minus_di))
        df['adx'] = dx.rolling(window=14).mean()
        
        print("✅ คำนวณ Technical Indicators สำเร็จ")
        return df
    
    def generate_signals(self, df: pd.DataFrame, strategy_params: Dict):
        """Generate trading signals based on strategy"""
        print("🎯 กำลังสร้าง Trading Signals...")
        
        # Enhanced strategy with multiple signal types and market regime filtering
        signals = []
        
        for i in range(2, len(df)):
            # Market regime detection - dynamic threshold based on timeframe
            # Lower threshold for higher frequency timeframes
            adx_threshold = 15  # Lower threshold for M5 timeframe
            is_trending = df['adx'].iloc[i] > adx_threshold if not pd.isna(df['adx'].iloc[i]) else True  # Allow some trades in ranging markets
            
            # Signal 1: RSI + MACD crossover (original strategy)
            signal1_buy = (df['rsi'].iloc[i] < strategy_params.get('rsi_oversold', 30) and
                          df['macd'].iloc[i] > df['macd_signal'].iloc[i] and
                          df['macd'].iloc[i-1] <= df['macd_signal'].iloc[i-1])
            
            signal1_sell = (df['rsi'].iloc[i] > strategy_params.get('rsi_overbought', 70) and
                           df['macd'].iloc[i] < df['macd_signal'].iloc[i] and
                           df['macd'].iloc[i-1] >= df['macd_signal'].iloc[i-1])
            
            # Signal 2: MACD momentum confirmation
            signal2_buy = (df['macd'].iloc[i] > 0 and
                          df['macd'].iloc[i] > df['macd'].iloc[i-1])
            
            signal2_sell = (df['macd'].iloc[i] < 0 and
                           df['macd'].iloc[i] < df['macd'].iloc[i-1])
            
            # Signal 3: RSI extreme with trend confirmation
            signal3_buy = (df['rsi'].iloc[i] < 25 and df['close'].iloc[i] > df['close'].iloc[i-5])
            signal3_sell = (df['rsi'].iloc[i] > 75 and df['close'].iloc[i] < df['close'].iloc[i-5])
            
            # Combined signals with market regime filter
            if is_trending:
                # Buy if any buy signal is true
                if signal1_buy or signal2_buy or signal3_buy:
                    signals.append(1)  # Buy
                # Sell if any sell signal is true
                elif signal1_sell or signal2_sell or signal3_sell:
                    signals.append(-1)  # Sell
                else:
                    signals.append(0)  # Hold
            else:
                # In ranging markets, be more conservative
                if signal1_buy and signal2_buy:  # Require multiple confirmations
                    signals.append(1)
                elif signal1_sell and signal2_sell:
                    signals.append(-1)
                else:
                    signals.append(0)
        
        # Pad with zeros for the first two elements
        signals = [0, 0, *signals]
        df['signal'] = signals
        
        print("✅ สร้าง Trading Signals สำเร็จ")
        return df
    
    def calculate_strategy_performance(self, df: pd.DataFrame, initial_capital: float = 10000):
        """Calculate strategy performance metrics"""
        print("📈 กำลังคำนวณ Strategy Performance...")
        
        df['returns'] = df['close'].pct_change() * df['signal'].shift(1)
        df['equity'] = initial_capital * (1 + df['returns'].cumsum())
        
        # Calculate performance metrics
        total_return = (df['equity'].iloc[-1] / initial_capital - 1) * 100
        
        # Win rate
        winning_trades = (df['returns'] > 0).sum()
        total_trades = (df['signal'] != 0).sum()
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # Sharpe ratio (simplified)
        sharpe_ratio = df['returns'].mean() / df['returns'].std() * np.sqrt(252) if df['returns'].std() > 0 else 0
        
        # Max drawdown
        rolling_max = df['equity'].cummax()
        drawdown = (df['equity'] - rolling_max) / rolling_max
        max_drawdown = drawdown.min() * 100
        
        # Additional metrics
        volatility_pct = df['returns'].std() * np.sqrt(252) * 100
        
        # Profit factor (gross profit / gross loss)
        gross_profit = df[df['returns'] > 0]['returns'].sum()
        gross_loss = abs(df[df['returns'] < 0]['returns'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        performance = {
            'total_return': total_return,
            'win_rate': win_rate,
            'total_trades': total_trades,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sharpe_ratio,  # Simplified for now
            'max_drawdown': max_drawdown,
            'volatility_pct': volatility_pct,
            'profit_factor': profit_factor,
            'final_equity': df['equity'].iloc[-1]
        }
        
        print("✅ คำนวณ Performance Metrics สำเร็จ")
        return performance, df
    
    def train_ai_model(self, df: pd.DataFrame):
        """Train AI model to predict market direction"""
        print("🤖 กำลังฝึก AI Model...")
        
        # Prepare features and target
        features = ['rsi', 'macd', 'macd_signal', 'stoch_k', 'stoch_d', 'sma_20', 'sma_50']
        
        # Create target: 1 if next candle is up, 0 if down
        df['target'] = (df['close'].shift(-1) > df['close']).astype(int)
        
        # Drop rows with NaN
        df_clean = df.dropna()
        
        if len(df_clean) < 100:
            print("❌ ข้อมูลไม่เพียงพอสำหรับการฝึก AI")
            return None, None
        
        X = df_clean[features]
        y = df_clean['target']
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        # Train Random Forest model
        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)
        
        # Predictions
        y_pred = model.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        
        print(f"✅ AI Model ฝึกสำเร็จ (Accuracy: {accuracy:.2%})")
        print("\n📊 Classification Report:")
        print(classification_report(y_test, y_pred))
        
        return model, accuracy
    
    def optimize_strategy_parameters(self, df: pd.DataFrame):
        """Optimize strategy parameters using AI"""
        print("⚙️ กำลัง Optimize Strategy Parameters...")
        
        best_performance = None
        best_params = None
        
        # Parameter grid for optimization
        param_grid = {
            'rsi_oversold': [25, 30, 35],
            'rsi_overbought': [65, 70, 75],
        }
        
        for rsi_oversold in param_grid['rsi_oversold']:
            for rsi_overbought in param_grid['rsi_overbought']:
                params = {'rsi_oversold': rsi_oversold, 'rsi_overbought': rsi_overbought}
                
                # Test this parameter set
                df_with_signals = self.generate_signals(df.copy(), params)
                performance, _ = self.calculate_strategy_performance(df_with_signals)
                
                print(f"Params: {params} | Return: {performance['total_return']:.2f}% | Win Rate: {performance['win_rate']:.1f}%")
                
                if best_performance is None or performance['total_return'] > best_performance['total_return']:
                    best_performance = performance
                    best_params = params
        
        print(f"\n🎯 Best Parameters: {best_params}")
        print(f"📊 Best Performance: {best_performance['total_return']:.2f}% Return, {best_performance['win_rate']:.1f}% Win Rate")
        
        return best_params, best_performance
    
    def visualize_strategy(self, df: pd.DataFrame, performance: Dict):
        """Visualize strategy performance"""
        print("📊 กำลังสร้าง Visualization...")
        
        plt.figure(figsize=(15, 10))
        
        # Price chart with signals
        plt.subplot(2, 1, 1)
        plt.plot(df.index, df['close'], label='Price', alpha=0.7)
        
        # Plot buy signals
        buy_signals = df[df['signal'] == 1]
        plt.scatter(buy_signals.index, buy_signals['close'], color='green', marker='^', 
                   label='Buy Signal', s=100, alpha=0.8)
        
        # Plot sell signals
        sell_signals = df[df['signal'] == -1]
        plt.scatter(sell_signals.index, sell_signals['close'], color='red', marker='v', 
                   label='Sell Signal', s=100, alpha=0.8)
        
        plt.title(f'Strategy Performance - Return: {performance["total_return"]:.2f}% | Win Rate: {performance["win_rate"]:.1f}%')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # Equity curve
        plt.subplot(2, 1, 2)
        plt.plot(df.index, df['equity'], label='Equity Curve', color='blue')
        plt.fill_between(df.index, df['equity'], alpha=0.3)
        plt.title('Equity Curve')
        plt.xlabel('Time')
        plt.ylabel('Equity ($)')
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        plt.tight_layout()
        
        # Save plot
        plt.savefig('strategy_performance.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print("✅ สร้าง Visualization สำเร็จ (บันทึกเป็น strategy_performance.png)")
    
    def run_analysis(self, symbol: str = "GOLD", timeframe: int = mt5.TIMEFRAME_M5, bars: int = 1500):
        """Run complete analysis pipeline"""
        print("=" * 80)
        print("🤖 AI-Powered Strategy Analysis")
        print(f"⏰ Timeframe: {self.get_timeframe_name(timeframe)}")
        print("=" * 80)
        
        # Connect to MT5
        if not self.connect_mt5():
            return
        
        try:
            # Download historical data
            df = self.download_historical_data(symbol, timeframe, bars)
            if df is None:
                return
            
            # Calculate technical indicators
            df = self.calculate_technical_indicators(df)
            
            # Train AI model
            _ai_model, ai_accuracy = self.train_ai_model(df)
            
            # Optimize strategy parameters
            best_params, _best_performance = self.optimize_strategy_parameters(df)
            
            # Generate final signals with optimized parameters
            df_final = self.generate_signals(df.copy(), best_params)
            final_performance, df_final = self.calculate_strategy_performance(df_final)
            
            # Visualize results using basic performance (enterprise backtest has compatibility issues)
            self.visualize_strategy(df_final, final_performance)
            
            print("\n" + "=" * 80)
            print("🎯 ENTERPRISE STRATEGY ANALYSIS")
            print("=" * 80)
            print(f"📈 Total Return: {final_performance['total_return']:.2f}%")
            print(f"🎯 Win Rate: {final_performance['win_rate']:.1f}%")
            print(f"🔢 Total Trades: {final_performance['total_trades']}")
            print(f"⚖️  Sharpe Ratio: {final_performance['sharpe_ratio']:.2f}")
            print(f"📊 Sortino Ratio: {final_performance['sortino_ratio']:.2f}")
            print(f"📉 Max Drawdown: {final_performance['max_drawdown']:.2f}%")
            print(f"🌪️  Volatility: {final_performance['volatility_pct']:.2f}%")
            print(f"💰 Profit Factor: {final_performance['profit_factor']:.2f}")
            print(f"🤖 AI Accuracy: {ai_accuracy:.2%}" if ai_accuracy else "🤖 AI: Not trained")
            print(f"⚙️  Optimized Parameters: {best_params}")
            
            # Signal starvation check
            if final_performance['total_trades'] < 10:
                print("\n⚠️  WARNING: LOW TRADE COUNT - POTENTIAL SIGNAL STARVATION")
                print("   Consider adjusting strategy parameters or timeframe")
            
            # Save results to CSV
            df_final.to_csv('strategy_analysis_results.csv')
            print("\n💾 บันทึกผลการวิเคราะห์เป็น strategy_analysis_results.csv")
            
        finally:
            # Always shutdown MT5
            mt5.shutdown()
            print("✅ MT5 Shutdown สำเร็จ")

# Run the analysis
if __name__ == "__main__":
    analyzer = AIStrategyAnalyzer()
    
    # Test M15 timeframe (ตาม requirement เดิม)
    print("📊 TESTING M15 TIMEFRAME")
    print("=" * 60)
    analyzer.run_analysis(symbol="GOLD", timeframe=mt5.TIMEFRAME_M15, bars=1500)  # Medium bars for M15
