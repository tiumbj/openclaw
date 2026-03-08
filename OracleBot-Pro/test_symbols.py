"""
MT5 Symbols Test
Version: 1.0.0
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_mt5_symbols():
    """Test MT5 symbols availability"""
    print("🔧 กำลังทดสอบ MT5 Symbols...")
    
    try:
        import MetaTrader5 as mt5
        print("✅ MetaTrader5 import สำเร็จ")
        
        # Initialize MT5
        if not mt5.initialize():
            error = mt5.last_error()
            print(f"❌ MT5 Initialize ล้มเหลว: {error}")
            return
        
        print("✅ MT5 Initialize สำเร็จ")
        
        # Get all symbols
        symbols = mt5.symbols_get()
        print(f"📊 พบทั้งหมด {len(symbols)} สัญลักษณ์:")
        
        # Display first 20 symbols
        for i, symbol in enumerate(symbols[:20]):
            print(f"   {i+1:2d}. {symbol.name} - {symbol.description}")
        
        if len(symbols) > 20:
            print(f"   ... และอีก {len(symbols) - 20} สัญลักษณ์")
        
        # Find popular symbols
        popular_symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'BTCUSD']
        print("\n🔍 กำลังค้นหาสัญลักษณ์ยอดนิยม...")
        
        for sym in popular_symbols:
            symbol_info = mt5.symbol_info(sym)
            if symbol_info:
                print(f"✅ พบ {sym}: {symbol_info.description}")
                print(f"   Bid: {symbol_info.bid if hasattr(symbol_info, 'bid') else 'N/A'}")
                print(f"   Ask: {symbol_info.ask if hasattr(symbol_info, 'ask') else 'N/A'}")
            else:
                print(f"❌ ไม่พบ {sym}")
        
        # Try to select XAUUSD if available
        xau_info = mt5.symbol_info("XAUUSD")
        if xau_info:
            print("\n🎯 พบ XAUUSD!")
            print(f"   Description: {xau_info.description}")
            print(f"   Bid: {xau_info.bid}")
            print(f"   Ask: {xau_info.ask}")
            
            # Try to select it
            selected = mt5.symbol_select("XAUUSD", True)
            print(f"   Selected: {selected}")
        else:
            print("\n❌ ไม่พบ XAUUSD ในบัญชีนี้")
            
            # Try to find gold symbols
            gold_symbols = [s for s in symbols if 'GOLD' in s.name or 'XAU' in s.name]
            if gold_symbols:
                print("\n💰 พบสัญลักษณ์ทองคำ:")
                for gold in gold_symbols:
                    print(f"   - {gold.name}: {gold.description}")
        
        mt5.shutdown()
        print("✅ MT5 Shutdown สำเร็จ")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_mt5_symbols()