#!/usr/bin/env python3
"""
Analyze XAUUSD prices for last 3 hours to check confluence scores
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

def get_3h_prices():
    """Get XAUUSD prices for last 3 hours"""
    
    # Initialize MT5
    if not mt5.initialize():
        print('❌ MT5 Initialize failed')
        print('Error:', mt5.last_error())
        return None
    
    print('✅ MT5 initialized successfully')
    
    try:
        # Get rates for last 3 hours (M5 timeframe)
        rates = mt5.copy_rates_from('XAUUSD', mt5.TIMEFRAME_M5, datetime.now(), 36)  # 36 bars for 3 hours
        if rates is None:
            print('❌ Cannot get rates')
            print('Error:', mt5.last_error())
            return None
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        print('📊 Last 3 hours XAUUSD prices:')
        print(df[['time', 'open', 'high', 'low', 'close']].tail(10))
        print(f'\n📈 Total bars: {len(df)}')
        print(f'💰 Current price: {df.iloc[-1]["close"]:.2f}')
        print(f'🕒 Time range: {df.iloc[0]["time"]} to {df.iloc[-1]["time"]}')
        
        return df
        
    finally:
        mt5.shutdown()

def simulate_confluence_analysis(df):
    """Simulate confluence analysis on historical prices"""
    
    print('\n🎯 Simulating Confluence Analysis (threshold = 40.0)')
    print('=' * 60)
    
    # Simple simulation - in real system this would use MTF analysis
    results = []
    
    for i in range(len(df)):
        if i < 20:  # Need enough data for proper analysis
            continue
            
        # Mock confluence score based on price action (simplified)
        current_close = df.iloc[i]['close']
        prev_close = df.iloc[i-1]['close']
        
        # Simple scoring based on momentum and volatility
        price_change = abs(current_close - prev_close)
        avg_volatility = df['high'][i-20:i].max() - df['low'][i-20:i].min()
        
        if avg_volatility == 0:
            score = 0
        else:
            # Score based on recent momentum vs average volatility
            momentum_factor = min(price_change / (avg_volatility * 0.1), 3.0)
            score = min(momentum_factor * 33.3, 100)  # Scale to 0-100
        
        # Add some randomness to simulate real market conditions
        import random
        score = max(0, min(100, score + random.uniform(-15, 15)))
        
        results.append({
            'time': df.iloc[i]['time'],
            'price': current_close,
            'confluence_score': round(score, 1),
            'above_threshold': score >= 40.0
        })
    
    return results

def main():
    """Main analysis function"""
    
    print('🔍 Analyzing XAUUSD prices for last 3 hours...')
    
    # Get price data
    df = get_3h_prices()
    if df is None:
        return
    
    # Simulate confluence analysis
    analysis_results = simulate_confluence_analysis(df)
    
    print('\n📊 Confluence Analysis Results:')
    print('=' * 60)
    
    # Count signals above threshold
    signals_above = sum(1 for r in analysis_results if r['above_threshold'])
    total_signals = len(analysis_results)
    
    print(f'📈 Total analysis periods: {total_signals}')
    print(f'✅ Signals above 40.0 threshold: {signals_above}')
    print(f'📉 Signals below threshold: {total_signals - signals_above}')
    print(f'🎯 Success rate: {signals_above/total_signals*100:.1f}%' if total_signals > 0 else 'N/A')
    
    # Show recent signals
    print('\n🔍 Recent confluence scores:')
    for result in analysis_results[-10:]:
        status = '✅' if result['above_threshold'] else '❌'
        print(f'{status} {result["time"]} - Price: {result["price"]:.2f}, Score: {result["confluence_score"]:.1f}')
    
    # Recommendation
    if signals_above == 0:
        print('\n⚠️  RECOMMENDATION: Threshold 40.0 might be too strict!')
        print('   Consider lowering to 35.0 or 30.0 for more trading opportunities')
    else:
        print(f'\n✅ Threshold 40.0 appears reasonable with {signals_above} signals')

if __name__ == "__main__":
    main()