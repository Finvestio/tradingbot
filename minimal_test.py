#!/usr/bin/env python3
"""
Final test script - exactly as requested by the user
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from database import SessionLocal
from models import MarketData

session = SessionLocal()
print(session.query(MarketData).count())
session.close()