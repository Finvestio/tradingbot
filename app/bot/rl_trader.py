import time
import torch
import json
import asyncio
import numpy as np
import os
from app.rl.dqn import DQNAgent
from app.rl.env import TradingEnv
from app.db import get_db_connection
from app.rl.replay_store import add_experience
from collections import deque

# Global storage for trade proposals
trade_proposals = {}

class RLTrader:
    """Autonomous RL-based trader that trades one action per interval."""

    def __init__(self, user_id, symbol, asset_type, interval_sec=30, auto_execute=True):
        self.user_id = user_id
        self.symbol = symbol
        self.asset_type = asset_type
        self.interval = interval_sec
        self.auto_execute = auto_execute
        self.model_path = f"models/dqn_{asset_type}_{symbol}.pth"

        # Load RL configuration FIRST
        self.config = self.load_rl_config()
        self.apply_config()

        # Get user's actual wallet balance from database
        self.conn = get_db_connection()
        user_wallet = self.get_user_wallet()
        
        # Environment and model - initialize with user's actual wallet
        self.env = TradingEnv(symbol, asset_type, init_cash=user_wallet)
        self.agent = None

        # Replay memory for continuous learning
        self.memory = deque(maxlen=1000)

        # Learning frequency settings (from config)
        self.learn_every = self.config_learn_every
        self.checkpoint_every = self.config_checkpoint_every
        self.trade_count = 0
        self.current_state = None

    def get_user_wallet(self):
        """Get user's current wallet balance from database."""
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT wallet_balance FROM users WHERE id = %s", (self.user_id,))
            result = cur.fetchone()
            cur.close()
            
            if result:
                wallet = float(result[0])
                print(f"💰 Loaded user {self.user_id} wallet: ${wallet:,.2f}")
                return wallet
            else:
                print(f"⚠️ User {self.user_id} not found, using default wallet")
                return 100000.0
        except Exception as e:
            print(f"⚠️ Error loading wallet for user {self.user_id}: {e}, using default")
            return 100000.0

    def load_rl_config(self):
        """Load RL configuration from rl_config.json"""
        try:
            config_path = "rl_config.json"
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    print(f"✅ Loaded RL config: {config.get('strategy')} strategy")
                    return config
            else:
                print("⚠️ No rl_config.json found, using defaults")
                return self.get_default_config()
        except Exception as e:
            print(f"⚠️ Error loading RL config: {e}, using defaults")
            return self.get_default_config()

    def get_default_config(self):
        """Return default configuration"""
        return {
            "strategy": "trend-following",
            "riskPerTrade": 3.0,
            "maxPortfolioExposure": 5.0,
            "riskTolerance": "moderate",
            "rewardStrategy": "risk_adjusted",
            "continuousLearning": True,
            "retrainingFrequency": "after_trade",
            "indicators": ["RSI", "MACD", "SMA_FAST", "SMA_SLOW"],
            "customRewardWeights": {
                "profit": 0.4,
                "risk": 0.3,
                "drawdown": 0.2,
                "volatility": 0.1
            }
        }

    def apply_config(self):
        """Apply configuration settings to bot parameters"""
        # Risk management from config
        self.risk_per_trade = self.config.get("riskPerTrade", 3.0) / 100
        self.max_exposure = self.config.get("maxPortfolioExposure", 5.0) / 100
        
        # Risk tolerance affects exploration rate
        risk_tolerance = self.config.get("riskTolerance", "moderate")
        if risk_tolerance == "conservative":
            self.exploration_multiplier = 0.5
            self.min_confidence = 0.7
        elif risk_tolerance == "aggressive":
            self.exploration_multiplier = 1.5
            self.min_confidence = 0.4
        else:  # moderate
            self.exploration_multiplier = 1.0
            self.min_confidence = 0.5
        
        # Learning settings from config
        retraining = self.config.get("retrainingFrequency", "after_trade")
        if retraining == "after_trade":
            self.config_learn_every = 1
        elif retraining == "daily":
            self.config_learn_every = 100
        elif retraining == "weekly":
            self.config_learn_every = 500
        else:
            self.config_learn_every = 10
        
        # Continuous learning
        self.continuous_learning = self.config.get("continuousLearning", True)
        if not self.continuous_learning:
            self.config_learn_every = 999999
        
        self.config_checkpoint_every = 200
        
        # Reward strategy
        self.reward_strategy = self.config.get("rewardStrategy", "risk_adjusted")
        self.reward_weights = self.config.get("customRewardWeights", {
            "profit": 0.4,
            "risk": 0.3,
            "drawdown": 0.2,
            "volatility": 0.1
        })
        
        # Trading strategy
        self.trading_strategy = self.config.get("strategy", "trend-following")
        
        # Indicators
        self.indicators = self.config.get("indicators", ["RSI", "MACD", "SMA_FAST", "SMA_SLOW"])
        
        print(f"📊 Config Applied:")
        print(f"   Risk/Trade: {self.risk_per_trade*100:.1f}% | Max Exposure: {self.max_exposure*100:.1f}%")
        print(f"   Strategy: {self.trading_strategy} | Risk Tolerance: {risk_tolerance}")
        print(f"   Learn Every: {self.config_learn_every} trades | Continuous: {self.continuous_learning}")
        print(f"   Indicators: {', '.join(self.indicators)}") 

    # -------------------- MODEL LOADING --------------------
    def load_model(self):
        """Load DQN model or fallback to random."""
        try:
            dummy_state = self.env.reset()
            self.agent = DQNAgent(len(dummy_state))
            self.agent.q.load_state_dict(torch.load(self.model_path))
            self.agent.q.eval()
            print(f"✅ Loaded model {self.model_path}")
        except Exception as e:
            print(f"⚠️ No model found ({e}), using random policy")
            dummy_state = self.env.reset()
            self.agent = DQNAgent(len(dummy_state))
            # For untrained models, use high exploration (80%) to encourage trading
            self.agent.epsilon = 0.8
            print(f"🎲 Exploration rate set to 80% for untrained model")

    # -------------------- DATABASE --------------------
    def update_wallet(self, delta):
        """Apply profit/loss atomically to the user's wallet and sync with environment."""
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE users SET wallet_balance = wallet_balance + %s WHERE id = %s",
            (float(delta), self.user_id)
        )
        self.conn.commit()
        
        # Get updated wallet balance
        cur.execute("SELECT wallet_balance FROM users WHERE id = %s", (self.user_id,))
        result = cur.fetchone()
        cur.close()
        
        if result:
            new_wallet = float(result[0])
            # Sync environment cash with actual database wallet
            self.env.cash = new_wallet - (self.env.position * self.get_current_price())
            print(f"💰 Wallet updated: ${new_wallet:,.2f} (delta: ${delta:+.2f})")
        
    def get_current_price(self):
        """Get current market price."""
        try:
            current_data = self.env.df.iloc[self.env.t] if self.env.t < len(self.env.df) else self.env.df.iloc[-1]
            return float(current_data["close"])
        except:
            return 0.0

    def record_trade(self, action, reward, equity):
        """Insert trade record into bot_trades table for history."""
        cur = self.conn.cursor()
        
        # Get current price
        try:
            current_price = self.get_current_price()
        except:
            current_price = 0.0
        
        # Determine action name and quantity
        action_name = self.get_action_name(action)
        quantity = 1  # Default quantity
        
        # Insert into bot_trades table
        cur.execute("""
            INSERT INTO bot_trades 
            (user_id, symbol, asset_type, action, price, quantity, reward, equity, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            self.user_id, 
            self.symbol, 
            self.asset_type, 
            action_name,  # 'BUY', 'SELL', or 'HOLD'
            float(current_price),
            quantity,
            float(reward), 
            float(equity)
        ))
        self.conn.commit()
        cur.close()
        print(f"📝 Trade recorded in bot_trades: {action_name} {self.symbol} @ ${current_price:.2f}")

    # -------------------- NOTIFICATIONS --------------------
    async def notify_frontend(self, message: dict):
        """Send real-time message via WebSocket if user connected."""
        from app.api import active_connections  # lazy import avoids circular import
        
        print(f"🔌 Attempting to send WebSocket message to user {self.user_id}")
        print(f"🔌 Active connections: {list(active_connections.keys())}")
        
        ws = active_connections.get(self.user_id)
        if ws:
            try:
                message_json = json.dumps(message)
                await ws.send_text(message_json)
                print(f"✅ WebSocket message sent successfully to user {self.user_id}")
                print(f"📋 Message: {message_json}")
            except Exception as e:
                print(f"❌ Failed to send WebSocket message to user {self.user_id}: {e}")
        else:
            print(f"❌ No WebSocket connection found for user {self.user_id}")
            print(f"📋 Message that couldn't be sent: {json.dumps(message)}")

    def create_proposal(self, action, price, equity):
        """Create an enhanced trade proposal with strategy analysis and confidence scoring."""
        key = (self.user_id, self.symbol)
        
        print(f"\n{'┌'+'─'*58+'┐'}")
        print(f"│ 📋 CREATING TRADE PROPOSAL{' '*30}│")
        print(f"{'└'+'─'*58+'┘'}")
        
        # Check if there's already a pending proposal
        if key in trade_proposals:
            print(f"⏸️ Previous proposal still pending for {self.symbol}")
            print(f"   Skipping new proposal to avoid conflicts")
            return None
        
        print(f"✅ No pending proposal found, proceeding...")
        
        # Generate enhanced analysis
        print(f"📊 Analyzing market strategy...")
        strategy_analysis = self.analyze_market_strategy(action, price)
        
        print(f"🎯 Calculating confidence score...")
        confidence_score = self.calculate_confidence(action, price)
        
        print(f"⚖️ Calculating risk metrics...")
        risk_analysis = self.calculate_risk_metrics(action, price, equity)
        
        print(f"📈 Generating technical summary...")
        technical_summary = self.generate_technical_summary()
        
        proposal = {
            "type": "proposal",
            "user_id": self.user_id,
            "symbol": self.symbol,
            "asset_type": self.asset_type,
            "action": int(action),
            "price": float(price),
            "equity": float(equity),
            "quantity": 1,
            "timestamp": time.time(),
            "proposal_id": f"{self.user_id}_{self.symbol}_{int(time.time())}",
            "strategy": strategy_analysis["strategy"],
            "confidence": confidence_score,
            "reason": strategy_analysis["reason"],
            "risk_amount": risk_analysis["risk_amount"],
            "profit_target": risk_analysis["profit_target"],
            "technical_summary": technical_summary
        }
        
        # Store proposal
        trade_proposals[key] = proposal
        print(f"💾 Proposal stored in memory")
        
        # Send proposal via WebSocket
        print(f"📡 Sending proposal to frontend via WebSocket...")
        asyncio.run(self.notify_frontend(proposal))
        
        # Enhanced logging
        action_name = self.get_action_name(action)
        confidence_percent = int(confidence_score * 100)
        print(f"\n✅ PROPOSAL CREATED SUCCESSFULLY:")
        print(f"   Action: {action_name}")
        print(f"   Symbol: {self.symbol}")
        print(f"   Price: ${price:.2f}")
        print(f"   Strategy: {strategy_analysis['strategy']}")
        print(f"   Confidence: {confidence_percent}%")
        print(f"   Risk Amount: ${risk_analysis['risk_amount']:.2f}")
        print(f"   Profit Target: ${risk_analysis['profit_target']:.2f}")
        print(f"   Reason: {strategy_analysis['reason']}")
        print(f"{'─'*60}\n")
        
        return proposal

    def analyze_market_strategy(self, action, price):
        """Analyze what trading strategy the action represents based on config."""
        try:
            current_data = self.env.df.iloc[self.env.t] if self.env.t < len(self.env.df) else self.env.df.iloc[-1]
            close_prices = self.env.df['close'].iloc[max(0, self.env.t-20):self.env.t+1]
            sma_20 = close_prices.rolling(20).mean().iloc[-1] if len(close_prices) >= 20 else price
            sma_50 = self.env.df['close'].iloc[max(0, self.env.t-50):self.env.t+1].rolling(50).mean().iloc[-1] if self.env.t >= 50 else price
            
            # Use configured strategy
            strategy_name = self.trading_strategy.replace("-", " ").title()
            
            if action == 1:  # BUY
                if self.trading_strategy == "mean-reversion" and price < sma_20:
                    return {
                        "strategy": "Mean Reversion",
                        "reason": f"Price ${price:.2f} below SMA - bounce expected (Config: {strategy_name})"
                    }
                elif self.trading_strategy == "trend-following" and price > sma_20 and sma_20 > sma_50:
                    return {
                        "strategy": "Trend Following",
                        "reason": f"Strong uptrend confirmed (Config: {strategy_name})"
                    }
                else:
                    return {
                        "strategy": strategy_name,
                        "reason": f"RL detected BUY signal using {strategy_name} strategy"
                    }
            elif action == 2:  # SELL
                if self.trading_strategy == "mean-reversion" and price > sma_20:
                    return {
                        "strategy": "Mean Reversion",
                        "reason": f"Price ${price:.2f} above SMA - pullback expected (Config: {strategy_name})"
                    }
                elif self.trading_strategy == "trend-following" and price < sma_20 and sma_20 < sma_50:
                    return {
                        "strategy": "Trend Following",
                        "reason": f"Downtrend confirmed (Config: {strategy_name})"
                    }
                else:
                    return {
                        "strategy": strategy_name,
                        "reason": f"RL detected SELL signal using {strategy_name} strategy"
                    }
            
            return {"strategy": strategy_name, "reason": f"AI analysis using {strategy_name}"}
            
        except Exception as e:
            return {"strategy": "Default", "reason": f"Market analysis (Error: {str(e)}"}

    def calculate_confidence(self, action, price):
        """Calculate confidence score adjusted by config risk tolerance."""
        try:
            if self.agent and hasattr(self.agent, 'last_q_values'):
                q_values = self.agent.last_q_values
                max_q = max(q_values)
                min_q = min(q_values)
                confidence = (max_q - min_q) / (abs(max_q) + abs(min_q) + 1e-8)
            else:
                confidence = 0.6
            
            # Adjust based on market conditions
            try:
                current_data = self.env.df.iloc[self.env.t] if self.env.t < len(self.env.df) else self.env.df.iloc[-1]
                volume = current_data.get('volume', 1000000)
                avg_volume = self.env.df['volume'].iloc[max(0, self.env.t-20):self.env.t+1].mean()
                
                if volume > avg_volume * 1.5:
                    confidence += 0.1
                elif volume < avg_volume * 0.5:
                    confidence -= 0.1
            except Exception:
                pass
            
            # Clamp based on config min_confidence
            return max(self.min_confidence - 0.2, min(0.95, confidence))
            
        except Exception:
            return 0.6

    def calculate_risk_metrics(self, action, price, equity):
        """Calculate risk amount and profit target based on config risk settings."""
        try:
            # Use config risk per trade
            risk_amount = equity * self.risk_per_trade
            
            # Profit target based on risk-reward ratio from config
            risk_reward = self.config.get("riskRewardRatio", "1:2")
            reward_multiple = float(risk_reward.split(":")[1]) if ":" in risk_reward else 2.0
            
            if action == 1:  # BUY
                profit_target = price * (1 + self.risk_per_trade * reward_multiple)
            elif action == 2:  # SELL
                profit_target = price * (1 - self.risk_per_trade * reward_multiple)
            else:
                profit_target = 0
            
            return {
                "risk_amount": risk_amount,
                "profit_target": profit_target,
                "risk_percent": self.risk_per_trade * 100
            }
            
        except Exception:
            return {"risk_amount": 0, "profit_target": 0, "risk_percent": 3}

    def generate_technical_summary(self):
        """Generate technical analysis summary using config indicators."""
        try:
            current_data = self.env.df.iloc[self.env.t] if self.env.t < len(self.env.df) else self.env.df.iloc[-1]
            close_prices = self.env.df['close'].iloc[max(0, self.env.t-20):self.env.t+1]
            
            sma_20 = close_prices.rolling(20).mean().iloc[-1] if len(close_prices) >= 20 else current_data['close']
            current_price = current_data['close']
            volume = current_data.get('volume', 0)
            
            # RSI calculation if in indicators
            rsi = 50
            if "RSI" in self.indicators:
                price_changes = close_prices.diff().dropna()
                if len(price_changes) > 14:
                    gains = price_changes.where(price_changes > 0, 0).rolling(14).mean()
                    losses = (-price_changes.where(price_changes < 0, 0)).rolling(14).mean()
                    rsi = 100 - (100 / (1 + gains.iloc[-1] / (losses.iloc[-1] + 1e-8)))
            
            return {
                "rsi": rsi,
                "sma_20": sma_20,
                "current_price": current_price,
                "volume": volume,
                "trend": "Bullish" if current_price > sma_20 else "Bearish",
                "momentum": "Strong" if abs(current_price - sma_20) / sma_20 > 0.02 else "Moderate",
                "indicators_used": self.indicators
            }
            
        except Exception as e:
            return {
                "rsi": 50,
                "trend": "Neutral",
                "momentum": "Unknown",
                "error": str(e)
            }
    
    def get_action_name(self, action):
        """Get human-readable action name."""
        return {1: "BUY", 2: "SELL", 0: "HOLD"}.get(action, "UNKNOWN")

    def execute_trade_immediately(self, action, price, equity, state):
        """Execute trade immediately without user approval (auto-execute mode)."""
        try:
            action_name = self.get_action_name(action)
            print(f"\n{'═'*60}")
            print(f"⚡ AUTO-EXECUTING TRADE")
            print(f"{'═'*60}")
            print(f"Action: {action_name}")
            print(f"Symbol: {self.symbol}")
            print(f"Price: ${price:.2f}")
            print(f"Equity Before: ${equity:.2f}")
            print(f"Strategy: {self.trading_strategy}")
            print(f"Risk Tolerance: {self.config.get('riskTolerance')}")
            
            # Execute the action in the trading environment
            next_state, reward, done, info = self.env.step(action)
            actual_equity = float(info.get("equity", equity))
            
            print(f"\n📊 EXECUTION RESULTS:")
            print(f"   Reward: {reward:.4f}")
            print(f"   Equity After: ${actual_equity:.2f}")
            print(f"   P&L: ${actual_equity - equity:.2f}")
            print(f"   Done: {done}")
            print(f"   Reward Strategy: {self.reward_strategy}")
            print(f"   Reward Weights: Profit={self.reward_weights['profit']}, Risk={self.reward_weights['risk']}")
            
            # Update wallet and record trade
            self.update_wallet(reward)
            self.record_trade(action, reward, actual_equity)
            print(f"✅ Wallet updated | Trade recorded in database")
            
            # Store experience for learning
            try:
                self.memory.append((state, action, reward, next_state, done))
                self.agent.push(state, action, reward, next_state, done)
                add_experience(
                    self.user_id, self.asset_type, self.symbol,
                    state, int(action), float(reward), next_state, bool(done)
                )
                print(f"📚 Experience stored for learning")
            except Exception as e:
                print(f"⚠️ Experience storage failed: {e}")
            
            # Send execution notification to frontend
            notification = {
                "type": "trade_executed",
                "user_id": self.user_id,
                "symbol": self.symbol,
                "asset_type": self.asset_type,
                "action": int(action),
                "action_name": action_name,
                "price": float(price),
                "reward": float(reward),
                "equity": float(actual_equity),
                "timestamp": time.time(),
                "auto_executed": True
            }
            asyncio.run(self.notify_frontend(notification))
            print(f"🔔 WebSocket notification sent to frontend")
            print(f"{'═'*60}\n")
            
            return next_state, reward, done
            
        except Exception as e:
            print(f"❌ Failed to execute trade: {e}")
            import traceback
            traceback.print_exc()
            return state, 0, False

    def execute_approved_trade(self, proposal):
        """Execute a previously approved trade proposal."""
        try:
            action = proposal["action"]
            price = proposal["price"]
            equity = proposal["equity"]
            
            print(f"✅ EXECUTING APPROVED TRADE → {self.get_action_name(action)} {self.symbol} @ ${price:.2f}")
            
            # Execute the approved action in the trading environment
            if hasattr(self, 'env') and self.env:
                try:
                    current_state = self.env._get_state()
                    next_state, reward, done, info = self.env.step(action)
                    actual_equity = float(info.get("equity", equity))
                    
                    print(f"✅ Trade executed in environment: reward={reward:.4f}, equity={actual_equity:.2f}")
                    
                except Exception as e:
                    print(f"⚠️ Environment execution failed: {e}")
                    reward = -price * 0.01 if action == 1 else price * 0.01 if action == 2 else 0
                    actual_equity = equity
            else:
                reward = -price * 0.01 if action == 1 else price * 0.01 if action == 2 else 0
                actual_equity = equity
            
            # Update wallet and record trade
            self.update_wallet(reward)
            self.record_trade(action, reward, actual_equity)
            
            # Store experience for learning
            try:
                from app.rl.replay_store import add_experience
                dummy_state = [0] * 10
                add_experience(
                    self.user_id, self.asset_type, self.symbol,
                    dummy_state, int(action), float(reward), dummy_state, False
                )
                print(f"📚 Experience stored for approved {self.get_action_name(action)} trade")
            except Exception as e:
                print(f"⚠️ Experience storage failed: {e}")
            
            # Send execution confirmation
            confirmation = {
                "type": "executed",
                "user_id": self.user_id,
                "symbol": self.symbol,
                "asset_type": self.asset_type,
                "action": int(action),
                "reward": float(reward),
                "equity": float(equity),
                "timestamp": time.time()
            }
            asyncio.run(self.notify_frontend(confirmation))
            
            print(f"✅ TRADE COMPLETED → User {self.user_id}: {self.get_action_name(action)} {self.symbol} @ ${price:.2f} | Reward: {reward:.2f}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to execute trade: {e}")
            return False

    # -------------------- MAIN LOOP --------------------
    def run(self):
        """Main autonomous trading loop with config-driven behavior."""
        import time
        import sys
        from app.rl.replay_store import add_experience

        print("\n" + "="*80, flush=True)
        print("🚀 INITIALIZING RL TRADING BOT", flush=True)
        print("="*80, flush=True)
        
        self.load_model()
        state = self.env.reset()

        mode = "AUTO-EXECUTE" if self.auto_execute else "MANUAL APPROVAL"
        print(f"\n📊 BOT CONFIGURATION:", flush=True)
        print(f"   Symbol: {self.asset_type}:{self.symbol}", flush=True)
        print(f"   User ID: {self.user_id}", flush=True)
        print(f"   Mode: {mode}", flush=True)
        print(f"   Interval: {self.interval} seconds", flush=True)
        print(f"   Strategy: {self.trading_strategy}", flush=True)
        print(f"   Risk Per Trade: {self.risk_per_trade*100:.1f}%", flush=True)
        print(f"   Max Exposure: {self.max_exposure*100:.1f}%", flush=True)
        print(f"   Risk Tolerance: {self.config.get('riskTolerance')}", flush=True)
        print(f"   Reward Strategy: {self.reward_strategy}", flush=True)
        print(f"   Continuous Learning: {self.continuous_learning}", flush=True)
        print(f"   Learn Every: {self.learn_every} trades", flush=True)
        print(f"   Indicators: {', '.join(self.indicators)}", flush=True)
        
        if self.auto_execute:
            base_exploration = 0.2
            self.exploration_rate = base_exploration * self.exploration_multiplier
            print(f"\n⚡ AUTO-EXECUTE MODE ENABLED", flush=True)
            print(f"   Exploration Rate: {self.exploration_rate*100:.0f}%", flush=True)
            print(f"   Bot will execute trades AUTOMATICALLY every {self.interval}s", flush=True)
        else:
            self.exploration_rate = 0.8
            print(f"\n⛔ MANUAL APPROVAL MODE ENABLED", flush=True)
            print(f"   Exploration Rate: {self.exploration_rate*100:.0f}%", flush=True)
            print(f"   Bot will create PROPOSALS requiring user approval", flush=True)
            
        print(f"\n⏰ Starting trading loop... First action in {self.interval} seconds", flush=True)
        print("="*80 + "\n", flush=True)
        sys.stdout.flush()

        cycle = 0
        while True:
            try:
                cycle += 1
                print(f"\n{'─'*80}", flush=True)
                print(f"🔄 CYCLE #{cycle} - {self.symbol} at {time.strftime('%H:%M:%S')}", flush=True)
                print(f"{'─'*80}", flush=True)
                sys.stdout.flush()
                
                self.current_state = state
                
                # Decide action with config-based exploration
                print(f"🧠 Making decision with {self.exploration_rate*100:.0f}% exploration rate...")
                action = self.agent.act(state, eps=self.exploration_rate)
                action_name = self.get_action_name(action)
                print(f"🎯 Decision: {action_name} (action={action})")
                
                # Get real-time price
                print(f"💹 Fetching current market price...")
                try:
                    from app.data.loader import fetch_realtime_price
                    realtime_data = fetch_realtime_price(self.symbol, self.asset_type)
                    current_price = float(realtime_data["price"])
                    print(f"✅ Real-time price: ${current_price:.2f}")
                except Exception as e:
                    current_data = self.env.df.iloc[self.env.t] if self.env.t < len(self.env.df) else self.env.df.iloc[-1]
                    current_price = float(current_data["close"])
                    print(f"⚠️ Using cached price: ${current_price:.2f} (API error: {e})")
                
                current_equity = self.env.cash + self.env.position * current_price
                print(f"💰 Portfolio: Cash=${self.env.cash:.2f} | Position={self.env.position} | Equity=${current_equity:.2f}")
                sys.stdout.flush()

                # Handle actions
                if action in [1, 2]:  # BUY or SELL
                    print(f"\n{'▸'*40}", flush=True)
                    print(f"📌 TRADE SIGNAL: {action_name} @ ${current_price:.2f}", flush=True)
                    print(f"{'▸'*40}", flush=True)
                    sys.stdout.flush()
                    
                    if self.auto_execute:
                        print(f"⚡ AUTO-EXECUTE MODE: Executing trade immediately...")
                        print(f"   Risk Amount: ${current_equity * self.risk_per_trade:.2f} ({self.risk_per_trade*100:.1f}%)")
                        next_state, reward, done = self.execute_trade_immediately(
                            action, current_price, current_equity, state
                        )
                        print(f"✅ Trade executed | Reward: {reward:.4f}")
                        state = next_state
                        if done:
                            print(f"🔄 Episode complete, resetting environment...")
                            state = self.env.reset()
                    else:
                        print(f"📋 MANUAL MODE: Creating proposal for user approval...")
                        proposal_state = state.copy() if hasattr(state, 'copy') else state
                        
                        try:
                            # Calculate strategy analysis for logging
                            strategy_analysis = self.analyze_market_strategy(action, current_price)
                            confidence = self.calculate_confidence(action, current_price)
                            risk_metrics = self.calculate_risk_metrics(action, current_price, current_equity)
                            
                            print(f"   Strategy: {strategy_analysis['strategy']}")
                            print(f"   Reason: {strategy_analysis['reason']}")
                            print(f"   Confidence: {confidence*100:.0f}%")
                            print(f"   Risk Amount: ${risk_metrics['risk_amount']:.2f}")
                            print(f"   Profit Target: ${risk_metrics['profit_target']:.2f}")
                            
                            proposal_created = self.create_proposal(
                                action=action,
                                price=current_price,
                                equity=current_equity
                            )
                            
                            if proposal_created:
                                print(f"✅ PROPOSAL SENT TO FRONTEND via WebSocket")
                                print(f"⏳ Waiting for user to ACCEPT or REJECT...")
                                
                                proposal_key = (self.user_id, self.symbol)
                                if proposal_key not in trade_proposals:
                                    trade_proposals[proposal_key] = {}
                                trade_proposals[proposal_key]['proposal_state'] = proposal_state
                                trade_proposals[proposal_key]['proposal_action'] = action
                            else:
                                print(f"⏸️ Proposal NOT created (previous proposal still pending)")
                                
                        except Exception as e:
                            print(f"❌ Failed to create proposal: {e}")
                            import traceback
                            traceback.print_exc()
                        
                        self.env.t = min(self.env.t + 1, len(self.env.df) - 1)
                    
                elif action == 0:  # HOLD action
                    print(f"⏸️ HOLD signal - No trade executed")
                    print(f"   Current position: {self.env.position} shares")
                    print(f"   Cash available: ${self.env.cash:.2f}")
                    
                    next_state, reward, done, info = self.env.step(action)
                    
                    try:
                        self.update_wallet(reward)
                        self.memory.append((state, action, reward, next_state, done))
                        self.agent.push(state, action, reward, next_state, done)
                        add_experience(
                            self.user_id, self.asset_type, self.symbol,
                            state, int(action), float(reward), next_state, bool(done)
                        )
                        
                        print(f"✅ HOLD executed | Reward: {reward:.4f}")
                        state = next_state
                        if done:
                            print(f"🔄 Episode complete, resetting environment...")
                            state = self.env.reset()
                            
                    except Exception as e:
                        print(f"⚠️ HOLD processing failed: {e}")
                
                else:
                    print(f"⚠️ Unknown action: {action}")
                    self.env.t = min(self.env.t + 1, len(self.env.df) - 1)

                # Learning and checkpointing
                self.trade_count += 1
                
                if self.continuous_learning and self.trade_count % self.learn_every == 0:
                    print(f"\n📚 LEARNING TRIGGERED (every {self.learn_every} trades)")
                    self.online_learn()
                    
                if self.trade_count % self.checkpoint_every == 0:
                    print(f"💾 CHECKPOINT: Saving model (every {self.checkpoint_every} trades)")
                    self.save_model()

                print(f"\n⏰ Sleeping for {self.interval} seconds until next cycle...")
                print(f"{'─'*80}\n")
                time.sleep(self.interval)

            except Exception as e:
                print(f"\n❌ RUNTIME ERROR in cycle #{cycle}:")
                print(f"   Error: {e}")
                import traceback
                traceback.print_exc()
                print(f"⏰ Retrying in {self.interval} seconds...")
                time.sleep(self.interval)

    def online_learn(self):
        """Perform online learning from replay memory."""
        if len(self.memory) < 32:  # Minimum batch size
            return
        
        try:
            # Sample from replay memory and train
            batch_size = min(32, len(self.memory))
            batch = list(self.memory)[-batch_size:]  # Use recent experiences
            
            # Simple learning - in a real implementation, this would be more sophisticated
            for state, action, reward, next_state, done in batch:
                self.agent.learn(state, action, reward, next_state, done)
            
            print(f"📚 Online learning completed: {batch_size} experiences")
        except Exception as e:
            print(f"⚠️ Online learning failed: {e}")

    def save_model(self):
        """Save the current model to disk."""
        try:
            import os
            os.makedirs("models", exist_ok=True)
            torch.save(self.agent.q.state_dict(), self.model_path)
            print(f"💾 Model saved: {self.model_path}")
        except Exception as e:
            print(f"⚠️ Failed to save model: {e}")

