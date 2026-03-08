"""
Live Trading Script for OracleBot-Pro
Executes real trades using MTF-Risk integration
"""

import MetaTrader5 as mt5
from datetime import datetime
import time
from typing import Dict

# Import our trading orchestrator
from mtf_risk_integration import TradingOrchestrator

# Import RiskFirewall for enterprise-grade risk management
from risk_firewall import RiskFirewall

# Import Institutional Execution Gatekeeper for XAUUSD
from execution_gatekeeper_optimized import (
    create_institutional_gatekeeper, 
    GatekeeperDecision
)

from oraclebot_pro_runtime import (
    TelegramNotifier,
    is_market_open_enhanced as runtime_is_market_open_enhanced,
    load_dotenv_file,
    load_trading_config,
)

load_dotenv_file()
CONFIG: Dict = load_trading_config()
TELEGRAM = TelegramNotifier.from_env_and_config(CONFIG)


def is_market_open_enhanced(symbol: str = "GOLD") -> bool:
    return runtime_is_market_open_enhanced(symbol)

# RiskFirewall Configuration - Enterprise-grade risk management
RISK_FIREWALL = None

# Institutional Execution Gatekeeper for XAUUSD
EXECUTION_GATEKEEPER = None

def initialize_mt5() -> bool:
    """Initialize MT5 connection for live trading"""
    print("🔗 Initializing MT5 for Live Trading...")
    
    # Try to initialize MT5
    if not mt5.initialize():
        print("❌ MT5 Initialize failed")
        print("   Error:", mt5.last_error())
        return False
    
    print("✅ MT5 initialized successfully")
    
    # Try to login with any available account
    mt5.login()
    
    # Get account info regardless of login status
    account_info = mt5.account_info()
    
    if account_info is not None:
        print("✅ Connected to MT5 Account Successfully")
        print(f"   Account: {account_info.login}")
        print(f"   Balance: ${account_info.balance:.2f}")
        print(f"   Equity: ${account_info.equity:.2f}")
        print(f"   Broker: {account_info.server}")
        print(f"   Trade Allowed: {account_info.trade_allowed}")
        print(f"   Trade Expert: {account_info.trade_expert}")
        
        # Initialize RiskFirewall after successful MT5 connection
        global RISK_FIREWALL
        RISK_FIREWALL = RiskFirewall(
            max_open_trades=4,                    # Maximum 4 concurrent positions
            max_risk_usd=200.0,                  # $200 maximum risk per trade
            min_distance_points=50                # 50 points minimum distance
        )
        print("✅ RiskFirewall initialized successfully")
        
        # Initialize Institutional Execution Gatekeeper for XAUUSD
        global EXECUTION_GATEKEEPER
        EXECUTION_GATEKEEPER = create_institutional_gatekeeper()
        print("✅ Institutional Execution Gatekeeper initialized successfully")
        
        return True
    else:
        print("⚠️  Cannot get account info")
        print("   Error:", mt5.last_error())
        
        # Check if we can get market data (demo mode)
        try:
            rates = mt5.copy_rates_from_pos("GOLD", mt5.TIMEFRAME_M5, 0, 1)
            if rates is not None:
                print("✅ Market data accessible (demo mode)")
                return True
            else:
                print("❌ Cannot access market data")
                print("   Error:", mt5.last_error())
                return False
        except Exception as e:
            print(f"❌ Market data error: {e}")
            return False

def send_telegram_message(message: str) -> bool:
    return TELEGRAM.send_html(message)


def send_system_startup_notification():
    """Send intelligent system startup notification"""
    try:
        # Get current market state
        rates = mt5.copy_rates_from_pos("GOLD", mt5.TIMEFRAME_M5, 0, 1)
        if rates is not None:
            current_price = rates[0]['close']
            
            message = (
                f"🎯 <b>OracleBot LIVE TRADING STARTED</b>\n\n"
                f"📊 <b>System Status:</b> Online and Monitoring\n"
                f"💰 <b>Current GOLD:</b> {current_price:.2f}\n"
                f"⚡ <b>Strategy:</b> MTF Confluence + RiskFirewall\n"
                f"🎯 <b>Target:</b> GOLD Only | Confluence ≥ 20.0\n\n"
                f"<i>📈 ระบบพร้อมทำงานอัตโนมัติ จะแจ้งเตือนเมื่อมีสัญญาณเทรด\n"
                f"⚠️  ตรวจสอบตลาดทุก 30 วินาที สำหรับสัญญาณเทรด</i>"
            )
            send_telegram_message(message)
    except Exception as e:
        print(f"❌ Startup notification error: {e}")


def send_intelligent_trade_notification(decision: Dict, result, stop_loss: float, take_profit: float):
    """Send intelligent mentor-style trade notification"""
    try:
        symbol = decision['symbol']
        trade_type = decision['trade_type']
        
        # Thai/English mixed intelligent message
        direction_th = "LONG" if trade_type == mt5.ORDER_TYPE_BUY else "SHORT"
        reason_th = decision.get('reason', 'MTF Confluence')
        
        # Market context analysis
        market_context = ""
        if decision['confluence_score'] >= 60:
            market_context = "📈 <b>Strong Signal</b> - Multiple timeframe alignment"
        elif decision['confluence_score'] >= 40:
            market_context = "📊 <b>Good Signal</b> - Favorable market conditions"
        else:
            market_context = "⚠️  <b>Moderate Signal</b> - Lower confluence but valid setup"
        
        # Risk assessment
        risk_assessment = ""
        risk_percent = decision['risk_percentage']
        if risk_percent <= 1.0:
            risk_assessment = "✅ <b>Risk Level:</b> Conservative (≤1%)"
        elif risk_percent <= 2.0:
            risk_assessment = "⚠️  <b>Risk Level:</b> Moderate (1-2%)"
        else:
            risk_assessment = "🔴 <b>Risk Level:</b> Aggressive (>2%)"
        
        # Price action context
        price_context = ""
        if 'current_price' in decision:
            price_move = abs(decision['current_price'] - decision.get('previous_price', decision['current_price']))
            if price_move > 50:
                price_context = "⚡ <b>Price Action:</b> High volatility - manage position carefully"
            else:
                price_context = "📉 <b>Price Action:</b> Normal volatility - standard management"
        
        message = (
            f"🚀 <b>NEW TRADE ENTRY - {direction_th}</b>\n\n"
            f"📊 <b>Symbol:</b> {symbol}\n"
            f"🎯 <b>Direction:</b> {trade_type}\n"
            f"💰 <b>Entry Price:</b> {result.price:.2f}\n"
            f"🛑 <b>Stop Loss:</b> {stop_loss:.2f}\n"
            f"🎯 <b>Take Profit:</b> {take_profit:.2f}\n"
            f"📦 <b>Size:</b> {result.volume:.2f} lots\n"
            f"⚠️  <b>Risk Amount:</b> ${decision['risk_amount']:.2f} ({risk_percent:.1f}%)\n\n"
            f"📈 <b>Confluence Score:</b> {decision['confluence_score']:.1f}/100\n"
            f"🔍 <b>Reason:</b> {reason_th}\n\n"
            f"{market_context}\n"
            f"{risk_assessment}\n"
            f"{price_context}\n\n"
            f"<i>💡 <b>เพราะอะไรถึงเทรด:</b> {reason_th}\n"
            f"📊 สัญญาณจาก multiple timeframe confluence\n"
            f"⚠️  <b>ระวัง:</b> หากราคาแตะ {stop_loss:.2f} จะตัด loss อัตโนมัติ\n"
            f"🎯 <b>เป้าหมาย:</b> {take_profit:.2f} (+{(take_profit - result.price):.1f} points)</i>\n\n"
            f"🆔 <b>Order ID:</b> {result.order}"
        )
        
        send_telegram_message(message)
        
    except Exception as e:
        print(f"❌ Intelligent notification error: {e}")
        # Fallback to basic notification
        basic_message = (
            f"🚀 NEW TRADE\n"
            f"Symbol: {decision['symbol']}\n"
            f"Type: {decision['trade_type']}\n"
            f"Price: {result.price:.2f}\n"
            f"Size: {result.volume:.2f} lots\n"
            f"Order ID: {result.order}"
        )
        send_telegram_message(basic_message)

def execute_real_trade(decision: Dict) -> bool:
    """Execute real trade on MT5"""
    if not decision['trade_recommended']:
        return False
    
    symbol = decision['symbol']
    trade_type = decision['trade_type']
    volume = decision['position_size']
    price = decision['current_price']
    stop_loss = decision['stop_loss_price']
    take_profit = decision['take_profit_price']
    
    print("\n🎯 EXECUTING REAL TRADE:")
    print(f"   Symbol: {symbol}")
    print(f"   Type: {trade_type}")
    print(f"   Volume: {volume:.2f} lots")
    print(f"   Price: {price:.2f}")
    print(f"   Stop Loss: {stop_loss:.2f}")
    print(f"   Take Profit: {take_profit:.2f}")
    print(f"   Risk: ${decision['risk_amount']:.2f} ({decision['risk_percentage']:.1f}%)")
    
    # 🔒 RISK ASSESSMENT - Enterprise-grade risk management
    print("\n🔒 Performing Risk Assessment...")
    
    # Convert trade type to MT5 order type
    order_type = mt5.ORDER_TYPE_BUY if trade_type == 'BUY' else mt5.ORDER_TYPE_SELL
    
    # Use RiskFirewall's validate_signal to get proper lot size and validation
    validation = RISK_FIREWALL.validate_signal(
        symbol=symbol,
        order_type=order_type,
        entry_price=price,
        sl_price=stop_loss
    )
    
    # Check if trade is valid and get the safe lot size
    if not validation["is_valid"]:
        print("❌ TRADE REJECTED BY RISK FIREWALL")
        print(f"   Reason: {validation['reason']}")
        return False
        
    # Use the safe lot size calculated by RiskFirewall
    volume = validation["lot_size"]
    print(f"✅ RiskFirewall approved trade with lot size: {volume:.2f} lots")

    # 🔒 INSTITUTIONAL EXECUTION GATEKEEPER VALIDATION
    print("\n🔒 Performing Institutional Execution Validation...")
    
    # Validate with institutional execution gatekeeper
    gatekeeper_decision, gatekeeper_reason = EXECUTION_GATEKEEPER.validate_execution(
        symbol=symbol,
        order_type=order_type,
        entry_price=price
    )
    
    if gatekeeper_decision != GatekeeperDecision.APPROVED:
        print("❌ TRADE REJECTED BY INSTITUTIONAL EXECUTION GATEKEEPER")
        print(f"   Decision: {gatekeeper_decision.value}")
        print(f"   Reason: {gatekeeper_reason}")
        return False
        
    print("✅ Institutional Execution Gatekeeper approved trade")

    # Risk assessment is already done by validate_signal above
    # Prepare trade request
    
    # Prepare trade request
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_BUY if trade_type == 'BUY' else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": stop_loss,
        "tp": take_profit,
        "deviation": 20,
        "magic": 234000,
        "comment": "OracleBot-Pro Live Trade",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    # Send order
    result = mt5.order_send(request)
    
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        error_code = result.retcode if result else "No result"
        error_msg = mt5.last_error()
        
        print(f"❌ Trade execution failed: {error_code}")
        print(f"   Error: {error_msg}")
        
        # Send Telegram alert for failed trade
        telegram_error = f"❌ TRADE FAILED\nSymbol: {symbol}\nType: {trade_type}\nError Code: {error_code}\nError: {error_msg}"
        send_telegram_message(telegram_error)
        
        return False
    else:
        print("✅ Trade executed successfully!")
        print(f"   Order ID: {result.order}")
        print(f"   Volume: {result.volume:.2f} lots")
        print(f"   Price: {result.price:.2f}")
        print(f"   Order ID: {result.order}")
        
        # Send intelligent Telegram notification
        send_intelligent_trade_notification(decision, result, stop_loss, take_profit)
        return True

def monitor_open_positions():
    """Monitor currently open positions"""
    positions = mt5.positions_get()
    
    if positions is None:
        print("❌ No positions or error getting positions")
        return []
    
    print(f"\n📊 Open Positions: {len(positions)}")
    
    total_profit = 0
    for pos in positions:
        profit_pct = (pos.profit / (pos.volume * pos.price_open * 100)) * 100 if pos.volume > 0 else 0
        print(f"   {pos.symbol} {pos.type} {pos.volume:.2f} lots: ${pos.profit:.2f} ({profit_pct:.1f}%)")
        total_profit += pos.profit
    
    print(f"   Total Profit: ${total_profit:.2f}")
    return positions

def live_trading_loop():
    """Main live trading loop"""
    print("🚀 STARTING LIVE TRADING")
    print("=" * 60)
    
    # Initialize MT5
    if not initialize_mt5():
        print("❌ Cannot start live trading - MT5 connection failed")
        return
    
    # Send system startup notification
    send_system_startup_notification()
    
    # Create trading orchestrator with actual account balance
    account_info = mt5.account_info()
    initial_capital = account_info.balance
    
    orchestrator = TradingOrchestrator(initial_capital)
    
    print(f"💰 Starting Capital: ${initial_capital:.2f}")
    print(f"🎯 Confluence Threshold: {orchestrator.confluence_threshold}/100")
    print("⏰ Trading interval: 30 seconds")
    print("📊 Timeframes: M5, M15, H1, H4, D1")
    print("=" * 60)
    
    # Main trading loop
    cycle_count = 0
    while True:
        cycle_count += 1
        print(f"\n📈 TRADING CYCLE {cycle_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 50)
        
        try:
            # Step 0: Enhanced Market Open Check
            if not is_market_open_enhanced("GOLD"):
                print("⏸ Market closed or internet issue - waiting 5 minutes")
                time.sleep(300)  # Wait 5 minutes
                continue
            
            # Step 1: Market Analysis & Decision
            confluence = orchestrator.analyze_market("GOLD")
            if not confluence:
                print("❌ Market analysis failed, skipping cycle")
                time.sleep(900)  # Wait 15 minutes
                continue
            
            # Get current price
            rates = mt5.copy_rates_from_pos("GOLD", mt5.TIMEFRAME_M1, 0, 1)
            if rates is None or len(rates) == 0:
                print("❌ Cannot get current price")
                time.sleep(900)
                continue
            
            current_price = rates[0]['close']
            
            # Step 2: Generate Trading Decision
            decision = orchestrator.generate_trading_decision(confluence, current_price)
            
            # Step 3: Display Decision
            orchestrator.display_decision(decision)
            
            # Step 4: Execute Real Trade if recommended
            if decision is not None and decision['trade_recommended']:
                trade_success = execute_real_trade(decision)
                
                if trade_success:
                    # Update risk manager with new equity
                    account_info = mt5.account_info()
                    orchestrator.risk_manager.update_equity(account_info.equity)
            
            # Step 5: Monitor current positions
            monitor_open_positions()
            
            # Step 6: Risk Report
            risk_report = orchestrator.risk_manager.get_risk_report()
            print("\n📊 Risk Report:")
            for key, value in risk_report.items():
                print(f"   {key}: {value}")
            
            # Wait for next cycle (30 seconds)
            print("\n⏳ Waiting 30 seconds for next analysis...")
            time.sleep(30)
            
        except KeyboardInterrupt:
            print("\n🛑 Live trading stopped by user")
            break
        except Exception as e:
            print(f"❌ Error in trading cycle: {e}")
            print("🔄 Retrying in 5 minutes...")
            time.sleep(300)

def main():
    """Main function"""
    print("OracleBot-Pro Live Trading System")
    print("=" * 50)
    print("This script will execute REAL trades on your MT5 account")
    print("Ensure you understand the risks before continuing!")
    print()
    
    # Warning confirmation - auto confirm if 'yes' provided as argument
    import sys
    if len(sys.argv) > 1 and sys.argv[1].lower() == 'yes':
        print("✅ Auto-confirmed live trading (yes parameter provided)")
        confirm = 'yes'
    else:
        confirm = input("⚠️  Do you want to continue with LIVE TRADING? (yes/no): ")
    
    if confirm.lower() != 'yes':
        print("🛑 Live trading cancelled")
        return
    
    try:
        live_trading_loop()
    finally:
        # Cleanup
        mt5.shutdown()
        print("✅ MT5 connection closed")

if __name__ == "__main__":
    main()
