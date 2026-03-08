"""
Simple Configuration for MT5 Testing
Version: 1.0.0
"""

import os
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class MT5Config(BaseModel):
    """MT5 connection configuration."""
    server: str = Field("default_server", description="MT5 server address")
    login: int = Field(123456, description="MT5 account login")
    password: str = Field("password", description="MT5 account password")
    timeout: int = Field(30, description="Connection timeout in seconds")
    max_retries: int = Field(5, description="Maximum connection retries")
    heartbeat_interval: int = Field(30, description="Heartbeat check interval in seconds")


class TradingConfig(BaseModel):
    """Trading parameters configuration."""
    default_symbol: str = Field("XAUUSD", description="Default trading symbol")
    max_position_size: float = Field(0.1, description="Maximum position size in lots")
    max_daily_trades: int = Field(10, description="Maximum trades per day")
    risk_per_trade: float = Field(0.02, description="Risk percentage per trade")
    slippage: float = Field(2.0, description="Allowed slippage in pips")


class OpenClawConfig(BaseModel):
    """OpenClaw AI integration configuration."""
    enabled: bool = Field(False, description="Enable OpenClaw integration")
    api_url: str = Field("http://localhost:8000", description="OpenClaw API URL")
    timeout: int = Field(30, description="API request timeout")
    retry_attempts: int = Field(3, description="API retry attempts")


class Config(BaseModel):
    """Main application configuration."""
    mt5: MT5Config
    trading: TradingConfig
    openclaw: OpenClawConfig
    environment: str = Field("development", description="Current environment")


def load_simple_config() -> Config:
    """
    Load simple configuration without YAML dependency.
    Uses environment variables if available, otherwise defaults.
    """
    # Get MT5 config from environment or use defaults
    mt5_config = {
        'server': os.getenv('MT5_SERVER', 'default_server'),
        'login': int(os.getenv('MT5_LOGIN', '123456')),
        'password': os.getenv('MT5_PASSWORD', 'password'),
        'timeout': int(os.getenv('MT5_TIMEOUT', '30')),
        'max_retries': int(os.getenv('MT5_MAX_RETRIES', '5')),
        'heartbeat_interval': int(os.getenv('MT5_HEARTBEAT_INTERVAL', '30'))
    }
    
    # Trading config
    trading_config = {
        'default_symbol': os.getenv('TRADING_SYMBOL', 'XAUUSD'),
        'max_position_size': float(os.getenv('TRADING_MAX_SIZE', '0.1')),
        'max_daily_trades': int(os.getenv('TRADING_MAX_TRADES', '10')),
        'risk_per_trade': float(os.getenv('TRADING_RISK', '0.02')),
        'slippage': float(os.getenv('TRADING_SLIPPAGE', '2.0'))
    }
    
    # OpenClaw config
    openclaw_config = {
        'enabled': os.getenv('OPENCLAW_ENABLED', 'false').lower() == 'true',
        'api_url': os.getenv('OPENCLAW_API_URL', 'http://localhost:8000'),
        'timeout': int(os.getenv('OPENCLAW_TIMEOUT', '30')),
        'retry_attempts': int(os.getenv('OPENCLAW_RETRIES', '3'))
    }
    
    return Config(
        mt5=MT5Config(**mt5_config),
        trading=TradingConfig(**trading_config),
        openclaw=OpenClawConfig(**openclaw_config),
        environment=os.getenv('ORACLEBOT_ENV', 'development')
    )