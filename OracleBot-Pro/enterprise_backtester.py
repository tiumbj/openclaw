"""
Enterprise Backtesting Framework for Trading Strategy Analysis
- Vectorized backtesting for speed and accuracy
- Comprehensive performance metrics
- Risk management integration
- Market regime detection
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict
import warnings
warnings.filterwarnings('ignore')

class EnterpriseBacktester:
    """Enterprise-grade backtesting framework with institutional standards"""
    
    def __init__(self, initial_capital: float = 10000):
        self.initial_capital = initial_capital
        self.results = {}
        
    def vectorized_backtest(self, df: pd.DataFrame, strategy_params: Dict) -> Dict:
        """Vectorized backtesting for maximum performance"""
        
        # Create signals using vectorized operations
        df = df.copy()
        
        # Market regime filter - only trade in trending markets (ADX > 15)
        trending_market = df['adx'] > 15
        
        # Buy signals: RSI oversold + MACD bullish crossover + trending market
        buy_condition = (
            (df['rsi'] < strategy_params.get('rsi_oversold', 30)) &
            (df['macd'] > df['macd_signal']) &
            (df['macd'].shift(1) <= df['macd_signal'].shift(1)) &
            trending_market
        )
        
        # Sell signals: RSI overbought + MACD bearish crossover + trending market
        sell_condition = (
            (df['rsi'] > strategy_params.get('rsi_overbought', 70)) &
            (df['macd'] < df['macd_signal']) &
            (df['macd'].shift(1) >= df['macd_signal'].shift(1)) &
            trending_market
        )
        
        # Generate signals (1 = Buy, -1 = Sell, 0 = Hold)
        df['signal'] = 0
        df.loc[buy_condition, 'signal'] = 1
        df.loc[sell_condition, 'signal'] = -1
        
        # Calculate returns
        df['strategy_returns'] = df['close'].pct_change() * df['signal'].shift(1)
        df['cumulative_returns'] = (1 + df['strategy_returns']).cumprod()
        df['equity_curve'] = self.initial_capital * df['cumulative_returns']
        
        # Calculate performance metrics
        performance = self.calculate_performance_metrics(df, strategy_params)
        
        return performance, df
    
    def calculate_performance_metrics(self, df: pd.DataFrame, strategy_params: Dict) -> Dict:
        """Calculate comprehensive performance metrics"""
        
        # Basic metrics
        total_return = (df['equity_curve'].iloc[-1] / self.initial_capital - 1) * 100
        
        # Trade analysis
        trades = self.analyze_trades(df)
        
        # Risk metrics
        sharpe_ratio = self.calculate_sharpe_ratio(df['strategy_returns'])
        sortino_ratio = self.calculate_sortino_ratio(df['strategy_returns'])
        max_drawdown = self.calculate_max_drawdown(df['equity_curve'])
        
        # Volatility metrics
        volatility = df['strategy_returns'].std() * np.sqrt(252) * 100
        
        # Win rate and profit factor
        win_rate = trades['win_rate'] if trades['total_trades'] > 0 else 0
        profit_factor = trades['profit_factor'] if trades['total_trades'] > 0 else 0
        
        performance = {
            'total_return_pct': total_return,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'max_drawdown_pct': max_drawdown,
            'volatility_pct': volatility,
            'win_rate_pct': win_rate,
            'profit_factor': profit_factor,
            'total_trades': trades['total_trades'],
            'winning_trades': trades['winning_trades'],
            'losing_trades': trades['losing_trades'],
            'avg_profit_per_trade': trades['avg_profit'],
            'avg_loss_per_trade': trades['avg_loss'],
            'largest_win': trades['largest_win'],
            'largest_loss': trades['largest_loss'],
            'strategy_params': strategy_params
        }
        
        return performance
    
    def analyze_trades(self, df: pd.DataFrame) -> Dict:
        """Analyze individual trades for detailed statistics"""
        
        # Identify trade entries and exits
        in_trade = False
        entry_price = 0
        trades = []
        
        for i, row in df.iterrows():
            if not in_trade and row['signal'] == 1:
                # Enter long trade
                in_trade = True
                entry_price = row['close']
            elif in_trade and (row['signal'] == -1 or i == len(df) - 1):
                # Exit trade
                exit_price = row['close']
                profit_pct = (exit_price / entry_price - 1) * 100
                trades.append(profit_pct)
                in_trade = False
        
        # Calculate trade statistics
        if trades:
            trades_array = np.array(trades)
            winning_trades = trades_array[trades_array > 0]
            losing_trades = trades_array[trades_array <= 0]
            
            stats = {
                'total_trades': len(trades),
                'winning_trades': len(winning_trades),
                'losing_trades': len(losing_trades),
                'win_rate': len(winning_trades) / len(trades) * 100,
                'profit_factor': abs(winning_trades.sum() / losing_trades.sum()) if losing_trades.any() else float('inf'),
                'avg_profit': winning_trades.mean() if len(winning_trades) > 0 else 0,
                'avg_loss': losing_trades.mean() if len(losing_trades) > 0 else 0,
                'largest_win': winning_trades.max() if len(winning_trades) > 0 else 0,
                'largest_loss': losing_trades.min() if len(losing_trades) > 0 else 0
            }
        else:
            stats = {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'profit_factor': 0,
                'avg_profit': 0,
                'avg_loss': 0,
                'largest_win': 0,
                'largest_loss': 0
            }
        
        return stats
    
    def calculate_sharpe_ratio(self, returns: pd.Series, risk_free_rate: float = 0.02) -> float:
        """Calculate annualized Sharpe ratio"""
        excess_returns = returns - risk_free_rate / 252
        sharpe = excess_returns.mean() / excess_returns.std() * np.sqrt(252)
        return sharpe if not np.isnan(sharpe) else 0
    
    def calculate_sortino_ratio(self, returns: pd.Series, risk_free_rate: float = 0.02) -> float:
        """Calculate annualized Sortino ratio"""
        excess_returns = returns - risk_free_rate / 252
        downside_returns = excess_returns[excess_returns < 0]
        
        if len(downside_returns) == 0 or downside_returns.std() == 0:
            return 0
        
        sortino = excess_returns.mean() / downside_returns.std() * np.sqrt(252)
        return sortino if not np.isnan(sortino) else 0
    
    def calculate_max_drawdown(self, equity_curve: pd.Series) -> float:
        """Calculate maximum drawdown"""
        rolling_max = equity_curve.cummax()
        drawdown = (equity_curve - rolling_max) / rolling_max
        return drawdown.min() * 100
    
    def generate_report(self, performance: Dict, df: pd.DataFrame):
        """Generate comprehensive performance report"""
        
        print("=" * 80)
        print("📊 ENTERPRISE BACKTESTING REPORT")
        print("=" * 80)
        
        # Strategy parameters
        print("\n🎯 STRATEGY PARAMETERS:")
        for key, value in performance['strategy_params'].items():
            print(f"   {key}: {value}")
        
        # Performance summary
        print("\n📈 PERFORMANCE SUMMARY:")
        print(f"   Total Return: {performance['total_return_pct']:.2f}%")
        print(f"   Sharpe Ratio: {performance['sharpe_ratio']:.2f}")
        print(f"   Sortino Ratio: {performance['sortino_ratio']:.2f}")
        print(f"   Max Drawdown: {performance['max_drawdown_pct']:.2f}%")
        print(f"   Volatility: {performance['volatility_pct']:.2f}%")
        
        # Trade statistics
        print("\n🎯 TRADE STATISTICS:")
        print(f"   Total Trades: {performance['total_trades']}")
        print(f"   Win Rate: {performance['win_rate_pct']:.1f}%")
        print(f"   Profit Factor: {performance['profit_factor']:.2f}")
        print(f"   Avg Profit/Trade: {performance['avg_profit_per_trade']:.2f}%")
        print(f"   Avg Loss/Trade: {performance['avg_loss_per_trade']:.2f}%")
        print(f"   Largest Win: {performance['largest_win']:.2f}%")
        print(f"   Largest Loss: {performance['largest_loss']:.2f}%")
        
        # Signal frequency analysis
        signals_count = len(df[df['signal'] != 0])
        total_bars = len(df)
        signal_frequency = (signals_count / total_bars) * 100
        
        print("\n📶 SIGNAL ANALYSIS:")
        print(f"   Total Signals: {signals_count}")
        print(f"   Signal Frequency: {signal_frequency:.2f}%")
        print(f"   Bars Between Signals: {total_bars / signals_count:.1f}" if signals_count > 0 else "   No signals generated")
        
        # Check for signal starvation
        if signals_count == 0:
            print("\n⚠️  WARNING: SIGNAL STARVATION DETECTED!")
            print("   No trading signals were generated during the test period.")
            print("   Consider adjusting strategy parameters or timeframes.")
        elif signals_count < 10:
            print(f"\n⚠️  WARNING: LOW SIGNAL COUNT ({signals_count})")
            print("   Strategy may suffer from signal starvation in live trading.")
        
        print("=" * 80)
        
        return performance
    
    def plot_performance(self, df: pd.DataFrame, performance: Dict):
        """Plot performance charts"""
        
        _fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
        
        # Equity curve
        ax1.plot(df.index, df['equity_curve'], label='Strategy', linewidth=2)
        ax1.plot(df.index, [self.initial_capital] * len(df), 'r--', label='Initial Capital', alpha=0.7)
        ax1.set_title('Equity Curve')
        ax1.set_ylabel('Equity ($)')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Drawdown
        rolling_max = df['equity_curve'].cummax()
        drawdown = (df['equity_curve'] - rolling_max) / rolling_max * 100
        ax2.fill_between(df.index, drawdown, 0, alpha=0.3, color='red')
        ax2.plot(df.index, drawdown, color='red', linewidth=1)
        ax2.set_title('Drawdown')
        ax2.set_ylabel('Drawdown (%)')
        ax2.grid(True, alpha=0.3)
        
        # Daily returns distribution
        ax3.hist(df['strategy_returns'].dropna() * 100, bins=50, alpha=0.7, edgecolor='black')
        ax3.set_title('Daily Returns Distribution')
        ax3.set_xlabel('Daily Return (%)')
        ax3.set_ylabel('Frequency')
        ax3.grid(True, alpha=0.3)
        
        # Signal frequency
        signals = df['signal'].value_counts()
        ax4.bar(['Sell', 'Hold', 'Buy'], [signals.get(-1, 0), signals.get(0, 0), signals.get(1, 0)], 
                color=['red', 'gray', 'green'], alpha=0.7)
        ax4.set_title('Signal Distribution')
        ax4.set_ylabel('Count')
        
        plt.tight_layout()
        plt.savefig('backtest_performance.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print("✅ Saved performance charts to 'backtest_performance.png'")

# Example usage
if __name__ == "__main__":
    # Create sample data for testing
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', '2024-01-01', freq='D')
    data = {
        'close': 100 + np.cumsum(np.random.randn(len(dates)) * 0.5),
        'rsi': np.random.uniform(20, 80, len(dates)),
        'macd': np.random.randn(len(dates)) * 0.1,
        'macd_signal': np.random.randn(len(dates)) * 0.08
    }
    df = pd.DataFrame(data, index=dates)
    
    # Initialize backtester
    backtester = EnterpriseBacktester(initial_capital=10000)
    
    # Test strategy
    strategy_params = {
        'rsi_oversold': 30,
        'rsi_overbought': 70
    }
    
    performance, result_df = backtester.vectorized_backtest(df, strategy_params)
    backtester.generate_report(performance, result_df)
    backtester.plot_performance(result_df, performance)
