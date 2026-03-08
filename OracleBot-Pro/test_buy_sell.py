"""
MT5 Buy/Sell Order Test
Version: 1.0.0
"""

import asyncio
import sys
import os
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

@pytest.fixture(scope="module")
def mt5():
    import MetaTrader5 as mt5

    if not mt5.initialize():
        pytest.skip(f"MT5 not available: {mt5.last_error()}")

    return mt5


def test_mt5_basic(mt5):
    account_info = mt5.account_info()
    if account_info:
        assert account_info.login is not None
    assert mt5.version() is not None

def test_buy_order(mt5, symbol="XAUUSD", volume=0.01):
    """Test BUY order execution"""
    print(f"\n🚀 กำลังทดสอบ BUY Order: {symbol} {volume} lots...")
    
    try:
        # Get symbol info
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            pytest.skip(f"Symbol not available: {symbol}")
        
        if not symbol_info.visible:
            print(f"⚠️  สัญลักษณ์ {symbol} ยังไม่ถูกเลือก")
            mt5.symbol_select(symbol, True)
        
        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            pytest.skip(f"No tick for {symbol}")
        price = tick.ask
        print(f"📈 Current Ask Price: {price}")
        
        # Prepare order request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY,
            "price": price,
            "sl": 0.0,
            "tp": 0.0,
            "deviation": 20,
            "magic": 234000,
            "comment": "Test BUY Order",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        # Send order
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"❌ BUY Order ล้มเหลว: {result.retcode}")
            print(f"   Error: {result.comment}")
            return False
        
        print("✅ BUY Order สำเร็จ!")
        print(f"   Order ID: {result.order}")
        print(f"   Volume: {result.volume} lots")
        print(f"   Price: {result.price}")
        print(f"   Profit: {result.profit}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error ใน BUY Order: {e}")
        return False

def test_sell_order(mt5, symbol="XAUUSD", volume=0.01):
    """Test SELL order execution"""
    print(f"\n🚀 กำลังทดสอบ SELL Order: {symbol} {volume} lots...")
    
    try:
        # Get symbol info
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            pytest.skip(f"Symbol not available: {symbol}")
        
        if not symbol_info.visible:
            print(f"⚠️  สัญลักษณ์ {symbol} ยังไม่ถูกเลือก")
            mt5.symbol_select(symbol, True)
        
        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            pytest.skip(f"No tick for {symbol}")
        price = tick.bid
        print(f"📉 Current Bid Price: {price}")
        
        # Prepare order request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": 0.0,
            "tp": 0.0,
            "deviation": 20,
            "magic": 234000,
            "comment": "Test SELL Order",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        # Send order
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"❌ SELL Order ล้มเหลว: {result.retcode}")
            print(f"   Error: {result.comment}")
            return False
        
        print("✅ SELL Order สำเร็จ!")
        print(f"   Order ID: {result.order}")
        print(f"   Volume: {result.volume} lots")
        print(f"   Price: {result.price}")
        print(f"   Profit: {result.profit}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error ใน SELL Order: {e}")
        return False

def test_get_positions(mt5):
    """Test getting open positions"""
    print("\n📊 กำลังตรวจสอบ Open Positions...")
    
    try:
        positions = mt5.positions_get()
        
        if positions is None:
            print("INFO: ไม่มี Open Positions")
            return []
        
        print(f"✅ พบ {len(positions)} Open Positions:")
        for pos in positions:
            print(f"   - {pos.symbol} {pos.volume} lots (Profit: {pos.profit})")
        
        return positions
        
    except Exception as e:
        print(f"❌ Error ในการดึง Positions: {e}")
        return []

def test_close_all_positions(mt5):
    """Test closing all open positions"""
    print("\n🔒 กำลังปิดทั้งหมด Open Positions...")
    
    try:
        positions = mt5.positions_get()
        
        if positions is None or len(positions) == 0:
            print("INFO: ไม่มี Positions ที่ต้องปิด")
            return True
        
        success_count = 0
        for pos in positions:
            # Determine order type for closing
            order_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
            tick = mt5.symbol_info_tick(pos.symbol)
            if tick is None:
                continue
            price = tick.bid if pos.type == 0 else tick.ask
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": order_type,
                "position": pos.ticket,
                "price": price,
                "deviation": 20,
                "magic": 234000,
                "comment": "Close Position",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"✅ ปิด Position {pos.ticket} สำเร็จ")
                success_count += 1
            else:
                print(f"❌ ปิด Position {pos.ticket} ล้มเหลว: {result.comment}")
        
        print(f"📊 สรุป: ปิดได้ {success_count}/{len(positions)} Positions")
        return success_count == len(positions)
        
    except Exception as e:
        print(f"❌ Error ในการปิด Positions: {e}")
        return False

async def main():
    """Main test function"""
    print("=" * 70)
    print("🧪 เริ่มการทดสอบ MT5 Buy/Sell Orders")
    print("=" * 70)
    
    # Test basic connection
    mt5 = test_mt5_basic()
    if mt5 is None:
        print("❌ ไม่สามารถเชื่อมต่อ MT5 ได้")
        return
    
    try:
        # Check current positions
        test_get_positions(mt5)
        
        # Test BUY order
        buy_success = test_buy_order(mt5, "GOLD", 0.01)
        
        if buy_success:
            print("\n⏳ รอ 2 วินาที...")
            await asyncio.sleep(2)
            
            # Check positions after BUY
            test_get_positions(mt5)
            
            # Test SELL order
            sell_success = test_sell_order(mt5, "GOLD", 0.01)
            
            if sell_success:
                print("\n⏳ รอ 2 วินาที...")
                await asyncio.sleep(2)
                
                # Check final positions
                test_get_positions(mt5)
        
        # Close all positions (cleanup)
        print("\n🧹 กำลังทำความสะอาด...")
        test_close_all_positions(mt5)
        
        print("\n" + "=" * 70)
        if buy_success and sell_success:
            print("🎉 การทดสอบ Buy/Sell Orders สำเร็จสมบูรณ์!")
            print("✅ MT5 พร้อมสำหรับการเทรดจริง")
            print("✅ Order Execution ทำงานได้ดี")
        else:
            print("⚠️  การทดสอบมีบางส่วนล้มเหลว แต่พื้นฐานทำงานได้")
        
    finally:
        # Always shutdown MT5
        mt5.shutdown()
        print("✅ MT5 Shutdown สำเร็จ")

if __name__ == "__main__":
    asyncio.run(main())
