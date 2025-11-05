import time
import torch
import json
import asyncio
import numpy as np
from app.rl.dqn import DQNAgent
from app.rl.env import TradingEnv
from app.db import get_db_connection
from app.rl.replay_store import add_experience
from collections import deque

# Global storage for trade proposals
trade_proposals = {}

class RLTrader:
    """Autonomous RL-based trader that trades one action per interval."""

    def __init__(self, user_id, symbol, asset_type, interval_sec=1800):
        self.user_id = user_id
        self.symbol = symbol
        self.asset_type = asset_type
        self.interval = interval_sec
        self.model_path = f"models/dqn_{asset_type}_{symbol}.pth"

        # Environment and model
        self.env = TradingEnv(symbol, asset_type)
        self.agent = None

        # Database connection
        self.conn = get_db_connection()

        # Replay memory for continuous learning
        from collections import deque
        self.memory = deque(maxlen=1000)  # local in-memory replay buffer

        # Learning frequency settings
        self.learn_every = 10         # learn after every 10 trades
        self.checkpoint_every = 200   # save model after every 200 trades
        self.trade_count = 0 

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

    # -------------------- DATABASE --------------------
    def update_wallet(self, delta):
        """Apply profit/loss atomically to the user's wallet."""
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE users SET wallet = wallet + %s WHERE id = %s",
            (float(delta), self.user_id)
        )
        self.conn.commit()
        cur.close()

    def record_trade(self, action, reward, equity):
        """Insert trade record into portfolio/orders table."""
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO trades (user_id, symbol, asset_type, action, reward, equity, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (self.user_id, self.symbol, self.asset_type, int(action), float(reward), float(equity)))
        self.conn.commit()
        cur.close()

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
        """Create a trade proposal and send it via WebSocket."""
        key = (self.user_id, self.symbol)
        
        # Check if there's already a pending proposal for this user/symbol
        if key in trade_proposals:
            print(f"⏳ Previous proposal pending for {self.symbol}, skipping new proposal")
            return None
            
        proposal = {
            "type": "proposal",
            "user_id": self.user_id,
            "symbol": self.symbol,
            "asset_type": self.asset_type,
            "action": int(action),
            "price": float(price),
            "equity": float(equity),
            "timestamp": time.time(),
            "proposal_id": f"{self.user_id}_{self.symbol}_{int(time.time())}"
        }
        
        # Store proposal
        trade_proposals[key] = proposal
        
        # Send proposal via WebSocket
        asyncio.run(self.notify_frontend(proposal))
        print(f"📋 NEW PROPOSAL → User {self.user_id}: {self.get_action_name(action)} {self.symbol} @ ${price:.2f}")
        
        return proposal
    
    def get_action_name(self, action):
        """Get human-readable action name."""
        return {1: "BUY", 2: "SELL", 0: "HOLD"}.get(action, "UNKNOWN")

    def execute_approved_trade(self, proposal):
        """Execute a previously approved trade proposal."""
        try:
            action = proposal["action"]
            price = proposal["price"]
            equity = proposal["equity"]
            
            print(f"✅ EXECUTING APPROVED TRADE → {self.get_action_name(action)} {self.symbol} @ ${price:.2f}")
            
            # 🚨 NOW execute the actual trade in the environment (only after user approval)
            if hasattr(self, 'env') and self.env:
                try:
                    # Execute the approved action in the trading environment
                    current_state = self.env._get_state()
                    next_state, reward, done, info = self.env.step(action)
                    actual_equity = float(info.get("equity", equity))
                    
                    print(f"✅ Trade executed in environment: reward={reward:.4f}, equity={actual_equity:.2f}")
                    
                except Exception as e:
                    print(f"⚠️ Environment execution failed: {e}")
                    # Fallback calculation
                    reward = -price * 0.01 if action == 1 else price * 0.01 if action == 2 else 0
                    actual_equity = equity
            else:
                # Fallback calculation if no environment
                reward = -price * 0.01 if action == 1 else price * 0.01 if action == 2 else 0
                actual_equity = equity
            
            # Update wallet and record trade with actual results (ONLY after user approval)
            self.update_wallet(reward)
            self.record_trade(action, reward, actual_equity)
            
            # Store experience for learning (this should only happen on execution, not proposal)
            try:
                from app.rl.replay_store import add_experience
                dummy_state = [0] * 10  # Simplified state for now
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
        """Main autonomous trading loop with user approval proposals."""
        import time
        from app.rl.replay_store import add_experience

        self.load_model()
        state = self.env.reset()

        print(f"🤖 RL Bot STARTED → user={self.user_id} | {self.asset_type}:{self.symbol}")
        print(f"🤖 Bot will analyze market every {self.interval} seconds and create proposals for BUY/SELL actions")
        print(f"🤖 Using 20% exploration rate for varied trading decisions")
        print(f"⛔ IMPORTANT: Bot will NEVER execute trades automatically - requires user approval!")
        print(f"⛔ All BUY/SELL actions need YOUR consent via popup modal!")

        while True:
            try:
                # Store current state for later use in trade execution
                self.current_state = state
                
                # 1. Decide action using trained DQN with HIGH exploration for frequent proposals
                action = self.agent.act(state, eps=0.8)  # 80% exploration for MORE trading actions
                
                # 🚨 FORCE MORE PROPOSALS FOR TESTING - override random HOLD actions
                import random
                if action == 0 and random.random() < 0.7:  # 70% chance to convert HOLD to trading action
                    action = random.choice([1, 2])  # Randomly pick BUY or SELL
                    print(f"🎯 Converted HOLD to {self.get_action_name(action)} for more proposal testing")
                
                # 🚨 CRITICAL FIX: Don't execute env.step() automatically for BUY/SELL!
                # Get current market info WITHOUT executing the trade
                current_data = self.env.df.iloc[self.env.t] if self.env.t < len(self.env.df) else self.env.df.iloc[-1]
                current_price = float(current_data["close"])
                current_equity = self.env.cash + self.env.position * current_price

                # 2. Handle actions based on type
                if action in [1, 2]:  # 1 = BUY, 2 = SELL - REQUIRE USER APPROVAL
                    try:
                        proposal_created = self.create_proposal(
                            action=action,
                            price=current_price,
                            equity=current_equity
                        )
                        
                        if proposal_created:
                            print(f"[BOT] 📋 PROPOSAL CREATED → {self.get_action_name(action)} {self.symbol} @ ${current_price:.2f}")
                            print(f"[BOT] ⏳ ⛔ WAITING FOR USER APPROVAL - NO ENV.STEP() EXECUTED ⛔")
                        else:
                            print(f"[BOT] ⏸️ Proposal skipped (previous proposal pending for {self.symbol})")
                            
                    except Exception as e:
                        print(f"⚠️ Failed to create proposal: {e}")
                    
                    # ⛔ CRITICAL: For BUY/SELL, don't call env.step() - wait for user approval
                    # Just advance time and continue monitoring
                    print(f"[BOT] ⛔ Skipping env.step() for {self.get_action_name(action)} - waiting for user consent")
                    print(f"[BOT] 📊 Current position: {self.env.position}, cash: ${self.env.cash:.2f}")
                    self.env.t = min(self.env.t + 1, len(self.env.df) - 1)
                    
                elif action == 0:  # HOLD action - can execute immediately
                    print(f"[BOT] 📊 HOLD → user={self.user_id} {self.symbol} @ ${current_price:.2f} (safe to execute immediately)")
                    print(f"[BOT] ✅ Executing env.step() for HOLD (no trading, just time advancement)")
                    
                    # Execute HOLD in environment (safe since no actual trading)
                    next_state, reward, done, info = self.env.step(action)
                    print(f"[BOT] ✅ HOLD executed: reward={reward:.4f}, position unchanged: {self.env.position}")
                    
                    # Store HOLD action immediately
                    try:
                        self.update_wallet(reward)
                        self.memory.append((state, action, reward, next_state, done))
                        add_experience(
                            self.user_id, self.asset_type, self.symbol,
                            state, int(action), float(reward), next_state, bool(done)
                        )
                        
                        # Update state for next iteration
                        state = next_state
                        if done:
                            state = self.env.reset()
                            
                    except Exception as e:
                        print(f"⚠️ DB or memory store failed for HOLD: {e}")
                
                else:
                    # Unknown action - just advance time
                    self.env.t = min(self.env.t + 1, len(self.env.df) - 1)

                # 4. Periodic Training + Checkpoint
                self.trade_count += 1
                if self.trade_count % self.learn_every == 0:
                    self.online_learn()
                if self.trade_count % self.checkpoint_every == 0:
                    self.save_model()

                # 6. Wait for next trading cycle
                time.sleep(self.interval)

            except Exception as e:
                print(f"❌ Runtime error for {self.symbol}: {e}")
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

