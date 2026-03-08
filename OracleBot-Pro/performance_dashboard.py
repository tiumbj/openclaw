"""
Real-time Performance Dashboard for OracleBot-Pro
Monitors trading performance and system metrics
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import json
import time
from typing import Dict
import threading

class PerformanceDashboard:
    def __init__(self):
        self.metrics = {
            'equity': [],
            'drawdown': [],
            'trades': [],
            'win_rate': [],
            'sharpe_ratio': [],
            'timestamp': []
        }
        self.live_mode = False
        self.update_interval = 60  # seconds
        
    def load_results(self, results_file: str = 'forward_test_results.json'):
        """Load results from forward testing"""
        try:
            with open(results_file, 'r') as f:
                results = json.load(f)
            
            # Process trade history
            for trade in results.get('trade_history', []):
                self.metrics['trades'].append(trade)
            
            # Process equity curve
            for equity_point in results.get('equity_curve', []):
                if isinstance(equity_point, dict):
                    self.metrics['equity'].append(equity_point.get('equity', 0))
                    self.metrics['timestamp'].append(
                        datetime.fromisoformat(equity_point.get('timestamp')) 
                        if 'timestamp' in equity_point else datetime.now()
                    )
                else:
                    self.metrics['equity'].append(equity_point)
                    self.metrics['timestamp'].append(datetime.now())
            
            print(f"✅ Loaded {len(self.metrics['trades'])} trades and {len(self.metrics['equity'])} equity points")
            
        except FileNotFoundError:
            print("⚠️  No results file found - starting fresh")
        except Exception as e:
            print(f"❌ Error loading results: {e}")
    
    def calculate_metrics(self) -> Dict:
        """Calculate performance metrics"""
        if not self.metrics['trades']:
            return {}
        
        trades_df = pd.DataFrame(self.metrics['trades'])
        
        # Basic metrics
        total_trades = len(trades_df)
        winning_trades = len(trades_df[trades_df['profit'] > 0]) if 'profit' in trades_df.columns else 0
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # Equity metrics
        equity_series = pd.Series(self.metrics['equity'])
        peak_equity = equity_series.cummax()
        drawdown = (equity_series - peak_equity) / peak_equity * 100
        max_drawdown = drawdown.min() if not drawdown.empty else 0
        
        # Calculate returns for Sharpe ratio
        returns = equity_series.pct_change().dropna()
        sharpe_ratio = (returns.mean() / returns.std() * np.sqrt(252)) if len(returns) > 1 and returns.std() > 0 else 0
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'win_rate': win_rate,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'current_equity': equity_series.iloc[-1] if not equity_series.empty else 0,
            'peak_equity': peak_equity.iloc[-1] if not peak_equity.empty else 0
        }
    
    def update_metrics(self, new_equity: float, new_trade: Dict | None = None):
        """Update metrics with new data"""
        self.metrics['equity'].append(new_equity)
        self.metrics['timestamp'].append(datetime.now())
        
        if new_trade:
            self.metrics['trades'].append(new_trade)
        
        # Keep only last 1000 data points
        for key in self.metrics:
            if len(self.metrics[key]) > 1000:
                self.metrics[key] = self.metrics[key][-1000:]
    
    def generate_report(self) -> str:
        """Generate performance report"""
        metrics = self.calculate_metrics()
        
        if not metrics:
            return "No trading data available"
        
        report = f"""
📊 PERFORMANCE DASHBOARD - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{'='*60}

💰 Equity Metrics:
  Current Equity: ${metrics['current_equity']:,.2f}
  Peak Equity:    ${metrics['peak_equity']:,.2f}
  Max Drawdown:   {metrics['max_drawdown']:.2f}%

🎯 Trading Performance:
  Total Trades:   {metrics['total_trades']}
  Winning Trades: {metrics['winning_trades']}
  Win Rate:       {metrics['win_rate']:.1f}%
  Sharpe Ratio:   {metrics['sharpe_ratio']:.2f}

📈 System Status:
  Live Mode:      {'✅ ACTIVE' if self.live_mode else '⏸️ PAUSED'}
  Data Points:   {len(self.metrics['equity'])}
  Last Update:   {datetime.now().strftime('%H:%M:%S')}
"""
        
        return report
    
    def plot_equity_curve(self):
        """Plot equity curve"""
        if len(self.metrics['equity']) < 2:
            print("⚠️  Not enough data to plot")
            return
        
        plt.figure(figsize=(12, 6))
        
        # Create time index if timestamps are available
        if self.metrics['timestamp'] and len(self.metrics['timestamp']) == len(self.metrics['equity']):
            time_index = self.metrics['timestamp']
        else:
            time_index = range(len(self.metrics['equity']))
        
        plt.plot(time_index, self.metrics['equity'], label='Equity', linewidth=2)
        
        # Calculate and plot drawdown
        equity_series = pd.Series(self.metrics['equity'])
        peak_equity = equity_series.cummax()
        
        plt.fill_between(time_index, equity_series, peak_equity, 
                        where=equity_series < peak_equity, 
                        color='red', alpha=0.3, label='Drawdown')
        
        plt.title('Equity Curve & Drawdown')
        plt.xlabel('Time')
        plt.ylabel('Equity ($)')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # Format x-axis if using timestamps
        if isinstance(time_index[0], datetime):
            plt.xticks(rotation=45)
        
        plt.tight_layout()
        plt.show()
    
    def plot_trade_distribution(self):
        """Plot trade distribution"""
        if not self.metrics['trades']:
            print("⚠️  No trades to analyze")
            return
        
        trades_df = pd.DataFrame(self.metrics['trades'])
        
        if 'profit' not in trades_df.columns:
            print("⚠️  No profit data in trades")
            return
        
        plt.figure(figsize=(10, 8))
        
        # Profit distribution
        plt.subplot(2, 2, 1)
        trades_df['profit'].hist(bins=30, alpha=0.7, edgecolor='black')
        plt.title('Profit Distribution')
        plt.xlabel('Profit')
        plt.ylabel('Frequency')
        
        # Win/Loss pie chart
        plt.subplot(2, 2, 2)
        win_loss = trades_df['profit'] > 0
        win_loss.value_counts().plot.pie(autopct='%1.1f%%', 
                                        colors=['red', 'green'],
                                        labels=['Loss', 'Win'])
        plt.title('Win/Loss Ratio')
        
        # Cumulative profit
        plt.subplot(2, 2, 3)
        cumulative_profit = trades_df['profit'].cumsum()
        cumulative_profit.plot()
        plt.title('Cumulative Profit')
        plt.xlabel('Trade Number')
        plt.ylabel('Cumulative Profit')
        
        # Profit by trade size (if lots data available)
        if 'lots' in trades_df.columns:
            plt.subplot(2, 2, 4)
            plt.scatter(trades_df['lots'], trades_df['profit'], alpha=0.6)
            plt.title('Profit vs Trade Size')
            plt.xlabel('Lot Size')
            plt.ylabel('Profit')
        
        plt.tight_layout()
        plt.show()
    
    def start_live_monitoring(self):
        """Start live monitoring thread"""
        self.live_mode = True
        print("🚀 Starting live performance monitoring...")
        
        def monitor_loop():
            while self.live_mode:
                try:
                    # Generate and print report
                    report = self.generate_report()
                    print(report)
                    
                    # Save snapshot every 10 minutes
                    if datetime.now().minute % 10 == 0:
                        self.save_snapshot()
                    
                    time.sleep(self.update_interval)
                    
                except Exception as e:
                    print(f"❌ Monitoring error: {e}")
                    time.sleep(5)
        
        # Start monitoring thread
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()
    
    def stop_monitoring(self):
        """Stop live monitoring"""
        self.live_mode = False
        print("⏹️ Stopped live monitoring")
    
    def save_snapshot(self):
        """Save current snapshot"""
        snapshot = {
            'timestamp': datetime.now().isoformat(),
            'metrics': self.calculate_metrics(),
            'equity_data': self.metrics['equity'][-100:] if self.metrics['equity'] else [],
            'trade_count': len(self.metrics['trades'])
        }
        
        filename = f"performance_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w') as f:
            json.dump(snapshot, f, indent=2)
        
        print(f"💾 Saved snapshot: {filename}")
    
    def export_report(self, filename: str = 'performance_report.html'):
        """Export comprehensive HTML report"""
        metrics = self.calculate_metrics()
        
        html_report = f"""
<!DOCTYPE html>
<html>
<head>
    <title>OracleBot-Pro Performance Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .metric {{ margin: 10px 0; padding: 10px; background: #f5f5f5; }}
        .positive {{ color: green; }}
        .negative {{ color: red; }}
    </style>
</head>
<body>
    <h1>📊 Performance Report</h1>
    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    
    <div class="metric">
        <h2>💰 Equity Metrics</h2>
        <p>Current Equity: <span class="{'positive' if metrics['current_equity'] > 0 else 'negative'}">${metrics['current_equity']:,.2f}</span></p>
        <p>Max Drawdown: <span class="{'negative' if metrics['max_drawdown'] < 0 else 'positive'}">{metrics['max_drawdown']:.2f}%</span></p>
    </div>
    
    <div class="metric">
        <h2>🎯 Trading Performance</h2>
        <p>Total Trades: {metrics['total_trades']}</p>
        <p>Win Rate: <span class="{'positive' if metrics['win_rate'] > 50 else 'negative'}">{metrics['win_rate']:.1f}%</span></p>
        <p>Sharpe Ratio: <span class="{'positive' if metrics['sharpe_ratio'] > 1 else 'negative'}">{metrics['sharpe_ratio']:.2f}</span></p>
    </div>
    
    <div class="metric">
        <h2>📈 System Information</h2>
        <p>Data Points: {len(self.metrics['equity'])}</p>
        <p>Monitoring: {'ACTIVE' if self.live_mode else 'INACTIVE'}</p>
    </div>
</body>
</html>
"""
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_report)
        
        print(f"✅ Exported report: {filename}")

# Example usage
if __name__ == "__main__":
    # Create dashboard
    dashboard = PerformanceDashboard()
    
    # Load existing results
    dashboard.load_results()
    
    # Generate report
    print(dashboard.generate_report())
    
    # Start live monitoring
    dashboard.start_live_monitoring()
    
    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        dashboard.stop_monitoring()
        print("\n📊 Dashboard stopped")
