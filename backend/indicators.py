from db_config import create_connection

import pandas as pd
import pandas_ta as ta

import logging

# =========================================================
# LOGGING CONFIGURATION
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# =========================================================
# FETCH PRICE DATA
# =========================================================

def fetch_price_data(asset_id):

    conn = create_connection()

    query = """
        SELECT
            trade_date,
            open_price,
            high_price,
            low_price,
            close_price,
            volume

        FROM market_price_history

        WHERE asset_id = %s

        ORDER BY trade_date ASC;
    """

    df = pd.read_sql(query, conn, params=(asset_id,))

    conn.close()

    return df


# =========================================================
# FETCH ALL ASSETS
# =========================================================

def get_all_assets():

    conn = create_connection()

    cur = conn.cursor()

    cur.execute("""

        SELECT asset_id, ticker_symbol

        FROM market_assets

        ORDER BY ticker_symbol;

    """)

    rows = cur.fetchall()

    conn.close()

    return rows


# =========================================================
# CALCULATE INDICATORS
# =========================================================

def calculate_indicators(df):

    if df.empty or len(df) < 30:

        return None

    # -----------------------------------------------------
    # DAILY RETURNS
    # -----------------------------------------------------

    df["daily_return"] = (
        df["close_price"].pct_change()
    )

    # -----------------------------------------------------
    # RSI
    # -----------------------------------------------------

    df["rsi"] = ta.rsi(
        df["close_price"],
        length=14
    )

    # -----------------------------------------------------
    # MACD
    # -----------------------------------------------------

    macd = ta.macd(df["close_price"])

    df["macd"] = macd["MACD_12_26_9"]

    # -----------------------------------------------------
    # ATR
    # -----------------------------------------------------

    df["atr"] = ta.atr(
        high=df["high_price"],
        low=df["low_price"],
        close=df["close_price"],
        length=14
    )

    # -----------------------------------------------------
    # VOLATILITY
    # -----------------------------------------------------

    df["volatility"] = (
        df["daily_return"]
        .rolling(window=20)
        .std()
    )

    # -----------------------------------------------------
    # SMA20
    # -----------------------------------------------------

    df["sma_20"] = ta.sma(
        df["close_price"],
        length=20
    )

    # -----------------------------------------------------
    # EMA20
    # -----------------------------------------------------

    df["ema_20"] = ta.ema(
        df["close_price"],
        length=20
    )

    return df


# =========================================================
# INSERT INDICATORS
# =========================================================

def insert_indicators(asset_id, df):

    conn = create_connection()

    cur = conn.cursor()

    inserted = 0

    for _, row in df.iterrows():

        if pd.isna(row["rsi"]):
            continue

        cur.execute("""

            INSERT INTO technical_indicators
            (
                asset_id,
                trade_date,
                rsi,
                macd,
                atr,
                volatility,
                daily_return,
                sma_20,
                ema_20
            )

            VALUES
            (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )

            ON CONFLICT
            (
                asset_id,
                trade_date
            )

            DO UPDATE SET

                rsi = EXCLUDED.rsi,
                macd = EXCLUDED.macd,
                atr = EXCLUDED.atr,
                volatility = EXCLUDED.volatility,
                daily_return = EXCLUDED.daily_return,
                sma_20 = EXCLUDED.sma_20,
                ema_20 = EXCLUDED.ema_20;

        """, (

            asset_id,
            row["trade_date"],

            safe_float(row["rsi"]),
            safe_float(row["macd"]),
            safe_float(row["atr"]),
            safe_float(row["volatility"]),
            safe_float(row["daily_return"]),
            safe_float(row["sma_20"]),
            safe_float(row["ema_20"])

        ))

        inserted += 1

    conn.commit()

    conn.close()

    return inserted


# =========================================================
# SAFE FLOAT
# =========================================================

def safe_float(v):

    try:

        return float(v)

    except:

        return None


# =========================================================
# MAIN ENGINE
# =========================================================

def run_indicator_engine():

    assets = get_all_assets()

    logging.info("=" * 60)
    logging.info("TECHNICAL INDICATOR ENGINE STARTED")
    logging.info("=" * 60)

    total_inserted = 0

    for asset in assets:

        asset_id = asset[0]
        ticker   = asset[1]

        logging.info(f"Processing: {ticker}")

        try:

            df = fetch_price_data(asset_id)

            df = calculate_indicators(df)

            if df is None:

                logging.warning(
                    f"{ticker}: Insufficient Data"
                )

                continue

            inserted = insert_indicators(asset_id, df)

            total_inserted += inserted

            logging.info(
                f"✓ {ticker}: {inserted} Indicator Rows Processed"
            )

        except Exception as e:

            logging.error(
                f"✗ {ticker}: {str(e)}"
            )

    logging.info("=" * 60)
    logging.info("TECHNICAL INDICATOR ENGINE COMPLETED")
    logging.info(f"Total Rows Processed: {total_inserted}")
    logging.info("=" * 60)


# =========================================================
# RUN SCRIPT
# =========================================================

if __name__ == "__main__":

    run_indicator_engine()