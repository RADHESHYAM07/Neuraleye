import { useState, useEffect, useRef, useCallback } from "react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  FunnelChart,
  Funnel,
  LabelList,
} from "recharts";

const API = "http://localhost:8000";
const WS = "ws://localhost:8000/ws/live";

const ZONE_COLORS = {
  entry: "#00ff88",
  beauty: "#ff6b9d",
  skincare: "#4ecdc4",
  haircare: "#ffd93d",
  checkout: "#ff6348",
  floor: "#a29bfe",
};

const fmt = (n) => (n == null ? "—" : n);

// ── Pulse dot ────────────────────────────────────────────────────────────────
function Pulse({ color = "#00ff88" }) {
  return (
    <span
      style={{
        position: "relative",
        display: "inline-block",
        width: 10,
        height: 10,
      }}
    >
      <span
        style={{
          position: "absolute",
          inset: 0,
          borderRadius: "50%",
          background: color,
          animation: "pulse 1.5s ease-out infinite",
        }}
      />
      <span
        style={{
          position: "absolute",
          inset: 0,
          borderRadius: "50%",
          background: color,
        }}
      />
    </span>
  );
}

// ── Stat Card ────────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, accent = "#00ff88", icon }) {
  return (
    <div
      style={{
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.07)",
        borderRadius: 16,
        padding: "20px 24px",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          color: "rgba(255,255,255,0.4)",
          fontSize: 11,
          letterSpacing: 2,
          textTransform: "uppercase",
          marginBottom: 8,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 36,
          fontWeight: 700,
          color: accent,
          fontFamily: "'DM Mono', monospace",
          lineHeight: 1,
        }}
      >
        {fmt(value)}
      </div>
      {sub && (
        <div
          style={{ color: "rgba(255,255,255,0.3)", fontSize: 12, marginTop: 6 }}
        >
          {sub}
        </div>
      )}
      <div
        style={{
          position: "absolute",
          top: 16,
          right: 16,
          fontSize: 20,
          opacity: 0.2,
        }}
      >
        {icon}
      </div>
    </div>
  );
}

// ── Zone Heatmap ─────────────────────────────────────────────────────────────
function ZoneHeatmap({ data }) {
  const max = Math.max(...(data || []).map((d) => d.visits), 1);
  return (
    <div
      style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}
    >
      {(data || []).map((z) => {
        const intensity = z.visits / max;
        const color = ZONE_COLORS[z.zone_id] || "#888";
        return (
          <div
            key={z.zone_id}
            style={{
              background: `${color}${Math.round(intensity * 40 + 10)
                .toString(16)
                .padStart(2, "0")}`,
              border: `1px solid ${color}40`,
              borderRadius: 10,
              padding: "12px 14px",
            }}
          >
            <div
              style={{
                color,
                fontSize: 10,
                letterSpacing: 1.5,
                textTransform: "uppercase",
              }}
            >
              {z.zone_id}
            </div>
            <div
              style={{
                color: "#fff",
                fontSize: 22,
                fontWeight: 700,
                fontFamily: "'DM Mono', monospace",
              }}
            >
              {z.visits}
            </div>
            <div style={{ color: "rgba(255,255,255,0.4)", fontSize: 11 }}>
              avg {z.avg_dwell_seconds}s dwell
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Alert Feed ───────────────────────────────────────────────────────────────
function AlertFeed({ alerts }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 6,
        maxHeight: 240,
        overflowY: "auto",
      }}
    >
      {alerts.length === 0 && (
        <div
          style={{
            color: "rgba(255,255,255,0.25)",
            fontSize: 13,
            textAlign: "center",
            padding: 20,
          }}
        >
          No anomalies detected
        </div>
      )}
      {alerts.map((a, i) => (
        <div
          key={i}
          style={{
            background: `rgba(255,99,72,${0.05 + a.score * 0.15})`,
            border: "1px solid rgba(255,99,72,0.3)",
            borderRadius: 8,
            padding: "10px 14px",
            display: "flex",
            alignItems: "center",
            gap: 12,
          }}
        >
          <div style={{ color: "#ff6348", fontSize: 18 }}>⚠</div>
          <div style={{ flex: 1 }}>
            <div style={{ color: "#ff8a75", fontSize: 12, fontWeight: 600 }}>
              {a.event_type} · Zone: {a.zone_id}
            </div>
            <div style={{ color: "rgba(255,255,255,0.4)", fontSize: 11 }}>
              Track #{a.track_id} · {a.detail?.dwell_seconds}s dwell
            </div>
          </div>
          <div
            style={{
              background: "#ff6348",
              color: "#fff",
              borderRadius: 6,
              padding: "2px 8px",
              fontSize: 11,
              fontWeight: 700,
            }}
          >
            {Math.round((a.score || 0) * 100)}%
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Funnel ───────────────────────────────────────────────────────────────────
function StoreFunnel({ data }) {
  const funnel = (data?.funnel || []).map((f) => ({
    name: f.zone_id,
    value: f.visitors,
    rate: f.conversion_rate,
  }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {funnel.map((f, i) => (
        <div
          key={f.name}
          style={{ display: "flex", alignItems: "center", gap: 12 }}
        >
          <div
            style={{
              width: 72,
              color: "rgba(255,255,255,0.4)",
              fontSize: 11,
              textTransform: "uppercase",
              textAlign: "right",
            }}
          >
            {f.name}
          </div>
          <div
            style={{
              flex: 1,
              background: "rgba(255,255,255,0.05)",
              borderRadius: 4,
              height: 28,
            }}
          >
            <div
              style={{
                width: `${f.rate}%`,
                height: "100%",
                background: `linear-gradient(90deg, ${Object.values(ZONE_COLORS)[i % 6]}cc, ${Object.values(ZONE_COLORS)[i % 6]}66)`,
                borderRadius: 4,
                display: "flex",
                alignItems: "center",
                paddingLeft: 8,
                minWidth: 40,
              }}
            >
              <span style={{ color: "#fff", fontSize: 11, fontWeight: 600 }}>
                {f.value}
              </span>
            </div>
          </div>
          <div
            style={{
              width: 40,
              color: "rgba(255,255,255,0.5)",
              fontSize: 11,
              textAlign: "right",
            }}
          >
            {f.rate}%
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [live, setLive] = useState({});
  const [heatmap, setHeatmap] = useState([]);
  const [funnel, setFunnel] = useState({});
  const [traffic, setTraffic] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [wsStatus, setWsStatus] = useState("connecting");
  const wsRef = useRef(null);

  // Fetch REST data
  const fetchAll = useCallback(async () => {
    try {
      const [h, f, t, a] = await Promise.all([
        fetch(`${API}/api/v1/heatmap`).then((r) => r.json()),
        fetch(`${API}/api/v1/funnel`).then((r) => r.json()),
        fetch(`${API}/api/v1/traffic?minutes=60`).then((r) => r.json()),
        fetch(`${API}/api/v1/anomalies?hours=1`).then((r) => r.json()),
      ]);
      setHeatmap(h.zones || []);
      setFunnel(f);
      setTraffic(t.series || []);
      setAnomalies(a.anomalies || []);
    } catch (e) {
      console.error("Fetch error:", e);
    }
  }, []);

  // WebSocket
  useEffect(() => {
    const connect = () => {
      const ws = new WebSocket(WS);
      wsRef.current = ws;
      ws.onopen = () => setWsStatus("live");
      ws.onclose = () => {
        setWsStatus("reconnecting");
        setTimeout(connect, 2000);
      };
      ws.onerror = () => setWsStatus("error");
      ws.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.type === "ALERT") {
          setAlerts((prev) => [data, ...prev].slice(0, 20));
        } else {
          setLive(data);
        }
      };
    };
    connect();
    return () => wsRef.current?.close();
  }, []);

  useEffect(() => {
    fetchAll();
    const t = setInterval(fetchAll, 5000);
    return () => clearInterval(t);
  }, [fetchAll]);

  const activeCount = live.active_people ?? 0;
  const prediction = live.queue_prediction ?? {};
  const topZone = heatmap.sort((a, b) => b.visits - a.visits)[0];

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#070b0f",
        color: "#fff",
        fontFamily: "'DM Sans', sans-serif",
        padding: "24px 28px",
      }}
    >
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=DM+Mono:wght@400;500;700&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }
        @keyframes pulse {
          0% { transform: scale(1); opacity: 1; }
          100% { transform: scale(3); opacity: 0; }
        }
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .card { animation: fadeIn 0.4s ease both; }
        .section-title {
          font-size: 10px; letter-spacing: 2.5px; text-transform: uppercase;
          color: rgba(255,255,255,0.3); margin-bottom: 14px; font-weight: 500;
        }
      `}</style>

      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 28,
          paddingBottom: 20,
          borderBottom: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span
              style={{ fontSize: 22, fontWeight: 700, letterSpacing: -0.5 }}
            >
              Neural<span style={{ color: "#00ff88" }}>Eye</span>
            </span>
            <span
              style={{
                background: "rgba(0,255,136,0.1)",
                color: "#00ff88",
                fontSize: 10,
                border: "1px solid rgba(0,255,136,0.3)",
                borderRadius: 20,
                padding: "2px 10px",
                letterSpacing: 1,
              }}
            >
              STORE INTELLIGENCE
            </span>
          </div>
          <div
            style={{
              color: "rgba(255,255,255,0.3)",
              fontSize: 12,
              marginTop: 4,
            }}
          >
            PUR_MUM_001 · cam_01 · cam_02
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Pulse color={wsStatus === "live" ? "#00ff88" : "#ff6348"} />
          <span
            style={{
              fontSize: 12,
              color: "rgba(255,255,255,0.4)",
              textTransform: "uppercase",
              letterSpacing: 1,
            }}
          >
            {wsStatus}
          </span>
        </div>
      </div>

      {/* Top KPIs */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 12,
          marginBottom: 20,
        }}
        className="card"
      >
        <StatCard
          label="Live in Store"
          value={activeCount}
          sub="people right now"
          accent="#00ff88"
          icon="👥"
        />
        <StatCard
          label="Checkout Queue"
          value={prediction.predicted_queue ?? "—"}
          sub={`trend: ${prediction.trend ?? "—"}`}
          accent={prediction.trend === "rising" ? "#ff6348" : "#ffd93d"}
          icon="🛒"
        />
        <StatCard
          label="Hottest Zone"
          value={topZone?.zone_id ?? "—"}
          sub={`${topZone?.visits ?? 0} visits`}
          accent="#ff6b9d"
          icon="🔥"
        />
        <StatCard
          label="Anomalies (1h)"
          value={anomalies.length}
          sub={anomalies.length > 0 ? "review alerts" : "all clear"}
          accent={anomalies.length > 0 ? "#ff6348" : "#4ecdc4"}
          icon="⚡"
        />
      </div>

      {/* Middle row */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1.4fr 1fr",
          gap: 12,
          marginBottom: 12,
        }}
      >
        {/* Traffic Chart */}
        <div
          className="card"
          style={{
            background: "rgba(255,255,255,0.02)",
            border: "1px solid rgba(255,255,255,0.07)",
            borderRadius: 16,
            padding: "20px 24px",
          }}
        >
          <div className="section-title">Footfall — Last 60 Minutes</div>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart
              data={traffic}
              margin={{ top: 0, right: 0, bottom: 0, left: -20 }}
            >
              <defs>
                <linearGradient id="tg" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#00ff88" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#00ff88" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="time"
                tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 10 }}
                tickFormatter={(v) => v?.slice(11, 16)}
              />
              <YAxis tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 10 }} />
              <Tooltip
                contentStyle={{
                  background: "#111",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                labelFormatter={(v) => v?.slice(11, 16)}
              />
              <Area
                type="monotone"
                dataKey="count"
                stroke="#00ff88"
                strokeWidth={2}
                fill="url(#tg)"
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Funnel */}
        <div
          className="card"
          style={{
            background: "rgba(255,255,255,0.02)",
            border: "1px solid rgba(255,255,255,0.07)",
            borderRadius: 16,
            padding: "20px 24px",
          }}
        >
          <div className="section-title">Conversion Funnel</div>
          <StoreFunnel data={funnel} />
        </div>
      </div>

      {/* Bottom row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {/* Heatmap */}
        <div
          className="card"
          style={{
            background: "rgba(255,255,255,0.02)",
            border: "1px solid rgba(255,255,255,0.07)",
            borderRadius: 16,
            padding: "20px 24px",
          }}
        >
          <div className="section-title">Zone Heatmap — Last Hour</div>
          <ZoneHeatmap data={heatmap} />
        </div>

        {/* Anomaly Feed */}
        <div
          className="card"
          style={{
            background: "rgba(255,255,255,0.02)",
            border: "1px solid rgba(255,255,255,0.07)",
            borderRadius: 16,
            padding: "20px 24px",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 14,
            }}
          >
            <div className="section-title" style={{ marginBottom: 0 }}>
              Anomaly Alerts
            </div>
            {alerts.length > 0 && <Pulse color="#ff6348" />}
          </div>
          <AlertFeed alerts={[...alerts, ...anomalies].slice(0, 8)} />
        </div>
      </div>
    </div>
  );
}
