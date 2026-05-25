-- =========================================================
-- QUANTCOPILOT AI : FINAL DATABASE SCHEMA
-- =========================================================


-- =========================================================
-- 1. MARKET ASSETS
-- =========================================================

CREATE TABLE IF NOT EXISTS market_assets (

    asset_id SERIAL PRIMARY KEY,

    asset_name VARCHAR(255) NOT NULL,

    ticker_symbol VARCHAR(50) UNIQUE NOT NULL,

    asset_type VARCHAR(50),

    sector VARCHAR(100),

    market VARCHAR(50),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- =========================================================
-- 2. MARKET PRICE HISTORY
-- =========================================================

CREATE TABLE IF NOT EXISTS market_price_history (

    price_id SERIAL PRIMARY KEY,

    asset_id INTEGER NOT NULL,

    trade_date DATE NOT NULL,

    open_price DOUBLE PRECISION,

    high_price DOUBLE PRECISION,

    low_price DOUBLE PRECISION,

    close_price DOUBLE PRECISION,

    volume BIGINT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_asset_price
        FOREIGN KEY(asset_id)
        REFERENCES market_assets(asset_id)
        ON DELETE CASCADE,

    CONSTRAINT unique_asset_trade_date
        UNIQUE(asset_id, trade_date)
);


-- =========================================================
-- 3. TECHNICAL INDICATORS
-- =========================================================

CREATE TABLE IF NOT EXISTS technical_indicators (

    indicator_id SERIAL PRIMARY KEY,

    asset_id INTEGER NOT NULL,

    trade_date DATE NOT NULL,

    rsi DOUBLE PRECISION,

    macd DOUBLE PRECISION,

    atr DOUBLE PRECISION,

    volatility DOUBLE PRECISION,

    daily_return DOUBLE PRECISION,

    sma_20 DOUBLE PRECISION,

    ema_20 DOUBLE PRECISION,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_indicator_asset
        FOREIGN KEY(asset_id)
        REFERENCES market_assets(asset_id)
        ON DELETE CASCADE,

    CONSTRAINT unique_indicator_asset_date
        UNIQUE(asset_id, trade_date)
);


-- =========================================================
-- 4. MARKET REGIMES
-- =========================================================

CREATE TABLE IF NOT EXISTS market_regimes (

    regime_id SERIAL PRIMARY KEY,

    trade_date DATE NOT NULL,

    regime_label VARCHAR(100),

    confidence_score DOUBLE PRECISION,

    volatility_level VARCHAR(50),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- =========================================================
-- 5. AI MARKET REPORTS
-- =========================================================

CREATE TABLE IF NOT EXISTS ai_market_reports (

    report_id SERIAL PRIMARY KEY,

    report_date DATE NOT NULL,

    report_title VARCHAR(255),

    summary TEXT,

    risk_level VARCHAR(50),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- =========================================================
-- 6. ALERT LOGS
-- =========================================================

CREATE TABLE IF NOT EXISTS alert_logs (

    alert_id SERIAL PRIMARY KEY,

    alert_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    alert_type VARCHAR(100),

    alert_message TEXT
);