"""
Integration between Multi-Timeframe Analyzer and Risk Management
Combines market confluence analysis with advanced risk management
"""

import MetaTrader5 as mt5
from datetime import datetime
from typing import Dict

# Import our modules
from mtf_analyzer import MultiTimeframeAnalyzer
from risk_management import RiskManager, RiskParameters

class TradingOrchestrator:
    def __init__(self, initial_capital: float = 10000):
        self.mtf_analyzer = MultiTimeframeAnalyzer()
        self.risk_manager = RiskManager(initial_capital)
        self.confluence_threshold = 35.0  # Strong signal threshold (35-60 confidence range)
        self.openclaw_integration = False  # Flag for OpenClaw integration
        
        # Enhanced risk parameters based on confluence
        self.confluence_risk_map = {
            'STRONG': RiskParameters(risk_per_trade=0.03, max_drawdown=0.12),
            'MODERATE': RiskParameters(risk_per_trade=0.02, max_drawdown=0.15), 
            'WEAK': RiskParameters(risk_per_trade=0.01, max_drawdown=0.18),
            'NONE': RiskParameters(risk_per_trade=0.005, max_drawdown=0.20)
        }
    
    def analyze_market(self, symbol: str) -> Dict:
        """Analyze market using multi-timeframe confluence"""
        print(f"\n🎯 Analyzing {symbol} Market Conditions")
        print("=" * 50)
        
        confluence = self.mtf_analyzer.get_mtf_confluence(symbol)
        
        if not confluence:
            print("❌ No confluence data available")
            return {}
        
        # Adjust risk based on confluence strength
        self.adjust_risk_parameters(confluence)
        
        return confluence
    
    def adjust_risk_parameters(self, confluence: Dict):
        """Adjust risk parameters based on market confluence"""
        overall_score = confluence.get('overall_score', 0)
        recommendation = confluence.get('recommendation', '')
        
        # Determine risk profile based on confluence strength
        if overall_score >= 70:
            risk_profile = 'STRONG'
        elif overall_score >= 50:
            risk_profile = 'MODERATE'
        elif overall_score >= 30:
            risk_profile = 'WEAK'
        else:
            risk_profile = 'NONE'
        
        # Update risk parameters
        new_params = self.confluence_risk_map[risk_profile]
        self.risk_manager.parameters = new_params
        
        print("⚖️  Adjusted Risk Parameters:")
        print(f"   Profile: {risk_profile} (Score: {overall_score:.1f}/100)")
        print(f"   Risk per Trade: {new_params.risk_per_trade:.3%}")
        print(f"   Max Drawdown: {new_params.max_drawdown:.2%}")
        print(f"   Recommendation: {recommendation}")
    
    def generate_trading_decision(self, confluence: Dict, current_price: float) -> Dict:
        """Generate trading decision based on confluence and risk"""
        overall_score = confluence.get('overall_score', 0)
        direction = confluence.get('overall_direction', '')
        
        decision = {
            'timestamp': datetime.now().isoformat(),
            'symbol': 'GOLD',
            'direction': direction,
            'confluence_score': overall_score,
            'current_price': current_price,
            'trade_recommended': False,
            'reason': 'Insufficient confluence',
            'risk_profile': 'NONE',
            'openclaw_ready': False,
            'entry_price': None,
            'stop_loss': None,
            'take_profit': None
        }
        
        # Check if trading is allowed by risk manager
        if not self.risk_manager.check_trading_allowed():
            decision['reason'] = 'Trading not allowed by risk rules'
            return decision
            
        # Check confluence threshold
        if overall_score < self.confluence_threshold:
            decision['reason'] = f'Confluence score {overall_score:.1f} below threshold {self.confluence_threshold}'
            return decision
            
        # Determine position size if trade is recommended
        if direction in ['BULLISH', 'BEARISH']:
            # Calculate stop loss based on volatility
            if direction == 'BULLISH':
                stop_loss_price = current_price * (1 - self.risk_manager.parameters.stop_loss_pct)
                trade_type = 'BUY'
            else:
                stop_loss_price = current_price * (1 + self.risk_manager.parameters.stop_loss_pct) 
                trade_type = 'SELL'
            
            # Calculate position size
            position_size, risk_metrics = self.risk_manager.calculate_position_size(
                current_price, stop_loss_price
            )
            
            decision.update({
                'trade_recommended': True,
                'trade_type': trade_type,
                'position_size': position_size,
                'stop_loss_price': stop_loss_price,
                'take_profit_price': current_price * (1 + self.risk_manager.parameters.take_profit_pct) 
                                    if direction == 'BULLISH' else 
                                    current_price * (1 - self.risk_manager.parameters.take_profit_pct),
                'risk_amount': risk_metrics['risk_amount'],
                'risk_percentage': risk_metrics['risk_percentage'],
                'reason': f'Strong {direction.lower()} confluence ({overall_score:.1f}/100)',
                'risk_profile': 'MODERATE' if overall_score >= 50 else 'WEAK'
            })
        
        return decision
    
    def enable_openclaw_integration(self):
        """Enable OpenClaw integration mode"""
        self.openclaw_integration = True
        print("✅ OpenClaw Integration Enabled")
        print("   System will wait for OpenClaw's final entry/stop/take-profit numbers")
    
    def update_with_openclaw_decision(self, decision: Dict, openclaw_data: Dict):
        """Update trading decision with final numbers from OpenClaw"""
        if not self.openclaw_integration:
            return decision
            
        # Update with OpenClaw's final numbers
        decision.update({
            'openclaw_ready': True,
            'entry_price': openclaw_data.get('entry_price', decision['current_price']),
            'stop_loss': openclaw_data.get('stop_loss'),
            'take_profit': openclaw_data.get('take_profit'),
            'openclaw_confidence': openclaw_data.get('confidence', 0.0),
            'final_risk_percentage': openclaw_data.get('risk_percentage', decision.get('risk_percentage', 0))
        })
        
        print("🎯 OpenClaw Final Decision:")
        print(f"   Entry: {decision['entry_price']:.2f}")
        print(f"   Stop Loss: {decision['stop_loss']:.2f}")
        print(f"   Take Profit: {decision['take_profit']:.2f}")
        print(f"   Confidence: {decision['openclaw_confidence']:.1%}")
        
        return decision
    
    def execute_trading_cycle(self, symbol: str = "GOLD"):
        """Complete trading cycle: Analyze -> Decide -> Execute"""
        print(f"\n🚀 Starting Trading Cycle for {symbol}")
        print("=" * 60)
        
        # Step 1: Market Analysis
        confluence = self.analyze_market(symbol)
        if not confluence:
            print("❌ Market analysis failed")
            return
        
        # Get current market price
        current_price = self.get_current_price(symbol)
        if current_price is None:
            print("❌ Cannot get current price")
            return
        
        # Step 2: Generate Trading Decision
        decision = self.generate_trading_decision(confluence, current_price)
        
        # Step 3: Display Decision
        self.display_decision(decision)
        
        # Step 4: Execute if recommended
        if decision is None:
            return
            
        if decision['trade_recommended']:
            self.execute_trade(decision)
        
        # Step 5: Update risk metrics
        risk_report = self.risk_manager.get_risk_report()
        print("\n📊 Risk Report:")
        for key, value in risk_report.items():
            print(f"   {key}: {value}")
    
    def get_current_price(self, symbol: str) -> float:
        """Get current market price"""
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 1)
        if rates is not None and len(rates) > 0:
            return rates[0]['close']
        return None
    
    def display_decision(self, decision: Dict):
        """Display trading decision"""
        print("\n🎯 TRADING DECISION")
        print("-" * 40)
        
        if decision is None:
            print("❌ No decision data available")
            return
            
        if decision['trade_recommended']:
            print(f"✅ {decision['trade_type']} RECOMMENDED")
            print(f"   Price: {decision['current_price']:.2f}")
            print(f"   Size: {decision['position_size']:.2f} lots")
            print(f"   Stop Loss: {decision['stop_loss_price']:.2f}")
            print(f"   Take Profit: {decision['take_profit_price']:.2f}")
            print(f"   Risk Amount: ${decision['risk_amount']:.2f}")
            print(f"   Risk Percentage: {decision['risk_percentage']:.1f}%")
        else:
            print("⏸️  NO TRADE")
            print(f"   Reason: {decision['reason']}")
            print(f"   Confluence Score: {decision['confluence_score']:.1f}/100")
    
    def execute_trade(self, decision: Dict):
        """Execute trade (simulated for now)"""
        print("\n🔧 SIMULATED EXECUTION:")
        print(f"   Would execute {decision['trade_type']} {decision['position_size']:.2f} lots")
        print(f"   Entry: {decision['current_price']:.2f}")
        print(f"   Stop: {decision['stop_loss_price']:.2f}")
        print(f"   Target: {decision['take_profit_price']:.2f}")
        
        # In real implementation, this would send order to MT5
        # For now, we'll simulate the trade outcome
        self.simulate_trade_outcome(decision)
    
    def simulate_trade_outcome(self, decision: Dict):
        """Simulate trade outcome for testing"""
        # Simple simulation - 60% win rate
        import random
        
        is_win = random.random() < 0.6
        
        if is_win:
            # Win: reach take profit
            profit = abs(decision['take_profit_price'] - decision['current_price']) * decision['position_size'] * 100
            print(f"   ✅ SIMULATED WIN: +${profit:.2f}")
        else:
            # Loss: hit stop loss
            loss = abs(decision['stop_loss_price'] - decision['current_price']) * decision['position_size'] * 100
            print(f"   ❌ SIMULATED LOSS: -${loss:.2f}")
            
        # Update risk manager (simulated equity change)
        current_equity = self.risk_manager.current_equity
        new_equity = current_equity + (profit if is_win else -loss)
        self.risk_manager.update_equity(new_equity)
        
        # Record trade
        trade_record = {
            'time': datetime.now(),
            'type': decision['trade_type'],
            'size': decision['position_size'],
            'entry_price': decision['current_price'],
            'exit_price': decision['take_profit_price'] if is_win else decision['stop_loss_price'],
            'profit': profit if is_win else -loss,
            'win': is_win
        }
        self.risk_manager.record_trade(trade_record)

# Example usage
if __name__ == "__main__":
    # Initialize MT5
    if not mt5.initialize():
        print("❌ MT5 Initialize failed")
    else:
        # Create trading orchestrator
        orchestrator = TradingOrchestrator(initial_capital=10000)
        
        # Run trading cycle
        orchestrator.execute_trading_cycle("GOLD")
        
        # Run additional cycles for testing
        print("\n" + "="*60)
        print("🔄 Running additional test cycles...")
        print("="*60)
        
        for i in range(2):  # Run 2 more cycles
            print(f"\n📈 Cycle {i+2}:")
            orchestrator.execute_trading_cycle("GOLD")
        
        mt5.shutdown()
        print("\n✅ Trading simulation completed")
