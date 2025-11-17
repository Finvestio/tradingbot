# app/rl/dqn.py
import random
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from collections import deque, namedtuple

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

# ------------------- DQN Agent -------------------
class DQNAgent:
    def __init__(self, state_dim, action_dim=3, lr=1e-3, gamma=0.99, buffer_size=200_000):
        self.q = QNet(state_dim, action_dim)
        self.tgt = QNet(state_dim, action_dim)
        self.tgt.load_state_dict(self.q.state_dict())
        self.opt = optim.Adam(self.q.parameters(), lr=lr)
        self.gamma = gamma
        self.action_dim = action_dim
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
        self.buf.append(Transition(s, a, r, ns, d))

    def train_step(self, batch_size=256):
        if len(self.buf) < batch_size:
            return 0.0
        batch = random.sample(self.buf, batch_size)
        b = Transition(*zip(*batch))

        s = torch.tensor(np.stack(b.s)).float()
        a = torch.tensor(b.a).long().unsqueeze(1)
        r = torch.tensor(b.r).float().unsqueeze(1)
        ns = torch.tensor(np.stack(b.ns)).float()
        d = torch.tensor(b.d).float().unsqueeze(1)

        qsa = self.q(s).gather(1, a)
        with torch.no_grad():
            max_next = self.tgt(ns).max(1, keepdim=True)[0]
            target = r + (1 - d) * self.gamma * max_next

        loss = nn.MSELoss()(qsa, target)
        self.opt.zero_grad()
        loss.backward()
        self.opt.step()
        return float(loss.item())

    def soft_update(self, tau=0.01):
        for tp, sp in zip(self.tgt.parameters(), self.q.parameters()):
            tp.data.copy_(tau * sp.data + (1 - tau) * tp.data)
