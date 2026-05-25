"""
WEB REPORT GENERATOR
Generates a structured, detailed, data-analyst grade report for the website.
Email prompt is untouched in report_generator.py.
This module is called by api.py → /web-report endpoint.
"""

import logging
import json
import re
import os
from datetime import datetime
from typing import Dict, Any, List

from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
genai.configure(api_key=GEMINI_API_KEY)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL_PRIORITY = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.0-pro"]


# =========================================================
# SAFE PARSERS
# =========================================================

def safe_float(v, default=0.0):
    try:    return float(v)
    except: return default

def safe_int(v, default=0):
    try:    return int(float(v))
    except: return default

def ensure_list(data):
    if isinstance(data, list): return data
    if isinstance(data, str):
        try:
            p = json.loads(data)
            return p if isinstance(p, list) else []
        except: pass
    return []

def ensure_dict(data):
    if isinstance(data, dict): return data
    if isinstance(data, str):
        try:
            p = json.loads(data)
            return p if isinstance(p, dict) else {}
        except: pass
    return {}


# =========================================================
# NORMALISE PAYLOAD (same logic as report_generator)
# =========================================================

def normalise_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Accept both Format A (raw N8N) and Format B (data_processor output)."""

    # Format B: data_processor output
    if "assets" in raw and "metrics" in raw:
        metrics    = ensure_dict(raw.get("metrics", {}))
        assets     = ensure_list(raw.get("assets",  []))
        indicators = ensure_dict(raw.get("indicators", {}))

        raw_conf   = safe_float(metrics.get("confidence_score", 0))
        if "%" in str(metrics.get("confidence_score", "")):
            raw_conf = raw_conf / 100.0
        confidence = raw_conf if raw_conf <= 1.0 else raw_conf / 100.0

        trade_date = (
            metrics.get("trade_date") or
            indicators.get("trade_date") or
            raw.get("timestamp", "N/A")
        )

        regime = {
            "regime_label":     str(metrics.get("regime_label",    indicators.get("REGIME",    "UNKNOWN"))).strip(),
            "confidence_score": confidence,
            "volatility_level": str(metrics.get("volatility_level", indicators.get("VOLATILITY","N/A"))).strip(),
            "trade_date":       trade_date,
        }

        pipeline_status = {
            "data_fetch":        "Successful" if assets else "Failed",
            "indicators":        "Successful" if any(safe_float(a.get("rsi", 0)) for a in assets) else "Unknown",
            "regime_validation": "Successful" if regime["regime_label"] not in ("UNKNOWN", "") else "Failed",
            "report_generation": "Successful",
        }

        return {
            "regime":          regime,
            "movers":          assets,
            "alerts":          ensure_list(raw.get("alerts", [])),
            "total_movers":    safe_int(raw.get("total_assets", len(assets))),
            "pipeline_status": pipeline_status,
            "generated_at":    raw.get("timestamp", datetime.now().isoformat()),
        }

    # Format A: raw N8N
    if "regimes" in raw and "movers" in raw:
        regimes = ensure_list(raw.get("regimes", []))
        movers  = ensure_list(raw.get("movers",  []))
        regime  = {}
        if regimes:
            r          = ensure_dict(regimes[0])
            raw_conf   = safe_float(r.get("confidence_score", 0))
            confidence = raw_conf if raw_conf <= 1.0 else raw_conf / 100.0
            regime = {
                "regime_label":     str(r.get("regime_label",    "UNKNOWN")),
                "confidence_score": confidence,
                "volatility_level": str(r.get("volatility_level","N/A")),
                "trade_date":       r.get("trade_date", "N/A"),
            }
        return {
            "regime":          regime,
            "movers":          movers,
            "alerts":          ensure_list(raw.get("alerts", [])),
            "total_movers":    safe_int(raw.get("total_movers", len(movers))),
            "pipeline_status": {},
            "generated_at":    raw.get("generated_at", datetime.now().isoformat()),
        }

    return {
        "regime":          {"regime_label": "UNKNOWN", "confidence_score": 0, "volatility_level": "N/A", "trade_date": "N/A"},
        "movers":          [],
        "alerts":          [],
        "total_movers":    0,
        "pipeline_status": {},
        "generated_at":    datetime.now().isoformat(),
    }


# =========================================================
# GEMINI — WEBSITE REPORT PROMPT (detailed, structured JSON)
# =========================================================

def generate_web_analysis(report_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calls Gemini with a detailed structured prompt designed for website display.
    Returns a JSON dict with 7 sections for rendering in the React dashboard.
    Email prompt in report_generator.py is NOT touched.
    """
    regime  = report_data.get("regime", {})
    movers  = report_data.get("movers", [])

    label   = regime.get("regime_label", "N/A")
    conf    = safe_float(regime.get("confidence_score", 0)) * 100
    vol     = regime.get("volatility_level", "N/A")
    dt_raw  = regime.get("trade_date", "N/A")

    # Build a rich asset block for the prompt
    asset_rows = []
    for m in movers:
        sym   = m.get("ticker_symbol", "")
        rsi   = safe_float(m.get("rsi",          0))
        macd  = safe_float(m.get("macd",         0))
        ret   = safe_float(m.get("daily_return",  0)) * 100
        vol_a = safe_float(m.get("volatility",    0))
        atr   = safe_float(m.get("atr",          0))
        ema   = safe_float(m.get("ema_20",        0))
        sma   = safe_float(m.get("sma_20",        0))
        trend = "EMA>SMA(bullish)" if ema > sma else "SMA>EMA(bearish)"
        signal = "OVERBOUGHT" if rsi >= 70 else ("OVERSOLD" if rsi <= 30 else "NEUTRAL")
        asset_rows.append(
            f"  {sym:<14} RSI={rsi:5.1f}({signal:<10}) MACD={macd:+9.4f}  "
            f"Ret={ret:+6.2f}%  Vol={vol_a:.4f}  ATR={atr:6.2f}  {trend}"
        )

    assets_block = "\n".join(asset_rows)

    prompt = f"""You are a senior quantitative analyst and data scientist.
Generate a COMPREHENSIVE, STRUCTURED market intelligence report for website display.
Use ONLY the data provided. Be precise, data-driven, and professional.

=== MARKET DATA ===
Trade Date  : {dt_raw}
Regime      : {label}
Confidence  : {conf:.1f}%
Volatility  : {vol}
Assets Count: {len(movers)}

Asset Technical Data:
{assets_block}

=== TASK ===
Return a SINGLE valid JSON object with EXACTLY these 7 keys.
No text before or after the JSON. No markdown code fences.

{{
  "regime_analysis": {{
    "headline": "One sentence: regime + key implication (≤20 words)",
    "conviction": "LOW|MODERATE|HIGH",
    "conviction_reason": "Specific reason citing the {conf:.1f}% confidence score",
    "volatility_interpretation": "2-3 sentences: what HIGH/LOW/MEDIUM volatility means for this regime",
    "macro_context": "2-3 sentences: what this regime combination typically precedes historically",
    "trading_bias": "BULLISH_CAUTIOUS|BULLISH_AGGRESSIVE|BEARISH|NEUTRAL|RISK_OFF"
  }},

  "asset_scorecards": [
    {{
      "ticker": "symbol",
      "overall_signal": "STRONG_BUY|BUY|NEUTRAL|SELL|STRONG_SELL",
      "rsi_verdict": "one sentence on RSI reading with the actual number",
      "macd_verdict": "one sentence on MACD momentum with actual value",
      "trend_verdict": "one sentence on EMA vs SMA trend",
      "return_verdict": "one sentence contextualizing the daily return",
      "risk_score": 1-10,
      "key_level": "the one price/indicator level to watch (e.g. RSI 70.3 — exit zone)",
      "one_liner": "≤15 word actionable summary for this asset"
    }}
  ],

  "sector_breakdown": [
    {{
      "sector": "sector name (e.g. US TECH, INDIAN PHARMA, COMMODITIES, VOLATILITY)",
      "tickers": ["ticker1", "ticker2"],
      "sector_signal": "BULLISH|BEARISH|MIXED|NEUTRAL",
      "sector_insight": "2 sentences: collective reading + rotation opportunity if any"
    }}
  ],

  "risk_matrix": [
    {{
      "risk_type": "name of specific risk",
      "severity": "HIGH|MEDIUM|LOW",
      "trigger": "exact indicator/level that signals this risk",
      "affected_assets": ["ticker1"],
      "mitigation": "specific, actionable mitigation step"
    }}
  ],

  "opportunities": [
    {{
      "type": "LONG|SHORT|HEDGE|WAIT",
      "ticker": "symbol",
      "rationale": "2 sentences citing specific indicator values",
      "entry_condition": "exact technical condition to enter",
      "exit_condition": "exact technical condition to exit",
      "risk_reward": "estimated R:R ratio e.g. 1:2.5",
      "time_horizon": "INTRADAY|SWING(2-5D)|POSITIONAL(1-4W)"
    }}
  ],

  "portfolio_strategy": {{
    "positioning": "1 paragraph: overall portfolio bias, cash allocation idea, sector weights",
    "hedge_recommendation": "specific hedge instrument + sizing idea",
    "rebalancing_trigger": "exact condition (indicator + level) that should trigger rebalance",
    "top_3_watchlist": [
      {{"ticker": "sym", "reason": "≤15 words why this is the top watch"}}
    ]
  }},

  "summary_bullets": [
    "Bullet 1: regime conviction insight with number",
    "Bullet 2: strongest bullish asset with specific indicator",
    "Bullet 3: biggest risk flag with specific number",
    "Bullet 4: best opportunity setup with entry condition",
    "Bullet 5: key sector rotation or hedge idea"
  ]
}}

RULES:
- Every insight must cite at least one specific number from the data
- No generic statements like "monitor closely" without specifying what level
- asset_scorecards must include ALL {len(movers)} assets
- sector_breakdown should group by: US TECH, INDIAN IT/PHARMA, COMMODITIES/ETFs, VOLATILITY/BONDS
- risk_matrix: minimum 4 risks, maximum 6
- opportunities: minimum 3, maximum 5 (only high-conviction setups)
- Return ONLY the JSON object. No preamble, no explanation, no markdown.
"""

    for attempt, model_name in enumerate(MODEL_PRIORITY, 1):
        try:
            logger.info(f"🤖 Web report [{attempt}] trying {model_name}...")
            model    = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            text     = response.text.strip()

            # Strip markdown fences if model wraps in them
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()

            parsed = json.loads(text)
            logger.info(f"✅ Web report Gemini OK: {model_name}")
            return {
                "success":      True,
                "analysis":     parsed,
                "model_used":   model_name,
                "generated_at": datetime.now().isoformat(),
            }

        except json.JSONDecodeError as e:
            logger.warning(f"⚠️  {model_name} returned invalid JSON: {str(e)[:80]}")
        except Exception as e:
            logger.warning(f"⚠️  {model_name} failed: {str(e)[:80]}")

    logger.error("❌ All Gemini models failed for web report — returning structured fallback")
    return {
        "success":    False,
        "analysis":   _fallback_analysis(report_data),
        "model_used": "fallback",
        "generated_at": datetime.now().isoformat(),
    }


# =========================================================
# FALLBACK (if ALL Gemini calls fail)
# =========================================================

def _fallback_analysis(report_data: Dict[str, Any]) -> Dict[str, Any]:
    """Returns a minimal structured dict computed purely from the data."""
    regime  = report_data.get("regime", {})
    movers  = report_data.get("movers", [])
    label   = regime.get("regime_label", "UNKNOWN")
    conf    = safe_float(regime.get("confidence_score", 0)) * 100
    vol     = regime.get("volatility_level", "N/A")

    scorecards = []
    for m in movers:
        rsi  = safe_float(m.get("rsi",         50))
        macd = safe_float(m.get("macd",         0))
        ret  = safe_float(m.get("daily_return",  0)) * 100
        ema  = safe_float(m.get("ema_20",        0))
        sma  = safe_float(m.get("sma_20",        0))
        sig  = "STRONG_BUY" if (rsi < 35 and macd > 0) else \
               "SELL"       if (rsi > 70 and macd < 0) else \
               "BUY"        if macd > 0 else "NEUTRAL"
        scorecards.append({
            "ticker":        m.get("ticker_symbol", "—"),
            "overall_signal": sig,
            "rsi_verdict":   f"RSI at {rsi:.1f}",
            "macd_verdict":  f"MACD at {macd:+.4f}",
            "trend_verdict": "EMA>SMA (bullish)" if ema > sma else "SMA>EMA (bearish)",
            "return_verdict": f"Daily return {ret:+.2f}%",
            "risk_score":    8 if rsi > 70 or rsi < 30 else 5,
            "key_level":     f"RSI {rsi:.1f}",
            "one_liner":     f"Signal: {sig}",
        })

    return {
        "regime_analysis": {
            "headline":               f"{label} regime, {conf:.0f}% confidence",
            "conviction":             "LOW" if conf < 50 else ("MODERATE" if conf < 70 else "HIGH"),
            "conviction_reason":      f"Confidence score of {conf:.1f}% indicates uncertain directional bias.",
            "volatility_interpretation": f"Volatility is {vol}.",
            "macro_context":          "Insufficient AI analysis — Gemini unavailable.",
            "trading_bias":           "NEUTRAL",
        },
        "asset_scorecards":  scorecards,
        "sector_breakdown":  [],
        "risk_matrix":       [],
        "opportunities":     [],
        "portfolio_strategy": {
            "positioning":          "AI analysis unavailable.",
            "hedge_recommendation": "N/A",
            "rebalancing_trigger":  "N/A",
            "top_3_watchlist":      [],
        },
        "summary_bullets": [f"{label} regime with {conf:.0f}% confidence and {vol} volatility."],
    }


# =========================================================
# MAIN ENTRY — called from api.py
# =========================================================

def generate_web_report(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Full pipeline:
      1. Normalise payload
      2. Call Gemini with website prompt
      3. Return structured JSON for React frontend
    """
    logger.info("🌐 Web report generation started")

    report_data  = normalise_payload(raw_data)
    ai_result    = generate_web_analysis(report_data)

    return {
        "status":       "success" if ai_result["success"] else "fallback",
        "generated_at": ai_result["generated_at"],
        "model_used":   ai_result["model_used"],
        "regime":       report_data["regime"],
        "movers":       report_data["movers"],
        "total_movers": report_data["total_movers"],
        "pipeline":     report_data["pipeline_status"],
        "analysis":     ai_result["analysis"],   # The 7-section structured dict
    }