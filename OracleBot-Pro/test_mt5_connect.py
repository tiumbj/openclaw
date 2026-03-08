#!/usr/bin/env python3
"""
Test MT5 Connection Script
ทดสอบการเชื่อมต่อ MT5 ใหม่ทั้งหมด
"""

import MetaTrader5 as mt5

def test_mt5_connection():
    """ทดสอบการเชื่อมต่อ MT5"""
    print("=" * 60)
    print("🔗 TESTING MT5 CONNECTION")
    print("=" * 60)
    
    # 1. Check MT5 version
    print(f"📦 MT5 Python package version: {mt5.__version__}")
    
    # 2. Initialize MT5
    print("\n🔗 Initializing MT5...")
    initialized = mt5.initialize()
    print(f"✅ Initialize success: {initialized}")
    
    if not initialized:
        error = mt5.last_error()
        print(f"❌ MT5 Initialize failed: {error}")
        return False
    
    # 3. Get account info
    print("\n📋 Getting account info...")
    account_info = mt5.account_info()
    
    if account_info:
        print(f"✅ Account Login: {account_info.login}")
        print(f"✅ Account Name: {account_info.name}")
        print(f"✅ Broker: {account_info.server}")
        print(f"✅ Balance: ${account_info.balance:.2f}")
        print(f"✅ Equity: ${account_info.equity:.2f}")
        print(f"✅ Trade Allowed: {account_info.trade_allowed}")
        print(f"✅ Trade Expert: {account_info.trade_expert}")
        print(f"✅ Margin Mode: {account_info.margin_mode}")
    else:
        print("❌ Cannot get account info")
        print(f"Error: {mt5.last_error()}")
        mt5.shutdown()
        return False
    
    # 4. Test market data
    print("\n📊 Testing market data...")
    symbols = ["GOLD", "XAUUSD", "EURUSD", "GBPUSD"]
    
    for symbol in symbols:
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info:
            print(f"✅ {symbol}:")
            print(f"   Bid: {symbol_info.bid}")
            print(f"   Ask: {symbol_info.ask}")
            print(f"   Spread: {symbol_info.spread * 0.01:.1f} pips")
            print(f"   Trade Mode: {symbol_info.trade_mode}")
            print(f"   Select: {symbol_info.select}")
        else:
            print(f"❌ Cannot get {symbol} info")
    
    # 5. Test order sending capability
    print("\n🚀 Testing order capability...")
    gold_info = mt5.symbol_info("GOLD")
    if gold_info:
        print(f"GOLD trade_mode: {gold_info.trade_mode}")
        
        # Check if we can open positions
        if gold_info.trade_mode == 0:
            print("✅ GOLD: Can open positions (TRADE_MODE_FULL)")
        elif gold_info.trade_mode == 4:
            print("❌ GOLD: Close only mode (TRADE_MODE_CLOSEONLY)")
        else:
            print(f"INFO: GOLD: Trade mode {gold_info.trade_mode}")
    
    # 6. Check terminal info
    print("\n💻 Terminal info:")
    terminal_info = mt5.terminal_info()
    if terminal_info:
        print(f"✅ Connected: {terminal_info.connected}")
        print(f"✅ Build: {terminal_info.build}")
        print(f"✅ Community Account: {terminal_info.community_account}")
        print(f"✅ Community Connection: {terminal_info.community_connection}")
    
    # 7. Shutdown
    print("\n🔌 Shutting down MT5...")
    mt5.shutdown()
    print("✅ MT5 shutdown complete")
    
    return True

if __name__ == "__main__":
    test_mt5_connection()
