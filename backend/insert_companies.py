from db_config import create_connection
import logging
from datetime import datetime
from psycopg2.extras import RealDictCursor

# -----------------------------------
# LOGGING CONFIGURATION
# -----------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# -----------------------------------
# ENHANCED ASSET DATABASE
# -----------------------------------

DEFAULT_ASSETS = [

    # ================================
    # INDIAN INDICES & BENCHMARKS
    # ================================

    ("NIFTY 50 Index", "^NSEI", "INDEX", "INDEX", "INDIA"),
    ("NIFTY Bank Index", "^NSEBANK", "INDEX", "BANKING", "INDIA"),
    ("NIFTY IT Index", "^CNXIT", "INDEX", "IT", "INDIA"),
    ("NIFTY Pharma Index", "^CNXPHARMA", "INDEX", "PHARMA", "INDIA"),

    # ================================
    # INDIAN LARGE CAP STOCKS
    # ================================

    ("Reliance Industries", "RELIANCE.NS", "STOCK", "ENERGY", "INDIA"),
    ("HDFC Bank", "HDFCBANK.NS", "STOCK", "BANKING", "INDIA"),
    ("ICICI Bank", "ICICIBANK.NS", "STOCK", "BANKING", "INDIA"),
    ("State Bank of India", "SBIN.NS", "STOCK", "BANKING", "INDIA"),
    ("Axis Bank", "AXISBANK.NS", "STOCK", "BANKING", "INDIA"),
    ("Kotak Mahindra Bank", "KOTAKBANK.NS", "STOCK", "BANKING", "INDIA"),

    # ================================
    # INDIAN IT STOCKS
    # ================================

    ("Tata Consultancy Services", "TCS.NS", "STOCK", "IT", "INDIA"),
    ("Infosys", "INFY.NS", "STOCK", "IT", "INDIA"),
    ("HCL Technologies", "HCLTECH.NS", "STOCK", "IT", "INDIA"),
    ("Wipro", "WIPRO.NS", "STOCK", "IT", "INDIA"),

    # ================================
    # INDIAN PHARMA & HEALTHCARE
    # ================================

    ("Dr. Reddy's Laboratories", "DRREDDY.NS", "STOCK", "PHARMA", "INDIA"),
    ("Sun Pharma", "SUNPHARMA.NS", "STOCK", "PHARMA", "INDIA"),
    ("Cipla", "CIPLA.NS", "STOCK", "PHARMA", "INDIA"),

    # ================================
    # INDIAN TELECOM & UTILITIES
    # ================================

    ("Bharti Airtel", "BHARTIARTL.NS", "STOCK", "TELECOM", "INDIA"),
    ("Jio (Reliance Jio)", "RELJIO.NS", "STOCK", "TELECOM", "INDIA"),
    ("Power Grid", "POWERGRID.NS", "STOCK", "UTILITIES", "INDIA"),

    # ================================
    # US MAJOR INDICES
    # ================================

    ("S&P 500 Index", "^GSPC", "INDEX", "INDEX", "USA"),
    ("NASDAQ Composite", "^IXIC", "INDEX", "INDEX", "USA"),
    ("Dow Jones Industrial Average", "^DJI", "INDEX", "INDEX", "USA"),

    # ================================
    # US MEGA CAP TECH
    # ================================

    ("Apple", "AAPL", "STOCK", "TECHNOLOGY", "USA"),
    ("Microsoft", "MSFT", "STOCK", "TECHNOLOGY", "USA"),
    ("NVIDIA", "NVDA", "STOCK", "TECHNOLOGY", "USA"),
    ("Tesla", "TSLA", "STOCK", "TECHNOLOGY", "USA"),
    ("Meta Platforms", "META", "STOCK", "TECHNOLOGY", "USA"),
    ("Alphabet (Google)", "GOOGL", "STOCK", "TECHNOLOGY", "USA"),
    ("Amazon", "AMZN", "STOCK", "TECHNOLOGY", "USA"),

    # ================================
    # US FINANCIALS & BANKS
    # ================================

    ("JPMorgan Chase", "JPM", "STOCK", "BANKING", "USA"),
    ("Bank of America", "BAC", "STOCK", "BANKING", "USA"),
    ("Goldman Sachs", "GS", "STOCK", "BANKING", "USA"),

    # ================================
    # US ENERGY & INDUSTRIALS
    # ================================

    ("ExxonMobil", "XOM", "STOCK", "ENERGY", "USA"),
    ("Chevron", "CVX", "STOCK", "ENERGY", "USA"),

    # ================================
    # VOLATILITY INDICATORS
    # ================================

    ("VIX (Volatility Index)", "^VIX", "VOLATILITY", "VOLATILITY", "USA"),

    # ================================
    # CRYPTOCURRENCIES
    # ================================

    ("Bitcoin", "BTC-USD", "CRYPTO", "CRYPTO", "GLOBAL"),
    ("Ethereum", "ETH-USD", "CRYPTO", "CRYPTO", "GLOBAL"),

    # ================================
    # COMMODITIES & ETFs
    # ================================

    ("Gold ETF", "GLD", "ETF", "COMMODITY", "USA"),
    ("Silver ETF", "SLV", "ETF", "COMMODITY", "USA"),
    ("Crude Oil ETF", "USO", "ETF", "COMMODITY", "USA"),

    # ================================
    # BONDS & FIXED INCOME
    # ================================

    ("US Treasury 10Y", "^TNX", "BOND", "BONDS", "USA"),

]



# -----------------------------------
# VALIDATION FUNCTIONS
# -----------------------------------

def validate_asset(asset_name, ticker_symbol, asset_type, sector, market):
    """
    Validate asset data before insertion.
    
    Args:
        asset_name (str): Name of the asset
        ticker_symbol (str): Ticker symbol
        asset_type (str): Type of asset
        sector (str): Sector classification
        market (str): Market location
    
    Returns:
        tuple: (is_valid, error_message)
    """
    
    if not asset_name or len(asset_name.strip()) == 0:
        return False, f"Invalid asset_name: {asset_name}"
    
    if not ticker_symbol or len(ticker_symbol.strip()) == 0:
        return False, f"Invalid ticker_symbol: {ticker_symbol}"
    
    valid_asset_types = ["INDEX", "STOCK", "CRYPTO", "ETF", "VOLATILITY", "BOND"]
    if asset_type not in valid_asset_types:
        return False, f"Invalid asset_type: {asset_type}. Must be one of {valid_asset_types}"
    
    if not sector or len(sector.strip()) == 0:
        return False, f"Invalid sector: {sector}"
    
    if not market or len(market.strip()) == 0:
        return False, f"Invalid market: {market}"
    
    return True, None


# -----------------------------------
# MAIN ASSET INSERTION FUNCTION
# -----------------------------------

def insert_market_assets():
    """
    Insert market assets into database with proper error handling and logging.
    
    Returns:
        dict: Status report with inserted, updated, skipped, and failed counts
    """
    
    conn = None
    status = {
        "total": len(DEFAULT_ASSETS),
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "errors": []
    }
    
    try:
        logging.info("=" * 60)
        logging.info("Starting Market Asset Initialization")
        logging.info(f"Total assets to process: {len(DEFAULT_ASSETS)}")
        logging.info("=" * 60)
        
        conn = create_connection()
        
        if not conn:
            logging.error("Failed to establish database connection")
            status["failed"] = len(DEFAULT_ASSETS)
            return status
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        for idx, asset in enumerate(DEFAULT_ASSETS, 1):
            try:
                asset_name, ticker_symbol, asset_type, sector, market = asset
                
                # Validate asset data
                is_valid, error_msg = validate_asset(asset_name, ticker_symbol, asset_type, sector, market)
                
                if not is_valid:
                    logging.warning(f"[{idx}/{len(DEFAULT_ASSETS)}] Validation failed: {error_msg}")
                    status["skipped"] += 1
                    status["errors"].append(f"{ticker_symbol}: {error_msg}")
                    continue
                
                # Try to insert/update asset
                cur.execute("""
                    INSERT INTO market_assets
                    (
                        asset_name,
                        ticker_symbol,
                        asset_type,
                        sector,
                        market
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    
                    ON CONFLICT (ticker_symbol)
                    DO UPDATE SET
                        asset_name = EXCLUDED.asset_name,
                        asset_type = EXCLUDED.asset_type,
                        sector = EXCLUDED.sector,
                        market = EXCLUDED.market,
                        created_at = CURRENT_TIMESTAMP
                    
                    RETURNING asset_id;
                """, (asset_name, ticker_symbol, asset_type, sector, market))
                
                result = cur.fetchone()
                
                if result:
                    # Check if it was insert or update
                    cur.execute("""
                        SELECT COUNT(*) as count FROM market_assets 
                        WHERE ticker_symbol = %s 
                        AND created_at = CURRENT_TIMESTAMP;
                    """, (ticker_symbol,))
                    
                    is_new = cur.fetchone()['count'] > 0
                    
                    if is_new:
                        status["inserted"] += 1
                        logging.info(f"[{idx}/{len(DEFAULT_ASSETS)}] ✓ INSERTED: {ticker_symbol} - {asset_name}")
                    else:
                        status["updated"] += 1
                        logging.info(f"[{idx}/{len(DEFAULT_ASSETS)}] ✓ UPDATED: {ticker_symbol} - {asset_name}")
                
            except Exception as e:
                status["failed"] += 1
                error_msg = f"{asset[1]}: {str(e)}"
                status["errors"].append(error_msg)
                logging.error(f"[{idx}/{len(DEFAULT_ASSETS)}] ✗ FAILED: {error_msg}")
        
        # Commit all changes
        conn.commit()
        
        # Log final summary
        logging.info("=" * 60)
        logging.info("MARKET ASSET INITIALIZATION COMPLETE")
        logging.info(f"✓ Inserted: {status['inserted']}")
        logging.info(f"✓ Updated:  {status['updated']}")
        logging.info(f"⊘ Skipped:  {status['skipped']}")
        logging.info(f"✗ Failed:   {status['failed']}")
        
        if status["errors"]:
            logging.warning("Errors encountered:")
            for error in status["errors"]:
                logging.warning(f"  - {error}")
        
        logging.info("=" * 60)
        
        return status
    
    except Exception as e:
        logging.error(f"Fatal error during asset initialization: {str(e)}")
        status["failed"] = len(DEFAULT_ASSETS)
        status["errors"].append(f"Fatal error: {str(e)}")
        return status
    
    finally:
        if conn:
            try:
                conn.close()
                logging.info("Database connection closed")
            except Exception as e:
                logging.error(f"Error closing connection: {str(e)}")


if __name__ == "__main__":
    
    result = insert_market_assets()
    
    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    print(f"Total Processed: {result['total']}")
    print(f"✓ Inserted:     {result['inserted']}")
    print(f"✓ Updated:      {result['updated']}")
    print(f"⊘ Skipped:      {result['skipped']}")
    print(f"✗ Failed:       {result['failed']}")
    print("=" * 60)