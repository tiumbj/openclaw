"""
Risk Management Module for OracleBot-Pro
Implements advanced risk management features
"""

import numpy as np
from typing import Dict, List, Tuple
from oraclebot_pro_runtime import RiskParameters

class RiskManager:
    def __init__(self, initial_capital: float = 10000):
        self.initial_capital = initial_capital
        self.current_equity = initial_capital
        self.peak_equity = initial_capital
        self.consecutive_losses = 0
        self.trade_history = []
        self.parameters = RiskParameters()
    
    def calculate_position_size(self, current_price: float, stop_loss_price: float) -> Tuple[float, Dict]:
        """Calculate position size with risk management"""
        
        # Calculate risk amount based on 2% rule
        risk_amount = self.current_equity * self.parameters.risk_per_trade
        
        # Calculate stop loss in pips/points
        if current_price > stop_loss_price:
            # Long position - stop loss below entry
            risk_per_unit = current_price - stop_loss_price
        else:
            # Short position - stop loss above entry  
            risk_per_unit = stop_loss_price - current_price
        
        # Avoid division by zero
        if risk_per_unit <= 0:
            risk_per_unit = current_price * self.parameters.stop_loss_pct
        
        # Calculate position size
        position_size = risk_amount / risk_per_unit
        
        # Apply maximum position size constraint
        max_size = self.current_equity * self.parameters.max_position_size / current_price
        position_size = min(position_size, max_size)
        
        # For GOLD, round to 2 decimal places (0.01 lot minimum)
        position_size = max(round(position_size, 2), 0.01)
        
        risk_metrics = {
            'risk_amount': risk_amount,
            'risk_per_unit': risk_per_unit,
            'position_size': position_size,
            'risk_percentage': self.parameters.risk_per_trade * 100,
            'max_position_size': max_size
        }
        
        return position_size, risk_metrics
    
    def check_drawdown_limits(self) -> bool:
        """Check if current drawdown exceeds limits"""
        drawdown = (self.peak_equity - self.current_equity) / self.peak_equity
        
        if drawdown > self.parameters.max_drawdown:
            print(f"🚫 Drawdown limit exceeded: {drawdown:.2%} > {self.parameters.max_drawdown:.2%}")
            return False
        return True
    
    def check_volatility_limits(self, recent_returns: List[float]) -> bool:
        """Check volatility limits"""
        if len(recent_returns) < 5:
            return True
            
        volatility = np.std(recent_returns)
        if volatility > self.parameters.volatility_threshold:
            print(f"⚠️  High volatility detected: {volatility:.3%} > {self.parameters.volatility_threshold:.3%}")
            return False
        return True
    
    def update_equity(self, new_equity: float):
        """Update equity and track peak"""
        self.current_equity = new_equity
        self.peak_equity = max(self.peak_equity, new_equity)
    
    def record_trade(self, trade_result: Dict):
        """Record trade result and update consecutive losses"""
        self.trade_history.append(trade_result)
        
        if trade_result['profit'] < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
    
    def check_trading_allowed(self) -> bool:
        """Check if trading is allowed based on risk rules"""
        
        # Check drawdown limits
        if not self.check_drawdown_limits():
            return False
        
        # Check consecutive losses
        if self.consecutive_losses >= self.parameters.max_consecutive_losses:
            print(f"🚫 Maximum consecutive losses reached: {self.consecutive_losses}")
            return False
        
        # Check if equity is sufficient
        min_trade_size = self.current_equity * self.parameters.risk_per_trade
        if min_trade_size < 10:  # Minimum $10 risk amount
            print(f"⚠️  Equity too low for trading: ${self.current_equity:.2f}")
            return False
        
        return True
    
    def get_risk_report(self) -> Dict:
        """Generate risk management report"""
        drawdown = (self.peak_equity - self.current_equity) / self.peak_equity if self.peak_equity > 0 else 0
        
        return {
            'current_equity': self.current_equity,
            'peak_equity': self.peak_equity,
            'drawdown_pct': drawdown * 100,
            'consecutive_losses': self.consecutive_losses,
            'total_trades': len(self.trade_history),
            'winning_trades': sum(1 for t in self.trade_history if t['profit'] > 0),
            'max_drawdown_limit': self.parameters.max_drawdown * 100,
            'risk_per_trade': self.parameters.risk_per_trade * 100
        }
    
    def auto_adjust_risk(self, recent_performance: Dict):
        """Automatically adjust risk parameters based on performance"""
        
        # Reduce risk after losses
        if self.consecutive_losses > 0:
            risk_reduction = 1.0 / (1.0 + self.consecutive_losses)
            new_risk = self.parameters.risk_per_trade * risk_reduction
            self.parameters.risk_per_trade = max(new_risk, 0.005)  # Minimum 0.5%
            print(f"🔻 Reduced risk to {self.parameters.risk_per_trade:.3%} after {self.consecutive_losses} losses")
        
        # Increase risk after winning streak
        winning_streak = 0
        for trade in reversed(self.trade_history):
            if trade['profit'] > 0:
                winning_streak += 1
            else:
                break
        
        if winning_streak >= 3:
            risk_increase = min(1.0 + (winning_streak * 0.1), 1.5)  # Max 50% increase
            new_risk = self.parameters.risk_per_trade * risk_increase
            self.parameters.risk_per_trade = min(new_risk, 0.05)  # Maximum 5%
            print(f"🔺 Increased risk to {self.parameters.risk_per_trade:.3%} after {winning_streak} wins")

# Example usage
if __name__ == "__main__":
    # Initialize risk manager
    risk_mgr = RiskManager(initial_capital=10000)
    
    # Simulate some trades
    risk_mgr.update_equity(10500)  # Profit of $500
    
    # Calculate position size for a trade
    current_price = 5400.0
    stop_loss = 5340.0  # 60 points stop loss
    
    position_size, metrics = risk_mgr.calculate_position_size(current_price, stop_loss)
    print(f"Position Size: {position_size:.2f} lots")
    print(f"Risk Amount: ${metrics['risk_amount']:.2f}")
    print(f"Risk per Unit: {metrics['risk_per_unit']:.2f}")
    
    # Generate risk report
    report = risk_mgr.get_risk_report()
    print("\nRisk Report:")
    for key, value in report.items():
        print(f"{key}: {value}")
