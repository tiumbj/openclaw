#!/usr/bin/env python3
"""
Test Close Only Mode
ทดสอบการทำงานในโหมด Close Only ของ broker XMGlobal-MT5
"""

import MetaTrader5 as mt5
import time

def test_close_only_capabilities():
    """ทดสอบความสามารถในโหมด Close Only"""
    print("=" * 60)
    print("🔧 TESTING CLOSE ONLY MODE CAPABILITIES")
    print("=" * 60)
    
    # Initialize MT5
    if not mt5.initialize():
        print(f"❌ MT5 Initialize failed: {mt5.last_error()}")
        return False
    
    print("✅ MT5 initialized successfully")
    
    # Get account info
    account_info = mt5.account_info()
    if not account_info:
        print("❌ Cannot get account info")
        mt5.shutdown()
        return False
    
    print(f"📋 Account: {account_info.login} ({account_info.server})")
    print(f"💵 Balance: ${account_info.balance:.2f}")
    
    # Check current positions
    print("\n📊 Checking existing positions...")
    positions = mt5.positions_get()
    
    if positions:
        print(f"✅ Found {len(positions)} open positions")
        for i, pos in enumerate(positions):
            print(f"\n#{i+1} {pos.symbol} {pos.type}")
            print(f"   Ticket: {pos.ticket}")
            print(f"   Volume: {pos.volume}")
            print(f"   Open Price: {pos.price_open}")
            print(f"   Current Price: {mt5.symbol_info_tick(pos.symbol).ask if pos.type == 0 else mt5.symbol_info_tick(pos.symbol).bid}")
            print(f"   Profit: ${pos.profit:.2f}")
            
            # Test closing this position
            print(f"\n🔧 Testing close position #{pos.ticket}...")
            
            # Create close request
            symbol_info = mt5.symbol_info(pos.symbol)
            if symbol_info:
                price = symbol_info.ask if pos.type == 1 else symbol_info.bid  # 1=BUY, 0=SELL
                
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "position": pos.ticket,
                    "symbol": pos.symbol,
                    "volume": pos.volume,
                    "type": mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY,
                    "price": price,
                    "deviation": 20,
                    "magic": 1001,
                    "comment": "Close by test script",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                
                # Send close order
                result = mt5.order_send(request)
                
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    print(f"✅ Successfully closed position #{pos.ticket}")
                    print(f"   Close price: {result.price}")
                    print(f"   Profit: ${result.profit:.2f}")
                else:
                    print(f"❌ Failed to close position #{pos.ticket}")
                    if result:
                        print(f"   Retcode: {result.retcode}")
                        print(f"   Error: {result.comment}")
                    else:
                        print(f"   Error: {mt5.last_error()}")
            
            time.sleep(1)
    else:
        print("INFO: No open positions found")
        print("\n📝 Note: In close-only mode, you can only close existing positions")
        print("   You cannot open new positions with this broker demo account")
    
    # Test opening new position (should fail)
    print("\n🚀 Testing new position opening (should fail)...")
    
    symbol = "GOLD"
    symbol_info = mt5.symbol_info(symbol)
    
    if symbol_info and symbol_info.trade_mode == 4:
        print("✅ Confirmed: GOLD is in close-only mode")
        
        # Try to open BUY position
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": 0.01,
            "type": mt5.ORDER_TYPE_BUY,
            "price": symbol_info.ask,
            "deviation": 20,
            "magic": 1002,
            "comment": "Test open in close-only mode",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result and result.retcode != mt5.TRADE_RETCODE_DONE:
            print("✅ Expected: Opening new position failed")
            print(f"   Retcode: {result.retcode}")
            print(f"   Error: {result.comment}")
        else:
            print("❌ Unexpected: Position opened successfully")
    
    # Shutdown
    mt5.shutdown()
    print("\n✅ MT5 shutdown complete")
    
    return True

def check_broker_alternatives():
    """ตรวจสอบ broker alternatives"""
    print("\n" + "=" * 60)
    print("🔍 BROKER ALTERNATIVES FOR FULL TRADING")
    print("=" * 60)
    
    print("📋 Brokers that typically allow demo trading:")
    print("   1. IC Markets - Often allows full demo trading")
    print("   2. Pepperstone - Good for demo accounts") 
    print("   3. FXPro - Usually allows demo trading")
    print("   4. ThinkMarkets - Good demo capabilities")
    print("   5. RoboForex - Often allows full demo")
    
    print("\n💡 Recommendations:")
    print("   - Look for brokers with 'TRADE_MODE_FULL (0)' for demo accounts")
    print("   - Check if they offer GOLD/XAUUSD trading")
    print("   - Ensure low spreads for gold trading")
    print("   - Consider real account if demo restrictions persist")

if __name__ == "__main__":
    test_close_only_capabilities()
    check_broker_alternatives()
