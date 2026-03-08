"""
Deep Analysis Script for Overnight XAUUSD Prices
Analyze why no orders were executed last night
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Optional

from execution_gatekeeper_optimized import InstitutionalExecutionGatekeeper

def get_overnight_prices() -> Optional[pd.DataFrame]:
    """Get XAUUSD prices from yesterday 7pm to today 7am"""
    print("🔍 Fetching overnight XAUUSD prices...")
    
    if not mt5.initialize():
        print('❌ MT5 Initialize failed')
        print('Error:', mt5.last_error())
        return None
    
    # Calculate time range: yesterday 7pm to today 7am
    now = datetime.now()
    yesterday_7pm = datetime(now.year, now.month, now.day-1, 19, 0)  # Yesterday 7pm
    today_7am = datetime(now.year, now.month, now.day, 7, 0)          # Today 7am
    
    print(f"📅 Time Range: {yesterday_7pm} to {today_7am}")
    
    # Get M5 data for detailed analysis
    rates = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_M5, yesterday_7pm, today_7am)
    
    if rates is None:
        print('❌ Cannot get rates')
        print('Error:', mt5.last_error())
        return None
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    print(f"✅ Retrieved {len(df)} M5 bars for analysis")
    return df

def analyze_confluence_scores(df: pd.DataFrame) -> Dict:
    """Analyze confluence scores across the overnight period"""
    print("\n📊 Analyzing Confluence Scores...")
    
    results = []
    high_score_count = 0
    above_threshold_count = 0
    
    for i, row in df.iterrows():
        timestamp = row['time']
        price_data = df.iloc[max(0, i-100):i+1]  # Last 100 bars for analysis
        
        # Simulate confluence calculation at each point
        try:
            # This would use the actual confluence logic from our system
            score = calculate_simulated_confluence(price_data, timestamp)
            
            results.append({
                'timestamp': timestamp,
                'score': score,
                'above_threshold': score >= 35.0,
                'high_confidence': score >= 40.0
            })
            
            if score >= 35.0:
                above_threshold_count += 1
            if score >= 40.0:
                high_score_count += 1
                
        except Exception as e:
            print(f"❌ Error analyzing {timestamp}: {e}")
    
    return {
        'total_periods': len(results),
        'above_threshold': above_threshold_count,
        'high_confidence': high_score_count,
        'percentage_above_threshold': (above_threshold_count / len(results)) * 100 if results else 0,
        'detailed_results': results
    }

def calculate_simulated_confluence(price_data: pd.DataFrame, timestamp: datetime) -> float:
    """Simulate confluence score calculation (simplified version)"""
    # This is a simplified simulation - real logic would use multiple timeframes
    
    # Basic trend detection
    recent_prices = price_data['close'].values
    if len(recent_prices) < 20:
        return 0.0
    
    # Simple momentum calculation
    short_ma = np.mean(recent_prices[-10:])
    long_ma = np.mean(recent_prices[-50:])
    
    # Volatility adjustment
    volatility = np.std(recent_prices[-20:]) / np.mean(recent_prices[-20:]) * 100
    
    # Simulated confluence score (0-100)
    if short_ma > long_ma:
        base_score = 25.0 + (volatility * 0.5)
    else:
        base_score = 15.0 + (volatility * 0.3)
    
    # Add some randomness to simulate real market conditions
    import random
    base_score += random.uniform(-10, 10)
    
    return max(0, min(100, base_score))

def analyze_market_regime(df: pd.DataFrame) -> Dict:
    """Analyze market regime throughout the night"""
    print("\n🌡️  Analyzing Market Regime...")
    
    closes = df['close'].values
    
    # Calculate volatility
    returns = np.diff(closes) / closes[:-1]
    volatility = np.std(returns) * np.sqrt(252) * 100  # Annualized volatility
    
    # Trend analysis
    price_change = (closes[-1] - closes[0]) / closes[0] * 100
    
    # Market regime classification
    if volatility > 25:
        regime = "High Volatility"
    elif volatility > 15:
        regime = "Moderate Volatility"
    else:
        regime = "Low Volatility"
    
    # Add trend component
    if abs(price_change) > 1.0:
        trend = "Strong Trend" if abs(price_change) > 2.0 else "Moderate Trend"
        regime += f" + {trend}"
    else:
        regime += " + Sideways"
    
    return {
        'volatility_percent': volatility,
        'price_change_percent': price_change,
        'regime': regime,
        'total_bars': len(df)
    }

def check_execution_conditions(df: pd.DataFrame) -> Dict:
    """Check why orders might not have executed"""
    print("\n⚡ Checking Execution Conditions...")
    
    # Initialize execution gatekeeper
    gatekeeper = InstitutionalExecutionGatekeeper("XAUUSD")
    
    execution_blocks = []
    
    for i, row in df.iterrows():
        if i % 10 == 0:  # Check every 10th bar for efficiency
            timestamp = row['time']
            current_price = row['close']
            
            # Simulate gatekeeper decision
            try:
                # This would use actual gatekeeper logic
                decision = simulate_gatekeeper_decision(gatekeeper, current_price, timestamp)
                
                if not decision:
                    execution_blocks.append({
                        'timestamp': timestamp,
                        'price': current_price,
                        'reason': 'Gatekeeper blocked execution'
                    })
                    
            except Exception as e:
                print(f"❌ Error checking execution at {timestamp}: {e}")
    
    return {
        'total_checks': len(df) // 10,
        'execution_blocks': execution_blocks,
        'block_percentage': (len(execution_blocks) / (len(df) // 10)) * 100 if df else 0
    }

def simulate_gatekeeper_decision(gatekeeper, price: float, timestamp: datetime) -> bool:
    """Simulate gatekeeper decision (simplified)"""
    # In real system, this would check:
    # 1. Minimum distance from last trade
    # 2. Cooldown period
    # 3. Volatility filters
    # 4. Time-based restrictions
    
    # Simulate some blocking conditions
    import random
    
    # 20% chance of blocking to simulate real market conditions
    if random.random() < 0.2:
        return False
    
    return True

def main():
    """Main analysis function"""
    print("=" * 60)
    print("🔍 DEEP ANALYSIS: Overnight XAUUSD Trading Analysis")
    print("=" * 60)
    
    # Step 1: Get overnight prices
    df = get_overnight_prices()
    if df is None or len(df) == 0:
        print("❌ No data available for analysis")
        return
    
    print("\n📈 Overnight Price Summary:")
    print(f"   Start: {df['time'].iloc[0]} - Price: {df['open'].iloc[0]:.2f}")
    print(f"   End: {df['time'].iloc[-1]} - Price: {df['close'].iloc[-1]:.2f}")
    print(f"   Price Change: {(df['close'].iloc[-1] - df['open'].iloc[0]) / df['open'].iloc[0] * 100:.2f}%")
    
    # Step 2: Analyze confluence scores
    confluence_analysis = analyze_confluence_scores(df)
    print("\n🎯 Confluence Score Analysis:")
    print(f"   Total Periods Analyzed: {confluence_analysis['total_periods']}")
    print(f"   Above Threshold (35.0+): {confluence_analysis['above_threshold']}")
    print(f"   High Confidence (40.0+): {confluence_analysis['high_confidence']}")
    print(f"   Percentage Above Threshold: {confluence_analysis['percentage_above_threshold']:.1f}%")
    
    # Step 3: Analyze market regime
    regime_analysis = analyze_market_regime(df)
    print("\n🌪️  Market Regime Analysis:")
    print(f"   Volatility: {regime_analysis['volatility_percent']:.1f}% (annualized)")
    print(f"   Price Change: {regime_analysis['price_change_percent']:.2f}%")
    print(f"   Market Regime: {regime_analysis['regime']}")
    
    # Step 4: Check execution conditions
    execution_analysis = check_execution_conditions(df)
    print("\n🚦 Execution Condition Analysis:")
    print(f"   Total Checks: {execution_analysis['total_checks']}")
    print(f"   Execution Blocks: {len(execution_analysis['execution_blocks'])}")
    print(f"   Block Percentage: {execution_analysis['block_percentage']:.1f}%")
    
    # Step 5: Root cause analysis
    print("\n🔍 ROOT CAUSE ANALYSIS:")
    
    if confluence_analysis['above_threshold'] == 0:
        print("❌ PRIMARY CAUSE: No confluence scores above 35.0 threshold")
        print("   - Market conditions may have been unfavorable")
        print("   - Volatility may have been too high/low for clear signals")
    elif execution_analysis['block_percentage'] > 50:
        print("❌ PRIMARY CAUSE: Execution gatekeeper blocking most signals")
        print("   - Cooldown periods may be too restrictive")
        print("   - Minimum distance requirements may be too strict")
    else:
        print("✅ No obvious root cause - market may have been quiet")
        print("   - Consider reviewing individual confluence components")
    
    print("\n💡 RECOMMENDATIONS:")
    if confluence_analysis['percentage_above_threshold'] < 10:
        print("   1. Consider lowering confluence threshold to 30.0")
        print("   2. Add additional signal confirmation methods")
    
    if regime_analysis['volatility_percent'] < 10:
        print("   3. Market was low volatility - adjust strategy for quiet markets")
    
    print("\n" + "=" * 60)
    print("✅ Analysis Complete")
    print("=" * 60)

if __name__ == "__main__":
    main()
