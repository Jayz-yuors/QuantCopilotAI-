from db_config import create_connection
from insert_companies import insert_market_assets
from psycopg2.extras import RealDictCursor

import yfinance as yf
import pandas as pd

from datetime import datetime, timedelta, date

import logging
import time

# -----------------------------------
# LOGGING CONFIGURATION
# -----------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Audit report to track all operations
AUDIT_REPORT = {
    "start_time": None,
    "end_time": None,
    "total_tickers": 0,
    "successful_tickers": 0,
    "failed_tickers": 0,
    "skipped_tickers": 0,
    "total_records_fetched": 0,
    "total_records_inserted": 0,
    "total_records_updated": 0,
    "total_records_failed": 0,
    "ticker_details": {},
    "errors": []
}

# -----------------------------------
# CONFIG
# -----------------------------------

START_DATE = date(2015, 1, 1)

REQUEST_PAUSE_SEC = 0.5

SAFETY_LOOKBACK_DAYS = 7


# -----------------------------------
# SAFE TYPE CONVERSION
# -----------------------------------

def safe_float(v):
    try:
        return float(v)
    except:
        return None


def safe_int(v):
    try:
        return int(float(v))
    except:
        return 0


# -----------------------------------
# LOAD COMPANY LIST
# -----------------------------------

def get_company_list():

    conn = create_connection()

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT ticker_symbol
            FROM market_assets
            ORDER BY asset_name;
        """)

        rows = cur.fetchall()

    conn.close()

    if not rows:

        logging.warning("No market_assets found. Inserting defaults.")

        insert_market_assets()

        return get_company_list()

    return [r['ticker_symbol'] for r in rows]


# -----------------------------------
# GET LATEST DATE
# -----------------------------------

def get_latest_date(ticker):

    conn = create_connection()

    with conn.cursor(cursor_factory=RealDictCursor) as cur:

        cur.execute("""
            SELECT MAX(sp.trade_date)

            FROM market_price_history sp

            JOIN market_assets c
            ON sp.asset_id = c.asset_id

            WHERE c.ticker_symbol = %s;
        """, (ticker,))

        result = cur.fetchone()

    conn.close()

    return result['max'] if result and result['max'] else None


# -----------------------------------
# FETCH DATA FROM YFINANCE
# -----------------------------------

def fetch_yfinance(ticker, start_date):

    today = datetime.now().date()

    if start_date >= today:

        logging.info(f"{ticker}: Already Updated")

        return None

    logging.info(
        f"{ticker}: Fetching from {start_date} to {today}"
    )

    df = yf.download(
        ticker,
        start=start_date.strftime("%Y-%m-%d"),
        end=today.strftime("%Y-%m-%d"),
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True
    )

    if df.empty:

        logging.warning(f"{ticker}: No Data Received")

        return None

    df.index = pd.to_datetime(df.index)

    logging.info(
        f"{ticker}: Downloaded {len(df)} Rows"
    )

    return df


# -----------------------------------
# INSERT INTO DATABASE
# -----------------------------------

# -----------------------------------
# INSERT INTO DATABASE WITH AUDIT
# -----------------------------------

def insert_prices(df, ticker):
    """
    Insert/Update price data with comprehensive audit tracking.
    
    Args:
        df (DataFrame): Price data from yfinance
        ticker (str): Ticker symbol
    
    Returns:
        dict: Insertion statistics
    """
    
    stats = {
        "ticker": ticker,
        "total_records": len(df),
        "inserted": 0,
        "updated": 0,
        "failed": 0,
        "error": None
    }
    
    conn = None
    
    try:
        conn = create_connection()
        
        if not conn:
            stats["error"] = "Database connection failed"
            AUDIT_REPORT["errors"].append(f"{ticker}: {stats['error']}")
            logging.error(f"{ticker}: Database connection failed")
            return stats
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            
            cur.execute("""
                SELECT asset_id
                FROM market_assets
                WHERE ticker_symbol = %s;
            """, (ticker,))
            
            row = cur.fetchone()
        
        if not row:
            stats["error"] = "Asset not found in database"
            AUDIT_REPORT["errors"].append(f"{ticker}: {stats['error']}")
            logging.warning(f"{ticker}: Asset Not Found")
            conn.close()
            return stats
        
        asset_id = row['asset_id']
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            
            for ts, row_data in df.iterrows():
                
                try:
                    trade_date = ts.date()
                    
                    def get_col(col_name):
                        if col_name in df.columns:
                            return row_data[col_name]
                        for key in df.columns:
                            if isinstance(key, tuple) and key[0] == col_name:
                                return row_data[key]
                        return None
                    
                    # Validate data
                    close_price = safe_float(get_col("Close"))
                    if close_price is None or close_price <= 0:
                        stats["failed"] += 1
                        continue
                    
                    cur.execute("""
                        INSERT INTO market_price_history
                        (
                            asset_id,
                            trade_date,
                            open_price,
                            high_price,
                            low_price,
                            close_price,
                            volume
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        
                        ON CONFLICT (asset_id, trade_date)
                        DO UPDATE SET
                            open_price = EXCLUDED.open_price,
                            high_price = EXCLUDED.high_price,
                            low_price = EXCLUDED.low_price,
                            close_price = EXCLUDED.close_price,
                            volume = EXCLUDED.volume;
                    """, (
                        asset_id,
                        trade_date,
                        safe_float(get_col("Open")),
                        safe_float(get_col("High")),
                        safe_float(get_col("Low")),
                        close_price,
                        safe_int(get_col("Volume"))
                    ))
                    
                    # Track as inserted or updated
                    stats["inserted"] += 1
                
                except Exception as e:
                    stats["failed"] += 1
                    error_msg = f"Error processing {ticker} on {trade_date}: {str(e)}"
                    AUDIT_REPORT["errors"].append(error_msg)
                    logging.error(error_msg)
        
        conn.commit()
        logging.info(f"✓ {ticker}: Inserted={stats['inserted']}, Failed={stats['failed']}")
        
        AUDIT_REPORT["total_records_fetched"] += stats["total_records"]
        AUDIT_REPORT["total_records_inserted"] += stats["inserted"]
        AUDIT_REPORT["total_records_failed"] += stats["failed"]
        AUDIT_REPORT["ticker_details"][ticker] = stats
        
        return stats
    
    except Exception as e:
        error_msg = f"{ticker}: Fatal error during insertion: {str(e)}"
        stats["error"] = str(e)
        AUDIT_REPORT["errors"].append(error_msg)
        logging.error(error_msg)
        return stats
    
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                logging.error(f"Error closing connection for {ticker}: {str(e)}")


# -----------------------------------
# MAIN FETCHER WITH AUDIT TRACKING
# -----------------------------------

def run_fetcher():
    """
    Fetch market data for all assets and generate comprehensive audit report.
    
    Returns:
        dict: Complete audit report
    """
    
    AUDIT_REPORT["start_time"] = datetime.now()
    
    try:
        tickers = get_company_list()
        
        if not tickers:
            logging.error("No tickers found. Aborting.")
            AUDIT_REPORT["error"] = "No tickers found"
            return AUDIT_REPORT
        
        AUDIT_REPORT["total_tickers"] = len(tickers)
        
        logging.info("=" * 70)
        logging.info("MARKET DATA FETCHER - AUDIT STARTED")
        logging.info(f"Start Time: {AUDIT_REPORT['start_time']}")
        logging.info(f"Total Tickers to Process: {len(tickers)}")
        logging.info("=" * 70)
        
        for idx, ticker in enumerate(tickers, 1):
            
            try:
                logging.info(f"\n[{idx}/{len(tickers)}] Processing: {ticker}")
                
                last_date = get_latest_date(ticker)
                
                if last_date:
                    start_date = (
                        last_date -
                        timedelta(days=SAFETY_LOOKBACK_DAYS)
                    )
                    logging.info(f"  └─ Last record date: {last_date}, Starting from: {start_date}")
                else:
                    start_date = START_DATE
                    logging.info(f"  └─ No history found, Starting from: {start_date}")
                
                df = fetch_yfinance(ticker, start_date)
                
                if df is not None:
                    stats = insert_prices(df, ticker)
                    
                    if stats["error"]:
                        AUDIT_REPORT["failed_tickers"] += 1
                        logging.warning(f"  └─ FAILED: {stats['error']}")
                    else:
                        AUDIT_REPORT["successful_tickers"] += 1
                        logging.info(f"  └─ SUCCESS: Inserted {stats['inserted']} records")
                else:
                    AUDIT_REPORT["skipped_tickers"] += 1
                    logging.info(f"  └─ SKIPPED: No new data available")
                
                time.sleep(REQUEST_PAUSE_SEC)
            
            except Exception as e:
                AUDIT_REPORT["failed_tickers"] += 1
                error_msg = f"Exception processing {ticker}: {str(e)}"
                AUDIT_REPORT["errors"].append(error_msg)
                logging.error(f"  └─ EXCEPTION: {error_msg}")
        
        AUDIT_REPORT["end_time"] = datetime.now()
        duration = AUDIT_REPORT["end_time"] - AUDIT_REPORT["start_time"]
        
        # Generate final audit report
        logging.info("\n" + "=" * 70)
        logging.info("MARKET DATA FETCHER - AUDIT COMPLETED")
        logging.info("=" * 70)
        logging.info(f"End Time: {AUDIT_REPORT['end_time']}")
        logging.info(f"Duration: {duration}")
        logging.info("-" * 70)
        logging.info("SUMMARY STATISTICS:")
        logging.info("-" * 70)
        logging.info(f"Total Tickers Processed:  {AUDIT_REPORT['total_tickers']}")
        logging.info(f"✓ Successful:             {AUDIT_REPORT['successful_tickers']}")
        logging.info(f"✗ Failed:                 {AUDIT_REPORT['failed_tickers']}")
        logging.info(f"⊘ Skipped:                {AUDIT_REPORT['skipped_tickers']}")
        logging.info("-" * 70)
        logging.info("DATA STATISTICS:")
        logging.info("-" * 70)
        logging.info(f"Total Records Fetched:    {AUDIT_REPORT['total_records_fetched']}")
        logging.info(f"✓ Records Inserted:       {AUDIT_REPORT['total_records_inserted']}")
        logging.info(f"✗ Records Failed:         {AUDIT_REPORT['total_records_failed']}")
        
        if AUDIT_REPORT["errors"]:
            logging.info("-" * 70)
            logging.info("ERRORS ENCOUNTERED:")
            logging.info("-" * 70)
            for idx, error in enumerate(AUDIT_REPORT["errors"], 1):
                logging.info(f"{idx}. {error}")
        
        logging.info("=" * 70 + "\n")
        
        return AUDIT_REPORT
    
    except Exception as e:
        AUDIT_REPORT["end_time"] = datetime.now()
        error_msg = f"Fatal error in run_fetcher: {str(e)}"
        AUDIT_REPORT["errors"].append(error_msg)
        logging.error(error_msg)
        return AUDIT_REPORT


def print_audit_report(audit_report):
    """
    Print formatted audit report to console.
    
    Args:
        audit_report (dict): Audit report from run_fetcher
    """
    
    print("\n" + "=" * 70)
    print("QUANTCOPILOT AI - MARKET DATA AUDIT REPORT")
    print("=" * 70)
    print(f"Start Time:    {audit_report['start_time']}")
    print(f"End Time:      {audit_report['end_time']}")
    
    if audit_report['start_time'] and audit_report['end_time']:
        duration = audit_report['end_time'] - audit_report['start_time']
        print(f"Duration:      {duration}")
    
    print("-" * 70)
    print("TICKER PROCESSING:")
    print("-" * 70)
    print(f"Total:         {audit_report['total_tickers']}")
    print(f"✓ Successful:  {audit_report['successful_tickers']}")
    print(f"✗ Failed:      {audit_report['failed_tickers']}")
    print(f"⊘ Skipped:     {audit_report['skipped_tickers']}")
    print("-" * 70)
    print("DATA INSERTION:")
    print("-" * 70)
    print(f"Records Fetched:  {audit_report['total_records_fetched']}")
    print(f"✓ Inserted:       {audit_report['total_records_inserted']}")
    print(f"✗ Failed:         {audit_report['total_records_failed']}")
    print("=" * 70 + "\n")


# -----------------------------------
# RUN SCRIPT
# -----------------------------------

if __name__ == "__main__":
    
    audit_report = run_fetcher()
    print_audit_report(audit_report)