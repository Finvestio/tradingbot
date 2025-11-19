# app/api_rl_explanation.py
"""
API endpoint for generating RL bot decision explanations.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
import json
import time

router = APIRouter()

@router.get("/api/rl/explain_decision")
def explain_rl_decision(
    user_id: int,
    symbol: str,
    asset_type: str = "stock",
    action: Optional[int] = None
):
    """
    Generate a detailed explanation of why the RL bot made a specific decision.
    
    Args:
        user_id: User ID
        symbol: Trading symbol
        asset_type: Asset type (stock, crypto, derivative)
        action: Optional action (0=HOLD, 1=BUY, 2=SELL). If not provided, gets latest decision.
    
    Returns:
        Explanation text that can be read aloud
    """
    try:
        from app.api import running_bots
        from app.bot.rl_trader import trade_proposals
        
        # Find the running bot for this user and symbol
        bot_key = f"{user_id}_{symbol}_{asset_type}"
        bot = running_bots.get(bot_key)
        
        if not bot:
            # Try to find any bot for this user
            user_bots = {k: v for k, v in running_bots.items() if k.startswith(f"{user_id}_")}
            if user_bots:
                bot = list(user_bots.values())[0]
                print(f"⚠️ Bot not found for {symbol}, using first available bot for user {user_id}")
            else:
                raise HTTPException(
                    status_code=404, 
                    detail=f"No running bot found for user {user_id} and symbol {symbol}"
                )
        
        # Get the latest proposal or current state (include asset_type in key)
        proposal_key = (user_id, symbol, asset_type)
        latest_proposal = trade_proposals.get(proposal_key)
        
        # Try old format for backward compatibility
        if not latest_proposal:
            proposal_key_old = (user_id, symbol)
            latest_proposal = trade_proposals.get(proposal_key_old)
            if latest_proposal:
                print(f"⚠️ Found proposal with old key format, using it")
        
        # Determine action if not provided - use latest decision first
        if action is None:
            # Priority 1: Use latest_decision (most recent cycle)
            if hasattr(bot, 'latest_decision') and bot.latest_decision:
                action = bot.latest_decision.get("action", 0)
                latest_proposal = bot.latest_decision  # Use latest decision as proposal
                action_name = bot.get_action_name(action)
                decision_symbol = bot.latest_decision.get('symbol', symbol)
                decision_price = bot.latest_decision.get('price', 0.0)
                print(f"📊 Using latest decision: {action_name} for {decision_symbol} @ ${decision_price:.2f}")
                
                # Verify this is a real decision, not default HOLD
                if action == 0 and bot.latest_decision.get("timestamp", 0) < time.time() - 60:
                    print(f"⚠️ Latest decision is old (HOLD), trying to get current action from agent...")
                    # Try to get current action from agent
                    if hasattr(bot, 'agent') and bot.agent and hasattr(bot, 'current_state') and bot.current_state is not None:
                        try:
                            current_action = bot.agent.act(bot.current_state, eps=0.0)
                            if current_action != 0:
                                action = current_action
                                print(f"📊 Updated action from agent: {bot.get_action_name(action)}")
                        except:
                            pass
            
            # Priority 2: Use latest proposal
            elif latest_proposal:
                action = latest_proposal.get("action", 0)
                print(f"📊 Using proposal action: {bot.get_action_name(action)}")
            
            # Priority 3: Use Q-values
            elif hasattr(bot, 'agent') and bot.agent and hasattr(bot.agent, 'last_q_values'):
                q_values = bot.agent.last_q_values
                if q_values and len(q_values) >= 3:
                    action = q_values.index(max(q_values))
                    print(f"📊 Using Q-value based action: {bot.get_action_name(action)}")
                else:
                    action = 0  # Default to HOLD
                    print(f"⚠️ Q-values not available, defaulting to HOLD")
            
            # Priority 4: Use current state
            elif hasattr(bot, 'current_state') and bot.current_state is not None:
                try:
                    if bot.agent:
                        action = bot.agent.act(bot.current_state, eps=0.0)
                        print(f"📊 Using current state action: {bot.get_action_name(action)}")
                    else:
                        action = 0
                        print(f"⚠️ No agent available, defaulting to HOLD")
                except Exception as e:
                    action = 0
                    print(f"⚠️ Error getting action from state: {e}, defaulting to HOLD")
            else:
                action = 0  # Default to HOLD
                print(f"⚠️ No decision found, defaulting to HOLD")
        
        # Generate explanation - ensure we use the most recent data
        try:
            # Force refresh of latest decision data if available
            if hasattr(bot, 'latest_decision') and bot.latest_decision:
                # Ensure we have the most recent Q-values
                if bot.agent and hasattr(bot.agent, 'last_q_values'):
                    bot.latest_decision["q_values"] = bot.agent.last_q_values
                
                # Use latest decision as the primary source
                latest_proposal = bot.latest_decision
            
            explanation = bot.generate_decision_explanation(action, latest_proposal)
            print(f"📊 Generated explanation for {bot.get_action_name(action)} {symbol}: {explanation[:100]}...")
        except Exception as e:
            print(f"⚠️ Error generating explanation: {e}")
            import traceback
            traceback.print_exc()
            # Fallback explanation
            action_name = bot.get_action_name(action)
            explanation = f"I decided to {action_name} {symbol} based on my reinforcement learning analysis."
        
        return {
            "explanation": explanation,
            "action": action,
            "action_name": bot.get_action_name(action),
            "symbol": symbol,
            "asset_type": asset_type,
            "user_id": user_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating explanation: {str(e)}")

