import time
import torch
import json
import asyncio
import numpy as np
import pandas as pd
import os
from app.rl.dqn import DQNAgent
from app.rl.env import TradingEnv
from app.rl.portfolio_env import PortfolioEnv
from app.db import get_db_connection
from app.rl.replay_store import add_experience
from collections import deque
import queue as q

# Global storage for trade proposals
trade_proposals = {}

class RLTrader:
    """Autonomous RL-based trader that trades one action per interval.
    Supports both single-asset and multi-asset portfolio trading.
    """

    def __init__(self, user_id, symbol, asset_type, interval_sec=30, auto_execute=True, 
                 symbols=None, use_per=True):
        """
        Args:
            user_id: User ID
            symbol: Single symbol (for backward compatibility)
            asset_type: Asset type for single symbol
            interval_sec: Trading interval in seconds
            auto_execute: Whether to auto-execute trades
            symbols: List of (symbol, asset_type) tuples for multi-asset trading.
                    If provided, overrides symbol/asset_type parameters.
            use_per: Whether to use Prioritized Experience Replay (default: True)
        """
        self.user_id = user_id
        self.interval = interval_sec
        self.auto_execute = auto_execute
        self.running = True  # Flag to control bot execution
        self.use_per = use_per
        
        # Determine if multi-asset or single-asset
        if symbols and isinstance(symbols, list) and len(symbols) > 1:
            # Multi-asset portfolio mode
            self.is_multi_asset = True
            self.symbols = symbols  # List of (symbol, asset_type) tuples
            self.symbol = None  # Not used in multi-asset mode
            self.asset_type = None  # Not used in multi-asset mode
            self.model_path = f"models/dqn_portfolio_{user_id}.pth"
            print(f"📊 Multi-asset portfolio mode: {len(symbols)} assets")
        else:
            # Single-asset mode (backward compatible)
            self.is_multi_asset = False
            if symbols and isinstance(symbols, list) and len(symbols) == 1:
                # Single symbol from list
                self.symbol, self.asset_type = symbols[0]
            else:
                # Direct symbol/asset_type
                self.symbol = symbol
                self.asset_type = asset_type
            self.symbols = [(self.symbol, self.asset_type)]
            self.model_path = f"models/dqn_{self.asset_type}_{self.symbol}.pth"
            print(f"📊 Single-asset mode: {self.symbol} ({self.asset_type})")

        # Load RL configuration FIRST
        self.config = self.load_rl_config()
        self.apply_config()

        # Get user's actual wallet balance from database
        self.conn = get_db_connection()
        user_wallet = self.get_user_wallet()
        
        # Environment and model - initialize with user's actual wallet
        if self.is_multi_asset:
            self.env = PortfolioEnv(self.symbols, init_cash=user_wallet)
            print(f"✅ Portfolio environment initialized with {len(self.symbols)} assets")
        else:
            self.env = TradingEnv(self.symbol, self.asset_type, init_cash=user_wallet)
            print(f"✅ Single-asset environment initialized for {self.symbol}")
        
        self.agent = None

        # Replay memory for continuous learning
        self.memory = deque(maxlen=1000)

        # Learning frequency settings (from config)
        self.learn_every = self.config_learn_every
        self.checkpoint_every = self.config_checkpoint_every
        self.trade_count = 0
        self.current_state = None
        
        # Store latest decision for explanation
        self.latest_decision = {
            "action": 0,  # HOLD
            "action_name": "HOLD",
            "symbol": self.symbol if not self.is_multi_asset else "PORTFOLIO",
            "price": 0.0,
            "timestamp": time.time(),
            "q_values": None,
            "confidence": 0.0,
            "strategy_reason": "",
            "technical_indicators": {}
        }

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
            # Initialize agent with PER enabled
            self.agent = DQNAgent(len(dummy_state), use_per=self.use_per)
            self.agent.q.load_state_dict(torch.load(self.model_path))
            self.agent.q.eval()
            print(f"✅ Loaded model {self.model_path} (PER: {self.use_per})")
        except Exception as e:
            print(f"⚠️ No model found ({e}), using random policy")
            dummy_state = self.env.reset()
            # Initialize agent with PER enabled
            self.agent = DQNAgent(len(dummy_state), use_per=self.use_per)
            # For untrained models, use high exploration (80%) to encourage trading
            self.agent.epsilon = 0.8
            print(f"🎲 Exploration rate set to 80% for untrained model (PER: {self.use_per})")

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

    def record_trade(self, action, reward, equity, use_price=None):
        """Insert trade record into bot_trades table and update portfolio."""
        if not self.conn:
            print(f"❌ Cannot record trade: database connection not available")
            return
        
        cur = None
        try:
            cur = self.conn.cursor()
            
            # Get price - prefer provided price, then proposal price, then current price
            if use_price and use_price > 0:
                current_price = float(use_price)
                print(f"📊 Using provided price: ${current_price:.2f}")
            elif hasattr(self, '_last_proposal_price') and self._last_proposal_price > 0:
                current_price = float(self._last_proposal_price)
                print(f"📊 Using proposal price: ${current_price:.2f}")
            else:
                try:
                    current_price = self.get_current_price()
                    if current_price <= 0:
                        # Try to get price from proposal or use a fallback
                        print(f"⚠️ Current price is 0, using equity-based estimate")
                        current_price = equity / 100 if equity > 0 else 100.0
                except Exception as e:
                    print(f"⚠️ Error getting current price: {e}, using fallback")
                    current_price = equity / 100 if equity > 0 else 100.0
            
            # Determine action name and quantity
            action_name = self.get_action_name(action)
            quantity = 1  # Default quantity
            
            # Record ALL actions including HOLD
            print(f"📝 Recording trade: {action_name} {self.symbol} @ ${current_price:.2f} for user {self.user_id}")
            
            # Insert into bot_trades table for history
            cur.execute("""
                INSERT INTO bot_trades 
                (user_id, symbol, asset_type, action, price, quantity, reward, equity, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """, (
                self.user_id, 
                self.symbol, 
                self.asset_type, 
                action_name,  # 'BUY' or 'SELL'
                float(current_price),
                quantity,
                float(reward), 
                float(equity)
            ))
            print(f"✅ Inserted into bot_trades: {action_name} {self.symbol}")
            
            # Update portfolio table for BUY/SELL actions
            if action == 1:  # BUY
                # Check if position exists
                cur.execute("""
                    SELECT quantity, avg_price FROM portfolio 
                    WHERE user_id = %s AND symbol = %s AND asset_type = %s
                """, (self.user_id, self.symbol, self.asset_type))
                
                existing = cur.fetchone()
                
                if existing:
                    # Update existing position (average price calculation)
                    old_qty = float(existing[0])
                    old_avg = float(existing[1])
                    new_qty = old_qty + quantity
                    new_avg = ((old_qty * old_avg) + (quantity * current_price)) / new_qty
                    
                    cur.execute("""
                        UPDATE portfolio 
                        SET quantity = %s, avg_price = %s
                        WHERE user_id = %s AND symbol = %s AND asset_type = %s
                    """, (new_qty, new_avg, self.user_id, self.symbol, self.asset_type))
                    print(f"📊 Portfolio updated: {self.symbol} quantity {old_qty} → {new_qty}, avg ${old_avg:.2f} → ${new_avg:.2f}")
                else:
                    # Insert new position
                    cur.execute("""
                        INSERT INTO portfolio (user_id, symbol, asset_type, quantity, avg_price)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (self.user_id, self.symbol, self.asset_type, quantity, current_price))
                    print(f"📊 Portfolio created: {self.symbol} quantity {quantity} @ ${current_price:.2f}")
                    
            elif action == 2:  # SELL
                # Reduce position
                cur.execute("""
                    SELECT quantity FROM portfolio 
                    WHERE user_id = %s AND symbol = %s AND asset_type = %s
                """, (self.user_id, self.symbol, self.asset_type))
                
                existing = cur.fetchone()
                
                if existing and float(existing[0]) >= quantity:
                    new_qty = float(existing[0]) - quantity
                    
                    if new_qty > 0:
                        cur.execute("""
                            UPDATE portfolio 
                            SET quantity = %s
                            WHERE user_id = %s AND symbol = %s AND asset_type = %s
                        """, (new_qty, self.user_id, self.symbol, self.asset_type))
                        print(f"📊 Portfolio reduced: {self.symbol} quantity {existing[0]} → {new_qty}")
                    else:
                        # Close position completely
                        cur.execute("""
                            DELETE FROM portfolio 
                            WHERE user_id = %s AND symbol = %s AND asset_type = %s
                        """, (self.user_id, self.symbol, self.asset_type))
                        print(f"📊 Portfolio position closed: {self.symbol}")
                else:
                    print(f"⚠️ Cannot SELL {self.symbol}: No position or insufficient quantity")
            
            # Commit all changes
            self.conn.commit()
            print(f"✅ Database transaction committed successfully")
            
        except Exception as e:
            print(f"❌ Error recording trade: {e}")
            import traceback
            traceback.print_exc()
            if self.conn:
                try:
                    self.conn.rollback()
                    print(f"🔄 Database transaction rolled back")
                except:
                    pass
        finally:
            if cur:
                cur.close()
            print(f"📝 Trade recording completed: {action_name} {self.symbol} @ ${current_price:.2f}")

    # -------------------- NOTIFICATIONS --------------------
    def _serialize_message(self, message: dict) -> dict:
        """Convert numpy arrays and other non-JSON-serializable types to JSON-compatible types."""
        import numpy as np
        
        def convert_value(value):
            if isinstance(value, np.ndarray):
                return value.tolist()
            elif isinstance(value, (np.integer, np.floating)):
                return float(value)
            elif isinstance(value, dict):
                return {k: convert_value(v) for k, v in value.items()}
            elif isinstance(value, (list, tuple)):
                return [convert_value(item) for item in value]
            else:
                return value
        
        return convert_value(message)
    
    def notify_frontend_sync(self, message: dict):
        """Send real-time message via WebSocket using message queue (thread-safe, synchronous)."""
        from app.api import ws_message_queues, active_connections
        import asyncio
        import json
        
        print(f"🔌 Attempting to send WebSocket message to user {self.user_id}")
        print(f"🔌 Available message queues: {list(ws_message_queues.keys())}")
        print(f"🔌 Active WebSocket connections: {list(active_connections.keys())}")
        
        # Serialize message to ensure all numpy arrays are converted to lists
        try:
            serialized_message = self._serialize_message(message)
        except Exception as e:
            print(f"⚠️ Error serializing message: {e}, using original message")
            serialized_message = message
        
        # First, try to send directly if WebSocket is connected
        ws = active_connections.get(self.user_id)
        if ws:
            try:
                # Create message queue if it doesn't exist (for consistency)
                if self.user_id not in ws_message_queues:
                    ws_message_queues[self.user_id] = q.Queue(maxsize=100)
                
                # Try to send directly via WebSocket
                message_json = json.dumps(serialized_message)
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(ws.send_text(message_json))
                    print(f"✅ Message sent directly via WebSocket to user {self.user_id}")
                    print(f"📋 Message type: {serialized_message.get('type')}, Symbol: {serialized_message.get('symbol')}")
                    return True
                finally:
                    loop.close()
            except Exception as e:
                print(f"⚠️ Direct WebSocket send failed: {e}, falling back to queue")
                import traceback
                traceback.print_exc()
                # Fall through to queue method
        
        # Fallback: Use message queue (will be picked up by WebSocket loop)
        try:
            # Create message queue if it doesn't exist yet (proactive creation)
            if self.user_id not in ws_message_queues:
                ws_message_queues[self.user_id] = q.Queue(maxsize=100)
                print(f"📦 Created message queue for user {self.user_id} (WebSocket will connect later)")
            
            try:
                ws_message_queues[self.user_id].put_nowait(serialized_message)
                print(f"✅ Message queued for WebSocket delivery to user {self.user_id}")
                print(f"📋 Message type: {message.get('type')}, Symbol: {message.get('symbol')}")
                return True
            except q.Full:
                print(f"⚠️ WebSocket message queue full for user {self.user_id}")
                return False
        except Exception as e:
            print(f"❌ Failed to queue WebSocket message: {e}")
            import traceback
            traceback.print_exc()
            return False

    def create_proposal(self, action, price, equity):
        """Create an enhanced trade proposal with strategy analysis and confidence scoring."""
        # Handle both single-asset and multi-asset modes
        if self.is_multi_asset:
            # For multi-asset, use first symbol for proposal key (or create portfolio-level proposal)
            primary_symbol = self.symbols[0][0] if self.symbols else "PORTFOLIO"
            primary_asset_type = self.symbols[0][1] if self.symbols else "portfolio"
            key = (self.user_id, primary_symbol, primary_asset_type)
        else:
            # Include asset_type in key to differentiate between stock/crypto/derivative
            key = (self.user_id, self.symbol, self.asset_type)
        
        print(f"\n{'┌'+'─'*58+'┐'}")
        print(f"│ 📋 CREATING TRADE PROPOSAL{' '*30}│")
        print(f"{'└'+'─'*58+'┘'}")
        
        # Check if there's already a pending proposal
        if key in trade_proposals:
            # Check if proposal is expired (older than 2 minutes)
            existing_proposal = trade_proposals[key]
            proposal_age = time.time() - existing_proposal.get('timestamp', 0)
            
            if proposal_age > 120:  # 2 minutes timeout
                print(f"⏰ Previous proposal expired (age: {proposal_age:.0f}s), creating new one...")
                del trade_proposals[key]  # Clear expired proposal
            else:
                print(f"⏸️ Previous proposal still pending for {self.symbol} (age: {proposal_age:.0f}s)")
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
        
        # Determine symbol and asset_type for proposal
        if self.is_multi_asset:
            proposal_symbol = self.symbols[0][0] if self.symbols else "PORTFOLIO"
            proposal_asset_type = self.symbols[0][1] if self.symbols else "portfolio"
        else:
            proposal_symbol = self.symbol
            proposal_asset_type = self.asset_type
        
        proposal = {
            "type": "proposal",
            "user_id": self.user_id,
            "symbol": proposal_symbol,
            "asset_type": proposal_asset_type,
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
        print(f"💾 Proposal stored in memory with key: {key}")
        try:
            # Serialize before printing to avoid numpy array issues
            serialized_proposal = self._serialize_message(proposal)
            print(f"📋 Proposal data: {json.dumps(serialized_proposal, indent=2)}")
        except Exception as e:
            print(f"📋 Proposal created (serialization skipped: {e})")
        
        # Ensure proposal has all required fields for frontend
        proposal["action_name"] = self.get_action_name(action)
        proposal["user_id"] = str(self.user_id)  # Ensure user_id is string for consistency
        
        # Send proposal via WebSocket
        print(f"📡 Sending proposal to frontend via WebSocket...")
        if self.is_multi_asset:
            print(f"📋 Proposal details: {self.get_action_name(action)} Portfolio ({len(self.symbols)} assets) @ ${price:.2f}")
        else:
            print(f"📋 Proposal details: {self.get_action_name(action)} {self.symbol} @ ${price:.2f}")
        
        sent = self.notify_frontend_sync(proposal)
        
        if sent:
            print(f"✅ Proposal successfully queued for WebSocket delivery")
        else:
            print(f"⚠️ Proposal queued but WebSocket not connected yet - will be sent when user connects")
        
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
            # Handle multi-asset mode
            if self.is_multi_asset:
                # For multi-asset, use first asset's data
                if hasattr(self.env, 'asset_data') and self.symbols:
                    first_key = self.symbols[0]
                    if first_key in self.env.asset_data:
                        df = self.env.asset_data[first_key]
                        current_data = df.iloc[self.env.t] if self.env.t < len(df) else df.iloc[-1]
                    else:
                        return {"strategy": "Portfolio", "reason": "Multi-asset portfolio strategy"}
                else:
                    return {"strategy": "Portfolio", "reason": "Multi-asset portfolio strategy"}
            else:
                current_data = self.env.df.iloc[self.env.t] if self.env.t < len(self.env.df) else self.env.df.iloc[-1]
            
            # Calculate SMAs (handle both single and multi-asset)
            if self.is_multi_asset:
                # For multi-asset, use first asset's data for SMAs
                if hasattr(self.env, 'asset_data') and self.symbols:
                    first_key = self.symbols[0]
                    if first_key in self.env.asset_data:
                        df = self.env.asset_data[first_key]
                        close_prices = df['close'].iloc[max(0, self.env.t-20):self.env.t+1]
                        sma_20 = close_prices.rolling(20).mean().iloc[-1] if len(close_prices) >= 20 else price
                        sma_50 = df['close'].iloc[max(0, self.env.t-50):self.env.t+1].rolling(50).mean().iloc[-1] if self.env.t >= 50 else price
                    else:
                        sma_20 = price
                        sma_50 = price
                else:
                    sma_20 = price
                    sma_50 = price
            else:
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
                if not self.is_multi_asset:
                    # Only adjust for single-asset mode
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
            return float(max(self.min_confidence - 0.2, min(0.95, confidence)))
            
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
                "risk_amount": float(risk_amount),
                "profit_target": float(profit_target),
                "risk_percent": float(self.risk_per_trade * 100)
            }
            
        except Exception:
            return {"risk_amount": 0.0, "profit_target": 0.0, "risk_percent": 3.0}

    def generate_technical_summary(self):
        """Generate technical analysis summary using config indicators."""
        try:
            # Handle multi-asset mode
            if self.is_multi_asset:
                # For multi-asset, return portfolio-level summary
                return {
                    "portfolio_size": len(self.symbols),
                    "equity": float(self.env.equity),
                    "cash_ratio": float(self.env.cash / max(self.env.equity, 1e-9)),
                    "num_positions": sum(1 for qty in self.env.positions.values() if qty > 0),
                    "trend": "Portfolio",
                    "momentum": "Multi-asset",
                    "indicators_used": self.indicators
                }
            
            current_data = self.env.df.iloc[self.env.t] if self.env.t < len(self.env.df) else self.env.df.iloc[-1]
            close_prices = self.env.df['close'].iloc[max(0, self.env.t-20):self.env.t+1]
            
            # Convert to float to avoid Decimal/float issues
            current_price = float(current_data['close'])
            volume = float(current_data.get('volume', 0))
            
            # Calculate SMA_20
            if len(close_prices) >= 20:
                sma_20 = float(close_prices.rolling(20).mean().iloc[-1])
            else:
                sma_20 = current_price
            
            # RSI calculation if in indicators
            rsi = 50.0
            if "RSI" in self.indicators:
                try:
                    price_changes = close_prices.diff().dropna()
                    if len(price_changes) > 14:
                        gains = price_changes.where(price_changes > 0, 0).rolling(14).mean()
                        losses = (-price_changes.where(price_changes < 0, 0)).rolling(14).mean()
                        gains_val = float(gains.iloc[-1]) if not pd.isna(gains.iloc[-1]) else 0.0
                        losses_val = float(losses.iloc[-1]) if not pd.isna(losses.iloc[-1]) else 0.0
                        if losses_val > 0:
                            rsi = 100.0 - (100.0 / (1.0 + gains_val / losses_val))
                except Exception:
                    rsi = 50.0
            
            # Calculate trend and momentum
            price_diff = abs(current_price - sma_20)
            momentum_threshold = sma_20 * 0.02 if sma_20 > 0 else 0.02
            
            return {
                "rsi": float(rsi),
                "sma_20": float(sma_20),
                "current_price": float(current_price),
                "volume": float(volume),
                "trend": "Bullish" if current_price > sma_20 else "Bearish",
                "momentum": "Strong" if price_diff > momentum_threshold else "Moderate",
                "indicators_used": self.indicators
            }
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "rsi": 50.0,
                "sma_20": 0.0,
                "current_price": 0.0,
                "volume": 0.0,
                "trend": "Neutral",
                "momentum": "Unknown",
                "error": str(e)
            }
    
    def get_action_name(self, action):
        """Get human-readable action name."""
        return {1: "BUY", 2: "SELL", 0: "HOLD"}.get(action, "UNKNOWN")
    
    def generate_decision_explanation(self, action=None, proposal=None):
        """Generate a detailed voice explanation of why the RL bot made this decision."""
        try:
            # Use latest decision if action not provided
            if action is None and hasattr(self, 'latest_decision'):
                action = self.latest_decision.get("action", 0)
                latest = self.latest_decision
            else:
                latest = self.latest_decision if hasattr(self, 'latest_decision') else {}
            
            action_name = self.get_action_name(action)
            symbol_name = latest.get("symbol", self.symbol if not self.is_multi_asset else "PORTFOLIO")
            current_price = latest.get("price", 0.0)
            
            # Start with clear action and symbol
            if action == 1:
                explanation_parts = [f"I decided to BUY {symbol_name}"]
            elif action == 2:
                explanation_parts = [f"I decided to SELL {symbol_name}"]
            else:
                explanation_parts = [f"I decided to HOLD {symbol_name}"]
            
            # Add price if available
            if current_price > 0:
                explanation_parts.append(f"at the current price of ${current_price:.2f}")
            
            # Add symbol/portfolio info for clarity
            if self.is_multi_asset:
                explanation_parts.append(f"This is for my portfolio with {len(self.symbols)} assets")
            else:
                explanation_parts.append(f"{symbol_name} is the asset I'm currently monitoring")
            
            # For HOLD actions, add specific reasoning
            if action == 0:
                explanation_parts.append(f"After analyzing the market conditions, I determined that holding is the best action right now")
            
            # Get Q-values and confidence from latest decision or agent
            q_values = latest.get("q_values")
            if not q_values and hasattr(self, 'agent') and self.agent and hasattr(self.agent, 'last_q_values'):
                q_values = self.agent.last_q_values
            
            if q_values and len(q_values) >= 3:
                action_q = q_values[action] if action < len(q_values) else q_values[0]
                buy_q = q_values[1] if len(q_values) > 1 else 0
                sell_q = q_values[2] if len(q_values) > 2 else 0
                hold_q = q_values[0] if len(q_values) > 0 else 0
                max_q = max(q_values)
                min_q = min(q_values)
                
                # Calculate confidence
                if max_q != min_q:
                    confidence = (action_q - min_q) / (max_q - min_q)
                    confidence_percent = int(confidence * 100)
                    explanation_parts.append(f"My confidence level is {confidence_percent} percent")
                    
                    # Store confidence
                    self.latest_decision["confidence"] = confidence
                
                # Detailed Q-value comparison for explanation
                if action == 0:  # HOLD
                    if buy_q > hold_q and sell_q > hold_q:
                        # Both BUY and SELL scored higher, but we're holding - explain why
                        explanation_parts.append(f"Although buying scored {buy_q:.2f} and selling scored {sell_q:.2f}, I'm choosing to hold with a score of {hold_q:.2f} because the market conditions are uncertain")
                    elif buy_q > hold_q:
                        explanation_parts.append(f"Buying scored {buy_q:.2f} which is higher than holding's {hold_q:.2f}, but I'm waiting for better entry conditions")
                    elif sell_q > hold_q:
                        explanation_parts.append(f"Selling scored {sell_q:.2f} which is higher than holding's {hold_q:.2f}, but I'm maintaining my position to avoid premature exits")
                    else:
                        explanation_parts.append(f"Holding scored {hold_q:.2f}, which is the highest among all actions, indicating this is the optimal decision right now")
                else:
                    # For BUY or SELL, compare with alternatives
                    other_actions = [i for i in range(3) if i != action]
                    other_q_values = [q_values[i] for i in other_actions if i < len(q_values)]
                    if other_q_values:
                        max_other = max(other_q_values)
                        if action_q > max_other:
                            advantage = ((action_q - max_other) / abs(max_other + 1e-8)) * 100
                            explanation_parts.append(f"This {action_name} action scored {advantage:.1f} percent higher than the alternatives")
                        else:
                            explanation_parts.append(f"This {action_name} action scored {action_q:.2f}, which is my best option given current conditions")
            
            # Add strategy information from proposal or latest decision
            strategy_reason = latest.get("strategy_reason", "")
            if proposal and proposal.get("strategy"):
                strategy = proposal.get("strategy", "")
                reason = proposal.get("reason", "")
                explanation_parts.append(f"Based on the {strategy} strategy")
                if reason:
                    explanation_parts.append(reason)
                    self.latest_decision["strategy_reason"] = reason
            elif strategy_reason:
                explanation_parts.append(strategy_reason)
            elif hasattr(self, 'trading_strategy'):
                strategy_name = self.trading_strategy.replace("-", " ").title()
                explanation_parts.append(f"I'm using the {strategy_name} trading strategy")
                
                # Add specific reason based on action and strategy
                if action == 1:  # BUY
                    explanation_parts.append(f"For buying {symbol_name}, the {strategy_name} strategy suggests entering a position now")
                elif action == 2:  # SELL
                    explanation_parts.append(f"For selling {symbol_name}, the {strategy_name} strategy suggests exiting or reducing position now")
                else:  # HOLD
                    explanation_parts.append(f"For holding {symbol_name}, the {strategy_name} strategy suggests waiting for clearer signals before making a move")
                    explanation_parts.append(f"I'm monitoring the market and will act when conditions align with my strategy")
            
            # Add technical indicators if available (from proposal or latest decision)
            tech = latest.get("technical_indicators", {})
            if proposal and proposal.get("technical_summary"):
                tech = proposal.get("technical_summary", {})
            
            if isinstance(tech, dict) and tech:
                if "rsi" in tech:
                    rsi = tech["rsi"]
                    if rsi > 70:
                        explanation_parts.append(f"For {symbol_name}, the RSI indicator shows {rsi:.0f}, which indicates overbought conditions")
                    elif rsi < 30:
                        explanation_parts.append(f"For {symbol_name}, the RSI indicator shows {rsi:.0f}, which indicates oversold conditions")
                    else:
                        explanation_parts.append(f"For {symbol_name}, the RSI is at {rsi:.0f}, showing neutral momentum")
                
                if "trend" in tech:
                    trend = tech["trend"]
                    explanation_parts.append(f"The trend analysis for {symbol_name} indicates a {trend} market")
                
                if "sma_20" in tech and current_price > 0:
                    sma_20 = tech["sma_20"]
                    if current_price > sma_20:
                        explanation_parts.append(f"The current price of ${current_price:.2f} is above the 20-day moving average of ${sma_20:.2f}")
                    elif current_price < sma_20:
                        explanation_parts.append(f"The current price of ${current_price:.2f} is below the 20-day moving average of ${sma_20:.2f}")
            
            # Add risk information
            if proposal and proposal.get("risk_amount"):
                risk = proposal.get("risk_amount", 0)
                explanation_parts.append(f"The risk for this trade is ${risk:.2f}")
            
            # Add confidence from proposal if available
            if proposal and proposal.get("confidence"):
                conf = proposal.get("confidence", 0.5)
                conf_percent = int(conf * 100)
                if conf_percent > 70:
                    explanation_parts.append(f"I am highly confident in this decision")
                elif conf_percent > 50:
                    explanation_parts.append(f"I am moderately confident in this decision")
                else:
                    explanation_parts.append(f"I have lower confidence, but the analysis suggests this action")
            
            # Add exploration vs exploitation info
            if hasattr(self, 'exploration_rate'):
                if self.exploration_rate > 0.5:
                    exploration_pct = int(self.exploration_rate * 100)
                    explanation_parts.append(f"I am currently in exploration mode with {exploration_pct} percent exploration rate, which means I'm trying different strategies to learn and improve")
                    if action == 0:
                        explanation_parts.append("During exploration, holding allows me to observe market behavior without committing capital")
                else:
                    explanation_parts.append("I am using my learned knowledge and experience to make this decision")
            
            # Add position context for HOLD
            if action == 0:
                if hasattr(self.env, 'position'):
                    position = self.env.position
                    if position > 0:
                        explanation_parts.append(f"I currently hold {position} shares of {symbol_name}, and I'm maintaining this position")
                    elif position == 0:
                        explanation_parts.append(f"I have no current position in {symbol_name}, and I'm waiting for the right opportunity to enter")
                
                if hasattr(self.env, 'cash'):
                    cash = self.env.cash
                    if cash > 0:
                        explanation_parts.append(f"I have ${cash:,.2f} in cash available, but I'm waiting for better market conditions before deploying it")
            
            # Add portfolio context for multi-asset
            if self.is_multi_asset and hasattr(self.env, 'equity'):
                equity = self.env.equity
                cash_ratio = self.env.cash / max(equity, 1e-9)
                num_positions = sum(1 for qty in self.env.positions.values() if qty > 0)
                explanation_parts.append(f"Current portfolio equity is ${equity:,.2f}")
                if num_positions > 0:
                    explanation_parts.append(f"I am managing {num_positions} active positions")
                if cash_ratio > 0.5:
                    explanation_parts.append("I have significant cash available for new positions")
            
            # Combine all parts
            full_explanation = ". ".join(explanation_parts) + "."
            
            return full_explanation
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            action_name = self.get_action_name(action)
            return f"I decided to {action_name} {self.symbol if not self.is_multi_asset else 'the portfolio'} based on my reinforcement learning analysis. Error generating detailed explanation: {str(e)}"


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
            trade_executed = info.get("trade_executed", False)
            
            print(f"\n📊 EXECUTION RESULTS:")
            print(f"   Reward: {reward:.4f}")
            print(f"   Equity After: ${actual_equity:.2f}")
            print(f"   P&L: ${actual_equity - equity:.2f}")
            print(f"   Trade Executed: {trade_executed}")
            print(f"   Done: {done}")
            print(f"   Reward Strategy: {self.reward_strategy}")
            print(f"   Reward Weights: Profit={self.reward_weights['profit']}, Risk={self.reward_weights['risk']}")
            
            # Only update wallet and record trade if it was actually executed
            if trade_executed:
                # Update wallet and record trade in database
                self.update_wallet(reward)
                self.record_trade(action, reward, actual_equity)
                print(f"✅ Wallet updated | Trade recorded in database")
                
                # Send execution notification to frontend
                # Determine symbol/asset_type for notification
                if self.is_multi_asset:
                    notif_symbol = self.symbols[0][0] if self.symbols else "PORTFOLIO"
                    notif_asset_type = self.symbols[0][1] if self.symbols else "portfolio"
                else:
                    notif_symbol = self.symbol
                    notif_asset_type = self.asset_type
                
                notification = {
                    "type": "trade_executed",
                    "user_id": self.user_id,
                    "symbol": notif_symbol,
                    "asset_type": notif_asset_type,
                    "action": int(action),
                    "action_name": action_name,
                    "price": float(price),
                    "reward": float(reward),
                    "equity": float(actual_equity),
                    "timestamp": time.time(),
                    "auto_executed": True
                }
                self.notify_frontend_sync(notification)
                print(f"🔔 WebSocket notification sent to frontend")
            else:
                print(f"⚠️ Trade NOT executed (invalid action: {action_name})")
                print(f"   Reason: {'Insufficient funds' if action == 1 else 'No position to sell'}")
            
            # Store experience for learning (always, even for invalid trades to learn from mistakes)
            try:
                self.memory.append((state, action, reward, next_state, done))
                if self.agent:
                    self.agent.push(state, action, reward, next_state, done)
                add_experience(
                    self.user_id, self.asset_type, self.symbol,
                    state.tolist() if hasattr(state, 'tolist') else list(state), 
                    int(action), float(reward), 
                    next_state.tolist() if hasattr(next_state, 'tolist') else list(next_state), 
                    bool(done)
                )
                print(f"📚 Experience stored for learning")
            except Exception as e:
                print(f"⚠️ Experience storage failed: {e}")
                import traceback
                traceback.print_exc()
            
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
            price = float(proposal.get("price", 0.0))  # Use proposal price
            equity = float(proposal.get("equity", 0.0))
            
            print(f"✅ EXECUTING APPROVED TRADE → {self.get_action_name(action)} {self.symbol} @ ${price:.2f}")
            print(f"📋 Proposal price: ${price:.2f}, Equity: ${equity:.2f}")
            
            # Execute the approved action in the trading environment
            trade_executed = False
            if hasattr(self, 'env') and self.env:
                try:
                    current_state = self.env._get_state()
                    next_state, reward, done, info = self.env.step(action)
                    actual_equity = float(info.get("equity", equity))
                    trade_executed = info.get("trade_executed", False)
                    
                    print(f"✅ Trade executed in environment: reward={reward:.4f}, equity={actual_equity:.2f}, executed={trade_executed}")
                    print(f"📊 Environment state: position={self.env.position}, cash=${self.env.cash:.2f}")
                    
                except Exception as e:
                    print(f"⚠️ Environment execution failed: {e}")
                    import traceback
                    traceback.print_exc()
                    # Calculate reward based on action type
                    reward = -price * 0.01 if action == 1 else price * 0.01 if action == 2 else 0
                    actual_equity = equity
                    trade_executed = True  # Assume executed if env fails but we proceed
            else:
                print(f"⚠️ Environment not available, using fallback calculation")
                reward = -price * 0.01 if action == 1 else price * 0.01 if action == 2 else 0
                actual_equity = equity
                trade_executed = True  # Proceed with recording
            
            # For manually approved trades, always record them even if environment says not executed
            # The user explicitly approved it, so we should record it
            if action in [1, 2]:  # BUY or SELL
                # If environment says not executed, we still record it because user approved
                if not trade_executed:
                    print(f"⚠️ Environment says trade not executed, but user approved - recording anyway")
                    print(f"   This may happen if: SELL with no position, or BUY with insufficient funds")
                    # Force execution for manual approval
                    trade_executed = True
                
                # Update wallet and record trade in database
                try:
                    self.update_wallet(reward)
                    print(f"✅ Wallet updated with reward: {reward:.4f}")
                except Exception as e:
                    print(f"⚠️ Wallet update failed: {e}")
                    import traceback
                    traceback.print_exc()
                
                try:
                    # Use proposal price for recording (not current market price)
                    # Store the proposal price temporarily so record_trade can use it
                    self._last_proposal_price = price
                    self.record_trade(action, reward, actual_equity, use_price=price)
                    print(f"✅ Trade recorded in database: {self.get_action_name(action)} {self.symbol} @ ${price:.2f}")
                    print(f"✅ Portfolio should be updated in database")
                    
                    # Verify the trade was recorded
                    try:
                        from app.db import get_db_cursor
                        with get_db_cursor() as (cur, cnx):
                            if cur:
                                cur.execute("""
                                    SELECT quantity FROM portfolio 
                                    WHERE user_id = %s AND symbol = %s AND asset_type = %s
                                """, (self.user_id, self.symbol, self.asset_type))
                                result = cur.fetchone()
                                if result:
                                    print(f"✅ Verified portfolio position: {result[0]} shares of {self.symbol}")
                                else:
                                    print(f"⚠️ Warning: Portfolio position not found after trade (may be expected for SELL)")
                                
                                # Also verify bot_trades
                                cur.execute("""
                                    SELECT COUNT(*) as count FROM bot_trades 
                                    WHERE user_id = %s AND symbol = %s AND asset_type = %s
                                    ORDER BY timestamp DESC LIMIT 1
                                """, (self.user_id, self.symbol, self.asset_type))
                                trade_result = cur.fetchone()
                                if trade_result and trade_result[0] > 0:
                                    print(f"✅ Verified bot_trades record exists")
                                else:
                                    print(f"⚠️ Warning: bot_trades record not found")
                    except Exception as e:
                        print(f"⚠️ Could not verify database records: {e}")
                        
                except Exception as e:
                    print(f"❌ Failed to record trade in database: {e}")
                    import traceback
                    traceback.print_exc()
                    # Return False if recording failed - this is critical
                    return False
            
            # Store experience for learning
            try:
                from app.rl.replay_store import add_experience
                if hasattr(self, 'env') and self.env:
                    # Get the state that was used for the decision (before step)
                    if hasattr(self, 'current_state') and self.current_state is not None:
                        current_state = self.current_state
                    else:
                        current_state = self.env._get_state()
                    
                    # Get next state after step
                    next_state = self.env._get_state()
                else:
                    current_state = [0] * 10
                    next_state = [0] * 10
                
                add_experience(
                    self.user_id, self.asset_type, self.symbol,
                    current_state.tolist() if hasattr(current_state, 'tolist') else list(current_state),
                    int(action), float(reward),
                    next_state.tolist() if hasattr(next_state, 'tolist') else list(next_state),
                    False
                )
                print(f"📚 Experience stored for approved {self.get_action_name(action)} trade")
                
                # Also store in agent's replay buffer
                if self.agent:
                    self.agent.push(current_state, action, reward, next_state, False)
                    print(f"📚 Experience added to agent's replay buffer")
            except Exception as e:
                print(f"⚠️ Experience storage failed: {e}")
                import traceback
                traceback.print_exc()
            
            # Determine symbol/asset_type for confirmation
            if self.is_multi_asset:
                conf_symbol = self.symbols[0][0] if self.symbols else "PORTFOLIO"
                conf_asset_type = self.symbols[0][1] if self.symbols else "portfolio"
            else:
                conf_symbol = self.symbol
                conf_asset_type = self.asset_type
            
            # Send execution confirmation
            confirmation = {
                "type": "executed",
                "user_id": self.user_id,
                "symbol": conf_symbol,
                "asset_type": conf_asset_type,
                "action": int(action),
                "action_name": self.get_action_name(action),
                "price": float(price),
                "reward": float(reward),
                "equity": float(actual_equity),
                "timestamp": time.time()
            }
            self.notify_frontend_sync(confirmation)
            
            print(f"✅ TRADE COMPLETED → User {self.user_id}: {self.get_action_name(action)} {self.symbol} @ ${price:.2f} | Reward: {reward:.2f}")
            
            # Update latest_decision to reflect the executed trade (for voice explanation)
            self.latest_decision["action"] = action
            self.latest_decision["action_name"] = self.get_action_name(action)
            self.latest_decision["price"] = price
            self.latest_decision["timestamp"] = time.time()
            self.latest_decision["reward"] = reward
            self.latest_decision["equity"] = actual_equity
            print(f"📊 Updated latest_decision after execution: {self.get_action_name(action)} @ ${price:.2f}")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to execute trade: {e}")
            import traceback
            traceback.print_exc()
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
        while self.running:
            try:
                time.sleep(self.interval)
                cycle += 1
                print(f"\n{'─'*80}", flush=True)
                print(f"🔄 CYCLE #{cycle} - {self.symbol} at {time.strftime('%H:%M:%S')}", flush=True)
                print(f"{'─'*80}", flush=True)
                sys.stdout.flush()
                
                self.current_state = state
                
                # Decide action with config-based exploration
                print(f"🧠 Making decision with {self.exploration_rate*100:.0f}% exploration rate...")
                if not self.agent:
                    print(f"⚠️ Agent not initialized, loading model...")
                    self.load_model()
                action = self.agent.act(state, eps=self.exploration_rate) if self.agent else 0
                action_name = self.get_action_name(action)
                
                # Store latest decision for explanation
                self.latest_decision = {
                    "action": action,
                    "action_name": action_name,
                    "symbol": self.symbol if not self.is_multi_asset else "PORTFOLIO",
                    "price": 0.0,  # Will be updated with current price
                    "timestamp": time.time(),
                    "q_values": self.agent.last_q_values if (self.agent and hasattr(self.agent, 'last_q_values')) else None,
                    "confidence": 0.0,  # Will be calculated
                    "strategy_reason": "",
                    "technical_indicators": {}
                }
                
                print(f"🎯 Decision: {action_name} (action={action})")
                
                # Get real-time price (handle both single-asset and multi-asset)
                if self.is_multi_asset:
                    # For multi-asset, get prices for all assets
                    print(f"💹 Fetching current market prices for {len(self.symbols)} assets...")
                    try:
                        from app.data.loader import fetch_realtime_price
                        asset_prices = {}
                        for symbol, asset_type in self.symbols:
                            try:
                                realtime_data = fetch_realtime_price(symbol, asset_type)
                                asset_prices[(symbol, asset_type)] = float(realtime_data["price"])
                                print(f"   ✅ {symbol}: ${asset_prices[(symbol, asset_type)]:.2f}")
                            except Exception as e:
                                # Fallback to cached price
                                if hasattr(self.env, 'asset_data') and (symbol, asset_type) in self.env.asset_data:
                                    df = self.env.asset_data[(symbol, asset_type)]
                                    cached_price = float(df.iloc[self.env.t]["close"]) if self.env.t < len(df) else float(df.iloc[-1]["close"])
                                    asset_prices[(symbol, asset_type)] = cached_price
                                    print(f"   ⚠️ {symbol}: ${cached_price:.2f} (cached, API error: {e})")
                        # Use first asset's price for current_price (for compatibility)
                        current_price = list(asset_prices.values())[0] if asset_prices else 0.0
                    except Exception as e:
                        print(f"⚠️ Error fetching prices: {e}")
                        current_price = 0.0
                    
                    # Calculate portfolio equity
                    current_equity = self.env.equity
                    print(f"💰 Portfolio Equity: ${current_equity:.2f} | Cash: ${self.env.cash:.2f}")
                else:
                    # Single-asset mode
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
                
                # Update latest decision with current price
                if self.is_multi_asset:
                    self.latest_decision["price"] = current_price
                else:
                    self.latest_decision["price"] = current_price
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
                            
                            # Update latest decision with strategy analysis before creating proposal
                            try:
                                # Ensure latest_decision has the current action and price
                                self.latest_decision["action"] = action
                                self.latest_decision["action_name"] = self.get_action_name(action)
                                self.latest_decision["price"] = current_price
                                self.latest_decision["symbol"] = self.symbol if not self.is_multi_asset else "PORTFOLIO"
                                self.latest_decision["timestamp"] = time.time()
                                
                                strategy_analysis = self.analyze_market_strategy(action, current_price)
                                self.latest_decision["strategy_reason"] = strategy_analysis.get("reason", "")
                                
                                confidence = self.calculate_confidence(action, current_price)
                                self.latest_decision["confidence"] = confidence
                                
                                tech_summary = self.generate_technical_summary()
                                self.latest_decision["technical_indicators"] = tech_summary
                                
                                # Update Q-values if available
                                if self.agent and hasattr(self.agent, 'last_q_values'):
                                    self.latest_decision["q_values"] = self.agent.last_q_values
                                
                                print(f"📊 Updated latest_decision: {self.get_action_name(action)} {self.symbol} @ ${current_price:.2f}")
                            except Exception as e:
                                print(f"⚠️ Error updating latest decision: {e}")
                                import traceback
                                traceback.print_exc()
                            
                            proposal_created = self.create_proposal(
                                action=action,
                                price=current_price,
                                equity=current_equity
                            )
                            
                            if proposal_created:
                                print(f"✅ PROPOSAL SENT TO FRONTEND via WebSocket")
                                print(f"⏳ Waiting for user to ACCEPT or REJECT...")
                                
                                # Determine proposal key based on mode (include asset_type)
                                if self.is_multi_asset:
                                    primary_symbol = self.symbols[0][0] if self.symbols else "PORTFOLIO"
                                    primary_asset_type = self.symbols[0][1] if self.symbols else "portfolio"
                                    proposal_key = (self.user_id, primary_symbol, primary_asset_type)
                                else:
                                    proposal_key = (self.user_id, self.symbol, self.asset_type)
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
                    
                    # Update latest decision with strategy analysis and technical indicators for HOLD
                    try:
                        strategy_analysis = self.analyze_market_strategy(action, current_price)
                        self.latest_decision["strategy_reason"] = strategy_analysis.get("reason", "")
                        
                        confidence = self.calculate_confidence(action, current_price)
                        self.latest_decision["confidence"] = confidence
                        
                        tech_summary = self.generate_technical_summary()
                        self.latest_decision["technical_indicators"] = tech_summary
                        
                        # Update Q-values if available
                        if self.agent and hasattr(self.agent, 'last_q_values'):
                            self.latest_decision["q_values"] = self.agent.last_q_values
                    except Exception as e:
                        print(f"⚠️ Error updating latest decision for HOLD: {e}")
                    
                    next_state, reward, done, info = self.env.step(action)
                    actual_equity = float(info.get("equity", self.env.cash + self.env.position * self.get_current_price()))
                    
                    try:
                        self.update_wallet(reward)
                        
                        # Record HOLD action in database
                        try:
                            self.record_trade(action, reward, actual_equity)
                            print(f"✅ HOLD recorded in database")
                        except Exception as e:
                            print(f"⚠️ Failed to record HOLD in database: {e}")
                        
                        self.memory.append((state, action, reward, next_state, done))
                        if self.agent:
                            self.agent.push(state, action, reward, next_state, done)
                        add_experience(
                            self.user_id, self.asset_type, self.symbol,
                            state.tolist() if hasattr(state, 'tolist') else list(state),
                            int(action), float(reward),
                            next_state.tolist() if hasattr(next_state, 'tolist') else list(next_state),
                            bool(done)
                        )
                        
                        print(f"✅ HOLD executed | Reward: {reward:.4f}")
                        state = next_state
                        if done:
                            print(f"🔄 Episode complete, resetting environment...")
                            state = self.env.reset()
                            
                    except Exception as e:
                        print(f"⚠️ HOLD processing failed: {e}")
                        import traceback
                        traceback.print_exc()
                
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

            except Exception as e:
                print(f"\n❌ RUNTIME ERROR in cycle #{cycle}:")
                print(f"   Error: {e}")
                import traceback
                traceback.print_exc()
                print(f"⏰ Retrying in {self.interval} seconds...")
                
        # Bot stopped - send notification
        print(f"\n{'='*80}", flush=True)
        print(f"🛑 BOT STOPPED", flush=True)
        print(f"   Symbol: {self.symbol}", flush=True)
        print(f"   User: {self.user_id}", flush=True)
        print(f"   Total Cycles: {cycle}", flush=True)
        print(f"{'='*80}\n", flush=True)
        
        # Notify frontend
        stop_message = {
            "type": "bot_stopped",
            "symbol": self.symbol,
            "user_id": self.user_id,
            "total_cycles": cycle
        }
        self.notify_frontend_sync(stop_message)

    def online_learn(self):
        """Perform online learning from replay memory."""
        if len(self.memory) < 32:  # Minimum batch size
            return
        
        try:
            # Sample from replay memory and train
            batch_size = min(32, len(self.memory))
            batch = list(self.memory)[-batch_size:]  # Use recent experiences
            
            # Simple learning - in a real implementation, this would be more sophisticated
            if self.agent:
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
            if self.agent and self.agent.q:
                torch.save(self.agent.q.state_dict(), self.model_path)
                print(f"💾 Model saved: {self.model_path}")
            else:
                print(f"⚠️ Cannot save model: agent not initialized")
        except Exception as e:
            print(f"⚠️ Failed to save model: {e}")
            import traceback
            traceback.print_exc()

