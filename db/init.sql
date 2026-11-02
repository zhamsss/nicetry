CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE accounts (
    account_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_number VARCHAR(20) NOT NULL UNIQUE,
    bank_name VARCHAR(100) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    current_balance NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_accounts_number ON accounts(account_number);

CREATE TABLE transactions (
    transaction_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id UUID NOT NULL,
    direction VARCHAR(3) NOT NULL CHECK (direction IN ('IN', 'OUT')),
    amount NUMERIC(15, 2) NOT NULL CHECK (amount > 0),
    currency VARCHAR(3) NOT NULL,
    counterparty_inn VARCHAR(12),
    purpose TEXT,
    value_date TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_transactions_account FOREIGN KEY (account_id) 
        REFERENCES accounts(account_id) ON DELETE RESTRICT
);

CREATE INDEX idx_transactions_account_date ON transactions(account_id, value_date);

CREATE TABLE risk_limits (
    limit_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id UUID,
    metric_name VARCHAR(50) NOT NULL,
    yellow_zone_threshold NUMERIC(10, 4) NOT NULL,
    red_zone_threshold NUMERIC(10, 4) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_risk_limits_account FOREIGN KEY (account_id) 
        REFERENCES accounts(account_id) ON DELETE CASCADE
);

CREATE TABLE system_alerts (
    alert_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    limit_id UUID NOT NULL,
    actual_value NUMERIC(10, 4) NOT NULL,
    severity VARCHAR(10) NOT NULL CHECK (severity IN ('WARNING', 'CRITICAL')),
    status VARCHAR(15) NOT NULL DEFAULT 'NEW' CHECK (status IN ('NEW', 'ACKNOWLEDGED', 'RESOLVED')),
    triggered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT fk_system_alerts_limit FOREIGN KEY (limit_id) 
        REFERENCES risk_limits(limit_id) ON DELETE CASCADE
);

CREATE INDEX idx_system_alerts_status ON system_alerts(status) WHERE status = 'NEW';
