"""
Test Script for MT5 Order Execution
ทดสอบการส่งคำสั่ง Buy/Sell อย่างง่ายเพื่อตรวจสอบการทำงาน
"""

import MetaTrader5 as mt5
import time
import pytest


@pytest.fixture(scope="module", autouse=True)
def _mt5_ready():
    if not mt5.initialize():
        pytest.skip(f"MT5 not available: {mt5.last_error()}")
    yield
    mt5.shutdown()

def initialize_mt5() -> bool:
    """Initialize MT5 connection"""
    print("🔗 Initializing MT5...")
    
    if not mt5.initialize():
        print(f"❌ MT5 Initialize failed: {mt5.last_error()}")
        return False
    
    print("✅ MT5 initialized successfully")
    
    # ใช้การเชื่อมต่อแบบไม่ต้อง login (ใช้ account default)
    try:
        # พยายามดึง account info โดยไม่ต้อง login
        account_info = mt5.account_info()
        
        if account_info:
            print("✅ Connected to MT5 Account")
            print(f"   Account: {account_info.login}")
            print(f"   Balance: ${account_info.balance:.2f}")
            print(f"   Equity: ${account_info.equity:.2f}")
            print(f"   Broker: {account_info.server}")
            print(f"   Trade Allowed: {account_info.trade_allowed}")
            print(f"   Trade Expert: {account_info.trade_expert}")
            return True
        else:
            print("⚠️  Cannot get account info (demo mode)")
            print(f"   Error: {mt5.last_error()}")
            
            # Check if we can get market data (demo mode)
            rates = mt5.copy_rates_from_pos("GOLD", mt5.TIMEFRAME_M5, 0, 1)
            if rates is not None:
                print("✅ Market data accessible (demo mode)")
                return True
            else:
                print("❌ Cannot access market data")
                print(f"   Error: {mt5.last_error()}")
                return False
                
    except Exception as e:
        print(f"❌ Account info error: {e}")
        
        # Check if we can get market data (demo mode)
        rates = mt5.copy_rates_from_pos("GOLD", mt5.TIMEFRAME_M5, 0, 1)
        if rates is not None:
            print("✅ Market data accessible (demo mode)")
            return True
        else:
            print("❌ Cannot access market data")
            return False

def test_market_data():
    """ทดสอบการดึงข้อมูล market"""
    print("\n📊 Testing Market Data...")
    
    symbols = ["XAUUSD", "EURUSD", "GBPUSD", "GOLD", "XAUUSD.a"]
    
    for symbol in symbols:
        try:
            # ข้อมูล symbol
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info:
                print(f"✅ {symbol}:")
                print(f"   Bid: {symbol_info.bid:.5f}")
                print(f"   Ask: {symbol_info.ask:.5f}")
                print(f"   Spread: {symbol_info.spread * 0.01:.1f} pips")
                print(f"   Trade Allowed: {symbol_info.trade_allowed}")
                print(f"   Trade Mode: {symbol_info.trade_mode}")
            else:
                print(f"❌ Cannot get info for {symbol}")
                
        except Exception as e:
            print(f"❌ Error getting {symbol} info: {e}")

def test_buy_order():
    """ทดสอบการส่งคำสั่ง BUY"""
    print("\n🚀 Testing BUY Order...")
    
    symbol = "GOLD"
    symbol_info = mt5.symbol_info(symbol)
    
    if symbol_info is None:
        pytest.skip(f"Symbol not available: {symbol}")
    if symbol_info.trade_mode != 0:
        pytest.skip(f"{symbol} not tradeable (trade_mode: {symbol_info.trade_mode})")
    
    # คำนวณ volume ขนาดเล็กสำหรับทดสอบ
    volume = 0.01  # 0.01 lot (ขนาดเล็กสุด)
    
    # ราคาปัจจุบัน
    current_price = symbol_info.ask
    
    # คำนวณ stop loss และ take profit
    stop_loss = current_price - 100 * 0.1  # 100 pips stop loss
    take_profit = current_price + 200 * 0.1  # 200 pips take profit
    
    # สร้างคำสั่ง order
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_BUY,
        "price": current_price,
        "sl": stop_loss,
        "tp": take_profit,
        "deviation": 50,  # 50 points slippage allowance
        "magic": 999888,
        "comment": "Test BUY Order",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    print("📋 Order Details:")
    print(f"   Symbol: {symbol}")
    print("   Type: BUY")
    print(f"   Volume: {volume} lots")
    print(f"   Price: {current_price:.2f}")
    print(f"   Stop Loss: {stop_loss:.2f}")
    print(f"   Take Profit: {take_profit:.2f}")
    print(f"   Risk: ${(current_price - stop_loss) * volume * 100:.2f}")
    
    # ส่งคำสั่ง order
    result = mt5.order_send(request)
    
    if result is None:
        print("❌ Order failed: No result returned")
        print(f"   Error: {mt5.last_error()}")
        return False
    
    print("\n📨 Order Result:")
    print(f"   Retcode: {result.retcode}")
    print(f"   Order ID: {result.order}")
    print(f"   Volume: {result.volume}")
    print(f"   Price: {result.price}")
    print(f"   Profit: {result.profit}")
    print(f"   Comment: {result.comment}")
    
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print("✅ BUY Order executed successfully!")
        return True
    else:
        print(f"❌ Order failed with retcode: {result.retcode}")
        print(f"   Error: {mt5.last_error()}")
        print(f"   Result: {result}")
        return False

def test_sell_order():
    """ทดสอบการส่งคำสั่ง SELL"""
    print("\n🚀 Testing SELL Order...")
    
    symbol = "GOLD"
    symbol_info = mt5.symbol_info(symbol)
    
    if symbol_info is None:
        pytest.skip(f"Symbol not available: {symbol}")
    if symbol_info.trade_mode != 0:
        pytest.skip(f"{symbol} not tradeable (trade_mode: {symbol_info.trade_mode})")
    
    # คำนวณ volume ขนาดเล็กสำหรับทดสอบ
    volume = 0.01  # 0.01 lot (ขนาดเล็กสุด)
    
    # ราคาปัจจุบัน
    current_price = symbol_info.bid
    
    # คำนวณ stop loss และ take profit
    stop_loss = current_price + 100 * 0.1  # 100 pips stop loss
    take_profit = current_price - 200 * 0.1  # 200 pips take profit
    
    # สร้างคำสั่ง order
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_SELL,
        "price": current_price,
        "sl": stop_loss,
        "tp": take_profit,
        "deviation": 50,  # 50 points slippage allowance
        "magic": 999888,
        "comment": "Test SELL Order",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    print("📋 Order Details:")
    print(f"   Symbol: {symbol}")
    print("   Type: SELL")
    print(f"   Volume: {volume} lots")
    print(f"   Price: {current_price:.2f}")
    print(f"   Stop Loss: {stop_loss:.2f}")
    print(f"   Take Profit: {take_profit:.2f}")
    print(f"   Risk: ${(stop_loss - current_price) * volume * 100:.2f}")
    
    # ส่งคำสั่ง order
    result = mt5.order_send(request)
    
    if result is None:
        print("❌ Order failed: No result returned")
        print(f"   Error: {mt5.last_error()}")
        return False
    
    print("\n📨 Order Result:")
    print(f"   Retcode: {result.retcode}")
    print(f"   Order ID: {result.order}")
    print(f"   Volume: {result.volume}")
    print(f"   Price: {result.price}")
    print(f"   Profit: {result.profit}")
    print(f"   Comment: {result.comment}")
    
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print("✅ SELL Order executed successfully!")
        return True
    else:
        print(f"❌ Order failed with retcode: {result.retcode}")
        print(f"   Error: {mt5.last_error()}")
        print(f"   Result: {result}")
        return False

def check_open_positions():
    """ตรวจสอบ positions ที่เปิดอยู่"""
    print("\n📊 Checking Open Positions...")
    
    positions = mt5.positions_get()
    
    if positions is None:
        print("❌ No positions or error getting positions")
        print(f"   Error: {mt5.last_error()}")
        return
    
    if len(positions) == 0:
        print("✅ No open positions")
        return
    
    print(f"📈 Found {len(positions)} open positions:")
    
    for i, position in enumerate(positions):
        print(f"\n#{i+1} {position.symbol} {position.type}")
        print(f"   Ticket: {position.ticket}")
        print(f"   Volume: {position.volume} lots")
        print(f"   Open Price: {position.price_open}")
        print(f"   Current Price: {position.price_current}")
        print(f"   Profit: ${position.profit:.2f}")
        print(f"   SL: {position.sl}")
        print(f"   TP: {position.tp}")

def main():
    """Main function"""
    print("=" * 60)
    print("MT5 ORDER EXECUTION TEST SCRIPT")
    print("=" * 60)
    
    # Initialize MT5
    if not initialize_mt5():
        print("❌ Cannot continue without MT5 connection")
        return
    
    # Test market data
    test_market_data()
    
    # Test BUY order
    buy_success = test_buy_order()
    
    # Wait a bit
    time.sleep(2)
    
    # Check positions after BUY
    check_open_positions()
    
    # Wait a bit before SELL test
    time.sleep(3)
    
    # Test SELL order (if BUY was successful)
    if buy_success:
        test_sell_order()
        
        # Wait a bit
        time.sleep(2)
        
        # Check final positions
        check_open_positions()
    
    # Shutdown MT5
    mt5.shutdown()
    print("\n✅ MT5 connection closed")
    print("\n🎯 Test completed!")

if __name__ == "__main__":
    main()
