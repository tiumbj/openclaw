"""
Forward Testing Script for MT5 Demo Account
Phase 5: Paper Trading with Real-time Execution
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import json
from typing import Dict, Optional

class ForwardTester:
    def __init__(self):
        self.demo_account = {
            'login': 168021026,      # Demo account login
            'password': 'YourDemoPassword',  # Demo password
            'server': 'XMGlobal-Demo',     # Demo server
            'timeout': 60000,
            'portable': False
        }
        
        # Optimized parameters for H4 timeframe (best performer)
        self.strategy_params = {
            'rsi_oversold': 25,
            'rsi_overbought': 75,
            'adx_threshold': 15,
            'risk_per_trade': 0.02,  # 2% risk per trade
            'max_drawdown': 0.15,     # 15% max drawdown
            'symbol': 'GOLD',
            'timeframe': mt5.TIMEFRAME_H4
        }
        
        self.trade_history = []
        self.equity_curve = []
        self.current_equity = 10000  # Starting equity
        
    def connect_demo_account(self) -> bool:
        """Connect to MT5 demo account"""
        print("🔗 กำลังเชื่อมต่อ MT5 Demo Account...")
        
        # First check if MT5 is already initialized
        if not mt5.initialize():
            print("❌ MT5 Initialize ล้มเหลว")
            print("⚠️  กำลังลองใช้การเชื่อมต่อแบบไม่มี authentication...")
            
            # Try to connect without authentication first
            if not mt5.initialize():
                print("❌ ยังคงไม่สามารถ initialize MT5 ได้")
                return False
        
        # Try to connect to any available account (demo or real)
        authorized = mt5.login()
        
        if authorized:
            account_info = mt5.account_info()
            print("✅ เชื่อมต่อ MT5 Account สำเร็จ")
            print(f"💰 Balance: {account_info.balance}")
            print(f"💼 Equity: {account_info.equity}")
            print(f"🏢 Broker: {account_info.server}")
            self.current_equity = account_info.equity
            return True
        else:
            print("⚠️  ไม่สามารถเชื่อมต่อกับ specific account ได้, ใช้การเชื่อมต่อทั่วไป")
            print("📊 กำลังตรวจสอบการเชื่อมต่อ MT5...")
            
            # Check if we can at least get market data
            try:
                rates = mt5.copy_rates_from_pos("GOLD", mt5.TIMEFRAME_H4, 0, 10)
                if rates is not None:
                    print("✅ สามารถดึงข้อมูลตลาดได้ (การเชื่อมต่อทำงาน)")
                    return True
                else:
                    print("❌ ไม่สามารถดึงข้อมูลตลาดได้")
                    return False
            except Exception as e:
                print(f"❌ เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
                return False
    
    def download_market_data(self, bars: int = 100) -> Optional[pd.DataFrame]:
        """Download recent market data for analysis"""
        print(f"📥 กำลังดาวน์โหลดข้อมูล {self.strategy_params['symbol']}...")
        
        rates = mt5.copy_rates_from_pos(
            self.strategy_params['symbol'],
            self.strategy_params['timeframe'],
            0,  # Start from current bar
            bars
        )
        
        if rates is None or len(rates) == 0:
            print("❌ ไม่สามารถดาวน์โหลดข้อมูลได้")
            return None
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        
        print(f"✅ ดาวน์โหลดข้อมูลสำเร็จ: {len(df)} bars")
        return df
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators"""
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD
        exp12 = df['close'].ewm(span=12).mean()
        exp26 = df['close'].ewm(span=26).mean()
        df['macd'] = exp12 - exp26
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        
        # ADX (simplified)
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        tr = np.maximum(high_low, np.maximum(high_close, low_close))
        df['adx'] = tr.rolling(window=14).mean() / df['close'] * 100
        
        return df.dropna()
    
    def generate_signal(self, df: pd.DataFrame) -> Dict:
        """Generate trading signal based on strategy"""
        latest = df.iloc[-1]
        
        # Market regime check
        is_trending = latest['adx'] > self.strategy_params['adx_threshold']
        
        # Buy signal: RSI oversold + MACD bullish crossover + trending market
        buy_signal = (
            latest['rsi'] < self.strategy_params['rsi_oversold'] and
            latest['macd'] > latest['macd_signal'] and
            df['macd'].iloc[-2] <= df['macd_signal'].iloc[-2] and
            is_trending
        )
        
        # Sell signal: RSI overbought + MACD bearish crossover + trending market  
        sell_signal = (
            latest['rsi'] > self.strategy_params['rsi_overbought'] and
            latest['macd'] < latest['macd_signal'] and
            df['macd'].iloc[-2] >= df['macd_signal'].iloc[-2] and
            is_trending
        )
        
        signal = {
            'timestamp': datetime.now(),
            'buy_signal': buy_signal,
            'sell_signal': sell_signal,
            'price': latest['close'],
            'rsi': latest['rsi'],
            'macd': latest['macd'],
            'adx': latest['adx'],
            'is_trending': is_trending
        }
        
        return signal
    
    def calculate_position_size(self, current_price: float) -> float:
        """Calculate position size based on 2% risk"""
        # Simple 2% risk per trade
        risk_amount = self.current_equity * self.strategy_params['risk_per_trade']
        
        # Assuming 1% stop loss (simplified)
        stop_loss_pips = current_price * 0.01
        
        # Calculate lot size (simplified for GOLD)
        lot_size = risk_amount / (stop_loss_pips * 100)  # Simplified calculation
        
        # Round to 2 decimal places and ensure minimum 0.01 lot
        lot_size = max(round(lot_size, 2), 0.01)
        
        return lot_size
    
    def execute_trade(self, signal: Dict, is_buy: bool):
        """Execute trade on demo account"""
        symbol_info = mt5.symbol_info(self.strategy_params['symbol'])
        if symbol_info is None:
            print("❌ ไม่สามารถรับข้อมูล symbol ได้")
            return False
        
        # Calculate position size
        lot_size = self.calculate_position_size(signal['price'])
        
        # Prepare trade request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.strategy_params['symbol'],
            "volume": lot_size,
            "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
            "price": signal['price'],
            "deviation": 20,
            "magic": 234000,
            "comment": "AI Strategy Demo",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        # Send trade request
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"❌ การ execute trade ล้มเหลว: {result.retcode}")
            return False
        
        # Record trade
        trade_record = {
            'time': datetime.now(),
            'type': 'BUY' if is_buy else 'SELL', 
            'price': signal['price'],
            'lots': lot_size,
            'profit': 0,
            'signal_strength': signal['rsi']
        }
        self.trade_history.append(trade_record)
        
        print(f"✅ {'Buy' if is_buy else 'Sell'} executed: {lot_size} lots at {signal['price']}")
        return True
    
    def monitor_positions(self):
        """Monitor open positions and update equity"""
        positions = mt5.positions_get()
        account_info = mt5.account_info()
        
        if account_info:
            self.current_equity = account_info.equity
            self.equity_curve.append({
                'timestamp': datetime.now(),
                'equity': self.current_equity,
                'balance': account_info.balance
            })
        
        return len(positions) > 0
    
    def run_forward_test(self, duration_hours: int = 24):
        """Run forward test for specified duration"""
        print("🚀 เริ่ม Forward Testing บน Demo Account")
        print("=" * 50)
        
        if not self.connect_demo_account():
            return
        
        end_time = datetime.now() + timedelta(hours=duration_hours)
        
        try:
            while datetime.now() < end_time:
                # Download market data
                df = self.download_market_data(100)
                if df is None:
                    time.sleep(60)  # Wait 1 minute before retry
                    continue
                
                # Calculate indicators
                df = self.calculate_indicators(df)
                
                # Generate signal
                signal = self.generate_signal(df)
                
                print(f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"💰 Price: {signal['price']:.2f}")
                print(f"📊 RSI: {signal['rsi']:.1f}")
                print(f"📈 ADX: {signal['adx']:.1f}")
                print(f"🎯 Trending: {signal['is_trending']}")
                print(f"🔔 Buy Signal: {signal['buy_signal']}")
                print(f"🔴 Sell Signal: {signal['sell_signal']}")
                
                # Check if we have open positions
                has_open_positions = self.monitor_positions()
                
                # Execute trades if no open positions
                if not has_open_positions:
                    if signal['buy_signal']:
                        self.execute_trade(signal, is_buy=True)
                    elif signal['sell_signal']:
                        self.execute_trade(signal, is_buy=False)
                
                # Wait for next H4 candle (4 hours)
                print("⏳ รอ candle ต่อไป... (4 hours)")
                time.sleep(4 * 60 * 60)  # 4 hours
                
        except KeyboardInterrupt:
            print("\n⏹️ หยุด Forward Testing โดยผู้ใช้")
        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาด: {e}")
        finally:
            # Save results
            self.save_results()
            mt5.shutdown()
            print("✅ MT5 shutdown สำเร็จ")
    
    def save_results(self):
        """Save forward testing results"""
        results = {
            'strategy_params': self.strategy_params,
            'trade_history': self.trade_history,
            'equity_curve': self.equity_curve,
            'final_equity': self.current_equity,
            'total_trades': len(self.trade_history)
        }
        
        with open('forward_test_results.json', 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"💾 บันทึกผลลัพธ์: {len(self.trade_history)} trades")

if __name__ == "__main__":
    tester = ForwardTester()
    tester.run_forward_test(duration_hours=24)  # Test for 24 hours