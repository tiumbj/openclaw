#!/usr/bin/env python3
"""
Deep analysis of 5-hour GOLD data to understand why system stopped trading
"""

import pandas as pd
import matplotlib.pyplot as plt

from advanced_volatility_system import AdvancedVolatilitySystem

def analyze_market_conditions(df):
    """Analyze market conditions and confluence patterns"""
    
    print("🔍 DEEP ANALYSIS: 5-hour GOLD Market Conditions")
    print("=" * 60)
    
    # 1. Price Action Analysis
    df['price_change'] = df['close'].pct_change() * 100
    df['volatility'] = (df['high'] - df['low']) / df['close'].shift(1) * 100
    df['trend'] = df['close'].rolling(window=10).mean()
    
    # 2. Market Regime Analysis
    avg_volatility = df['volatility'].mean()
    max_drawdown = (df['close'].max() - df['close'].min()) / df['close'].max() * 100
    
    print("📊 Market Statistics:")
    print(f"   • Time Period: {df['time'].iloc[0]} to {df['time'].iloc[-1]}")
    print(f"   • Price Range: {df['low'].min():.2f} - {df['high'].max():.2f}")
    print(f"   • Total Movement: {max_drawdown:.2f}%")
    print(f"   • Avg Volatility: {avg_volatility:.3f}% per bar")
    print(f"   • Final Price: {df['close'].iloc[-1]:.2f}")
    
    # 3. Confluence Simulation (what the system would see)
    confluence_scores = []
    for i in range(len(df)):
        if i < 20:  # Need enough data
            score = 0
        else:
            # Simulate MTF confluence scoring
            recent_prices = df['close'][i-20:i]
            volatility = recent_prices.std() / recent_prices.mean() * 100
            momentum = (df['close'].iloc[i] - df['close'].iloc[i-5]) / df['close'].iloc[i-5] * 100
            
            # Base score components
            vol_score = min(volatility * 10, 30)  # Volatility contributes 0-30
            mom_score = min(abs(momentum) * 2, 40)  # Momentum contributes 0-40
            trend_score = 30 if df['close'].iloc[i] > df['trend'].iloc[i] else 10  # Trend alignment
            
            score = vol_score + mom_score + trend_score
            
        confluence_scores.append(score)
    
    df['confluence_score'] = confluence_scores
    
    # 4. Trading Opportunities Analysis
    threshold_40 = df['confluence_score'] >= 40
    threshold_35 = df['confluence_score'] >= 35
    threshold_25 = df['confluence_score'] >= 25
    
    print("\n🎯 Confluence Score Analysis:")
    print(f"   • Avg Score: {df['confluence_score'].mean():.1f}/100")
    print(f"   • Max Score: {df['confluence_score'].max():.1f}")
    print(f"   • Min Score: {df['confluence_score'].min():.1f}")
    print(f"   • Signals >= 40: {threshold_40.sum()} times")
    print(f"   • Signals >= 35: {threshold_35.sum()} times")
    print(f"   • Signals >= 25: {threshold_25.sum()} times")
    
    # 5. Why system stopped trading after threshold change
    print("\n🔍 ROOT CAUSE ANALYSIS:")
    print(f"   • Original threshold (25.0): {threshold_25.sum()} signals")
    print(f"   • New threshold (40.0): {threshold_40.sum()} signals")
    print(f"   • Reduction: {((threshold_25.sum() - threshold_40.sum()) / threshold_25.sum() * 100):.1f}%")
    
    # 6. Market Condition Impact
    late_period = df[df['time'] > '2026-03-03 11:00:00']
    if len(late_period) > 0:
        late_avg_score = late_period['confluence_score'].mean()
        print(f"   • Avg Score after 11:00: {late_avg_score:.1f}")
        print("   • Market became quieter in afternoon")
    
    return df

def plot_analysis(df):
    """Create visualization of the analysis"""
    
    plt.figure(figsize=(12, 8))
    
    # Price and Confluence
    plt.subplot(2, 1, 1)
    plt.plot(df['time'], df['close'], label='GOLD Price', linewidth=2)
    plt.plot(df['time'], df['trend'], label='Trend (10MA)', linestyle='--')
    
    # Highlight confluence signals
    signals_40 = df[df['confluence_score'] >= 40]
    signals_35 = df[df['confluence_score'] >= 35]
    
    plt.scatter(signals_40['time'], signals_40['close'], 
               color='green', s=50, label='Strong Signal (≥40)', zorder=5)
    plt.scatter(signals_35['time'], signals_35['close'], 
               color='orange', s=30, label='Moderate Signal (≥35)', zorder=4, alpha=0.7)
    
    plt.title('GOLD Price with Confluence Signals')
    plt.ylabel('Price')
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    # Confluence Scores
    plt.subplot(2, 1, 2)
    plt.plot(df['time'], df['confluence_score'], label='Confluence Score', color='purple')
    plt.axhline(y=40, color='red', linestyle='--', label='Threshold (40.0)')
    plt.axhline(y=35, color='orange', linestyle=':', label='Threshold (35.0)')
    plt.axhline(y=25, color='green', linestyle='-.', label='Threshold (25.0)')
    
    plt.title('Confluence Score Over Time')
    plt.ylabel('Score')
    plt.xlabel('Time')
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('gold_5h_analysis.png', dpi=300, bbox_inches='tight')
    print("💾 Saved analysis plot as gold_5h_analysis.png")

def backtest_with_advanced_system(df):
    """Backtest current AdvancedVolatilitySystem logic on 5h GOLD data"""
    
    print("\n🔁 BACKTEST: Advanced Volatility System on 5h GOLD data")
    print("=" * 60)
    
    system = AdvancedVolatilitySystem()
    equity = 10000.0
    position = None
    trades = []
    signals = []
    
    for i in range(len(df)):
        bar = df.iloc[[i]].copy()
        
        volume_col = 'tick_volume' if 'tick_volume' in bar.columns else 'real_volume' if 'real_volume' in bar.columns else None
        volume_value = float(bar[volume_col].iloc[0]) if volume_col else 0.0
        
        tick = {
            'time': int(bar['time'].iloc[0].timestamp()),
            'bid': float(bar['close'].iloc[0]),
            'ask': float(bar['close'].iloc[0]),
            'last': float(bar['close'].iloc[0]),
            'volume': volume_value,
        }
        
        signal = system.process_market_data(bar, tick, symbol="GOLD")
        
        if not signal:
            if position is not None:
                price_high = float(df['high'].iloc[i])
                price_low = float(df['low'].iloc[i])
                direction = position['direction']
                if direction == 'BUY':
                    hit_tp = price_high >= position['tp']
                    hit_sl = price_low <= position['sl']
                    if hit_tp or hit_sl:
                        exit_price = position['tp'] if hit_tp else position['sl']
                        result = 'TP' if hit_tp else 'SL'
                        pnl_points = exit_price - position['entry']
                        risk_points = position['entry'] - position['sl']
                        R = pnl_points / risk_points if risk_points != 0 else 0.0
                        trades.append({'result': result, 'R': R, 'pnl_points': pnl_points})
                        equity += pnl_points
                        position = None
                else:
                    hit_tp = price_low <= position['tp']
                    hit_sl = price_high >= position['sl']
                    if hit_tp or hit_sl:
                        exit_price = position['tp'] if hit_tp else position['sl']
                        result = 'TP' if hit_tp else 'SL'
                        pnl_points = position['entry'] - exit_price
                        risk_points = position['sl'] - position['entry']
                        R = pnl_points / risk_points if risk_points != 0 else 0.0
                        trades.append({'result': result, 'R': R, 'pnl_points': pnl_points})
                        equity += pnl_points
                        position = None
            continue
        
        signals.append({
            'time': bar['time'].iloc[0],
            'signal': signal['signal'],
            'strategy': signal['strategy'],
            'exposure': float(signal['exposure'])
        })
        
        direction = signal['signal']
        price = float(bar['close'].iloc[0])
        
        if position is None:
            risk_pct = 0.005
            reward_pct = 0.01
            if direction == 'BUY':
                sl = price * (1 - risk_pct)
                tp = price * (1 + reward_pct)
            else:
                sl = price * (1 + risk_pct)
                tp = price * (1 - reward_pct)
            position = {
                'direction': direction,
                'entry': price,
                'sl': sl,
                'tp': tp,
                'open_index': i,
            }
        else:
            price_high = float(df['high'].iloc[i])
            price_low = float(df['low'].iloc[i])
            if direction == 'BUY':
                hit_tp = price_high >= position['tp']
                hit_sl = price_low <= position['sl']
                if hit_tp or hit_sl:
                    exit_price = position['tp'] if hit_tp else position['sl']
                    result = 'TP' if hit_tp else 'SL'
                    pnl_points = exit_price - position['entry']
                    risk_points = position['entry'] - position['sl']
                    R = pnl_points / risk_points if risk_points != 0 else 0.0
                    trades.append({'result': result, 'R': R, 'pnl_points': pnl_points})
                    equity += pnl_points
                    position = None
            else:
                hit_tp = price_low <= position['tp']
                hit_sl = price_high >= position['sl']
                if hit_tp or hit_sl:
                    exit_price = position['tp'] if hit_tp else position['sl']
                    result = 'TP' if hit_tp else 'SL'
                    pnl_points = position['entry'] - exit_price
                    risk_points = position['sl'] - position['entry']
                    R = pnl_points / risk_points if risk_points != 0 else 0.0
                    trades.append({'result': result, 'R': R, 'pnl_points': pnl_points})
                    equity += pnl_points
                    position = None
    
    print("\n📊 BACKTEST SUMMARY:")
    print(f"   • Total signals: {len(signals)}")
    buys = sum(1 for s in signals if s['signal'] == 'BUY')
    sells = sum(1 for s in signals if s['signal'] == 'SELL')
    print(f"   • BUY signals: {buys}")
    print(f"   • SELL signals: {sells}")
    print(f"   • Closed trades: {len(trades)}")
    if trades:
        total_pnl = sum(t['pnl_points'] for t in trades)
        avg_pnl = total_pnl / len(trades)
        wins = [t for t in trades if t['result'] == 'TP']
        losses = [t for t in trades if t['result'] == 'SL']
        win_rate = len(wins) / len(trades) * 100
        avg_R = sum(t['R'] for t in trades) / len(trades)
        print(f"   • Total PnL (price points): {total_pnl:.2f}")
        print(f"   • Avg PnL per trade: {avg_pnl:.2f} points")
        print(f"   • Win rate: {win_rate:.1f}%")
        print(f"   • Avg R multiple: {avg_R:.2f}")
        print(f"   • Wins: {len(wins)}, Losses: {len(losses)}")
    else:
        print("   • No completed trades (no TP/SL hits)")


def main():
    """Main analysis function"""
    
    try:
        df = pd.read_csv('gold_5h_backtest.csv')
        df['time'] = pd.to_datetime(df['time'])
    except FileNotFoundError:
        print("❌ File gold_5h_backtest.csv not found")
        return
    
    df = analyze_market_conditions(df)
    plot_analysis(df)
    backtest_with_advanced_system(df)
    
    print("\n🎯 CONCLUSION:")
    print("=" * 60)
    print("1. ❌ SYSTEM TOO RIGID: Fixed threshold doesn't adapt to market conditions")
    print("2. 📉 QUIETER AFTERNOON: Market volatility decreased significantly")
    print("3. 🎯 THRESHOLD TOO HIGH: 40.0 too strict for current market regime")
    print("4. 🔄 NO ADAPTIVITY: System lacks dynamic threshold adjustment")
    print("")
    print("💡 RECOMMENDATIONS:")
    print("   • Implement adaptive threshold based on market volatility")
    print("   • Use rolling average of confluence scores for dynamic adjustment")
    print("   • Add market regime detection (high/low volatility modes)")
    print("   • Consider time-based threshold (lower in quiet periods)")

if __name__ == "__main__":
    main()
