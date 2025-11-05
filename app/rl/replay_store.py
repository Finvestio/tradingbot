import json
from typing import List, Tuple
from app.db import get_db_connection

def _to_json(vec: List[float]) -> str:
    return json.dumps([float(x) for x in vec])

def add_experience(user_id: int, asset_type: str, symbol: str,
                   state: List[float], action: int, reward: float,
                   next_state: List[float], done: bool) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO rl_experiences
          (user_id, asset_type, symbol, action, reward, done, state_json, next_state_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (user_id, asset_type, symbol, int(action), float(reward), int(done),
         _to_json(state), _to_json(next_state))
    )
    conn.commit()
    cur.close()
    conn.close()

def sample_latest(user_id: int, symbol: str, limit: int = 512) -> List[Tuple]:
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT action, reward, done, state_json, next_state_json
        FROM rl_experiences
        WHERE user_id=%s AND symbol=%s
        ORDER BY id DESC
        LIMIT %s
        """,
        (user_id, symbol, int(limit))
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows
