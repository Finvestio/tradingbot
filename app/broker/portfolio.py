"""
Portfolio management module for the trading bot
Handles portfolio calculations, risk management, and position tracking
"""
from typing import List, Dict, Optional, Tuple
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass
from datetime import datetime

try:
    # Try relative imports first
    from ..models import Portfolio, User, OrderTrade
    from ..data.loader import fetch_realtime_price
    from ..database import get_db
except ImportError:
    # Fall back to direct imports
    from models import Portfolio, User, OrderTrade
    from data.loader import fetch_realtime_price
    from database import get_db

@dataclass
class PortfolioPosition:
    """Represents a single position in the portfolio"""
    symbol: str
    asset_type: str
    quantity: float
    avg_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    weight: float  # Percentage of total portfolio

@dataclass
class PortfolioSummary:
    """Complete portfolio summary with performance metrics"""
    user_id: int
    wallet_balance: float
    total_market_value: float
    total_portfolio_value: float
    total_unrealized_pnl: float
    total_unrealized_pnl_percent: float
    positions: List[PortfolioPosition]
    positions_count: int
    diversification_score: float
    
class PortfolioManager:
    """
    Advanced portfolio management system
    """
    
    def __init__(self, db_session=None):
        self.db = db_session or next(get_db())
    
    async def get_portfolio_summary(self, user_id: int) -> PortfolioSummary:
        """
        Get comprehensive portfolio summary with real-time pricing
        """
        # Get user and wallet balance
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        # Get all portfolio positions
        positions = self.db.query(Portfolio).filter(Portfolio.user_id == user_id).all()
        
        portfolio_positions = []
        total_market_value = 0.0
        
        for position in positions:
            if position.quantity > 0:  # Only include positions with holdings
                # Get real-time price (synchronous call, not async)
                try:
                    realtime_data = fetch_realtime_price(position.symbol, position.asset_type)
                    current_price = float(realtime_data["price"])
                except Exception:
                    # Fallback to average price if real-time fetch fails
                    current_price = position.avg_price
                
                # Calculate position metrics
                market_value = position.quantity * current_price
                unrealized_pnl = (current_price - position.avg_price) * position.quantity
                unrealized_pnl_percent = ((current_price - position.avg_price) / position.avg_price) * 100 if position.avg_price > 0 else 0
                
                portfolio_positions.append(PortfolioPosition(
                    symbol=position.symbol,
                    asset_type=position.asset_type,
                    quantity=position.quantity,
                    avg_price=position.avg_price,
                    current_price=current_price,
                    market_value=market_value,
                    unrealized_pnl=unrealized_pnl,
                    unrealized_pnl_percent=unrealized_pnl_percent,
                    weight=0  # Will be calculated after total is known
                ))
                
                total_market_value += market_value
        
        # Calculate position weights
        for position in portfolio_positions:
            position.weight = (position.market_value / total_market_value * 100) if total_market_value > 0 else 0
        
        # Calculate portfolio totals
        total_portfolio_value = user.wallet_balance + total_market_value
        total_unrealized_pnl = sum(pos.unrealized_pnl for pos in portfolio_positions)
        total_cost_basis = sum(pos.avg_price * pos.quantity for pos in portfolio_positions)
        total_unrealized_pnl_percent = (total_unrealized_pnl / total_cost_basis * 100) if total_cost_basis > 0 else 0
        
        # Calculate diversification score (higher is more diversified)
        diversification_score = self._calculate_diversification_score(portfolio_positions)
        
        return PortfolioSummary(
            user_id=user_id,
            wallet_balance=user.wallet_balance,
            total_market_value=total_market_value,
            total_portfolio_value=total_portfolio_value,
            total_unrealized_pnl=total_unrealized_pnl,
            total_unrealized_pnl_percent=total_unrealized_pnl_percent,
            positions=portfolio_positions,
            positions_count=len(portfolio_positions),
            diversification_score=diversification_score
        )
    
    def update_position(self, user_id: int, symbol: str, asset_type: str, 
                       quantity: float, price: float, action: str) -> Portfolio:
        """
        Update portfolio position after a trade
        """
        # Find existing position
        position = self.db.query(Portfolio).filter(
            Portfolio.user_id == user_id,
            Portfolio.symbol == symbol.upper(),
            Portfolio.asset_type == asset_type.lower()
        ).first()
        
        if action.upper() == "BUY":
            if position:
                # Calculate new weighted average price
                total_value = (position.quantity * position.avg_price) + (quantity * price)
                new_quantity = position.quantity + quantity
                position.avg_price = total_value / new_quantity if new_quantity > 0 else 0
                position.quantity = new_quantity
            else:
                # Create new position
                position = Portfolio(
                    user_id=user_id,
                    symbol=symbol.upper(),
                    asset_type=asset_type.lower(),
                    quantity=quantity,
                    avg_price=price
                )
                self.db.add(position)
        
        elif action.upper() == "SELL":
            if not position or position.quantity < quantity:
                raise ValueError(f"Insufficient holdings for {symbol}")
            
            # Reduce position
            position.quantity -= quantity
            # Note: avg_price remains the same for FIFO accounting
        
        self.db.commit()
        return position
    
    def execute_trade(self, user_id: int, symbol: str, action: str, 
                     quantity: float, price: float, asset_type: str = "stock") -> dict:
        """
        Execute a complete trade: validate, update portfolio, record order, update wallet
        This method provides a unified interface for both bot and manual trades
        
        Returns:
            dict with trade execution results and new balances
        """
        try:
            action = action.upper()
            symbol = symbol.upper()
            asset_type = asset_type.lower()
            
            # Get user
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                raise ValueError(f"User {user_id} not found")
            
            # Calculate order total
            order_total = price * quantity
            
            # Validate trade based on action
            if action == "BUY":
                if user.wallet_balance < order_total:
                    raise ValueError(
                        f"Insufficient balance. Available: ${user.wallet_balance:.2f}, Required: ${order_total:.2f}"
                    )
            elif action == "SELL":
                # Check if user has enough shares to sell
                portfolio = self.db.query(Portfolio).filter(
                    Portfolio.user_id == user_id,
                    Portfolio.symbol == symbol,
                    Portfolio.asset_type == asset_type
                ).first()
                
                available_quantity = portfolio.quantity if portfolio else 0
                if available_quantity < quantity:
                    raise ValueError(
                        f"Insufficient shares to sell. Available: {available_quantity}, Requested: {quantity}"
                    )
            else:
                raise ValueError(f"Invalid action: {action}. Must be BUY or SELL")
            
            # Update wallet balance
            if action == "BUY":
                user.wallet_balance -= order_total
            else:  # SELL
                user.wallet_balance += order_total
            
            # Update portfolio position
            position = self.update_position(user_id, symbol, asset_type, quantity, price, action)
            
            # Create trade record
            from datetime import date
            trade = OrderTrade(
                user_id=user_id,
                symbol=symbol,
                asset_type=asset_type,
                date=date.today(),
                action=action,
                price=price,
                qty=quantity
            )
            
            self.db.add(trade)
            self.db.commit()
            
            # Return execution results
            return {
                "success": True,
                "message": f"{action} order executed for {quantity} shares of {symbol} at ${price:.2f}",
                "trade_id": trade.id,
                "symbol": symbol,
                "action": action,
                "quantity": quantity,
                "price": price,
                "order_total": order_total,
                "new_wallet_balance": user.wallet_balance,
                "timestamp": trade.date.isoformat()
            }
            
        except Exception as e:
            self.db.rollback()
            raise ValueError(f"Trade execution failed: {str(e)}")

    def get_position_risk_metrics(self, user_id: int, symbol: str, asset_type: str) -> Dict:
        """
        Get risk metrics for a specific position
        """
        position = self.db.query(Portfolio).filter(
            Portfolio.user_id == user_id,
            Portfolio.symbol == symbol.upper(),
            Portfolio.asset_type == asset_type.lower()
        ).first()
        
        if not position:
            return {"error": "Position not found"}
        
        # Calculate position size as % of portfolio
        portfolio_summary = self.get_portfolio_summary(user_id)
        position_weight = (position.quantity * position.avg_price) / portfolio_summary.total_portfolio_value * 100
        
        return {
            "symbol": symbol,
            "quantity": position.quantity,
            "avg_price": position.avg_price,
            "position_weight": position_weight,
            "risk_level": "High" if position_weight > 20 else "Medium" if position_weight > 10 else "Low"
        }
    
    def get_portfolio_performance(self, user_id: int, days: int = 30) -> Dict:
        """
        Calculate portfolio performance over time
        """
        # Get recent trades for performance calculation
        trades = self.db.query(OrderTrade).filter(
            OrderTrade.user_id == user_id
        ).order_by(OrderTrade.date.desc()).limit(100).all()
        
        # Basic performance metrics
        total_trades = len(trades)
        buy_trades = [t for t in trades if t.action == "BUY"]
        sell_trades = [t for t in trades if t.action == "SELL"]
        
        total_invested = sum(t.price * t.qty for t in buy_trades)
        total_divested = sum(t.price * t.qty for t in sell_trades)
        
        return {
            "total_trades": total_trades,
            "total_invested": total_invested,
            "total_divested": total_divested,
            "net_investment": total_invested - total_divested,
            "trading_frequency": total_trades / max(days, 1)
        }
    
    def get_portfolio_summary_sync(self, user_id: int) -> PortfolioSummary:
        """
        Synchronous version of get_portfolio_summary for use in non-async contexts
        """
        # Get user and wallet balance
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        # Get all portfolio positions
        positions = self.db.query(Portfolio).filter(Portfolio.user_id == user_id).all()
        
        portfolio_positions = []
        total_market_value = 0.0
        
        for position in positions:
            if position.quantity > 0:  # Only include positions with holdings
                # Get real-time price (synchronous)
                try:
                    realtime_data = fetch_realtime_price(position.symbol, position.asset_type)
                    current_price = float(realtime_data["price"])
                except Exception:
                    # Fallback to average price if real-time fetch fails
                    current_price = position.avg_price
                
                # Calculate position metrics
                market_value = position.quantity * current_price
                unrealized_pnl = (current_price - position.avg_price) * position.quantity
                unrealized_pnl_percent = ((current_price - position.avg_price) / position.avg_price) * 100 if position.avg_price > 0 else 0
                
                portfolio_positions.append(PortfolioPosition(
                    symbol=position.symbol,
                    asset_type=position.asset_type,
                    quantity=position.quantity,
                    avg_price=position.avg_price,
                    current_price=current_price,
                    market_value=market_value,
                    unrealized_pnl=unrealized_pnl,
                    unrealized_pnl_percent=unrealized_pnl_percent,
                    weight=0  # Will be calculated after total is known
                ))
                
                total_market_value += market_value
        
        # Calculate position weights
        for position in portfolio_positions:
            position.weight = (position.market_value / total_market_value * 100) if total_market_value > 0 else 0
        
        # Calculate portfolio totals
        total_portfolio_value = user.wallet_balance + total_market_value
        total_unrealized_pnl = sum(pos.unrealized_pnl for pos in portfolio_positions)
        total_cost_basis = sum(pos.avg_price * pos.quantity for pos in portfolio_positions)
        total_unrealized_pnl_percent = (total_unrealized_pnl / total_cost_basis * 100) if total_cost_basis > 0 else 0
        
        # Calculate diversification score (higher is more diversified)
        diversification_score = self._calculate_diversification_score(portfolio_positions)
        
        return PortfolioSummary(
            user_id=user_id,
            wallet_balance=user.wallet_balance,
            total_market_value=total_market_value,
            total_portfolio_value=total_portfolio_value,
            total_unrealized_pnl=total_unrealized_pnl,
            total_unrealized_pnl_percent=total_unrealized_pnl_percent,
            positions=portfolio_positions,
            positions_count=len(portfolio_positions),
            diversification_score=diversification_score
        )
    
    def _calculate_diversification_score(self, positions: List[PortfolioPosition]) -> float:
        """
        Calculate portfolio diversification score (0-100)
        Based on number of positions and weight distribution
        """
        if not positions:
            return 0.0
        
        # Number of positions factor (more positions = better diversification)
        position_factor = min(len(positions) / 10.0, 1.0) * 50  # Max 50 points
        
        # Weight distribution factor (more even weights = better diversification)
        weights = [pos.weight for pos in positions]
        max_weight = max(weights) if weights else 100
        concentration_penalty = max_weight - (100 / len(positions))  # Penalty for concentration
        weight_factor = max(0, 50 - concentration_penalty)  # Max 50 points
        
        return round(position_factor + weight_factor, 2)
    
    def calculate_portfolio_beta(self, user_id: int, benchmark_symbol: str = "SPY") -> float:
        """
        Calculate portfolio beta against a benchmark (simplified)
        """
        # This is a placeholder for a more sophisticated beta calculation
        # In production, you'd need historical price data for proper calculation
        return 1.0  # Assume market beta for now
    
    async def get_risk_metrics(self, user_id: int) -> Dict:
        """
        Get comprehensive risk metrics for the portfolio
        """
        summary = await self.get_portfolio_summary(user_id)
        
        # Calculate concentration risk
        max_position_weight = max([pos.weight for pos in summary.positions]) if summary.positions else 0
        
        # Calculate volatility risk based on position types
        stock_weight = sum(pos.weight for pos in summary.positions if pos.asset_type == "stock")
        crypto_weight = sum(pos.weight for pos in summary.positions if pos.asset_type == "crypto")
        
        # Risk score (0-100, higher = riskier)
        risk_score = 0
        risk_score += min(max_position_weight, 50)  # Concentration risk (max 50 points)
        risk_score += crypto_weight * 0.5  # Crypto adds risk
        risk_score += max(0, (len(summary.positions) - 10) * -2)  # Diversification bonus
        
        return {
            "risk_score": round(risk_score, 2),
            "risk_level": "High" if risk_score > 70 else "Medium" if risk_score > 40 else "Low",
            "concentration_risk": max_position_weight,
            "diversification_score": summary.diversification_score,
            "asset_allocation": {
                "stocks": stock_weight,
                "crypto": crypto_weight,
                "cash": (summary.wallet_balance / summary.total_portfolio_value * 100) if summary.total_portfolio_value > 0 else 100
            }
        }
