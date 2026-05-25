from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import traceback
import logging
import requests
import os
from typing import Dict, Any
from dotenv import load_dotenv

from db_config import create_connection

load_dotenv()
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")

# =========================================================
# LOGGING SETUP
# =========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# =========================================================
# IMPORT YOUR ENGINES
# =========================================================

from fetcher import run_fetcher
from indicators import run_indicator_engine
from data_processor import process_build_report
from report_generator import generate_and_send_reports       # email — UNTOUCHED
from web_report_generator import generate_web_report         # website — NEW

# =========================================================
# FASTAPI INITIALIZATION
# =========================================================

app = FastAPI(
    title="QuantCopilot AI API",
    description="AI-Powered Quantitative Market Intelligence System",
    version="1.0"
)

# =========================================================
# CORS  (allow React frontend on localhost:5173 / 3000)
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================
# ROOT
# =========================================================

@app.get("/")
def root():
    return {"message": "QuantCopilot AI Backend Running"}

# =========================================================
# RUN FETCHER
# =========================================================

@app.get("/run-fetcher")
@app.post("/run-fetcher")
def run_fetcher_api():
    try:
        run_fetcher()
        return JSONResponse(status_code=200, content={"status": "success", "message": "Fetcher Completed Successfully"})
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# =========================================================
# RUN INDICATORS
# =========================================================

@app.get("/run-indicators")
@app.post("/run-indicators")
def run_indicators_api():
    try:
        run_indicator_engine()
        return JSONResponse(status_code=200, content={"status": "success", "message": "Indicator Engine Completed"})
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
def health_check():
    return {"backend": "healthy", "status": "running"}

# =========================================================
# VALIDATE REGIME RESULTS
# =========================================================

@app.get("/validate-regime")
def validate_regime():
    try:
        conn = create_connection()
        cur  = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) AS total_rows, MAX(trade_date) AS latest_date,
                   COUNT(DISTINCT regime_label) AS regime_count,
                   COUNT(confidence_score) AS confidence_count
            FROM market_regimes;
        """)
        result           = cur.fetchone()
        total_rows       = result[0]
        latest_date      = result[1]
        regime_count     = result[2]
        confidence_count = result[3]
        validation_passed = (
            total_rows > 1000 and latest_date is not None
            and regime_count >= 2 and confidence_count > 1000
        )
        conn.close()
        return {
            "status": "success",
            "validation_passed": validation_passed,
            "total_rows": total_rows,
            "latest_trade_date": str(latest_date),
            "detected_regimes": regime_count,
            "confidence_records": confidence_count,
        }
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# =========================================================
# BUILD REPORT & SEND EMAIL  (existing — UNTOUCHED)
# =========================================================

@app.post("/build-report")
def build_and_send_report(report_data: Dict[str, Any]):
    """
    Receives the BUILD REPORT from N8N.
    Enriches with latest regime from DB, sends email via report_generator.
    """
    try:
        # ── STEP 0: Enrich with latest regime from DB ──────────────
        try:
            conn = create_connection()
            cur  = conn.cursor()
            cur.execute("""
                SELECT regime_label, confidence_score, volatility_level, trade_date
                FROM market_regimes ORDER BY trade_date DESC LIMIT 1
            """)
            regime_row = cur.fetchone()
            cur.close()
            conn.close()
            if regime_row:
                if "metrics" not in report_data:
                    report_data["metrics"] = {}
                report_data["metrics"]["regime_label"]     = str(regime_row[0]).strip()
                report_data["metrics"]["confidence_score"] = float(regime_row[1])
                report_data["metrics"]["volatility_level"] = str(regime_row[2]).strip()
                report_data["metrics"]["trade_date"]       = str(regime_row[3])
                logger.info(f"✅ Injected regime from DB: {regime_row[0]} ({regime_row[1]*100:.1f}%)")
            else:
                logger.warning("⚠️ No regime found in DB, using N8N data")
        except Exception as e:
            logger.warning(f"⚠️ Regime enrich failed: {e}")

        # ── STEP 1: Process ────────────────────────────────────────
        processed_data = process_build_report(report_data)

        # ── STEP 2: Generate + Send email ──────────────────────────
        result = generate_and_send_reports(processed_data)

        return JSONResponse(
            status_code=200 if result["status"] == "success" else 206,
            content=result,
        )
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": f"Report generation failed: {str(e)}",
            "error": str(e),
        })

# =========================================================
# TRIGGER N8N WORKFLOW  (for frontend email submission)
# =========================================================

@app.post("/trigger-n8n")
def trigger_n8n_workflow(payload: Dict[str, Any]):
    """
    Frontend Email Report Flow:
    1. Receive email + dashboard_data from frontend
    2. Fire N8N webhook (triggers entire workflow: fetch data → calculate indicators → build report)
    3. WAIT for N8N to complete (returns complete report data)
    4. Pass report_data to report_generator to send email
    5. Return success to frontend
    """
    if not N8N_WEBHOOK_URL:
        logger.error("❌ N8N_WEBHOOK_URL not configured in .env")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": "N8N workflow not configured. Set N8N_WEBHOOK_URL in backend/.env"
        })
    
    try:
        # ── STEP 1: Validate email ──────────────────────────────────
        email = payload.get("email", "").strip()
        if not email or "@" not in email:
            logger.warning(f"⚠️ Invalid email: {email}")
            return JSONResponse(status_code=400, content={
                "status": "error",
                "message": "Invalid email address"
            })
        
        # ── STEP 2: Prepare N8N webhook payload ─────────────────────
        n8n_payload = {
            "email": email,
            "dashboard_data": payload.get("dashboard_data", {}),
            "timestamp": payload.get("timestamp", ""),
            "trigger_source": "frontend"
        }
        
        # ── STEP 3: Fire N8N webhook and WAIT for response ──────────
        logger.info(f"🚀 [STEP 3] Firing N8N webhook for email: {email}")
        logger.info(f"   N8N will execute: Fetch Data → Indicators → Build Report")
        
        response = requests.post(N8N_WEBHOOK_URL, json=n8n_payload, timeout=180)  # Wait up to 3 minutes
        
        if response.status_code not in [200, 201, 202]:
            logger.warning(f"⚠️ [STEP 3] N8N returned status {response.status_code}: {response.text[:200]}")
            return JSONResponse(status_code=500, content={
                "status": "error",
                "message": f"N8N workflow failed: {response.status_code}",
                "n8n_response": response.text[:200]
            })
        
        logger.info(f"✅ [STEP 3] N8N workflow completed successfully")
        
        # ── STEP 4: Extract report data from N8N response ──────────
        try:
            n8n_response = response.json()
            report_data = n8n_response.get("report_data", n8n_response)  # Use full response if no report_data key
            logger.info(f"✅ [STEP 4] Received report data from N8N")
        except:
            logger.warning(f"⚠️ Could not parse N8N response as JSON, using raw response")
            report_data = {"raw": response.text}
        
        # ── STEP 5: Pass report_data + email to report_generator ───
        logger.info(f"🔄 [STEP 5] Passing data to report_generator.generate_and_send_reports()")
        report_data["email"] = email
        result = generate_and_send_reports(report_data)
        
        # ── STEP 6: Return success to frontend ──────────────────────
        logger.info(f"✅ [STEP 6] Email sent to {email}")
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": f"Report generated and email sent to {email}",
            "report_status": result.get("status", "completed")
        })
    
    except requests.exceptions.Timeout:
        logger.error("⏱️ N8N workflow request timed out after 3 minutes")
        return JSONResponse(status_code=504, content={
            "status": "error",
            "message": "N8N workflow timeout (>3 min). Please try again or check N8N logs."
        })
    except Exception as e:
        logger.error(f"❌ N8N trigger failed: {str(e)}")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": f"N8N workflow error: {str(e)}"
        })

# =========================================================
# WEB REPORT  (NEW — for React dashboard)
# =========================================================

@app.post("/web-report")
def web_report(report_data: Dict[str, Any]):
    """
    Receives the same N8N payload as /build-report but:
    - Enriches with latest DB regime
    - Calls web_report_generator (detailed structured JSON for React)
    - Returns JSON — does NOT send email
    """
    try:
        # ── Enrich with DB regime ───────────────────────────────────
        try:
            conn = create_connection()
            cur  = conn.cursor()
            cur.execute("""
                SELECT regime_label, confidence_score, volatility_level, trade_date
                FROM market_regimes ORDER BY trade_date DESC LIMIT 1
            """)
            regime_row = cur.fetchone()
            cur.close()
            conn.close()
            if regime_row:
                if "metrics" not in report_data:
                    report_data["metrics"] = {}
                report_data["metrics"]["regime_label"]     = str(regime_row[0]).strip()
                report_data["metrics"]["confidence_score"] = float(regime_row[1])
                report_data["metrics"]["volatility_level"] = str(regime_row[2]).strip()
                report_data["metrics"]["trade_date"]       = str(regime_row[3])
        except Exception as e:
            logger.warning(f"⚠️ Web report regime enrich failed: {e}")

        # ── Process + Generate web report ──────────────────────────
        processed_data = process_build_report(report_data)
        result         = generate_web_report(processed_data)

        return JSONResponse(status_code=200, content=result)

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# =========================================================
# DASHBOARD DATA  (live DB query for the React charts)
# =========================================================

@app.get("/dashboard-data")
def dashboard_data():
    """
    Returns all chart data needed by the React dashboard in one call.
    Queries: market_regimes, technical_indicators, market_assets, market_price_history.
    """
    try:
        conn = create_connection()
        cur  = conn.cursor()

        # 1. Latest regime
        cur.execute("""
            SELECT regime_label, confidence_score, volatility_level, trade_date
            FROM market_regimes ORDER BY trade_date DESC LIMIT 1
        """)
        regime_row = cur.fetchone()
        regime = {
            "label":      regime_row[0] if regime_row else "UNKNOWN",
            "confidence": float(regime_row[1]) * 100 if regime_row else 0,
            "volatility": regime_row[2] if regime_row else "N/A",
            "date":       str(regime_row[3]) if regime_row else "N/A",
        }

        # 2. Regime distribution (last 90 days)
        cur.execute("""
            SELECT regime_label, COUNT(*) as cnt
            FROM market_regimes
            WHERE trade_date >= CURRENT_DATE - 90
            GROUP BY regime_label ORDER BY cnt DESC
        """)
        regime_dist = [{"label": r[0], "count": r[1]} for r in cur.fetchall()]

        # 3. Confidence trend (last 30 days)
        cur.execute("""
            SELECT trade_date, AVG(confidence_score)*100 AS avg_conf
            FROM market_regimes
            WHERE trade_date >= CURRENT_DATE - 30
            GROUP BY trade_date ORDER BY trade_date ASC
        """)
        conf_trend = [{"date": str(r[0]), "confidence": round(float(r[1]), 2)} for r in cur.fetchall()]

        # 4. Top 10 movers by latest volatility
        cur.execute("""
            SELECT ma.ticker_symbol, ti.rsi, ti.macd, ti.atr,
                   ti.volatility, ti.daily_return, ti.sma_20, ti.ema_20, ti.trade_date
            FROM technical_indicators ti
            JOIN market_assets ma ON ti.asset_id = ma.asset_id
            WHERE ti.trade_date = (SELECT MAX(trade_date) FROM technical_indicators)
              AND ti.rsi IS NOT NULL
            ORDER BY ti.volatility DESC NULLS LAST
            LIMIT 10
        """)
        cols   = ["ticker","rsi","macd","atr","volatility","daily_return","sma_20","ema_20","trade_date"]
        movers = []
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            d["trade_date"]   = str(d["trade_date"])
            d["daily_return"] = float(d["daily_return"]) if d["daily_return"] else 0
            d["rsi"]          = float(d["rsi"])          if d["rsi"]          else 0
            d["macd"]         = float(d["macd"])         if d["macd"]         else 0
            d["atr"]          = float(d["atr"])          if d["atr"]          else 0
            d["volatility"]   = float(d["volatility"])   if d["volatility"]   else 0
            d["sma_20"]       = float(d["sma_20"])       if d["sma_20"]       else 0
            d["ema_20"]       = float(d["ema_20"])       if d["ema_20"]       else 0
            movers.append(d)

        # 5. RSI distribution buckets
        cur.execute("""
            SELECT
              COUNT(CASE WHEN rsi < 30  THEN 1 END) AS oversold,
              COUNT(CASE WHEN rsi BETWEEN 30 AND 50 THEN 1 END) AS bearish_neutral,
              COUNT(CASE WHEN rsi BETWEEN 50 AND 70 THEN 1 END) AS bullish_neutral,
              COUNT(CASE WHEN rsi > 70  THEN 1 END) AS overbought
            FROM technical_indicators
            WHERE trade_date = (SELECT MAX(trade_date) FROM technical_indicators)
        """)
        rsi_row = cur.fetchone()
        rsi_dist = [
            {"bucket": "Oversold (<30)",    "count": rsi_row[0] or 0},
            {"bucket": "Bearish (30–50)",   "count": rsi_row[1] or 0},
            {"bucket": "Bullish (50–70)",   "count": rsi_row[2] or 0},
            {"bucket": "Overbought (>70)",  "count": rsi_row[3] or 0},
        ]

        # 6. Asset count by type
        cur.execute("""
            SELECT asset_type, COUNT(*) FROM market_assets GROUP BY asset_type ORDER BY 2 DESC
        """)
        asset_types = [{"type": r[0], "count": r[1]} for r in cur.fetchall()]

        # 7. Volatility history for top 5 most volatile tickers (last 30 days)
        cur.execute("""
            SELECT ma.ticker_symbol, ti.trade_date, ti.volatility
            FROM technical_indicators ti
            JOIN market_assets ma ON ti.asset_id = ma.asset_id
            WHERE ti.trade_date >= CURRENT_DATE - 30
              AND ma.ticker_symbol IN (
                  SELECT ma2.ticker_symbol FROM technical_indicators ti2
                  JOIN market_assets ma2 ON ti2.asset_id = ma2.asset_id
                  WHERE ti2.trade_date = (SELECT MAX(trade_date) FROM technical_indicators)
                  ORDER BY ti2.volatility DESC NULLS LAST LIMIT 5
              )
            ORDER BY ti.trade_date ASC
        """)
        vol_rows = cur.fetchall()
        # Pivot into {date: {ticker: vol}}
        vol_by_date = {}
        for row in vol_rows:
            d = str(row[1])
            if d not in vol_by_date:
                vol_by_date[d] = {"date": d}
            vol_by_date[d][row[0]] = round(float(row[2]), 5) if row[2] else 0
        vol_history = sorted(vol_by_date.values(), key=lambda x: x["date"])

        # 8. DB summary counts
        cur.execute("SELECT COUNT(*) FROM market_assets")
        asset_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM market_price_history")
        price_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM technical_indicators")
        ind_count   = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM market_regimes")
        reg_count   = cur.fetchone()[0]

        conn.close()

        return {
            "status":          "success",
            "regime":          regime,
            "regime_dist":     regime_dist,
            "conf_trend":      conf_trend,
            "top_movers":      movers,
            "rsi_distribution": rsi_dist,
            "asset_types":     asset_types,
            "vol_history":     vol_history,
            "db_summary": {
                "assets":     asset_count,
                "prices":     price_count,
                "indicators": ind_count,
                "regimes":    reg_count,
            },
        }

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})