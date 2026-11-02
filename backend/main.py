import os
import sqlite3
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, status

# Имя файла, где будет храниться наша реальная база данных
DB_FILE = "db/finrisk_test.db"

app = FastAPI(
    title="FinRisk-Monitor Real DB Test",
    description="Прототип системы, работающий с реальной базой данных SQLite через SQL-запросы"
)

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
def init_db():
    # Создаем папку db, если её нет
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Создаем таблицу расчетных счетов
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        account_id TEXT PRIMARY KEY,
        account_number TEXT NOT NULL UNIQUE,
        bank_name TEXT NOT NULL,
        currency TEXT NOT NULL,
        current_balance REAL NOT NULL DEFAULT 0.0,
        short_term_debt REAL NOT NULL DEFAULT 1500000.0, -- Добавим для теста Краткосрочный долг
        updated_at TEXT
    );
    """)
    
    # Создаем таблицу транзакций
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        transaction_id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        direction TEXT NOT NULL,
        amount REAL NOT NULL,
        currency TEXT NOT NULL,
        counterparty_inn TEXT,
        purpose TEXT,
        value_date TEXT,
        created_at TEXT,
        FOREIGN KEY (account_id) REFERENCES accounts (account_id)
    );
    """)
    
    # Создаем таблицу алертов
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_alerts (
        alert_id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        actual_value REAL NOT NULL,
        severity TEXT NOT NULL,
        status TEXT NOT NULL,
        triggered_at TEXT
    );
    """)
    
    # Наполняем базу тестовым счетом, если таблица пуста
    cursor.execute("SELECT COUNT(*) FROM accounts;")
    if cursor.fetchone()[0] == 0:
        test_account_id = "e3b0c442-98fc-11ee-b9d1-0242ac120002"
        cursor.execute("""
            INSERT INTO accounts (account_id, account_number, bank_name, currency, current_balance, short_term_debt, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (test_account_id, "40702810100000123456", "НГУ Банк", "RUB", 500000.00, 1500000.00, datetime.utcnow().isoformat()))
        conn.commit()
        print(f"База данных успешно инициализирована. Добавлен тестовый счет: {test_account_id}")
        
    conn.close()

# Запускаем создание базы данных при старте приложения
init_db()

# --- СХЕМЫ ВАЛИДАЦИИ (PYDANTIC) ---
class TransactionPayload(BaseModel):
    account_id: uuid.UUID
    direction: str = Field(..., description="IN или OUT")
    amount: float = Field(..., gt=0)
    currency: str = "RUB"
    counterparty_inn: Optional[str] = None
    purpose: Optional[str] = None
    value_date: datetime

# --- ЭНДПОИНТЫ С РАБОТОЙ ЧЕРЕЗ SQL ---

@app.post("/transactions", status_code=status.HTTP_202_ACCEPTED)
async def create_transaction(payload: TransactionPayload):
    account_id_str = str(payload.account_id)
    direction = payload.direction.upper()
    
    if direction not in ["IN", "OUT"]:
        raise HTTPException(status_code=400, detail="Направление должно быть IN или OUT")
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 1. Проверяем, существует ли такой счет в базе данных (SQL SELECT)
    cursor.execute("SELECT current_balance, short_term_debt FROM accounts WHERE account_id = ?;", (account_id_str,))
    account = cursor.fetchone()
    if not account:
        conn.close()
        raise HTTPException(status_code=404, detail="Указанный расчетный счет не найден в базе данных")
        
    current_balance, short_term_debt = account
    
    # 2. Рассчитываем новый баланс
    if direction == "IN":
        new_balance = current_balance + payload.amount
    else:
        new_balance = current_balance - payload.amount
        
    # 3. Обновляем баланс счета в базе данных (SQL UPDATE)
    cursor.execute("""
        UPDATE accounts 
        SET current_balance = ?, updated_at = ? 
        WHERE account_id = ?;
    """, (new_balance, datetime.utcnow().isoformat(), account_id_str))
    
    # 4. Записываем транзакцию в базу данных (SQL INSERT)
    tx_id = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO transactions (transaction_id, account_id, direction, amount, currency, counterparty_inn, purpose, value_date, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (tx_id, account_id_str, direction, payload.amount, payload.currency, payload.counterparty_inn, payload.purpose, payload.value_date.isoformat(), datetime.utcnow().isoformat()))
    
    # 5. RISK ENGINE: Проверяем риск-лимиты (Норматив ликвидности > 0.2)
    current_liquidity = new_balance / short_term_debt
    if current_liquidity < 0.2:
        alert_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO system_alerts (alert_id, account_id, actual_value, severity, status, triggered_at)
            VALUES (?, ?, ?, ?, ?, ?);
        """, (alert_id, account_id_str, current_liquidity, "CRITICAL", "NEW", datetime.utcnow().isoformat()))
        print(f"\033[91m[БД ALERT] Запись о риске сохранена в таблицу system_alerts! К_{{ал}} = {current_liquidity:.2f}\033[0m")

    conn.commit()
    conn.close()
    
    return {"transaction_id": tx_id, "status": "ACCEPTED_FOR_ANALYSIS_AND_SAVED"}


@app.get("/risks/status")
async def get_risk_status():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Вытягиваем актуальные данные из базы (SQL SELECT)
    cursor.execute("SELECT account_id, account_number, current_balance, short_term_debt FROM accounts;")
    account_data = cursor.fetchone()
    
    if not account_data:
        conn.close()
        return {"message": "Нет доступных счетов"}
        
    acc_id, acc_num, balance, debt = account_data
    current_liquidity = balance / debt
    
    # Проверяем количество активных алертов в базе данных
    cursor.execute("SELECT alert_id, actual_value, severity, triggered_at FROM system_alerts WHERE status = 'NEW';")
    active_alerts = cursor.fetchall()
    
    conn.close()
    
    status_zone = "CRITICAL" if current_liquidity < 0.2 else "WARNING" if current_liquidity < 0.4 else "STABLE"
    
    return {
        "company_status": status_zone,
        "database_file": DB_FILE,
        "account_info": {
            "account_id": acc_id,
            "account_number": acc_num,
            "current_balance_rub": balance
        },
        "metrics": {
            "absolute_liquidity": round(current_liquidity, 4),
            "normative": 0.2
        },
        "active_alerts_count": len(active_alerts),
        "alerts_from_db": [
            {"alert_id": a[0], "value": a[1], "severity": a[2], "triggered_at": a[3]} for a in active_alerts
        ]
    }
