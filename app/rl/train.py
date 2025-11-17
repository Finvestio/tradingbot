import sys
import time
import torch
from app.rl.env import TradingEnv
from app.rl.dqn import DQNAgent

def train(symbol: str, asset_type: str, episodes: int = 10, steps_per_episode: int = 1000):
    """
    Train a DQN reinforcement learning agent on any symbol and asset type.
    Works for stocks, crypto, or derivatives using the database or API data source.
    """
    env = TradingEnv(symbol, asset_type)
    state = env.reset()
    agent = DQNAgent(len(state))

    print(f"🚀 Starting RL training for {asset_type.upper()} — {symbol}")
    rewards = []

    for ep in range(episodes):
        s = env.reset()
        total_r = 0.0
        for t in range(steps_per_episode):
            a = agent.act(s, eps=max(0.1, 1 - ep / episodes))  # exploration decay
            ns, r, done, info = env.step(a)
            agent.push(s, a, r, ns, done)
            agent.train_step()
            agent.soft_update()
            s = ns
            total_r += r
            if done:
                break
        rewards.append(total_r)
        # Reduce logging frequency
        if ep % 5 == 0 or ep == episodes - 1:
            print(f"Episode {ep+1}/{episodes} | Reward={total_r:.4f} | Equity={info['equity']:.2f}")
        time.sleep(0.1)

    model_path = f"models/dqn_{asset_type}_{symbol}.pth"
    torch.save(agent.q.state_dict(), model_path)
    print(f"✅ Model saved to {model_path}")
    return rewards


if __name__ == "__main__":
    # Allow command-line usage: python -m app.rl.train TSLA stock 20 500
    if len(sys.argv) >= 3:
        symbol = sys.argv[1]
        asset_type = sys.argv[2]
        episodes = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        steps = int(sys.argv[4]) if len(sys.argv) > 4 else 1000
        train(symbol, asset_type, episodes, steps)
    else:
        print("Usage: python -m app.rl.train <symbol> <asset_type> [episodes] [steps_per_episode]")
        print("Example: python -m app.rl.train AAPL stock 10 1000")
