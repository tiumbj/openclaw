"""
Configuration management module for OracleBot Pro.
Supports multiple environments with environment variables override.
"""

import os
from typing import Dict, Any
import yaml
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class MT5Config(BaseModel):
    """MT5 connection configuration."""
    server: str = Field(..., description="MT5 server address")
    login: int = Field(..., description="MT5 account login")
    password: str = Field(..., description="MT5 account password")
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


def load_config(environment: str | None = None) -> Config:
    """
    Load configuration for specified environment.
    Environment variables take precedence over config file values.
    """
    env = str(environment or os.getenv("ORACLEBOT_ENV", "development"))
    config_file = f"config/{env}.yaml"
    
    # Load base configuration from YAML
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            config_data = yaml.safe_load(f)
    else:
        # Fallback to default config
        config_data = {}
    
    # Override with environment variables
    config_data = _override_with_env_vars(config_data)
    
    # Create configuration model
    return Config(
        mt5=MT5Config(**config_data.get('mt5', {})),
        trading=TradingConfig(**config_data.get('trading', {})),
        openclaw=OpenClawConfig(**config_data.get('openclaw', {})),
        environment=env
    )


def _override_with_env_vars(config_data: Dict[str, Any]) -> Dict[str, Any]:
    """Override configuration with environment variables."""
    
    # MT5 environment variables
    if mt5_login := os.getenv("MT5_LOGIN"):
        config_data.setdefault('mt5', {})['login'] = int(mt5_login)
    if mt5_password := os.getenv("MT5_PASSWORD"):
        config_data.setdefault('mt5', {})['password'] = mt5_password
    if mt5_server := os.getenv("MT5_SERVER"):
        config_data.setdefault('mt5', {})['server'] = mt5_server
    
    # OpenClaw environment variables
    if openclaw_url := os.getenv("OPENCLAW_API_URL"):
        config_data.setdefault('openclaw', {})['api_url'] = openclaw_url
    if openclaw_enabled := os.getenv("OPENCLAW_ENABLED"):
        config_data.setdefault('openclaw', {})['enabled'] = openclaw_enabled.lower() == 'true'
    
    return config_data


# Global configuration instance
config = load_config()
