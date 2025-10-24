# 🗄️ Database Fix Guide - SQLAlchemy OperationalError

## 🚨 Current Issue
```
OperationalError: (1054, "Unknown column 'users.email' or 'users.created_at' in 'field list'")
```

The User model has `email` and `created_at` fields, but the MySQL table doesn't have these columns yet.

## 🔧 Solution Options

### Option A: Run Database Migration (RECOMMENDED)
```bash
cd C:\Users\yassi\Desktop\trading_bot
.\.venv\Scripts\python.exe scripts\migrate_db.py
```
This will:
- ✅ Add missing `email` column (VARCHAR(100) UNIQUE)  
- ✅ Add missing `created_at` column (DATETIME DEFAULT CURRENT_TIMESTAMP)
- ✅ Update existing users with default email values
- ✅ Show final table structure

### Option B: Manual MySQL Commands
If you prefer to do it manually in MySQL:
```sql
USE trading_bot;
ALTER TABLE users ADD COLUMN email VARCHAR(100) UNIQUE;
ALTER TABLE users ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP;

-- Update existing users with default emails
UPDATE users 
SET email = CONCAT(username, '@example.com'),
    created_at = COALESCE(created_at, NOW())
WHERE email IS NULL OR email = '';
```

### Option C: Recreate Database (NUCLEAR OPTION)
⚠️ **This will delete all existing data!**
```bash
cd C:\Users\yassi\Desktop\trading_bot
.\.venv\Scripts\python.exe scripts\init_db.py
```

## 📋 Current User Model Structure
```python
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    wallet_balance = Column(Float, default=100000.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    trades = relationship("OrderTrade", back_populates="user")
```

## ✅ After Running Migration

1. **Start Backend:**
```bash
cd C:\Users\yassi\Desktop\trading_bot
.\.venv\Scripts\python.exe -m uvicorn app.api:app --reload --port 8081
```

2. **Start Frontend:**  
```bash
cd C:\Users\yassi\Desktop\trading_bot\trading-dashboard
npm start
```

3. **Test User Creation:**
- Go to http://localhost:4200
- Navigate to "Order Management" tab
- Try creating a new user with username and email

## 🔍 Verification
After migration, your users table should have:
- ✅ `id` (INT, PRIMARY KEY)
- ✅ `username` (VARCHAR(50), UNIQUE)  
- ✅ `email` (VARCHAR(100), UNIQUE) ← **NEW**
- ✅ `wallet_balance` (FLOAT, DEFAULT 100000)
- ✅ `created_at` (DATETIME, DEFAULT NOW()) ← **NEW**

## 🐛 Troubleshooting

**If migration fails:**
1. Ensure XAMPP MySQL is running
2. Check database `trading_bot` exists
3. Verify user has ALTER permissions
4. Check for existing data conflicts

**If you get "Duplicate entry" errors:**
- Some usernames might conflict when generating emails
- Edit the migration script to handle duplicates differently