#!/usr/bin/env python3
"""
Fetch 5 hours of GOLD price data for backtesting
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

def fetch_5h_gold_data():
    """Fetch 5 hours of GOLD price data"""
    
    print('📊 ดึงราคา GOLD 5 ชั่วโมงย้อนหลัง...')
    
    if not mt5.initialize():
        print('❌ MT5 Initialize failed')
        print('Error:', mt5.last_error())
        return None
    
    print('✅ MT5 initialized successfully')
    
    try:
        # Get rates for last 5 hours (M5 timeframe - 60 bars)
        rates = mt5.copy_rates_from('GOLD', mt5.TIMEFRAME_M5, datetime.now(), 60)
        
        if rates is None:
            print('❌ Cannot get rates for GOLD')
            print('Error:', mt5.last_error())
            return None
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        print(f'✅ ได้ข้อมูล {len(df)} bars (5 ชั่วโมง)')
        print(f'📅 ช่วงเวลา: {df.iloc[0]["time"]} ถึง {df.iloc[-1]["time"]}')
        print(f'💰 ราคาปัจจุบัน: {df.iloc[-1]["close"]:.2f}')
        print(f'📈 ราคาสูงสุด: {df["high"].max():.2f}')
        print(f'📉 ราคาต่ำสุด: {df["low"].min():.2f}')
        
        # Save to CSV for backtest
        csv_path = 'gold_5h_backtest.csv'
        df.to_csv(csv_path, index=False)
        print(f'💾 บันทึกข้อมูลลง {csv_path} แล้ว')
        
        # Show sample data
        print('\n📋 ตัวอย่างข้อมูล 5 บาร์ล่าสุด:')
        print(df[['time', 'open', 'high', 'low', 'close']].tail())
        
        return df
        
    finally:
        mt5.shutdown()
        print('✅ MT5 shutdown complete')

def main():
    """Main function"""
    data = fetch_5h_gold_data()
    
    if data is not None:
        print(f'\n🎯 พร้อมสำหรับ backtest ด้วยข้อมูล {len(data)} bars')
        print('📍 ไฟล์: gold_5h_backtest.csv')
    else:
        print('❌ ไม่สามารถดึงข้อมูลได้')

if __name__ == "__main__":
    main()