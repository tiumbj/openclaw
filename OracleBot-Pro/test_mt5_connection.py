"""
MT5 Connection Test Script
Version: 1.0.0
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_basic_mt5():
    """Test basic MT5 functionality"""
    print("🔧 กำลังทดสอบ Basic MT5 Functionality...")
    
    try:
        import MetaTrader5 as mt5
        print("✅ MetaTrader5 import สำเร็จ")
        
        # Try to initialize
        initialized = mt5.initialize()
        if initialized:
            print("✅ MT5 Initialize สำเร็จ")
            
            # Check version
            version = mt5.version()
            print(f"📋 MT5 Version: {version}")
            
            mt5.shutdown()
            print("✅ MT5 Shutdown สำเร็จ")
            return True
        else:
            error = mt5.last_error()
            print(f"❌ MT5 Initialize ล้มเหลว: {error}")
            return False
            
    except ImportError:
        print("❌ ไม่สามารถ import MetaTrader5 ได้")
        print("⚠️  กรุณาติดตั้ง: pip install MetaTrader5")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

async def test_enterprise_mt5():
    """Test enterprise MT5 manager"""
    print("\n🚀 กำลังทดสอบ Enterprise MT5 Manager...")
    
    try:
        from core.infrastructure.brokers.mt5_manager import MT5Manager
        from config import load_config
        
        print("✅ โหลด modules สำเร็จ")
        
        # Load config
        config = load_config('development')
        print("✅ โหลด configuration สำเร็จ")
        
        # Create manager
        mt5_manager = MT5Manager(
            server=config.mt5.server,
            login=config.mt5.login,
            password=config.mt5.password,
            timeout=config.mt5.timeout,
            max_retries=config.mt5.max_retries
        )
        
        print("✅ สร้าง MT5Manager สำเร็จ")
        
        # Test connection
        connected = await mt5_manager.connect()
        if connected:
            print("✅ MT5 Connection สำเร็จ!")
            
            # Test basic operations
            import MetaTrader5 as mt5
            
            # Account info
            account_info = mt5.account_info()
            if account_info:
                print(f"💰 Account: {account_info.login}")
                print(f"💼 Balance: {account_info.balance}")
            
            # Symbol info
            symbol_info = mt5.symbol_info('XAUUSD')
            if symbol_info:
                print(f"📊 Symbol: {symbol_info.name}")
                print(f"📈 Bid: {symbol_info.bid if hasattr(symbol_info, 'bid') else 'N/A'}")
            
            await mt5_manager.disconnect()
            print("✅ Disconnect สำเร็จ")
            return True
        else:
            print("❌ MT5 Connection ล้มเหลว")
            return False
            
    except Exception as e:
        print(f"❌ Error ใน enterprise test: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main test function"""
    print("=" * 50)
    print("🧪 เริ่มการทดสอบ MT5 Connection")
    print("=" * 50)
    
    # Test 1: Basic MT5 functionality
    basic_success = test_basic_mt5()
    
    if basic_success:
        # Test 2: Enterprise manager
        enterprise_success = await test_enterprise_mt5()
        
        if enterprise_success:
            print("\n🎉 การทดสอบทั้งหมดสำเร็จ!")
            print("✅ MT5 พร้อมสำหรับการเทรด")
        else:
            print("\n⚠️  Enterprise test ล้มเหลว แต่ basic ทำงานได้")
    else:
        print("\n❌ Basic MT5 test ล้มเหลว")
    
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())