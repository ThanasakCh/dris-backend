# Database Management Scripts

This directory contains utility scripts for managing the PostgreSQL database during development.

## Scripts

### 🔍 `check_db.py` - Check Database Status

```bash
python scripts/check_db.py
```

**Purpose:** Inspect database tables and columns  
**Use when:** You want to see what's in the database

**Output:**

- List of all tables
- Columns in the users table

---

### 🔨 `init_db.py` - Initialize Database

```bash
python scripts/init_db.py
```

**Purpose:** Create all database tables based on SQLAlchemy models  
**Use when:** First-time database setup

**Note:** Safe to run multiple times (won't delete existing data)

---

### 🗑️ `reset_db.py` - Reset Database

```bash
python scripts/reset_db.py
```

**Purpose:** Drop ALL tables and recreate them  
**Use when:** You want to start fresh

**⚠️ WARNING:** This will DELETE ALL DATA! Use with caution.

---

### 🔧 `fix_db.py` - Fix Database Schema

```bash
python scripts/fix_db.py
```

**Purpose:** Add missing columns to existing tables  
**Use when:** Manual schema fixes are needed

**Current fixes:**

- Adds `is_active` column to users table if missing

---

## Database Connection

All scripts connect to:

```
postgresql://postgres:1234@localhost:5432/DATA
```

To change the connection, edit the connection string in each script.

## Common Workflows

### First Time Setup

```bash
python scripts/init_db.py
```

### Check What's There

```bash
python scripts/check_db.py
```

### Start Over (Development)

```bash
python scripts/reset_db.py
```

### Fix Schema Issues

```bash
python scripts/fix_db.py
```

## Production Note

⚠️ These scripts are for **development only**. In production:

- Use **Alembic migrations** for schema changes
- Never use `reset_db.py` (data loss!)
- Use proper backup/restore procedures
