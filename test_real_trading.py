#!/usr/bin/env python3
"""
Test Real Trading with XMGlobal-MT5
ทดสอบการเทรดจริงกับ broker XMGlobal-MT5
"""

import MetaTrader5 as mt5
import time

def test_real_trading():
    """ทดสอบการเทรดจริง"""
    print("=" * 60)
    print("🚀 TESTING REAL TRADING WITH XMGLOBAL-MT5")
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
    print(f"✅ Trade Allowed: {account_info.trade_allowed}")
    
    # Test GOLD trading
    symbol = "GOLD"
    print(f"\n🎯 Testing {symbol} trading...")
    
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        print(f"❌ Cannot get {symbol} info")
        mt5.shutdown()
        return False
    
    print(f"📊 {symbol}:")
    print(f"   Bid: {symbol_info.bid:.2f}")
    print(f"   Ask: {symbol_info.ask:.2f}")
    print(f"   Spread: {(symbol_info.ask - symbol_info.bid):.2f} points")
    print(f"   Trade Mode: {symbol_info.trade_mode}")
    
    # Test BUY order
    print("\n🚀 Testing BUY order...")
    
    volume = 0.01  # 0.01 lot
    price = symbol_info.ask
    stop_loss = price - 100 * 0.1  # 100 points SL
    take_profit = price + 200 * 0.1  # 200 points TP
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_BUY,
        "price": price,
        "sl": stop_loss,
        "tp": take_profit,
        "deviation": 20,
        "magic": 999888,
        "comment": "Test BUY order",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    print("📋 Order details:")
    print(f"   Symbol: {symbol}")
    print(f"   Volume: {volume} lots")
    print(f"   Price: {price:.2f}")
    print(f"   SL: {stop_loss:.2f}")
    print(f"   TP: {take_profit:.2f}")
    
    # Send order
    result = mt5.order_send(request)
    
    if result is None:
        print("❌ Order failed: No result")
        print(f"   Error: {mt5.last_error()}")
    else:
        print("\n📊 Order result:")
        print(f"   Retcode: {result.retcode}")
        print(f"   Deal: {result.deal}")
        print(f"   Order: {result.order}")
        print(f"   Volume: {result.volume}")
        print(f"   Price: {result.price}")
        print(f"   Bid: {result.bid}")
        print(f"   Ask: {result.ask}")
        print(f"   Comment: {result.comment}")
        print(f"   Request ID: {result.request_id}")
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print("✅ Order executed successfully!")
            print(f"   Position opened at {result.price}")
            
            # Check positions
            time.sleep(2)
            print("\n📋 Checking open positions...")
            positions = mt5.positions_get()
            
            if positions:
                print(f"✅ Found {len(positions)} open positions")
                for pos in positions:
                    print(f"\n📊 Position #{pos.ticket}:")
                    print(f"   Symbol: {pos.symbol}")
                    print(f"   Type: {'BUY' if pos.type == 0 else 'SELL'}")
                    print(f"   Volume: {pos.volume}")
                    print(f"   Open Price: {pos.price_open}")
                    print(f"   Current Price: {mt5.symbol_info_tick(pos.symbol).ask if pos.type == 0 else mt5.symbol_info_tick(pos.symbol).bid}")
                    print(f"   Profit: ${pos.profit:.2f}")
                    print(f"   SL: {pos.sl}")
                    print(f"   TP: {pos.tp}")
            else:
                print("❌ No positions found")
                
        else:
            print(f"❌ Order failed with retcode: {result.retcode}")
            print(f"   Error: {result.comment}")
            print(f"   Last error: {mt5.last_error()}")
    
    # Shutdown
    mt5.shutdown()
    print("\n✅ MT5 shutdown complete")
    
    return True

if __name__ == "__main__":
    test_real_trading()