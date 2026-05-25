"""
DATA PROCESSOR
Validates, structures, and prepares N8N build report data for report generation
Separates data processing from report formatting logic
"""

import logging
import json
from typing import Dict, List, Any
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# =========================================================
# RAW DATA LOGGING & VALIDATION
# =========================================================

def log_raw_data(raw_data: Any) -> None:
    """Log the exact raw data received from N8N"""
    logger.info("=" * 60)
    logger.info("📥 RAW DATA FROM N8N:")
    logger.info("=" * 60)
    logger.info(f"{json.dumps(raw_data, indent=2)}")
    logger.info("=" * 60)

# =========================================================
# SAFE PARSING HELPERS
# =========================================================

def safe_parse_json(data, default=None):
    """Safely parse JSON strings"""
    if default is None:
        default = {} if isinstance(data, dict) else [] if isinstance(data, list) else {}
    
    if isinstance(data, (dict, list)):
        return data
    
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            return parsed if isinstance(parsed, (dict, list)) else default
        except:
            return default
    
    return default

def ensure_dict(data, key_name="data"):
    """Ensure data is dict"""
    parsed = safe_parse_json(data, default={})
    if not isinstance(parsed, dict):
        logger.warning(f"⚠️ {key_name} expected dict, got {type(parsed).__name__}")
        return {}
    return parsed

def ensure_list(data, key_name="data"):
    """Ensure data is list"""
    parsed = safe_parse_json(data, default=[])
    if not isinstance(parsed, list):
        logger.warning(f"⚠️ {key_name} expected list, got {type(parsed).__name__}")
        return []
    return parsed

# =========================================================
# DATA PROCESSOR
# =========================================================

def process_build_report(raw_data: Any) -> Dict[str, Any]:
    """
    Process raw N8N build report data into clean format
    
    Args:
        raw_data: Raw dictionary from N8N HTTP Request
        
    Returns:
        Structured dictionary ready for report_generator
    """
    
    # Step 1: Log raw data for debugging
    log_raw_data(raw_data)
    
    # Ensure we have a dict
    if not isinstance(raw_data, dict):
        logger.error(f"❌ Expected dict, got {type(raw_data).__name__}")
        return _get_empty_report()
    
    logger.info("🔧 Processing build report data...")
    
    # Step 2: Extract and validate basic fields
    processed = {
        "status": str(raw_data.get("status", "completed")).strip(),
        "timestamp": str(raw_data.get("timestamp", datetime.now().isoformat())).strip(),
        "total_assets": raw_data.get("total_assets", 0),
    }
    
    logger.info(f"✅ Basic fields extracted: status={processed['status']}, timestamp={processed['timestamp']}")
    
    # Step 3: Process METRICS
    raw_metrics = raw_data.get("metrics", {})
    processed["metrics"] = ensure_dict(raw_metrics, "metrics")
    logger.info(f"📊 Metrics extracted: {len(processed['metrics'])} fields")
    
    # Step 4: Process ASSETS (THE CRITICAL PART)
    raw_assets = raw_data.get("assets", [])
    logger.info(f"🔍 Processing assets field...")
    logger.info(f"   Raw assets type: {type(raw_assets).__name__}")
    logger.info(f"   Raw assets value: {raw_assets}")
    
    # Handle case where assets is a JSON string
    if isinstance(raw_assets, str):
        logger.warning(f"⚠️ Assets received as STRING! Parsing JSON...")
        try:
            raw_assets = json.loads(raw_assets)
            logger.info(f"✅ Parsed JSON string successfully")
        except:
            logger.error(f"❌ Failed to parse assets JSON string")
            raw_assets = []
    
    assets = ensure_list(raw_assets, "assets")
    
    if assets:
        logger.info(f"✅ Assets received: {len(assets)} items")
        logger.info(f"🏷️ First asset structure:")
        logger.info(f"{json.dumps(assets[0], indent=2)}")
        for i in range(min(3, len(assets))):
            logger.info(f"   Asset {i}: Symbol={assets[i].get('symbol', 'N/A')}, RSI={assets[i].get('rsi', 'N/A')}")
    else:
        logger.warning(f"⚠️ No assets in data! Expected list, processed list is empty")
    
    processed["assets"] = assets
    
    # Step 5: Process INDICATORS
    raw_indicators = raw_data.get("indicators", {})
    processed["indicators"] = ensure_dict(raw_indicators, "indicators")
    logger.info(f"📈 Indicators extracted: {len(processed['indicators'])} fields")
    
    # Step 6: Process INSIGHTS
    raw_insights = raw_data.get("insights", [])
    processed["insights"] = ensure_list(raw_insights, "insights")
    logger.info(f"💡 Insights extracted: {len(processed['insights'])} items")
    
    # Step 7: Process ALERTS
    raw_alerts = raw_data.get("alerts", [])
    processed["alerts"] = ensure_list(raw_alerts, "alerts")
    logger.info(f"🚨 Alerts extracted: {len(processed['alerts'])} items")
    
    # FINAL SUMMARY
    logger.info("=" * 60)
    logger.info("📋 PROCESSED DATA SUMMARY:")
    logger.info("=" * 60)
    logger.info(f"Status: {processed['status']}")
    logger.info(f"Total Assets: {processed['total_assets']}")
    logger.info(f"Metrics: {len(processed['metrics'])} fields")
    logger.info(f"Assets: {len(processed['assets'])} movers")
    logger.info(f"Indicators: {len(processed['indicators'])} fields")
    logger.info(f"Insights: {len(processed['insights'])} items")
    logger.info(f"Alerts: {len(processed['alerts'])} items")
    logger.info("=" * 60)
    
    return processed

def _get_empty_report() -> Dict[str, Any]:
    """Return empty report structure"""
    return {
        "status": "completed",
        "timestamp": datetime.now().isoformat(),
        "total_assets": 0,
        "metrics": {},
        "assets": [],
        "indicators": {},
        "insights": [],
        "alerts": []
    }
