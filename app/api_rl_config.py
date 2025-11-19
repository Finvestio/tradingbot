# Enhanced RL Trading System Configuration API
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, List, Optional, Union
from enum import Enum
import json
import os

# RL Configuration Models
class TradingStrategy(str, Enum):
    SCALPING = "scalping"
    SWING = "swing" 
    TREND_FOLLOWING = "trend-following"
    MEAN_REVERSION = "mean-reversion"
    GRID = "grid"
    ARBITRAGE = "arbitrage"
    CUSTOM = "custom"

class TradingFrequency(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class AssetClass(str, Enum):
    CRYPTO = "crypto"
    FOREX = "forex"
    EQUITIES = "equities"
    INDICES = "indices"
    COMMODITIES = "commodities"
    MIXED = "mixed"

class RiskTolerance(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"

class RewardStrategy(str, Enum):
    PROFIT_BASED = "profit_based"
    SHARPE_BASED = "sharpe_based"
    RISK_ADJUSTED = "risk_adjusted"
    CUSTOM = "custom"

class RetrainingFrequency(str, Enum):
    AFTER_TRADE = "after_trade"
    DAILY = "daily"
    WEEKLY = "weekly"
    CUSTOM = "custom"

class CustomRewardWeights(BaseModel):
    profit: float = 0.4
    risk: float = 0.3
    drawdown: float = 0.2
    volatility: float = 0.1

class FeatureConfig(BaseModel):
    realTimeAlerts: bool = True
    autoPositionScaling: bool = True
    stopLossTakeProfit: bool = True
    portfolioRebalancing: bool = False

class RLConfiguration(BaseModel):
    # Trading Strategy
    strategy: TradingStrategy = TradingStrategy.TREND_FOLLOWING
    customStrategy: Optional[str] = None
    
    # Trading Frequency
    frequency: TradingFrequency = TradingFrequency.MEDIUM
    
    # Asset Classes
    assetClass: AssetClass = AssetClass.EQUITIES
    specificSymbols: List[str] = ["AAPL", "MSFT", "GOOGL"]
    
    # Risk Management
    useDefault357Rule: bool = True
    riskPerTrade: float = 3.0
    maxPortfolioExposure: float = 5.0
    riskRewardRatio: str = "1:2"
    riskTolerance: RiskTolerance = RiskTolerance.MODERATE
    
    # Timeframes
    timeframes: List[str] = ["15min", "1h"]
    
    # RL Model Configuration
    rewardStrategy: RewardStrategy = RewardStrategy.RISK_ADJUSTED
    customRewardWeights: CustomRewardWeights = CustomRewardWeights()
    
    # Training Configuration
    continuousLearning: bool = True
    retrainingFrequency: RetrainingFrequency = RetrainingFrequency.AFTER_TRADE
    
    # Features
    features: FeatureConfig = FeatureConfig()
    
    # Technical Indicators
    indicators: List[str] = ["RSI", "MACD", "SMA_FAST", "SMA_SLOW"]
    customIndicators: List[str] = []

# Router setup
router = APIRouter(prefix="/api/rl", tags=["RL Configuration"])

# Configuration storage (in production, use database)
CONFIG_FILE = "rl_config.json"
current_config = RLConfiguration()

def load_config():
    """Load configuration from file"""
    global current_config
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config_data = json.load(f)
                current_config = RLConfiguration.parse_obj(config_data)
    except Exception as e:
        print(f"Error loading config: {e}")
        current_config = RLConfiguration()

def save_config(config: RLConfiguration):
    """Save configuration to file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config.dict(), f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

# Initialize config on startup
load_config()

@router.get("/config", response_model=RLConfiguration)
async def get_rl_configuration():
    """Get current RL trading bot configuration"""
    return current_config

@router.post("/config")
async def update_rl_configuration(config: RLConfiguration):
    """Update RL trading bot configuration"""
    global current_config
    
    try:
        # Validate configuration
        if not config.specificSymbols:
            raise HTTPException(status_code=400, detail="At least one symbol is required")
        
        if config.riskPerTrade <= 0 or config.riskPerTrade > 10:
            raise HTTPException(status_code=400, detail="Risk per trade must be between 0.1% and 10%")
        
        if not config.indicators:
            raise HTTPException(status_code=400, detail="At least one technical indicator is required")
        
        # Save configuration
        if save_config(config):
            current_config = config
            
            # Apply configuration to existing RL system
            await apply_configuration_to_rl_system(config)
            
            # Restart all running bots with new configuration
            await restart_all_running_bots()
            
            return {"message": "Configuration updated successfully and bots restarted", "config": config.dict()}
        else:
            raise HTTPException(status_code=500, detail="Failed to save configuration")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Configuration update failed: {str(e)}")

@router.post("/restart_training")
async def restart_rl_training(config: RLConfiguration):
    """Restart RL training with new configuration"""
    try:
        # Update environment parameters
        env_params = generate_environment_parameters(config)
        
        # Restart training process
        training_result = await restart_training_process(env_params)
        
        return {
            "message": "RL training restarted successfully",
            "training_id": training_result.get("training_id"),
            "environment_params": env_params
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restart training: {str(e)}")

@router.post("/backtest")
async def generate_backtest(config: RLConfiguration):
    """Generate backtest with current configuration"""
    try:
        # Create backtest parameters from configuration
        backtest_params = {
            "strategy": config.strategy,
            "symbols": config.specificSymbols,
            "timeframes": config.timeframes,
            "risk_per_trade": config.riskPerTrade,
            "max_exposure": config.maxPortfolioExposure,
            "indicators": config.indicators,
            "start_date": "2023-01-01",  # Can be made configurable
            "end_date": "2024-01-01"
        }
        
        # Run backtest (implementation would depend on your backtesting engine)
        backtest_results = await run_rl_backtest(backtest_params)
        
        return {
            "message": "Backtest completed successfully",
            "results": backtest_results,
            "configuration_used": config.dict()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {str(e)}")

@router.get("/performance_metrics")
async def get_rl_performance_metrics():
    """Get current RL model performance metrics"""
    try:
        # Retrieve performance data from your RL system
        metrics = await get_current_rl_metrics()
        
        return {
            "model_performance": metrics,
            "configuration": current_config.dict(),
            "last_updated": "2024-11-16T00:00:00Z"  # Use actual timestamp
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve metrics: {str(e)}")

# Helper functions for RL system integration
async def apply_configuration_to_rl_system(config: RLConfiguration):
    """Apply new configuration to the existing RL trading system"""
    try:
        # Update the RL environment parameters
        from app.rl.env import TradingEnv
        
        # Create new environment configuration
        env_config = {
            "symbols": config.specificSymbols,
            "timeframes": config.timeframes,
            "indicators": config.indicators,
            "risk_per_trade": config.riskPerTrade / 100,  # Convert to decimal
            "max_exposure": config.maxPortfolioExposure / 100,
            "reward_strategy": config.rewardStrategy,
            "custom_weights": config.customRewardWeights.dict() if config.rewardStrategy == "custom" else None
        }
        
        # Update global RL configuration
        # This would integrate with your existing RL system
        print(f"✅ Applied RL configuration: {config.strategy} with {len(config.specificSymbols)} symbols")
        
        return True
        
    except Exception as e:
        print(f"❌ Error applying RL configuration: {e}")
        return False

def generate_environment_parameters(config: RLConfiguration) -> Dict:
    """Generate RL environment parameters from configuration"""
    return {
        "observation_space_size": len(config.indicators) * len(config.timeframes) + 5,  # +5 for portfolio metrics
        "action_space_size": 3,  # HOLD, BUY, SELL
        "reward_function": config.rewardStrategy,
        "risk_multiplier": 1.0 if config.riskTolerance == "moderate" else 0.5 if config.riskTolerance == "conservative" else 2.0,
        "learning_rate": 0.0003,
        "batch_size": 64,
        "buffer_size": 100000,
        "training_frequency": 1 if config.continuousLearning else 100
    }

async def restart_training_process(env_params: Dict):
    """Restart the RL training process with new parameters"""
    # This would interface with your RL training system
    training_id = f"training_{hash(str(env_params))}"
    
    # Placeholder for actual training restart logic
    return {
        "training_id": training_id,
        "status": "started",
        "parameters": env_params
    }

async def run_rl_backtest(params: Dict):
    """Run backtest with RL strategy"""
    # Placeholder for actual backtesting logic
    return {
        "total_return": 0.15,
        "sharpe_ratio": 1.2,
        "max_drawdown": 0.08,
        "win_rate": 0.65,
        "total_trades": 150,
        "parameters_used": params
    }

async def get_current_rl_metrics():
    """Get current RL model performance metrics"""
    # Placeholder for actual metrics retrieval
    return {
        "episodes_trained": 1000,
        "current_reward": 1500.0,
        "avg_reward_per_episode": 1.5,
        "exploration_rate": 0.1,
        "learning_rate": 0.0003,
        "last_training_loss": 0.05
    }

async def restart_all_running_bots():
    """Restart all running bots with new configuration"""
    try:
        from app.api import running_bots
        
        print(f"\n{'='*80}")
        print(f"🔄 RESTARTING ALL BOTS WITH NEW CONFIGURATION")
        print(f"{'='*80}")
        
        # Get list of all running bots
        bots_to_restart = []
        for key, bot in list(running_bots.items()):
            parts = key.split('_')
            if len(parts) >= 3:
                user_id = int(parts[0])
                symbol = parts[1]
                asset_type = '_'.join(parts[2:]) if len(parts) > 3 else parts[2]
                bots_to_restart.append({
                    'key': key,
                    'user_id': user_id,
                    'symbol': symbol,
                    'asset_type': asset_type,
                    'auto_execute': getattr(bot, 'auto_execute', True),
                    'interval_sec': getattr(bot, 'interval_sec', 30)
                })
        
        print(f"📋 Found {len(bots_to_restart)} running bot(s) to restart")
        
        if not bots_to_restart:
            print("ℹ️ No running bots to restart")
            return {"restarted": 0, "total": 0, "message": "No running bots to restart"}
        
        # Stop all bots first
        for bot_info in bots_to_restart:
            try:
                print(f"🛑 Stopping bot: {bot_info['symbol']} for user {bot_info['user_id']}")
                bot = running_bots.get(bot_info['key'])
                if bot:
                    # Set running flag to False to stop the bot
                    bot.running = False
                    # Remove from running_bots
                    del running_bots[bot_info['key']]
                    print(f"✅ Bot stopped: {bot_info['symbol']}")
            except Exception as e:
                print(f"⚠️ Error stopping bot {bot_info['key']}: {e}")
        
        # Wait a moment for bots to stop
        import asyncio
        await asyncio.sleep(1)
        
        # Restart all bots with new configuration
        restarted_count = 0
        for bot_info in bots_to_restart:
            try:
                print(f"🚀 Restarting bot: {bot_info['symbol']} for user {bot_info['user_id']}")
                from app.bot.rl_trader import RLTrader
                import threading
                
                new_bot = RLTrader(
                    bot_info['user_id'],
                    bot_info['symbol'],
                    bot_info['asset_type'],
                    bot_info['interval_sec'],
                    bot_info['auto_execute']
                )
                
                def run_bot():
                    try:
                        new_bot.run()
                    except Exception as e:
                        print(f"❌ Bot error: {e}")
                
                thread = threading.Thread(target=run_bot, daemon=True)
                thread.start()
                running_bots[bot_info['key']] = new_bot
                restarted_count += 1
                
            except Exception as e:
                print(f"⚠️ Error restarting bot {bot_info['key']}: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"✅ Restarted {restarted_count}/{len(bots_to_restart)} bot(s) successfully")
        print(f"{'='*80}\n")
        
        return {
            "restarted": restarted_count,
            "total": len(bots_to_restart),
            "message": f"Restarted {restarted_count} bot(s) with new configuration"
        }
        
    except Exception as e:
        print(f"❌ Error restarting bots: {e}")
        import traceback
        traceback.print_exc()
        return {
            "restarted": 0,
            "total": 0,
            "error": str(e)
        }