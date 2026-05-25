import smtplib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import logging
from typing import Dict, List, Any
import os
from dotenv import load_dotenv
import google.generativeai as genai
import json

# =========================================================
# CONFIGURATION
# =========================================================

load_dotenv()

EMAIL_CONFIG = {
    "sender_email":    os.getenv("SENDER_EMAIL",    "your-email@gmail.com"),
    "sender_password": os.getenv("SENDER_PASSWORD", "your-app-password"),
    "smtp_server":     "smtp.gmail.com",
    "smtp_port":       587,
    "recipients":      ["jaykeluskar106@gmail.com"]
}

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
genai.configure(api_key=GEMINI_API_KEY)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# =========================================================
# SAFE PARSERS
# =========================================================

def safe_float(v, default=0.0):
    try:    return float(v)
    except: return default

def safe_int(v, default=0):
    try:    return int(float(v))
    except: return default

def ensure_dict(data, key="data"):
    if isinstance(data, dict): return data
    if isinstance(data, str):
        try:
            p = json.loads(data)
            return p if isinstance(p, dict) else {}
        except: pass
    return {}

def ensure_list(data, key="data"):
    if isinstance(data, list): return data
    if isinstance(data, str):
        try:
            p = json.loads(data)
            return p if isinstance(p, list) else []
        except: pass
    return []

# =========================================================
# DATA FLOW
# =========================================================
#
#  N8N  →  api.py  →  data_processor.process_build_report()
#                              ↓
#              report_generator.generate_and_send_reports()
#
#  data_processor ALWAYS outputs Format B keys:
#    status, timestamp, total_assets,
#    metrics   : { regime_label, confidence_score, volatility_level, trade_date, ... }
#    assets    : [ { ticker_symbol, rsi, macd, daily_return, volatility, atr, sma_20, ema_20 }, ... ]
#    indicators: { REGIME, CONFIDENCE, VOLATILITY, TOP_MOVERS }
#    insights  : [ "Market Regime: BULL", "Confidence: 46.0%", ... ]  ← metric echoes, NOT real insights
#    alerts    : []
#
#  normalise_processed() converts this into the internal structure
#  used by all _build_*() functions.
#
# =========================================================

def normalise_processed(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts data_processor output (Format B) → internal report structure.

    Handles BOTH entry paths:
      Path 1: api.py calls process_build_report() → output arrives here
      Path 2: raw N8N JSON arrives directly (has 'regimes' + 'movers' keys)
    """

    # ── PATH 1: data_processor output (has 'assets' + 'metrics') ──────────
    if "assets" in raw and "metrics" in raw:

        metrics    = ensure_dict(raw.get("metrics", {}))
        assets     = ensure_list(raw.get("assets",  []))
        indicators = ensure_dict(raw.get("indicators", {}))

        # ── Regime: pull from metrics (data_processor puts it there) ──────
        raw_conf = safe_float(metrics.get("confidence_score", 0))
        # Normalise: DB stores 0.46, N8N sometimes sends "46.0%"
        if isinstance(metrics.get("confidence_score", ""), str) and "%" in str(metrics.get("confidence_score", "")):
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

        # ── Pipeline: infer from data presence ────────────────────────────
        pipeline_status = {
            "data_fetch":        "Successful" if assets else "Failed",
            "indicators":        "Successful" if any(safe_float(a.get("rsi", 0)) for a in assets) else "Unknown",
            "regime_validation": "Successful" if regime["regime_label"] not in ("UNKNOWN", "") else "Failed",
            "report_generation": "Successful",
        }

        # ── Insights: skip the useless metric-echo strings N8N adds ──────
        #    Real insights are asset-derived signals we compute below.
        raw_insights = ensure_list(raw.get("insights", []))
        SKIP_PATTERNS = re.compile(
            r"^(market regime|confidence|volatility|total movers?)\s*[:\-]",
            re.IGNORECASE
        )
        real_insights = [
            str(i).strip() for i in raw_insights
            if str(i).strip() and not SKIP_PATTERNS.match(str(i).strip())
        ]

        return {
            "regime":          regime,
            "movers":          assets,
            "insights":        real_insights,   # may be [] — _derive_insights fills the gap
            "alerts":          ensure_list(raw.get("alerts", [])),
            "total_movers":    safe_int(raw.get("total_assets", len(assets))),
            "pipeline_status": pipeline_status,
            "generated_at":    raw.get("timestamp", datetime.now().isoformat()),
            "indicators":      indicators,      # kept for reference
        }

    # ── PATH 2: raw N8N JSON (has 'regimes' + 'movers') ──────────────────
    if "regimes" in raw and "movers" in raw:

        regimes = ensure_list(raw.get("regimes", []))
        movers  = ensure_list(raw.get("movers",  []))

        regime = {}
        if regimes:
            r = ensure_dict(regimes[0])
            raw_conf = safe_float(r.get("confidence_score", 0))
            confidence = raw_conf if raw_conf <= 1.0 else raw_conf / 100.0
            regime = {
                "regime_label":     str(r.get("regime_label",    "UNKNOWN")),
                "confidence_score": confidence,
                "volatility_level": str(r.get("volatility_level","N/A")),
                "trade_date":       r.get("trade_date", "N/A"),
            }

        report_text = str(raw.get("report", ""))
        def _pipe_status(keyword):
            m = re.search(rf"{keyword}\s*:\s*(\w+)", report_text, re.IGNORECASE)
            return m.group(1) if m else "Unknown"

        pipeline_status = {
            "data_fetch":        _pipe_status("Data Fetching"),
            "indicators":        _pipe_status("Indicator Engine"),
            "regime_validation": _pipe_status("Regime Validation"),
            "report_generation": _pipe_status("Report Generation"),
        }

        return {
            "regime":          regime,
            "movers":          movers,
            "insights":        [],
            "alerts":          ensure_list(raw.get("alerts", [])),
            "total_movers":    safe_int(raw.get("total_movers", len(movers))),
            "pipeline_status": pipeline_status,
            "generated_at":    raw.get("generated_at", datetime.now().isoformat()),
            "indicators":      {},
        }

    # ── FALLBACK ──────────────────────────────────────────────────────────
    logger.warning(f"⚠️ Unknown data format. Keys received: {list(raw.keys())}")
    return {
        "regime":          {"regime_label": "UNKNOWN", "confidence_score": 0, "volatility_level": "N/A", "trade_date": "N/A"},
        "movers":          [],
        "insights":        [],
        "alerts":          [],
        "total_movers":    0,
        "pipeline_status": {"data_fetch": "Unknown", "indicators": "Unknown", "regime_validation": "Unknown", "report_generation": "Unknown"},
        "generated_at":    datetime.now().isoformat(),
        "indicators":      {},
    }


# =========================================================
# DERIVED INSIGHTS  (computed from live asset data)
# =========================================================

def _derive_insights(regime: dict, movers: list) -> list:
    """
    Compute 4-6 factual, non-repetitive insights from the actual data.
    These replace the useless "Market Regime: BULL" echo strings N8N inserts.
    """
    insights = []
    if not movers:
        return insights

    conf      = safe_float(regime.get("confidence_score", 0)) * 100
    vol_level = regime.get("volatility_level", "N/A")
    label     = regime.get("regime_label", "N/A")

    # 1. Regime conviction
    conviction = "weak" if conf < 50 else ("moderate" if conf < 70 else "strong")
    insights.append(
        f"{label} regime with {conviction} conviction ({conf:.0f}%) — "
        f"{'caution advised on leveraged longs' if conf < 50 else 'directional bias confirmed'}."
    )

    # 2. Overbought / oversold
    ob  = [m["ticker_symbol"] for m in movers if safe_float(m.get("rsi", 50)) >= 70]
    os_ = [m["ticker_symbol"] for m in movers if safe_float(m.get("rsi", 50)) <= 30]
    if ob:
        insights.append(f"Overbought (RSI ≥ 70): {', '.join(ob)} — potential near-term pullback risk.")
    if os_:
        insights.append(f"Oversold (RSI ≤ 30): {', '.join(os_)} — watch for mean-reversion bounce.")

    # 3. Best / worst daily return
    sorted_ret = sorted(movers, key=lambda m: safe_float(m.get("daily_return", 0)), reverse=True)
    best  = sorted_ret[0]
    worst = sorted_ret[-1]
    b_ret = safe_float(best.get("daily_return",  0)) * 100
    w_ret = safe_float(worst.get("daily_return", 0)) * 100
    insights.append(
        f"Top performer: {best['ticker_symbol']} (+{b_ret:.2f}%)  ·  "
        f"Worst performer: {worst['ticker_symbol']} ({w_ret:.2f}%)."
    )

    # 4. MACD divergence alert (positive MACD but negative return = profit-taking)
    divergent = [
        m["ticker_symbol"] for m in movers
        if safe_float(m.get("macd", 0)) > 5
        and safe_float(m.get("daily_return", 0)) < -0.01
    ]
    if divergent:
        insights.append(
            f"MACD/Return divergence on {', '.join(divergent)} — "
            f"strong trend intact but short-term selling pressure present."
        )

    # 5. Volatility context
    high_atr = sorted(movers, key=lambda m: safe_float(m.get("atr", 0)), reverse=True)[:3]
    atr_names = [m["ticker_symbol"] for m in high_atr]
    insights.append(
        f"Highest intraday range (ATR): {', '.join(atr_names)} — "
        f"widen stop-losses on these positions in a {vol_level} vol environment."
    )

    return insights


# =========================================================
# GEMINI AI — FOCUSED PROMPT
# =========================================================

def enhance_report_with_gemini(report_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Crisp 5-section analysis. ≤350 words. Properly bolded headings.
    Model priority: gemini-2.5-flash → gemini-1.5-flash → gemini-1.0-pro
    """
    MODEL_PRIORITY = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.0-pro"]

    regime    = report_data.get("regime", {})
    movers    = report_data.get("movers", [])

    label     = regime.get("regime_label", "N/A")
    conf      = safe_float(regime.get("confidence_score", 0)) * 100
    vol       = regime.get("volatility_level", "N/A")
    trade_dt  = regime.get("trade_date", "N/A")

    asset_lines = []
    for m in movers:
        sym   = m.get("ticker_symbol", "")
        rsi   = safe_float(m.get("rsi",          0))
        macd  = safe_float(m.get("macd",         0))
        ret   = safe_float(m.get("daily_return",  0)) * 100
        atr   = safe_float(m.get("atr",          0))
        ema   = safe_float(m.get("ema_20",        0))
        sma   = safe_float(m.get("sma_20",        0))
        trend = "EMA>SMA" if ema > sma else "SMA>EMA"
        asset_lines.append(
            f"  {sym:<14} RSI={rsi:5.1f}  MACD={macd:+9.4f}  Ret={ret:+6.2f}%  ATR={atr:6.2f}  {trend}"
        )

    prompt = f"""You are a senior quantitative analyst writing a daily market brief.
Use ONLY the numbers provided. Be concise, professional, non-repetitive.

--- MARKET DATA ---
Trade Date : {trade_dt}
Regime     : {label}  |  Confidence: {conf:.1f}%  |  Volatility: {vol}
Assets Analyzed: {len(movers)}

Asset Snapshot:
{chr(10).join(asset_lines)}

--- INSTRUCTIONS ---
Write EXACTLY five sections. Format each as:
**N. Section Title**
• bullet (max 20 words, cite specific tickers/numbers)
• bullet
• bullet (3-5 bullets per section)

Sections:
**1. Regime & Macro Outlook**
**2. Standout Assets** (2-3 bullish, 1-2 bearish — cite RSI/MACD/return)
**3. Risk Flags** (use specific numbers, no generic warnings)
**4. Actionable Watch-List** (ticker + exact trigger condition + price level or indicator value)
**5. Strategy Snapshot** (3 sentences max: positioning bias, hedge, time horizon)

Rules:
- Zero repetition across sections
- No markdown ### headers
- Total output under 350 words
"""

    for attempt, model_name in enumerate(MODEL_PRIORITY, 1):
        try:
            logger.info(f"🤖 [{attempt}/{len(MODEL_PRIORITY)}] Trying {model_name}...")
            model    = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            text     = response.text.strip()
            logger.info(f"✅ Gemini OK: {model_name} ({len(text)} chars)")
            return {"success": True, "analysis": text, "model_used": model_name}
        except Exception as e:
            logger.warning(f"⚠️  {model_name} failed: {str(e)[:100]}")

    logger.error("❌ All Gemini models failed")
    return {"success": False, "analysis": None, "model_used": None}


# =========================================================
# COLOUR / LABEL HELPERS
# =========================================================

def _rsi_label(rsi: float) -> str:
    if rsi >= 70: return "Overbought"
    if rsi <= 30: return "Oversold"
    if rsi >= 60: return "Bullish"
    if rsi <= 40: return "Bearish"
    return "Neutral"

def _rsi_color(rsi: float) -> str:
    if rsi >= 70: return "#e74c3c"
    if rsi <= 30: return "#16a085"
    if rsi >= 60: return "#27ae60"
    if rsi <= 40: return "#e67e22"
    return "#7f8c8d"

def _ret_color(ret: float)  -> str: return "#27ae60" if ret >= 0 else "#e74c3c"
def _macd_color(macd: float)-> str: return "#27ae60" if macd >= 0 else "#e74c3c"

def _regime_color(label: str) -> str:
    return {"BULL": "#27ae60", "BEAR": "#e74c3c",
            "HIGH_VOLATILITY": "#e67e22", "SIDEWAYS": "#3498db"}.get(label.upper(), "#555")

def _vol_color(level: str) -> str:
    return {"LOW": "#27ae60", "MEDIUM": "#e67e22",
            "HIGH": "#e74c3c", "EXTREME": "#8e44ad"}.get(level.upper(), "#555")

def _conf_color(conf: float) -> str:
    if conf >= 70: return "#27ae60"
    if conf >= 50: return "#e67e22"
    return "#e74c3c"

def _fmt_date(raw: str) -> str:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%d %b %Y")
    except:
        return str(raw)


# =========================================================
# CSS
# =========================================================

CSS = """<style>
  body{margin:0;padding:0;background:#eef1f5;
       font-family:'Segoe UI',Arial,Helvetica,sans-serif;color:#1a1a2e}
  .wrap{max-width:720px;margin:24px auto;background:#fff;
        border-radius:14px;overflow:hidden;
        box-shadow:0 8px 32px rgba(0,0,0,.12)}

  /* ── Header ── */
  .hdr{background:linear-gradient(135deg,#0b2d4e 0%,#1a5276 100%);
       padding:28px 36px 24px;text-align:center}
  .hdr h1{margin:0;font-size:22px;color:#fff;letter-spacing:.5px;font-weight:700}
  .hdr .sub{margin:7px 0 0;font-size:13px;color:#aed6f1;letter-spacing:.2px}

  /* ── Section wrapper ── */
  .body{padding:28px 36px}
  .section{margin-bottom:32px}
  .sec-title{font-size:12px;font-weight:700;text-transform:uppercase;
             letter-spacing:1.2px;color:#566573;
             border-bottom:2px solid #e8eaed;
             padding-bottom:8px;margin-bottom:16px}

  /* ── Regime card ── */
  .regime-row{display:flex;align-items:center;gap:20px;flex-wrap:wrap}
  .reg-pill{padding:10px 26px;border-radius:30px;font-weight:700;
            font-size:15px;color:#fff;letter-spacing:.4px}
  .reg-stats{display:flex;gap:32px}
  .reg-stat .lbl{font-size:11px;color:#7f8c8d;text-transform:uppercase;letter-spacing:.6px;margin-bottom:2px}
  .reg-stat .val{font-size:24px;font-weight:700;line-height:1}

  /* ── Asset table ── */
  table{width:100%;border-collapse:collapse;font-size:13px;margin-top:4px}
  thead tr{background:#f5f9fc}
  th{padding:10px 8px;text-align:center;font-size:11px;text-transform:uppercase;
     letter-spacing:.6px;color:#5d6d7e;font-weight:700;
     border-bottom:2px solid #d4e6f1}
  td{padding:10px 8px;text-align:center;border-bottom:1px solid #f2f3f4;vertical-align:middle}
  td.sym{text-align:left;font-weight:700;color:#0b2d4e;padding-left:4px;font-size:13.5px}
  tr:last-child td{border-bottom:none}
  .badge{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;
         border-radius:12px;font-size:11px;font-weight:700;color:#fff;white-space:nowrap}
  .badge .sub-lbl{font-weight:500;font-size:9px;opacity:.85}
  .trend-tag{font-size:10px;font-weight:700;padding:3px 7px;
             border-radius:5px;color:#fff;letter-spacing:.2px}

  /* ── Insights (IMPROVED SPACING) ── */
  .ins-list{display:flex;flex-direction:column;gap:11px}
  .ins-row{display:flex;gap:13px;align-items:flex-start;
           padding:13px 14px;background:#fffef8;
           border-left:5px solid #f39c12;border-radius:6px;font-size:13px;
           line-height:1.5}
  .ins-num{flex:0 0 24px;height:24px;width:24px;border-radius:50%;
           background:#f39c12;color:#fff;display:flex;
           align-items:center;justify-content:center;
           font-weight:700;font-size:12px;margin-top:1px}
  .ins-txt{flex:1;color:#2c3e50}

  /* ── Alerts (ALWAYS SHOW, EVEN IF EMPTY) ── */
  .alt-list{display:flex;flex-direction:column;gap:11px}
  .alt-row{display:flex;gap:12px;align-items:flex-start;
           padding:13px 14px;background:#fdf5f5;
           border-left:5px solid #e74c3c;border-radius:6px;font-size:13px;
           line-height:1.5}
  .alt-ico{flex:0 0 20px;font-size:16px;margin-top:1px}
  .alt-txt{flex:1;color:#2c3e50}
  .alt-empty{text-align:center;color:#aaa;font-size:13px;padding:16px 14px;
             background:#f8f9fa;border:1px dashed #ddd;border-radius:6px}

  /* ── AI box ── */
  .ai-box{background:#f9fbff;border:1px solid #d4e6f1;border-radius:8px;
          padding:18px 20px;line-height:1.75;font-size:13.5px;color:#1a1a2e}
  .ai-box p{margin:0 0 10px}
  .ai-box ul{margin:4px 0 10px 18px;padding:0}
  .ai-box li{margin-bottom:5px;color:#2c3e50}
  .ai-box strong{color:#0b2d4e;font-weight:700}
  .ai-model{font-size:11px;color:#bdc3c7;margin-top:12px;
            text-align:right;font-style:italic}

  /* ── Pipeline ── */
  .pipe-row{display:flex;gap:10px;flex-wrap:wrap}
  .pipe-card{flex:1;min-width:140px;padding:12px 13px;
             border-radius:8px;background:#f8f9fa;
             border-left:5px solid #dfe6e9;font-size:12.5px}
  .pipe-card.ok{border-left-color:#27ae60;background:#f0fbf5}
  .pipe-card.fail{border-left-color:#e74c3c;background:#fdf5f5}
  .pipe-card.unk{border-left-color:#f39c12;background:#fffef8}
  .pipe-step{font-weight:700;color:#2c3e50;font-size:12px;margin-bottom:4px}
  .pipe-status{font-size:12px;color:#5a6c7d}

  /* ── Footer ── */
  .ftr{background:#f6f7f8;padding:16px 36px;text-align:center;
       font-size:11px;color:#a0b0b8;border-top:1px solid #e8eaed;letter-spacing:.3px}
</style>"""


# =========================================================
# HTML SECTION BUILDERS
# =========================================================

def _build_regime_block(regime: dict) -> str:
    label  = regime.get("regime_label", "UNKNOWN")
    conf   = safe_float(regime.get("confidence_score", 0)) * 100
    vol    = regime.get("volatility_level", "N/A")
    dt_raw = str(regime.get("trade_date", "N/A"))
    dt     = _fmt_date(dt_raw) if "T" in dt_raw else dt_raw

    return f"""
<div class="section">
  <div class="sec-title">📊 Market Regime — {dt}</div>
  <div class="regime-row">
    <span class="reg-pill" style="background:{_regime_color(label)}">{label}</span>
    <div class="reg-stats">
      <div class="reg-stat">
        <div class="lbl">Confidence</div>
        <div class="val" style="color:{_conf_color(conf)}">{conf:.0f}%</div>
      </div>
      <div class="reg-stat">
        <div class="lbl">Volatility</div>
        <div class="val" style="color:{_vol_color(vol)}">{vol}</div>
      </div>
    </div>
  </div>
</div>"""


def _build_asset_table(movers: list) -> str:
    if not movers:
        return "<p style='color:#aaa;font-size:13px;padding:10px 0'>No asset data available.</p>"

    rows = ""
    for m in movers:
        sym  = m.get("ticker_symbol", "—")
        rsi  = safe_float(m.get("rsi",          0))
        macd = safe_float(m.get("macd",         0))
        ret  = safe_float(m.get("daily_return",  0)) * 100
        vol  = safe_float(m.get("volatility",    0))
        atr  = safe_float(m.get("atr",          0))
        ema  = safe_float(m.get("ema_20",        0))
        sma  = safe_float(m.get("sma_20",        0))

        is_ema_above = ema > sma
        trend_lbl    = "EMA&gt;SMA" if is_ema_above else "SMA&gt;EMA"
        trend_col    = "#27ae60"    if is_ema_above else "#e74c3c"
        ret_sign     = "+" if ret >= 0 else ""

        rows += f"""
<tr>
  <td class="sym">{sym}</td>
  <td><span class="badge" style="background:{_rsi_color(rsi)}">{rsi:.1f}
    <span class="sub-lbl">{_rsi_label(rsi)}</span></span></td>
  <td style="color:{_macd_color(macd)};font-weight:700">{macd:+.4f}</td>
  <td style="color:{_ret_color(ret)};font-weight:700">{ret_sign}{ret:.2f}%</td>
  <td style="color:#555">{vol:.4f}</td>
  <td style="color:#555">{atr:.2f}</td>
  <td><span class="trend-tag" style="background:{trend_col}">{trend_lbl}</span></td>
</tr>"""

    return f"""
<div class="section">
  <div class="sec-title">📈 Asset Performance — {len(movers)} Assets by Volatility</div>
  <table>
    <thead><tr>
      <th style="text-align:left">Symbol</th>
      <th>RSI</th><th>MACD</th><th>Daily Return</th>
      <th>Volatility</th><th>ATR</th><th>Trend</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""


def _build_insights_block(insights: list, regime: dict, movers: list) -> str:
    """
    Shows derived insights (computed from live data).
    Falls back to _derive_insights() if the list coming in is empty or just metric echoes.
    """
    display = insights if insights else _derive_insights(regime, movers)
    if not display:
        display = [
            f"Market regime is {regime.get('regime_label', 'UNKNOWN')} with {safe_float(regime.get('confidence_score', 0))*100:.0f}% confidence.",
            f"Current volatility level is {regime.get('volatility_level', 'N/A')}."
        ]

    items = ""
    for i, txt in enumerate(display[:6], 1):  # Show up to 6 insights
        items += f"""
<div class="ins-row">
  <div class="ins-num">{i}</div>
  <div class="ins-txt">{txt}</div>
</div>"""

    return f"""
<div class="section">
  <div class="sec-title">💡 Key Insights</div>
  <div class="ins-list">{items}</div>
</div>"""


def _build_alerts_block(alerts: list) -> str:
    alerts = [str(a).strip() for a in ensure_list(alerts) if str(a).strip()]
    
    if not alerts:
        # Show "no alerts" message instead of nothing
        return f"""
<div class="section">
  <div class="sec-title">🚨 Critical Alerts</div>
  <div class="alt-empty">✓ No critical alerts at this time</div>
</div>"""

    items = "".join(
        f'<div class="alt-row"><span class="alt-ico">⚠️</span>'
        f'<span class="alt-txt">{a}</span></div>'
        for a in alerts[:6]  # Show up to 6 alerts
    )
    return f"""
<div class="section">
  <div class="sec-title">🚨 Critical Alerts {f"({len(alerts)})" if len(alerts) > 6 else ""}</div>
  <div class="alt-list">{items}</div>
</div>"""


def _build_ai_block(analysis: str, model_used: str) -> str:
    if not analysis:
        return ""

    # **bold** → <strong>
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", analysis)

    lines  = html.split("\n")
    out    = []
    in_ul  = False

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if in_ul: out.append("</ul>"); in_ul = False
            continue
        if line.startswith(("•", "-")) or (line.startswith("*") and not line.startswith("<strong>")):
            if not in_ul: out.append("<ul>"); in_ul = True
            out.append(f"<li>{re.sub(r'^[•\-\*]\s*', '', line)}</li>")
        else:
            if in_ul: out.append("</ul>"); in_ul = False
            style = "margin:14px 0 4px" if line.startswith("<strong>") else "margin:6px 0"
            out.append(f"<p style='{style}'>{line}</p>")

    if in_ul: out.append("</ul>")
    model_tag = f"Powered by {model_used}" if model_used else "Powered by Gemini AI"

    return f"""
<div class="section">
  <div class="sec-title">🤖 AI Market Intelligence</div>
  <div class="ai-box">
    {"".join(out)}
    <div class="ai-model">{model_tag}</div>
  </div>
</div>"""


def _build_pipeline_block(pipeline: dict) -> str:
    if not pipeline:
        return ""

    STEPS = {
        "data_fetch":        "Data Fetching",
        "indicators":        "Indicator Engine",
        "regime_validation": "Regime Validation",
        "report_generation": "Report Generation",
    }

    cards = ""
    for key, label in STEPS.items():
        raw    = str(pipeline.get(key, "Unknown")).strip()
        ok     = raw.lower() in ("successful", "success", "ok", "true", "1")
        unk    = raw.lower() in ("unknown", "")
        css    = "ok" if ok else ("unk" if unk else "fail")
        icon   = "✅" if ok else ("⚠️" if unk else "❌")
        cards += f"""
<div class="pipe-card {css}">
  <div class="pipe-step">{label}</div>
  <div class="pipe-status">{icon} {raw}</div>
</div>"""

    return f"""
<div class="section">
  <div class="sec-title">⚙️ Pipeline Status</div>
  <div class="pipe-row">{cards}</div>
</div>"""


# =========================================================
# MASTER EMAIL BUILDER
# =========================================================

def generate_detailed_report(report_data: Dict[str, Any]) -> str:
    now = datetime.now().strftime("%d %b %Y, %I:%M %p")

    regime   = report_data.get("regime",          {})
    movers   = report_data.get("movers",           [])
    pipeline = report_data.get("pipeline_status",  {})
    analysis = report_data.get("ai_analysis",      "")
    model    = report_data.get("model_used",        "")
    insights = report_data.get("insights",          [])
    alerts   = report_data.get("alerts",            [])
    indicators = report_data.get("indicators",      {})

    # Compute signal badges
    ob  = sum(1 for m in movers if safe_float(m.get("rsi", 50)) >= 70)
    os_ = sum(1 for m in movers if safe_float(m.get("rsi", 50)) <= 30)
    badges = ""
    if ob:  badges += f"&nbsp;🔴 {ob} overbought"
    if os_: badges += f"&nbsp;🟢 {os_} oversold"

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8">{CSS}</head>
<body>
<div class="wrap">

  <div class="hdr">
    <h1>📊 QuantCopilot AI — Daily Market Report</h1>
    <div class="sub">Generated: {now}{badges}</div>
  </div>

  <div class="body">
    {_build_regime_block(regime)}
    {_build_asset_table(movers)}
    {_build_insights_block(insights, regime, movers)}
    {_build_alerts_block(alerts)}
    {_build_ai_block(analysis, model)}
    {_build_pipeline_block(pipeline)}
  </div>

  <div class="ftr">
    Automated daily market intelligence · QuantCopilot AI &nbsp;|&nbsp; Do not reply to this email
  </div>

</div>
</body>
</html>"""


# backward-compat
def generate_summary_report(report_data: Dict[str, Any]) -> str:
    return generate_detailed_report(report_data)


# =========================================================
# EMAIL SENDER
# =========================================================

def send_email_report(html_body: str) -> bool:
    try:
        msg            = MIMEMultipart("alternative")
        msg["Subject"] = f"QuantCopilot AI — Daily Market Report {datetime.now().strftime('%Y-%m-%d')}"
        msg["From"]    = EMAIL_CONFIG["sender_email"]
        msg["To"]      = ", ".join(EMAIL_CONFIG["recipients"])
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"]) as srv:
            srv.starttls()
            srv.login(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["sender_password"])
            for r in EMAIL_CONFIG["recipients"]:
                srv.sendmail(EMAIL_CONFIG["sender_email"], r, msg.as_string())

        logger.info(f"✅ Email sent → {EMAIL_CONFIG['recipients']}")
        return True
    except Exception as e:
        logger.error(f"❌ Email failed: {e}")
        return False


# =========================================================
# MAIN ENTRY  (called from api.py via generate_and_send_reports)
# =========================================================

def generate_and_send_reports(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("🚀 Report generation started")
    try:
        # 1. Normalise
        report_data = normalise_processed(raw_data)
        logger.info(f"  regime : {report_data['regime']['regime_label']}  "
                    f"conf={safe_float(report_data['regime']['confidence_score'])*100:.0f}%  "
                    f"movers={len(report_data['movers'])}")

        # 2. Gemini AI
        ai = enhance_report_with_gemini(report_data)
        report_data["ai_analysis"] = ai.get("analysis", "")
        report_data["model_used"]  = ai.get("model_used", "")

        # 3. Build HTML
        html = generate_detailed_report(report_data)

        # 4. Send
        sent   = send_email_report(html)
        status = "success" if sent else "partial"

        return {
            "status":       status,
            "message":      "Report sent" if sent else "Built but email failed",
            "recipients":   EMAIL_CONFIG["recipients"],
            "ai_enhanced":  ai["success"],
            "model_used":   report_data["model_used"],
            "assets_count": len(report_data["movers"]),
        }

    except Exception as e:
        import traceback
        logger.error(f"❌ Fatal: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": str(e), "error": str(e)}


# =========================================================
# STANDALONE TEST
# =========================================================

if __name__ == "__main__":

    # ── Simulate data_processor output (what api.py actually passes in) ──
    sample_processed = {
        "status":       "completed",
        "timestamp":    "2026-05-23T20:06:52.121Z",
        "total_assets": 10,
        "metrics": {
            "total_regimes":   1,
            "total_movers":    10,
            "regime_label":    "BULL",
            "confidence_score":"0.46",
            "volatility_level":"HIGH",
            "trade_date":      "2026-05-18T00:00:00.000Z",
        },
        "assets": [
            {"ticker_symbol":"^VIX",      "rsi":"45.41","macd":"-0.8014","volatility":"0.0454","daily_return":"-0.0331","atr":"1.6831","sma_20":"18.00","ema_20":"18.33"},
            {"ticker_symbol":"SLV",       "rsi":"48.06","macd":"1.1538", "volatility":"0.0382","daily_return":"0.0130", "atr":"3.2309","sma_20":"70.37","ema_20":"71.43"},
            {"ticker_symbol":"USO",       "rsi":"62.35","macd":"5.4371", "volatility":"0.0354","daily_return":"0.0072", "atr":"6.7937","sma_20":"139.97","ema_20":"139.22"},
            {"ticker_symbol":"NVDA",      "rsi":"61.66","macd":"9.0599", "volatility":"0.0283","daily_return":"-0.0133","atr":"7.7921","sma_20":"211.31","ema_20":"212.24"},
            {"ticker_symbol":"HCLTECH.NS","rsi":"31.07","macd":"-52.8877","volatility":"0.0283","daily_return":"0.0124","atr":"32.6353","sma_20":"1200.67","ema_20":"1205.26"},
            {"ticker_symbol":"GOOGL",     "rsi":"70.30","macd":"19.3845","volatility":"0.0264","daily_return":"0.0004","atr":"10.0213","sma_20":"377.42","ema_20":"379.10"},
            {"ticker_symbol":"DRREDDY.NS","rsi":"58.62","macd":"11.8330","volatility":"0.0263","daily_return":"-0.0041","atr":"36.9059","sma_20":"1380.20","ema_20":"1372.80"},
            {"ticker_symbol":"CIPLA.NS",  "rsi":"68.57","macd":"35.4247","volatility":"0.0253","daily_return":"-0.0041","atr":"35.5618","sma_20":"1510.30","ema_20":"1521.40"},
            {"ticker_symbol":"TSLA",      "rsi":"52.68","macd":"13.4867","volatility":"0.0253","daily_return":"-0.0290","atr":"17.1595","sma_20":"402.19","ema_20":"408.32"},
            {"ticker_symbol":"META",      "rsi":"44.51","macd":"-6.5943","volatility":"0.0226","daily_return":"-0.0049","atr":"16.6875","sma_20":"628.40","ema_20":"622.02"},
        ],
        "indicators": {
            "REGIME":     "BULL",
            "CONFIDENCE": "46.0%",
            "VOLATILITY": "HIGH",
            "TOP_MOVERS": "10",
        },
        "insights": [
            "Market Regime: BULL",
            "Confidence: 46.0%",
            "Volatility: HIGH",
            "Total Movers: 10",
        ],
        "alerts": [],
    }

    result = generate_and_send_reports(sample_processed)
    print(json.dumps(result, indent=2))