"""
OracleBot Pro - Enterprise Algorithmic Trading System
Main entry point with production-grade orchestration and monitoring.
"""

import asyncio
import logging
import signal
import sys
from contextlib import AsyncExitStack
from typing import Dict, Any

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

# Configure structured logging for production
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    wrapper_class=structlog.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


class OracleBot:
    """
    Main trading bot orchestrator with:
    - Graceful startup/shutdown
    - Health monitoring
    - Dependency management
    - Fault isolation
    """
    
    def __init__(self):
        self.is_running = False
        self.exit_stack = AsyncExitStack()
        self.services: Dict[str, Any] = {}
        self._shutdown_task = None
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._handle_shutdown_signal)
        signal.signal(signal.SIGTERM, self._handle_shutdown_signal)
    
    def _handle_shutdown_signal(self, signum, frame) -> None:
        """Handle shutdown signals gracefully."""
        logger.warning(f"Received shutdown signal {signum}")
        self._shutdown_task = asyncio.create_task(self.shutdown())
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def initialize_services(self) -> None:
        """Initialize all trading services with dependency injection."""
        try:
            logger.info("Initializing OracleBot services...")
            
            # Initialize MT5 connection manager
            from core.infrastructure.brokers.mt5_manager import MT5Manager
            mt5_manager = MT5Manager(
                server="MetaQuotes-Demo",
                login=123456,  # Should be from config
                password="demo_password",
                timeout=30,
                max_retries=5
            )
            
            await mt5_manager.connect()
            self.services["mt5_manager"] = mt5_manager
            
            # Initialize trading strategies
            from strategies.implementations.xauusd_strategy import XAUUSDStrategy
            xauusd_strategy = XAUUSDStrategy(mt5_manager)
            self.services["xauusd_strategy"] = xauusd_strategy
            
            # Initialize health monitor
            self.services["health_monitor"] = HealthMonitor(self.services)
            
            logger.info("All services initialized successfully")
            
        except Exception as e:
            logger.error(f"Service initialization failed: {e}")
            await self.shutdown()
            raise
    
    async def run(self) -> None:
        """Main trading loop with production resilience."""
        try:
            await self.initialize_services()
            self.is_running = True
            
            logger.info("OracleBot started successfully", 
                       status="running", 
                       services=list(self.services.keys()))
            
            # Main trading loop
            while self.is_running:
                try:
                    await self._execute_trading_cycle()
                    await asyncio.sleep(1)  # Control loop speed
                    
                except Exception as e:
                    logger.error(f"Trading cycle failed: {e}")
                    await asyncio.sleep(5)  # Backoff on error
                    
        except asyncio.CancelledError:
            logger.info("Trading loop cancelled")
        except Exception as e:
            logger.critical(f"Fatal error in main loop: {e}")
            await self.shutdown()
    
    async def _execute_trading_cycle(self) -> None:
        """Execute single trading cycle with monitoring."""
        # Check system health
        if not await self._check_system_health():
            logger.warning("System health check failed - skipping cycle")
            return
        
        # Execute strategies
        strategy_results = []
        
        if "xauusd_strategy" in self.services:
            try:
                result = await self.services["xauusd_strategy"].execute()
                strategy_results.append({
                    "strategy": "XAUUSD",
                    "result": result
                })
            except Exception as e:
                logger.error(f"XAUUSD strategy execution failed: {e}")
        
        # Log cycle results
        if strategy_results:
            logger.info("Trading cycle completed", results=strategy_results)
    
    async def _check_system_health(self) -> bool:
        """Comprehensive system health check."""
        try:
            # Check MT5 connection
            mt5_manager = self.services.get("mt5_manager")
            if mt5_manager and not await mt5_manager.check_connection():
                logger.warning("MT5 connection unhealthy")
                return False
            
            # TODO: Add more health checks (memory, CPU, network)
            return True
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    async def shutdown(self) -> None:
        """Graceful shutdown of all services."""
        if not self.is_running:
            return
        
        self.is_running = False
        logger.info("Initiating graceful shutdown...")
        
        try:
            # Shutdown MT5 connection
            if "mt5_manager" in self.services:
                await self.services["mt5_manager"].disconnect()
            
            # Close all async resources
            await self.exit_stack.aclose()
            
            logger.info("Shutdown completed successfully")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        finally:
            sys.exit(0)


class HealthMonitor:
    """System health monitoring and alerting."""
    
    def __init__(self, services: Dict[str, Any]):
        self.services = services
        self.metrics: Dict[str, Any] = {}
    
    async def check_health(self) -> Dict[str, bool]:
        """Comprehensive health check across all services."""
        health_status = {}
        
        # MT5 health
        if "mt5_manager" in self.services:
            mt5_health = await self.services["mt5_manager"].check_connection()
            health_status["mt5"] = mt5_health
        
        # TODO: Add more health checks
        
        return health_status


def main() -> None:
    """Main entry point with production configuration."""
    try:
        # Configure logging level
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        logger.info("Starting OracleBot Pro - Enterprise Trading System")
        
        # Create and run bot
        bot = OracleBot()
        
        # Run with graceful shutdown handling
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(bot.run())
        except KeyboardInterrupt:
            logger.info("Shutdown requested via keyboard")
            loop.run_until_complete(bot.shutdown())
        finally:
            loop.close()
            
    except Exception as e:
        logger.critical(f"Fatal error during startup: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
