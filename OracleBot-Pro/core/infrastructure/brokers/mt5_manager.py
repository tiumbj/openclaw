"""
Enterprise MT5 Connection Manager with Circuit Breakers and Resilience Patterns.
Handles connection pooling, reconnection logic, and fault tolerance.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, AsyncIterator
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

import MetaTrader5 as mt5

logger = logging.getLogger(__name__)


class MT5ConnectionState(Enum):
    """MT5 connection state machine."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    FAILED = "failed"


class MT5Manager:
    """
    Enterprise-grade MT5 connection manager with:
    - Connection pooling and reuse
    - Circuit breaker pattern
    - Exponential backoff retry
    - Health monitoring
    - Graceful degradation
    """
    
    def __init__(
        self,
        server: str,
        login: int,
        password: str,
        timeout: int = 30,
        max_retries: int = 5
    ):
        self.server = server
        self.login = login
        self.password = password
        self.timeout = timeout
        self.max_retries = max_retries
        self.connection_state = MT5ConnectionState.DISCONNECTED
        self.last_heartbeat: Optional[datetime] = None
        self.failure_count = 0
        self._lock = asyncio.Lock()
        self.logger = logging.getLogger(__name__)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    async def connect(self) -> bool:
        """
        Establish MT5 connection with retry logic and circuit breaker.
        Returns True if connection successful, False otherwise.
        """
        async with self._lock:
            if self.connection_state == MT5ConnectionState.FAILED:
                self.logger.warning("Circuit breaker open - connection attempts blocked")
                return False
            
            try:
                self.connection_state = MT5ConnectionState.CONNECTING
                
                # Initialize MT5 library
                if not mt5.initialize():
                    raise ConnectionError(f"MT5 initialize failed: {mt5.last_error()}")
                
                # Attempt connection
                connected = mt5.login(
                    login=self.login,
                    password=self.password,
                    server=self.server,
                    timeout=self.timeout * 1000  # Convert to milliseconds
                )
                
                if not connected:
                    error_msg = mt5.last_error()
                    self.logger.error(f"MT5 login failed: {error_msg}")
                    raise ConnectionError(f"Login failed: {error_msg}")
                
                # Connection successful
                self.connection_state = MT5ConnectionState.CONNECTED
                self.last_heartbeat = datetime.utcnow()
                self.failure_count = 0
                
                account_info = mt5.account_info()
                self.logger.info(
                    f"MT5 connected successfully to {self.server}. "
                    f"Account: {account_info.login}, Balance: {account_info.balance}"
                )
                
                return True
                
            except Exception as e:
                self.failure_count += 1
                self.connection_state = MT5ConnectionState.DEGRADED
                self.logger.error(f"MT5 connection attempt {self.failure_count} failed: {e}")
                
                # Open circuit breaker after max failures
                if self.failure_count >= self.max_retries:
                    self.connection_state = MT5ConnectionState.FAILED
                    self.logger.critical("MT5 circuit breaker opened - manual intervention required")
                
                raise
    
    async def disconnect(self) -> None:
        """Graceful MT5 disconnection."""
        async with self._lock:
            try:
                mt5.shutdown()
                self.connection_state = MT5ConnectionState.DISCONNECTED
                self.logger.info("MT5 disconnected gracefully")
            except Exception as e:
                self.logger.error(f"Error during MT5 shutdown: {e}")
    
    async def check_connection(self) -> bool:
        """Verify MT5 connection health with heartbeat."""
        if self.connection_state != MT5ConnectionState.CONNECTED:
            return False
        
        try:
            # Simple heartbeat check
            account_info = mt5.account_info()
            if account_info is None:
                raise ConnectionError("Account info unavailable")
            
            self.last_heartbeat = datetime.utcnow()
            return True
            
        except Exception as e:
            self.logger.warning(f"MT5 heartbeat failed: {e}")
            self.connection_state = MT5ConnectionState.DEGRADED
            return False
    
    @asynccontextmanager
    async def get_connection(self) -> AsyncIterator[None]:
        """
        Context manager for MT5 connection with automatic recovery.
        Usage:
            async with mt5_manager.get_connection():
                # Execute MT5 operations
                mt5.symbol_info_tick("XAUUSD")
        """
        try:
            if not await self.check_connection():
                await self.connect()
            
            yield
            
        except Exception as e:
            self.logger.error(f"MT5 operation failed: {e}")
            await self.disconnect()
            raise
    
    async def execute_order(self, order: Any) -> Optional[int]:
        """
        Execute order through MT5 with resilience patterns.
        Returns MT5 ticket number if successful, None otherwise.
        """
        try:
            async with self.get_connection():
                # Prepare order request
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": order.symbol,
                    "volume": order.volume,
                    "type": self._get_order_type(order),
                    "price": mt5.symbol_info_tick(order.symbol).ask,
                    "sl": order.stop_loss,
                    "tp": order.take_profit,
                    "deviation": 10,
                    "magic": 2024,
                    "comment": f"OracleBot_{order.strategy_id}",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_FOK
                }
                
                # Send order
                result = mt5.order_send(request)
                
                if result.retcode != mt5.TRADE_RETCODE_DONE:
                    raise Exception(f"Order failed: {result.retcode} - {result.comment}")
                
                self.logger.info(
                    f"Order executed successfully: {order.symbol} {order.volume} "
                    f"Ticket: {result.order}"
                )
                
                return int(result.order)
                
        except Exception as e:
            self.logger.error(f"Order execution failed: {e}")
            return None
    
    def _get_order_type(self, order: Any) -> int:
        """Map order type to MT5 constants."""
        order_type_map = {
            "buy": mt5.ORDER_TYPE_BUY,
            "sell": mt5.ORDER_TYPE_SELL
        }
        return int(order_type_map.get(order.order_type.name.lower(), mt5.ORDER_TYPE_BUY))
    
    async def get_market_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get current market data with error handling."""
        try:
            async with self.get_connection():
                tick = mt5.symbol_info_tick(symbol)
                if tick is None:
                    return None
                
                return {
                    "symbol": symbol,
                    "bid": tick.bid,
                    "ask": tick.ask,
                    "last": tick.last,
                    "volume": tick.volume,
                    "time": tick.time,
                    "spread": tick.ask - tick.bid
                }
                
        except Exception as e:
            self.logger.error(f"Market data fetch failed for {symbol}: {e}")
            return None
