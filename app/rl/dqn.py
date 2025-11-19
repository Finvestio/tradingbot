# app/rl/dqn.py
import random
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from collections import deque, namedtuple
from app.rl.sumtree import SumTree

Transition = namedtuple("Transition", "s a r ns d")

# ------------------- Q-Network -------------------
class QNet(nn.Module):
    def __init__(self, in_dim, out_dim):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, 256), nn.ReLU(),
            nn.Linear(256, 256), nn.ReLU(),
            nn.Linear(256, out_dim)
        )
    def forward(self, x):
        return self.net(x)

# ------------------- DQN Agent with Prioritized Experience Replay -------------------
class DQNAgent:
    def __init__(self, state_dim, action_dim=3, lr=1e-3, gamma=0.99, buffer_size=200_000, 
                 use_per=True, alpha=0.6, beta=0.4, beta_increment=1e-6):
        """
        Args:
            state_dim: Dimension of state vector
            action_dim: Number of actions (3: HOLD, BUY, SELL)
            lr: Learning rate
            gamma: Discount factor
            buffer_size: Size of replay buffer
            use_per: Whether to use Prioritized Experience Replay
            alpha: PER priority exponent (0 = uniform, 1 = full prioritization)
            beta: PER importance sampling exponent (starts at beta, goes to 1.0)
            beta_increment: How much to increment beta per sample
        """
        self.q = QNet(state_dim, action_dim)
        self.tgt = QNet(state_dim, action_dim)
        self.tgt.load_state_dict(self.q.state_dict())
        self.opt = optim.Adam(self.q.parameters(), lr=lr)
        self.gamma = gamma
        self.action_dim = action_dim
        self.use_per = use_per
        
        if use_per:
            # Prioritized Experience Replay
            self.tree = SumTree(buffer_size)
            self.alpha = alpha  # Priority exponent
            self.beta = beta  # Importance sampling exponent
            self.beta_increment = beta_increment
            self.max_priority = 1.0  # Initial priority for new transitions
            self.buffer_size = buffer_size
        else:
            # Standard uniform replay buffer
            self.buf = deque(maxlen=buffer_size)

    def act(self, s, eps=0.1):
        """ε-greedy action selection with Q-value storage for confidence calculation."""
        if random.random() < eps:
            # Store random Q-values for random actions
            self.last_q_values = [0.0, 0.0, 0.0]  # Neutral confidence for random actions
            return random.randrange(self.action_dim)
        with torch.no_grad():
            qv = self.q(torch.tensor(s).float().unsqueeze(0))
            # Store Q-values for confidence calculation
            self.last_q_values = qv.squeeze().tolist()
            return int(qv.argmax().item())

    def push(self, s, a, r, ns, d):
        """Store transition in replay buffer."""
        transition = Transition(s, a, r, ns, d)
        
        if self.use_per:
            # Add with maximum priority (will be updated after first training step)
            self.tree.add(self.max_priority, transition)
        else:
            self.buf.append(transition)

    def train_step(self, batch_size=256):
        """Train on a batch of transitions."""
        if self.use_per:
            # Prioritized Experience Replay
            if self.tree.n_entries < batch_size:
                return 0.0
            
            # Sample batch using priorities
            batch = []
            tree_indices = []
            priorities = []
            
            segment = self.tree.total() / batch_size
            
            # Increment beta (importance sampling exponent)
            self.beta = min(1.0, self.beta + self.beta_increment)
            
            for i in range(batch_size):
                a = segment * i
                b = segment * (i + 1)
                s = random.uniform(a, b)
                (idx, p, data) = self.tree.get(s)
                priorities.append(p)
                tree_indices.append(idx)
                batch.append(data)
            
            # Compute importance sampling weights
            priorities = np.array(priorities)
            sampling_probabilities = priorities / self.tree.total()
            is_weights = np.power(self.tree.n_entries * sampling_probabilities, -self.beta)
            is_weights /= is_weights.max()  # Normalize
            
            # Convert to tensors
            is_weights = torch.tensor(is_weights, dtype=torch.float32).unsqueeze(1)
            
        else:
            # Standard uniform sampling
            if len(self.buf) < batch_size:
                return 0.0
            batch = random.sample(self.buf, batch_size)
            tree_indices = None
            is_weights = None
        
        # Unpack batch
        b = Transition(*zip(*batch))
        
        s = torch.tensor(np.stack(b.s)).float()
        a = torch.tensor(b.a).long().unsqueeze(1)
        r = torch.tensor(b.r).float().unsqueeze(1)
        ns = torch.tensor(np.stack(b.ns)).float()
        d = torch.tensor(b.d).float().unsqueeze(1)

        # Compute Q-values and targets
        qsa = self.q(s).gather(1, a)
        with torch.no_grad():
            max_next = self.tgt(ns).max(1, keepdim=True)[0]
            target = r + (1 - d) * self.gamma * max_next

        # Compute TD errors (for PER priority updates)
        td_errors = torch.abs(qsa - target).detach().cpu().numpy()
        
        # Compute loss with importance sampling weights if using PER
        if self.use_per:
            loss = (is_weights * nn.MSELoss(reduction='none')(qsa, target)).mean()
        else:
            loss = nn.MSELoss()(qsa, target)
        
        self.opt.zero_grad()
        loss.backward()
        # Gradient clipping for stability
        torch.nn.utils.clip_grad_norm_(self.q.parameters(), 10.0)
        self.opt.step()
        
        # Update priorities in PER
        if self.use_per and tree_indices is not None:
            for idx, td_error in zip(tree_indices, td_errors):
                priority = (td_error + 1e-6) ** self.alpha
                self.tree.update(idx, priority)
                self.max_priority = max(self.max_priority, priority)
        
        return float(loss.item())

    def soft_update(self, tau=0.01):
        for tp, sp in zip(self.tgt.parameters(), self.q.parameters()):
            tp.data.copy_(tau * sp.data + (1 - tau) * tp.data)
    
    def learn(self, s, a, r, ns, d):
        """Wrapper method for compatibility with rl_trader.py"""
        self.push(s, a, r, ns, d)
        return self.train_step()