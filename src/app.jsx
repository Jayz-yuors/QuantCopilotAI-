import React, { useState, useEffect, useCallback } from "react";
import {
  LineChart, Line, AreaChart, Area, BarChart, Bar,
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
  PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer
} from "recharts";
import {
  TrendingUp, TrendingDown, Activity, Database,
  AlertTriangle, CheckCircle, RefreshCw, Mail,
  BarChart2, Target, Shield, Zap, ChevronRight,
  Eye, ArrowUpRight, ArrowDownRight
} from "lucide-react";

// ── API BASE ─────────────────────────────────────────────────────────────
const API = "http://localhost:8000";

// ── COLOUR SYSTEM ────────────────────────────────────────────────────────
const C = {
  bg:      "#0A0E1A",
  surface: "#111827",
  border:  "#1F2937",
  accent:  "#6366F1",
  green:   "#10B981",
  red:     "#EF4444",
  amber:   "#F59E0B",
  blue:    "#3B82F6",
  purple:  "#8B5CF6",
  teal:    "#14B8A6",
  text:    "#F9FAFB",
  muted:   "#6B7280",
};

const CHART_COLORS = [C.accent, C.green, C.amber, C.blue, C.purple, C.teal, C.red, "#EC4899", "#F97316", "#A3E635"];

const REGIME_COLORS = { BULL: C.green, BEAR: C.red, HIGH_VOLATILITY: C.amber, SIDEWAYS: C.blue };
const VOL_COLORS    = { LOW: C.green,  MEDIUM: C.amber, HIGH: C.red, EXTREME: "#8B5CF6" };

// ── HELPERS ───────────────────────────────────────────────────────────────
const fmt  = (v, d = 2) => (typeof v === "number" ? v.toFixed(d) : "—");
const pct  = (v) => `${v >= 0 ? "+" : ""}${fmt(v * 100)}%`;
const fmtDate = (s) => { try { return new Date(s).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }); } catch { return s; } };

function rsiSignal(rsi) {
  if (rsi >= 70) return { label: "Overbought", color: C.red };
  if (rsi <= 30) return { label: "Oversold",   color: C.green };
  if (rsi >= 60) return { label: "Bullish",    color: "#6EE7B7" };
  if (rsi <= 40) return { label: "Bearish",    color: C.amber };
  return           { label: "Neutral",     color: C.muted };
}

function signalColor(sig) {
  const m = { STRONG_BUY: C.green, BUY: "#6EE7B7", NEUTRAL: C.muted, SELL: C.amber, STRONG_SELL: C.red };
  return m[sig] || C.muted;
}

// ── SMALL COMPONENTS ─────────────────────────────────────────────────────

function Pill({ label, color }) {
  return (
    <span style={{ background: color + "22", color, border: `1px solid ${color}44`, borderRadius: 20, padding: "2px 10px", fontSize: 11, fontWeight: 700, letterSpacing: ".4px" }}>
      {label}
    </span>
  );
}

function StatCard({ icon: Icon, label, value, sub, color = C.accent, trend }) {
  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: "20px 22px", display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <span style={{ fontSize: 12, color: C.muted, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".6px" }}>{label}</span>
        <div style={{ background: color + "18", padding: 7, borderRadius: 8 }}><Icon size={16} color={color} /></div>
      </div>
      <div style={{ fontSize: 28, fontWeight: 800, color: C.text, lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: C.muted }}>{sub}</div>}
      {trend !== undefined && (
        <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: trend >= 0 ? C.green : C.red }}>
          {trend >= 0 ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
          {Math.abs(trend).toFixed(2)}%
        </div>
      )}
    </div>
  );
}

function SectionTitle({ icon: Icon, title, sub }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
      <div style={{ background: C.accent + "20", padding: 8, borderRadius: 8 }}><Icon size={18} color={C.accent} /></div>
      <div>
        <div style={{ fontSize: 15, fontWeight: 700, color: C.text }}>{title}</div>
        {sub && <div style={{ fontSize: 12, color: C.muted }}>{sub}</div>}
      </div>
    </div>
  );
}

// ── CUSTOM TOOLTIP ────────────────────────────────────────────────────────
function ChartTip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "#1F2937", border: `1px solid ${C.border}`, borderRadius: 8, padding: "10px 14px", fontSize: 12 }}>
      <div style={{ color: C.muted, marginBottom: 4, fontWeight: 600 }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color, display: "flex", gap: 8 }}>
          <span style={{ minWidth: 80 }}>{p.name}</span>
          <span style={{ fontWeight: 700 }}>{typeof p.value === "number" ? p.value.toFixed(4) : p.value}</span>
        </div>
      ))}
    </div>
  );
}

// ── REGIME BADGE ──────────────────────────────────────────────────────────
function RegimeBadge({ label, confidence, volatility, date }) {
  const col = REGIME_COLORS[label] || C.accent;
  const vc  = VOL_COLORS[volatility] || C.amber;
  return (
    <div style={{ background: `linear-gradient(135deg, ${col}18 0%, ${C.surface} 100%)`, border: `1px solid ${col}44`, borderRadius: 14, padding: "22px 28px", display: "flex", alignItems: "center", gap: 24, flexWrap: "wrap" }}>
      <div style={{ background: col, color: "#fff", borderRadius: 30, padding: "8px 24px", fontWeight: 800, fontSize: 18, letterSpacing: ".5px" }}>{label || "—"}</div>
      <div style={{ display: "flex", gap: 28 }}>
        <div>
          <div style={{ fontSize: 11, color: C.muted, textTransform: "uppercase", letterSpacing: ".6px" }}>Confidence</div>
          <div style={{ fontSize: 26, fontWeight: 800, color: confidence >= 70 ? C.green : confidence >= 50 ? C.amber : C.red }}>{confidence?.toFixed(1)}%</div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: C.muted, textTransform: "uppercase", letterSpacing: ".6px" }}>Volatility</div>
          <div style={{ fontSize: 26, fontWeight: 800, color: vc }}>{volatility || "—"}</div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: C.muted, textTransform: "uppercase", letterSpacing: ".6px" }}>Trade Date</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: C.text, marginTop: 4 }}>{fmtDate(date)}</div>
        </div>
      </div>
    </div>
  );
}

// ── ASSET TABLE ───────────────────────────────────────────────────────────
function AssetTable({ movers }) {
  if (!movers?.length) return <div style={{ color: C.muted, padding: 16, textAlign: "center" }}>No asset data available.</div>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ background: "#161D2E" }}>
            {["Symbol","RSI","MACD","Daily Return","Volatility","ATR","Trend","Signal"].map(h => (
              <th key={h} style={{ padding: "10px 10px", textAlign: h === "Symbol" ? "left" : "center", color: C.muted, fontWeight: 700, fontSize: 11, textTransform: "uppercase", letterSpacing: ".5px", borderBottom: `2px solid ${C.border}` }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {movers.map((m, i) => {
            const rsiS  = rsiSignal(m.rsi);
            const retC  = m.daily_return >= 0 ? C.green : C.red;
            const macdC = m.macd >= 0 ? C.green : C.red;
            const emaUp = m.ema_20 > m.sma_20;
            return (
              <tr key={i} style={{ borderBottom: `1px solid ${C.border}` }}
                  onMouseEnter={e => e.currentTarget.style.background = "#161D2E"}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                <td style={{ padding: "10px 10px", fontWeight: 800, color: C.accent, fontSize: 14 }}>{m.ticker}</td>
                <td style={{ textAlign: "center", padding: "10px 10px" }}>
                  <span style={{ background: rsiS.color + "22", color: rsiS.color, border: `1px solid ${rsiS.color}44`, borderRadius: 12, padding: "2px 8px", fontSize: 11, fontWeight: 700 }}>
                    {fmt(m.rsi, 1)} <span style={{ fontWeight: 400, opacity: .8 }}>{rsiS.label}</span>
                  </span>
                </td>
                <td style={{ textAlign: "center", color: macdC, fontWeight: 700, padding: "10px 10px" }}>{m.macd >= 0 ? "+" : ""}{fmt(m.macd, 4)}</td>
                <td style={{ textAlign: "center", color: retC, fontWeight: 700, padding: "10px 10px" }}>{m.daily_return >= 0 ? "+" : ""}{fmt(m.daily_return * 100, 2)}%</td>
                <td style={{ textAlign: "center", color: C.muted, padding: "10px 10px" }}>{fmt(m.volatility, 4)}</td>
                <td style={{ textAlign: "center", color: C.muted, padding: "10px 10px" }}>{fmt(m.atr, 2)}</td>
                <td style={{ textAlign: "center", padding: "10px 10px" }}>
                  <span style={{ background: (emaUp ? C.green : C.red) + "22", color: emaUp ? C.green : C.red, border: `1px solid ${(emaUp ? C.green : C.red)}44`, borderRadius: 6, padding: "2px 8px", fontSize: 11, fontWeight: 700 }}>
                    {emaUp ? "EMA>SMA" : "SMA>EMA"}
                  </span>
                </td>
                <td style={{ textAlign: "center", padding: "10px 10px" }}>
                  {m.overall_signal && <Pill label={m.overall_signal} color={signalColor(m.overall_signal)} />}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── AI ANALYSIS PANEL ─────────────────────────────────────────────────────
function AIAnalysisPanel({ analysis }) {
  const [tab, setTab] = useState("regime");
  if (!analysis) return null;

  const tabs = [
    { id: "regime",    label: "Regime",       icon: Activity },
    { id: "scorecards",label: "Scorecards",   icon: Target },
    { id: "sectors",   label: "Sectors",      icon: BarChart2 },
    { id: "risks",     label: "Risk Matrix",  icon: AlertTriangle },
    { id: "opps",      label: "Opportunities",icon: Zap },
    { id: "strategy",  label: "Strategy",     icon: Shield },
  ];

  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, overflow: "hidden" }}>
      {/* Tab bar */}
      <div style={{ display: "flex", borderBottom: `1px solid ${C.border}`, overflowX: "auto" }}>
        {tabs.map(t => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              style={{ display: "flex", alignItems: "center", gap: 6, padding: "14px 18px", border: "none", cursor: "pointer", whiteSpace: "nowrap",
                       background: active ? C.accent + "18" : "transparent",
                       color: active ? C.accent : C.muted,
                       borderBottom: active ? `2px solid ${C.accent}` : "2px solid transparent",
                       fontWeight: active ? 700 : 500, fontSize: 13, transition: "all .15s" }}>
              <Icon size={14} />{t.label}
            </button>
          );
        })}
      </div>

      <div style={{ padding: "24px 26px" }}>

        {/* REGIME */}
        {tab === "regime" && analysis.regime_analysis && (() => {
          const r = analysis.regime_analysis;
          return (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{ fontSize: 18, fontWeight: 800, color: C.text, lineHeight: 1.3 }}>{r.headline}</div>
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                <Pill label={r.conviction + " CONVICTION"} color={r.conviction === "HIGH" ? C.green : r.conviction === "MODERATE" ? C.amber : C.red} />
                <Pill label={r.trading_bias?.replace("_", " ")} color={C.accent} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                {[
                  { label: "Conviction Reason",         text: r.conviction_reason },
                  { label: "Volatility Interpretation", text: r.volatility_interpretation },
                  { label: "Macro Context",             text: r.macro_context },
                ].map(({ label, text }) => (
                  <div key={label} style={{ background: "#161D2E", borderRadius: 10, padding: "14px 16px", gridColumn: label === "Macro Context" ? "1 / -1" : undefined }}>
                    <div style={{ fontSize: 11, color: C.muted, textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 6 }}>{label}</div>
                    <div style={{ fontSize: 13.5, color: C.text, lineHeight: 1.6 }}>{text}</div>
                  </div>
                ))}
              </div>
            </div>
          );
        })()}

        {/* SCORECARDS */}
        {tab === "scorecards" && analysis.asset_scorecards && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 14 }}>
            {analysis.asset_scorecards.map((sc, i) => {
              const sc_col = signalColor(sc.overall_signal);
              return (
                <div key={i} style={{ background: "#161D2E", border: `1px solid ${sc_col}33`, borderRadius: 12, padding: "16px 18px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                    <span style={{ fontSize: 16, fontWeight: 800, color: C.accent }}>{sc.ticker}</span>
                    <Pill label={sc.overall_signal?.replace("_", " ")} color={sc_col} />
                  </div>
                  <div style={{ fontSize: 12, color: C.text, lineHeight: 1.7, marginBottom: 8 }}>
                    <div>📊 {sc.rsi_verdict}</div>
                    <div>📈 {sc.macd_verdict}</div>
                    <div>🔀 {sc.trend_verdict}</div>
                    <div>💹 {sc.return_verdict}</div>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: `1px solid ${C.border}`, paddingTop: 10 }}>
                    <span style={{ fontSize: 11, color: C.muted }}>Risk: <b style={{ color: sc.risk_score >= 7 ? C.red : sc.risk_score >= 5 ? C.amber : C.green }}>{sc.risk_score}/10</b></span>
                    <span style={{ fontSize: 11, color: C.muted, maxWidth: 160, textAlign: "right" }}>{sc.key_level}</span>
                  </div>
                  <div style={{ marginTop: 8, fontSize: 12, color: C.accent, fontStyle: "italic" }}>→ {sc.one_liner}</div>
                </div>
              );
            })}
          </div>
        )}

        {/* SECTORS */}
        {tab === "sectors" && analysis.sector_breakdown && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {analysis.sector_breakdown.map((s, i) => {
              const sc = { BULLISH: C.green, BEARISH: C.red, MIXED: C.amber, NEUTRAL: C.muted }[s.sector_signal] || C.muted;
              return (
                <div key={i} style={{ background: "#161D2E", borderLeft: `4px solid ${sc}`, borderRadius: 10, padding: "16px 18px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                    <span style={{ fontSize: 15, fontWeight: 800, color: C.text }}>{s.sector}</span>
                    <Pill label={s.sector_signal} color={sc} />
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
                    {(s.tickers || []).map(t => <Pill key={t} label={t} color={C.accent} />)}
                  </div>
                  <div style={{ fontSize: 13, color: C.muted, lineHeight: 1.6 }}>{s.sector_insight}</div>
                </div>
              );
            })}
          </div>
        )}

        {/* RISKS */}
        {tab === "risks" && analysis.risk_matrix && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {analysis.risk_matrix.map((r, i) => {
              const sc = { HIGH: C.red, MEDIUM: C.amber, LOW: C.green }[r.severity] || C.muted;
              return (
                <div key={i} style={{ background: "#161D2E", border: `1px solid ${sc}33`, borderRadius: 10, padding: "16px 18px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                    <span style={{ fontSize: 14, fontWeight: 700, color: C.text }}>⚠️ {r.risk_type}</span>
                    <Pill label={r.severity} color={sc} />
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, fontSize: 12, color: C.muted, lineHeight: 1.6 }}>
                    <div><b style={{ color: C.text }}>Trigger:</b> {r.trigger}</div>
                    <div><b style={{ color: C.text }}>Affected:</b> {(r.affected_assets || []).join(", ")}</div>
                    <div style={{ gridColumn: "1 / -1" }}><b style={{ color: C.green }}>Mitigation:</b> {r.mitigation}</div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* OPPORTUNITIES */}
        {tab === "opps" && analysis.opportunities && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 14 }}>
            {analysis.opportunities.map((o, i) => {
              const tc = { LONG: C.green, SHORT: C.red, HEDGE: C.amber, WAIT: C.muted }[o.type] || C.muted;
              return (
                <div key={i} style={{ background: "#161D2E", borderTop: `3px solid ${tc}`, borderRadius: 10, padding: "16px 18px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <Pill label={o.type} color={tc} />
                      <span style={{ fontSize: 15, fontWeight: 800, color: C.accent }}>{o.ticker}</span>
                    </div>
                    <Pill label={o.time_horizon?.replace(/[()]/g, "")} color={C.purple} />
                  </div>
                  <div style={{ fontSize: 12, color: C.muted, lineHeight: 1.7 }}>
                    <div style={{ color: C.text, marginBottom: 4 }}>{o.rationale}</div>
                    <div>🟢 <b>Entry:</b> {o.entry_condition}</div>
                    <div>🔴 <b>Exit:</b>  {o.exit_condition}</div>
                    <div style={{ marginTop: 8 }}>
                      <span style={{ background: C.accent + "22", color: C.accent, borderRadius: 6, padding: "2px 8px", fontWeight: 700 }}>R:R {o.risk_reward}</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* STRATEGY */}
        {tab === "strategy" && analysis.portfolio_strategy && (() => {
          const s = analysis.portfolio_strategy;
          return (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {[
                { label: "Portfolio Positioning",   text: s.positioning },
                { label: "Hedge Recommendation",    text: s.hedge_recommendation },
                { label: "Rebalancing Trigger",     text: s.rebalancing_trigger },
              ].map(({ label, text }) => (
                <div key={label} style={{ background: "#161D2E", borderRadius: 10, padding: "16px 18px" }}>
                  <div style={{ fontSize: 11, color: C.muted, textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 6 }}>{label}</div>
                  <div style={{ fontSize: 13.5, color: C.text, lineHeight: 1.65 }}>{text}</div>
                </div>
              ))}
              {s.top_3_watchlist?.length > 0 && (
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: C.text, marginBottom: 10 }}>🎯 Top 3 Watchlist</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {s.top_3_watchlist.map((w, i) => (
                      <div key={i} style={{ display: "flex", gap: 12, alignItems: "center", background: "#161D2E", borderRadius: 8, padding: "10px 14px" }}>
                        <span style={{ background: C.accent + "22", color: C.accent, borderRadius: 6, padding: "3px 10px", fontWeight: 800, fontSize: 13 }}>{w.ticker}</span>
                        <span style={{ fontSize: 12, color: C.muted }}>{w.reason}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })()}
      </div>
    </div>
  );
}

// ── EMAIL REPORT SECTION ──────────────────────────────────────────────────
function EmailReportSection({ onSubmit, loading }) {
  const [email, setEmail]     = useState("");
  const [status, setStatus]   = useState(null); // "sent"|"error"|null

  const handleSubmit = async () => {
    if (!email.includes("@")) { setStatus("error"); return; }
    setStatus(null);
    const ok = await onSubmit(email);
    setStatus(ok ? "sent" : "error");
  };

  return (
    <div style={{ background: `linear-gradient(135deg, ${C.accent}15, ${C.surface})`, border: `1px solid ${C.accent}33`, borderRadius: 14, padding: "28px 30px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
        <Mail size={20} color={C.accent} />
        <span style={{ fontSize: 16, fontWeight: 800, color: C.text }}>Get the Full Report by Email</span>
      </div>
      <p style={{ fontSize: 13, color: C.muted, marginBottom: 18, lineHeight: 1.6 }}>
        Receive the daily AI market intelligence report — regime analysis, asset scorecards, risk matrix, and trade opportunities — formatted and delivered to your inbox.
      </p>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <input
          type="email"
          placeholder="your@email.com"
          value={email}
          onChange={e => setEmail(e.target.value)}
          onKeyDown={e => e.key === "Enter" && handleSubmit()}
          style={{ flex: 1, minWidth: 220, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8, padding: "11px 14px", color: C.text, fontSize: 14, outline: "none" }}
        />
        <button
          onClick={handleSubmit}
          disabled={loading}
          style={{ background: C.accent, color: "#fff", border: "none", borderRadius: 8, padding: "11px 22px", fontWeight: 700, fontSize: 14, cursor: loading ? "not-allowed" : "pointer", opacity: loading ? .7 : 1, display: "flex", alignItems: "center", gap: 8 }}>
          {loading ? <RefreshCw size={14} style={{ animation: "spin 1s linear infinite" }} /> : <Mail size={14} />}
          {loading ? "Sending…" : "Send Report"}
        </button>
      </div>
      {status === "sent"  && <div style={{ marginTop: 10, color: C.green,  fontSize: 12 }}>✅ Report sent! Check your inbox.</div>}
      {status === "error" && <div style={{ marginTop: 10, color: C.red,    fontSize: 12 }}>❌ Invalid email or send failed. Try again.</div>}
    </div>
  );
}

// ── MAIN APP ──────────────────────────────────────────────────────────────
export default function App() {
  const [dash, setDash]         = useState(null);
  const [webReport, setWebReport] = useState(null);
  const [loading, setLoading]   = useState(true);
  const [repLoading, setRepLoading] = useState(false);
  const [emailLoading, setEmailLoading] = useState(false);
  const [error, setError]       = useState(null);
  const [activeNav, setActiveNav] = useState("dashboard");

  // ── Fetch dashboard data ────────────────────────────────────────────
  const fetchDash = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const r = await fetch(`${API}/dashboard-data`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setDash(d);
    } catch (e) {
      setError("Backend unreachable. Make sure FastAPI is running on :8000");
    } finally {
      setLoading(false);
    }
  }, []);

  // ── Generate website report ─────────────────────────────────────────
  const fetchWebReport = useCallback(async () => {
    if (!dash) return;
    setRepLoading(true);
    try {
      const payload = {
        assets:  dash.top_movers.map(m => ({ ...m, ticker_symbol: m.ticker })),
        metrics: { ...dash.regime, regime_label: dash.regime.label, confidence_score: dash.regime.confidence / 100, trade_date: dash.regime.date },
        indicators: {},
        insights: [],
        alerts:  [],
        status:  "completed",
        timestamp: new Date().toISOString(),
        total_assets: dash.top_movers.length,
      };
      const r = await fetch(`${API}/web-report`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setWebReport(d);
    } catch (e) {
      console.error("Web report error:", e);
    } finally {
      setRepLoading(false);
    }
  }, [dash]);

  // ── Send email report (via N8N workflow) ──────────────────────────
  const sendEmailReport = useCallback(async (email) => {
    if (!dash) return false;
    setEmailLoading(true);
    try {
      const payload = {
        email: email,
        dashboard_data: {
          assets:  dash.top_movers.map(m => ({ ...m, ticker_symbol: m.ticker })),
          metrics: { ...dash.regime, regime_label: dash.regime.label, confidence_score: dash.regime.confidence / 100, trade_date: dash.regime.date },
          indicators: {},
          insights: [],
          alerts: [],
          status: "completed",
          timestamp: new Date().toISOString(),
          total_assets: dash.top_movers.length,
        },
        timestamp: new Date().toISOString(),
      };
      // Fire N8N workflow via backend endpoint
      const r = await fetch(`${API}/trigger-n8n`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const responseText = await r.text();
      console.log("🔄 Backend response status:", r.status);
      console.log("🔄 Backend response body:", responseText);
      if (!r.ok) {
        console.error("❌ Backend error:", r.status, responseText);
        return false;
      }
      console.log("✅ Backend returned success!");
      return r.ok;
    } catch (e) { 
      console.error("❌ Frontend fetch error:", e);
      return false; 
    }
    finally { setEmailLoading(false); }
  }, [dash]);

  useEffect(() => { 
    fetchDash(); 
    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchDash, 30000);
    return () => clearInterval(interval);
  }, [fetchDash]);

  // ── NAV ─────────────────────────────────────────────────────────────
  const navItems = [
    { id: "dashboard", label: "Dashboard",    icon: BarChart2 },
    { id: "assets",    label: "Assets",       icon: TrendingUp },
    { id: "analysis",  label: "AI Analysis",  icon: Zap },
    { id: "report",    label: "Get Report",   icon: Mail },
  ];

  // ── LOADING / ERROR ──────────────────────────────────────────────────
  if (loading) return (
    <div style={{ minHeight: "100vh", background: C.bg, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 16 }}>
      <RefreshCw size={32} color={C.accent} style={{ animation: "spin 1s linear infinite" }} />
      <div style={{ color: C.muted, fontSize: 14 }}>Loading QuantCopilot AI Dashboard…</div>
    </div>
  );

  if (error) return (
    <div style={{ minHeight: "100vh", background: C.bg, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 14, padding: 32 }}>
      <AlertTriangle size={36} color={C.red} />
      <div style={{ color: C.red, fontSize: 16, fontWeight: 700 }}>Connection Error</div>
      <div style={{ color: C.muted, fontSize: 13, textAlign: "center", maxWidth: 400 }}>{error}</div>
      <button onClick={fetchDash} style={{ background: C.accent, color: "#fff", border: "none", borderRadius: 8, padding: "10px 20px", fontWeight: 700, cursor: "pointer" }}>Retry</button>
    </div>
  );

  const d = dash;

  // Build merged movers (scorecards overlaid on dashboard movers)
  const mergedMovers = (d?.top_movers || []).map(m => {
    const sc = webReport?.analysis?.asset_scorecards?.find(s => s.ticker === m.ticker);
    return { ...m, ...sc };
  });

  // ── RENDER ───────────────────────────────────────────────────────────
  return (
    <div style={{ minHeight: "100vh", background: C.bg, color: C.text, fontFamily: "'DM Sans', 'Segoe UI', sans-serif" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700;800;900&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: ${C.bg}; }
        ::-webkit-scrollbar-thumb { background: ${C.border}; border-radius: 3px; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
      `}</style>

      {/* ── TOPBAR ── */}
      <div style={{ background: C.surface, borderBottom: `1px solid ${C.border}`, padding: "0 28px", display: "flex", alignItems: "center", justifyContent: "space-between", height: 60, position: "sticky", top: 0, zIndex: 100 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ background: C.accent, borderRadius: 8, padding: "6px 10px", fontWeight: 900, fontSize: 14, color: "#fff", letterSpacing: ".5px" }}>QC</div>
          <span style={{ fontWeight: 800, fontSize: 17, color: C.text }}>QuantCopilot</span>
          <span style={{ background: C.accent + "22", color: C.accent, borderRadius: 6, padding: "2px 8px", fontSize: 11, fontWeight: 700 }}>AI</span>
        </div>

        <nav style={{ display: "flex", gap: 4 }}>
          {navItems.map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setActiveNav(id)}
              style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 14px", border: "none", borderRadius: 8, cursor: "pointer",
                       background: activeNav === id ? C.accent + "22" : "transparent",
                       color: activeNav === id ? C.accent : C.muted,
                       fontWeight: activeNav === id ? 700 : 500, fontSize: 13 }}>
              <Icon size={14} />{label}
            </button>
          ))}
        </nav>

        <button onClick={fetchDash} style={{ display: "flex", alignItems: "center", gap: 6, background: "transparent", border: `1px solid ${C.border}`, borderRadius: 8, padding: "7px 12px", color: C.muted, cursor: "pointer", fontSize: 12 }}>
          <RefreshCw size={13} />Refresh
        </button>
      </div>

      {/* ── CONTENT ── */}
      <div style={{ maxWidth: 1400, margin: "0 auto", padding: "28px 24px", display: "flex", flexDirection: "column", gap: 28 }}>

        {/* ══════════ DASHBOARD TAB ══════════ */}
        {activeNav === "dashboard" && (
          <>
            {/* Regime Banner */}
            <RegimeBadge label={d?.regime?.label} confidence={d?.regime?.confidence} volatility={d?.regime?.volatility} date={d?.regime?.date} />

            {/* KPI Cards */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 14 }}>
              <StatCard icon={Database}    label="Total Assets"    value={d?.db_summary?.assets ?? "—"}    sub="In market_assets table" />
              <StatCard icon={BarChart2}   label="Price Records"   value={(d?.db_summary?.prices || 0).toLocaleString()} sub="market_price_history" color={C.blue} />
              <StatCard icon={Activity}    label="Indicator Rows"  value={(d?.db_summary?.indicators || 0).toLocaleString()} sub="technical_indicators" color={C.green} />
              <StatCard icon={TrendingUp}  label="Regime Records"  value={(d?.db_summary?.regimes || 0).toLocaleString()} sub="market_regimes" color={C.purple} />
              <StatCard icon={Target}      label="Confidence"      value={`${d?.regime?.confidence?.toFixed(1) ?? "—"}%`} sub="Current regime conviction" color={d?.regime?.confidence >= 50 ? C.green : C.red} />
              <StatCard icon={AlertTriangle} label="Overbought Now" value={d?.rsi_distribution?.find(r => r.bucket.includes("Overbought"))?.count ?? 0} sub="RSI > 70 today" color={C.red} />
            </div>

            {/* Charts Row 1: Confidence Trend + Regime Dist */}
            <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 18 }}>
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: "22px 24px" }}>
                <SectionTitle icon={Activity} title="Regime Confidence Trend" sub="30-day rolling average confidence score" />
                <ResponsiveContainer width="100%" height={220}>
                  <AreaChart data={d?.conf_trend || []}>
                    <defs>
                      <linearGradient id="confGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%"  stopColor={C.accent} stopOpacity={.3} />
                        <stop offset="95%" stopColor={C.accent} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={C.border} />
                    <XAxis dataKey="date" tick={{ fill: C.muted, fontSize: 11 }} tickFormatter={s => s?.slice(5)} />
                    <YAxis tick={{ fill: C.muted, fontSize: 11 }} domain={[0, 100]} unit="%" />
                    <Tooltip content={<ChartTip />} />
                    <Area type="monotone" dataKey="confidence" stroke={C.accent} strokeWidth={2} fill="url(#confGrad)" name="Confidence" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: "22px 24px" }}>
                <SectionTitle icon={TrendingUp} title="Regime Distribution" sub="Last 90 days" />
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie data={d?.regime_dist || []} dataKey="count" nameKey="label" cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={4}>
                      {(d?.regime_dist || []).map((r, i) => (
                        <Cell key={i} fill={REGIME_COLORS[r.label] || CHART_COLORS[i % CHART_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v, n) => [v + " days", n]} />
                    <Legend iconType="circle" iconSize={10} wrapperStyle={{ fontSize: 12, color: C.muted }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Charts Row 2: Volatility History + RSI Dist + Asset Types */}
            <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: 18 }}>
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: "22px 24px" }}>
                <SectionTitle icon={Activity} title="Volatility History" sub="Top 5 assets — last 30 days" />
                <ResponsiveContainer width="100%" height={210}>
                  <LineChart data={d?.vol_history || []}>
                    <CartesianGrid strokeDasharray="3 3" stroke={C.border} />
                    <XAxis dataKey="date" tick={{ fill: C.muted, fontSize: 10 }} tickFormatter={s => s?.slice(5)} />
                    <YAxis tick={{ fill: C.muted, fontSize: 10 }} />
                    <Tooltip content={<ChartTip />} />
                    <Legend iconSize={10} wrapperStyle={{ fontSize: 11, color: C.muted }} />
                    {d?.vol_history?.length
                      ? Object.keys(d.vol_history[0] || {}).filter(k => k !== "date").map((k, i) => (
                          <Line key={k} type="monotone" dataKey={k} stroke={CHART_COLORS[i % CHART_COLORS.length]} strokeWidth={2} dot={false} />
                        ))
                      : null}
                  </LineChart>
                </ResponsiveContainer>
              </div>

              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: "22px 24px" }}>
                <SectionTitle icon={Target} title="RSI Distribution" sub="Today's snapshot" />
                <ResponsiveContainer width="100%" height={210}>
                  <BarChart data={d?.rsi_distribution || []} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke={C.border} horizontal={false} />
                    <XAxis type="number" tick={{ fill: C.muted, fontSize: 10 }} />
                    <YAxis type="category" dataKey="bucket" tick={{ fill: C.muted, fontSize: 10 }} width={100} />
                    <Tooltip content={<ChartTip />} />
                    <Bar dataKey="count" radius={[0, 6, 6, 0]}>
                      {(d?.rsi_distribution || []).map((r, i) => {
                        const cols = [C.green, C.blue, C.amber, C.red];
                        return <Cell key={i} fill={cols[i]} />;
                      })}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: "22px 24px" }}>
                <SectionTitle icon={Database} title="Asset Types" sub="Portfolio composition" />
                <ResponsiveContainer width="100%" height={210}>
                  <PieChart>
                    <Pie data={d?.asset_types || []} dataKey="count" nameKey="type" cx="50%" cy="50%" outerRadius={80} paddingAngle={3}>
                      {(d?.asset_types || []).map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                    </Pie>
                    <Tooltip formatter={(v, n) => [v + " assets", n]} />
                    <Legend iconType="circle" iconSize={10} wrapperStyle={{ fontSize: 11, color: C.muted }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Charts Row 3: MACD comparison + daily return comparison */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: "22px 24px" }}>
                <SectionTitle icon={BarChart2} title="MACD Comparison" sub="All assets today" />
                <ResponsiveContainer width="100%" height={210}>
                  <BarChart data={(d?.top_movers || []).map(m => ({ name: m.ticker, macd: parseFloat(m.macd?.toFixed(2)) }))} margin={{ left: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={C.border} />
                    <XAxis dataKey="name" tick={{ fill: C.muted, fontSize: 11 }} />
                    <YAxis tick={{ fill: C.muted, fontSize: 10 }} />
                    <Tooltip content={<ChartTip />} />
                    <Bar dataKey="macd" name="MACD" radius={[4, 4, 0, 0]}>
                      {(d?.top_movers || []).map((m, i) => (
                        <Cell key={i} fill={m.macd >= 0 ? C.green : C.red} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: "22px 24px" }}>
                <SectionTitle icon={TrendingUp} title="Daily Returns" sub="All assets today (%)" />
                <ResponsiveContainer width="100%" height={210}>
                  <BarChart data={(d?.top_movers || []).map(m => ({ name: m.ticker, ret: parseFloat((m.daily_return * 100)?.toFixed(2)) }))} margin={{ left: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={C.border} />
                    <XAxis dataKey="name" tick={{ fill: C.muted, fontSize: 11 }} />
                    <YAxis tick={{ fill: C.muted, fontSize: 10 }} unit="%" />
                    <Tooltip content={<ChartTip />} />
                    <Bar dataKey="ret" name="Return %" radius={[4, 4, 0, 0]}>
                      {(d?.top_movers || []).map((m, i) => (
                        <Cell key={i} fill={m.daily_return >= 0 ? C.green : C.red} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* ATR Radar */}
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: "22px 24px" }}>
              <SectionTitle icon={Shield} title="Multi-Factor Radar" sub="Normalized RSI, MACD magnitude, Volatility, ATR for top 8 assets" />
              <ResponsiveContainer width="100%" height={320}>
                <RadarChart data={(d?.top_movers || []).slice(0, 8).map(m => ({
                  subject: m.ticker,
                  RSI:     parseFloat(((m.rsi || 0) / 100 * 10).toFixed(1)),
                  Volatility: parseFloat(((m.volatility || 0) * 200).toFixed(1)),
                  ATR:     parseFloat(Math.min((m.atr || 0) / 40 * 10, 10).toFixed(1)),
                  MACD_Abs: parseFloat(Math.min(Math.abs(m.macd || 0) / 60 * 10, 10).toFixed(1)),
                }))}>
                  <PolarGrid stroke={C.border} />
                  <PolarAngleAxis dataKey="subject" tick={{ fill: C.muted, fontSize: 11 }} />
                  <Radar name="RSI"       dataKey="RSI"       stroke={C.blue}   fill={C.blue}   fillOpacity={0.15} />
                  <Radar name="Volatility"dataKey="Volatility"stroke={C.amber}  fill={C.amber}  fillOpacity={0.12} />
                  <Radar name="ATR"       dataKey="ATR"       stroke={C.purple} fill={C.purple} fillOpacity={0.12} />
                  <Radar name="MACD Abs"  dataKey="MACD_Abs"  stroke={C.green}  fill={C.green}  fillOpacity={0.12} />
                  <Legend wrapperStyle={{ fontSize: 12, color: C.muted }} />
                  <Tooltip content={<ChartTip />} />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </>
        )}

        {/* ══════════ ASSETS TAB ══════════ */}
        {activeNav === "assets" && (
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, overflow: "hidden" }}>
            <div style={{ padding: "22px 24px 16px" }}>
              <SectionTitle icon={TrendingUp} title="Asset Performance Table" sub={`Live snapshot — ${d?.top_movers?.length || 0} assets sorted by volatility`} />
            </div>
            <AssetTable movers={mergedMovers.length ? mergedMovers : (d?.top_movers || []).map(m => ({ ...m, ticker: m.ticker }))} />
          </div>
        )}

        {/* ══════════ AI ANALYSIS TAB ══════════ */}
        {activeNav === "analysis" && (
          <>
            {!webReport && (
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: "36px", textAlign: "center" }}>
                <Zap size={40} color={C.accent} style={{ marginBottom: 14 }} />
                <div style={{ fontSize: 18, fontWeight: 700, color: C.text, marginBottom: 8 }}>AI Market Intelligence</div>
                <div style={{ fontSize: 13, color: C.muted, marginBottom: 22, maxWidth: 480, margin: "0 auto 22px" }}>
                  Generate a comprehensive 7-section analysis: regime outlook, asset scorecards, sector breakdown, risk matrix, trade opportunities, and portfolio strategy.
                </div>
                <button onClick={fetchWebReport} disabled={repLoading}
                  style={{ background: C.accent, color: "#fff", border: "none", borderRadius: 10, padding: "13px 28px", fontWeight: 700, fontSize: 14, cursor: repLoading ? "not-allowed" : "pointer", display: "inline-flex", alignItems: "center", gap: 8 }}>
                  {repLoading ? <RefreshCw size={16} style={{ animation: "spin 1s linear infinite" }} /> : <Zap size={16} />}
                  {repLoading ? "Generating Analysis…" : "Generate AI Analysis"}
                </button>
              </div>
            )}

            {webReport && (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ fontSize: 13, color: C.muted }}>
                    Generated {fmtDate(webReport.generated_at)} · Model: <b style={{ color: C.accent }}>{webReport.model_used}</b>
                  </div>
                  <button onClick={fetchWebReport} disabled={repLoading}
                    style={{ display: "flex", alignItems: "center", gap: 6, background: C.accent + "22", border: `1px solid ${C.accent}44`, color: C.accent, borderRadius: 8, padding: "7px 14px", fontWeight: 600, fontSize: 12, cursor: "pointer" }}>
                    <RefreshCw size={12} />{repLoading ? "Regenerating…" : "Regenerate"}
                  </button>
                </div>

                {/* Summary bullets */}
                {webReport.analysis?.summary_bullets?.length > 0 && (
                  <div style={{ background: C.accent + "10", border: `1px solid ${C.accent}30`, borderRadius: 12, padding: "18px 20px" }}>
                    <div style={{ fontSize: 12, color: C.accent, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 12 }}>Key Takeaways</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {webReport.analysis.summary_bullets.map((b, i) => (
                        <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start", fontSize: 13.5, color: C.text, lineHeight: 1.5 }}>
                          <ChevronRight size={14} color={C.accent} style={{ flexShrink: 0, marginTop: 2 }} />
                          {b}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <AIAnalysisPanel analysis={webReport.analysis} />
              </>
            )}
          </>
        )}

        {/* ══════════ REPORT / EMAIL TAB ══════════ */}
        {activeNav === "report" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 680 }}>
            <div>
              <div style={{ fontSize: 22, fontWeight: 800, color: C.text, marginBottom: 6 }}>Daily Market Report</div>
              <div style={{ fontSize: 13, color: C.muted }}>Enter your email to receive the full formatted report with AI analysis, charts summary, and trade recommendations.</div>
            </div>
            <EmailReportSection onSubmit={sendEmailReport} loading={emailLoading} />

            {/* What's included */}
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: "22px 24px" }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: C.text, marginBottom: 14 }}>What's in the report</div>
              {[
                { icon: Activity,       text: "Market Regime Analysis — label, confidence score, volatility interpretation" },
                { icon: TrendingUp,     text: "Asset Performance Table — RSI, MACD, daily return, ATR, trend for all assets" },
                { icon: Target,         text: "Key Insights — data-derived signals: overbought/oversold, divergences, ATR leaders" },
                { icon: Zap,            text: "AI Intelligence — 5-section Gemini analysis: standout assets, risk flags, watch-list" },
                { icon: Shield,         text: "Pipeline Status — confirms each pipeline step completed successfully" },
              ].map(({ icon: Icon, text }, i) => (
                <div key={i} style={{ display: "flex", gap: 12, alignItems: "flex-start", marginBottom: 10 }}>
                  <div style={{ background: C.accent + "18", padding: 7, borderRadius: 7, flexShrink: 0 }}><Icon size={14} color={C.accent} /></div>
                  <span style={{ fontSize: 13, color: C.muted, lineHeight: 1.5 }}>{text}</span>
                </div>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}