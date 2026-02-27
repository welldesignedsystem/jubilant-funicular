import { useState, useEffect, useCallback, useRef } from "react";

// ─── Config ─────────────────────────────────────────────────────────────────
const BASE    = "http://127.0.0.1:8000/api/v1";
const POLL_MS = 5000;

// ─── API ─────────────────────────────────────────────────────────────────────
async function get(path) {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${path}`);
  return (await r.json()).data;
}

// ─── Tokens ──────────────────────────────────────────────────────────────────
const T = {
  bg:       "#07090f",
  s1:       "#0c1220",
  s2:       "#101928",
  s3:       "#141f30",
  border:   "#1b2d45",
  border2:  "#0f1d2e",
  text:     "#c4d4e8",
  muted:    "#3f5670",
  dim:      "#1a2d44",
  cyan:     "#38bdf8",
  cyanBg:   "rgba(56,189,248,0.08)",
  green:    "#34d399",
  greenBg:  "rgba(52,211,153,0.08)",
  amber:    "#fbbf24",
  amberBg:  "rgba(251,191,36,0.08)",
  red:      "#f87171",
  redBg:    "rgba(248,113,113,0.08)",
  slate:    "#64748b",
  slateBg:  "rgba(100,116,139,0.06)",
};

const SMAP = {
  completed:   { color: T.green,  bg: T.greenBg,  label: "Completed"  },
  in_progress: { color: T.amber,  bg: T.amberBg,  label: "In Progress"},
  blocked:     { color: T.red,    bg: T.redBg,    label: "Blocked"    },
  not_started: { color: T.slate,  bg: T.slateBg,  label: "Not Started"},
};

const DEVMAP = {
  delayed:     { color: T.red,   label: "+delay"  },
  ahead:       { color: T.green, label: "ahead"   },
  on_baseline: { color: T.cyan,  label: "on track"},
};

// ─── Hooks ───────────────────────────────────────────────────────────────────
function usePolling(fetcher, interval = POLL_MS) {
  const [data, setData]     = useState(null);
  const [error, setError]   = useState(null);
  const [loading, setLoad]  = useState(true);
  const [lastAt, setLastAt] = useState(null);
  const timer = useRef(null);

  const run = useCallback(async () => {
    try {
      const d = await fetcher();
      setData(d);
      setError(null);
      setLastAt(new Date());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoad(false);
    }
  }, [fetcher]);

  useEffect(() => {
    run();
    timer.current = setInterval(run, interval);
    return () => clearInterval(timer.current);
  }, [run, interval]);

  return { data, error, loading, lastAt, refresh: run };
}

// ─── Shared UI ───────────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  const s = SMAP[status] || SMAP.not_started;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      padding: "2px 8px", borderRadius: 2, fontSize: 9,
      letterSpacing: "0.1em", textTransform: "uppercase", fontWeight: 700,
      background: s.bg, color: s.color, border: `1px solid ${s.color}30`,
    }}>
      <span style={{ width: 5, height: 5, borderRadius: "50%", background: s.color, flexShrink: 0 }} />
      {s.label}
    </span>
  );
}

function ProgressBar({ pct, status }) {
  const s = SMAP[status] || SMAP.not_started;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, height: 3, background: T.border, borderRadius: 2, minWidth: 60 }}>
        <div style={{ width: `${pct || 0}%`, height: "100%", background: s.color, borderRadius: 2, transition: "width 0.6s ease" }} />
      </div>
      <span style={{ fontSize: 10, color: s.color, minWidth: 28, textAlign: "right" }}>{Math.round(pct || 0)}%</span>
    </div>
  );
}

function Th({ children, style }) {
  return <th style={{ padding: "7px 12px", textAlign: "left", fontSize: 9, letterSpacing: "0.12em", textTransform: "uppercase", color: T.muted, borderBottom: `1px solid ${T.border}`, background: T.bg, whiteSpace: "nowrap", fontFamily: "inherit", ...style }}>{children}</th>;
}

function Td({ children, style }) {
  return <td style={{ padding: "9px 12px", borderBottom: `1px solid ${T.border2}`, verticalAlign: "middle", fontSize: 11, color: T.text, ...style }}>{children}</td>;
}

function Card({ children, style }) {
  return <div style={{ background: T.s1, border: `1px solid ${T.border}`, borderRadius: 3, overflow: "hidden", ...style }}>{children}</div>;
}

function SectionHead({ title, count, children }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 16px", background: T.s2, borderBottom: `1px solid ${T.border}` }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase", color: T.muted, fontWeight: 600 }}>{title}</span>
        {count != null && <span style={{ fontSize: 9, color: T.cyan, background: T.cyanBg, border: `1px solid ${T.cyan}30`, padding: "1px 6px", borderRadius: 10 }}>{count}</span>}
      </div>
      {children}
    </div>
  );
}

function PulseIndicator({ active }) {
  return (
    <span style={{ position: "relative", display: "inline-flex", alignItems: "center", gap: 5 }}>
      <span style={{
        width: 7, height: 7, borderRadius: "50%",
        background: active ? T.green : T.slate,
        boxShadow: active ? `0 0 0 0 ${T.green}` : "none",
        animation: active ? "pulse 2s infinite" : "none",
      }} />
      <span style={{ fontSize: 9, color: active ? T.green : T.muted, letterSpacing: "0.08em" }}>
        {active ? "LIVE" : "IDLE"}
      </span>
    </span>
  );
}

function LastRefresh({ at }) {
  if (!at) return null;
  return <span style={{ fontSize: 9, color: T.muted }}>Updated {at.toLocaleTimeString()}</span>;
}

function ErrorBanner({ msg }) {
  return (
    <div style={{ background: T.redBg, border: `1px solid ${T.red}40`, borderRadius: 3, padding: "8px 14px", fontSize: 11, color: T.red, marginBottom: 12 }}>
      ⚠ {msg}
    </div>
  );
}

function EmptyState({ msg }) {
  return <div style={{ padding: "28px 16px", textAlign: "center", color: T.muted, fontSize: 12, letterSpacing: "0.06em" }}>{msg}</div>;
}

// ─── Project Selector ────────────────────────────────────────────────────────
function ProjectSelector({ onSelect, selected }) {
  const { data, error, loading } = usePolling(useCallback(() => get("/projects"), []));
  if (loading) return <div style={{ color: T.muted, fontSize: 11, padding: 8 }}>Loading projects…</div>;
  if (error)   return <ErrorBanner msg={error} />;
  if (!data?.length) return <EmptyState msg="No projects found. Create one via POST /api/v1/projects" />;

  return (
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
      {data.map(p => (
        <button key={p.id} onClick={() => onSelect(p)} style={{
          padding: "8px 18px", border: `1px solid ${selected?.id === p.id ? T.cyan : T.border}`,
          background: selected?.id === p.id ? T.cyanBg : T.s2,
          color: selected?.id === p.id ? T.cyan : T.text,
          borderRadius: 3, cursor: "pointer", fontSize: 12,
          fontFamily: "inherit", letterSpacing: "0.04em", transition: "all 0.2s",
        }}>
          {p.name}
          <span style={{ fontSize: 9, color: T.muted, marginLeft: 8 }}>{p.vessel_type}</span>
        </button>
      ))}
    </div>
  );
}

// ─── KPI Bar ─────────────────────────────────────────────────────────────────
function KpiBar({ project }) {
  const pct = project?.overall_progress_pct ?? 0;
  const r = 20;
  const circ = 2 * Math.PI * r;
  const dash = circ * (pct / 100);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "auto 1fr 1fr 1fr 1fr", gap: 0, borderBottom: `1px solid ${T.border}` }}>
      {/* Ring */}
      <div style={{ padding: "14px 24px", borderRight: `1px solid ${T.border}`, display: "flex", alignItems: "center", gap: 14 }}>
        <svg width={48} height={48} viewBox="0 0 48 48">
          <circle cx={24} cy={24} r={r} fill="none" stroke={T.border} strokeWidth={4} />
          <circle cx={24} cy={24} r={r} fill="none" stroke={T.cyan} strokeWidth={4}
            strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
            transform="rotate(-90 24 24)" style={{ transition: "stroke-dasharray 0.8s ease" }} />
          <text x={24} y={28} textAnchor="middle" fill={T.text} fontSize={10} fontWeight={700} fontFamily="inherit">
            {Math.round(pct)}%
          </text>
        </svg>
        <div>
          <div style={{ fontSize: 9, color: T.muted, letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: 4 }}>Overall</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: T.cyan }}>{Math.round(pct)}<span style={{ fontSize: 11, color: T.muted }}>%</span></div>
        </div>
      </div>

      {[
        ["Planned Duration", `${project?.total_planned_duration_days ?? 0}`, "days"],
        ["Actual Duration",  `${project?.total_actual_duration_days ?? 0}`,  "days"],
        ["Baseline Duration",`${project?.total_baseline_duration_days ?? 0}`,"days"],
        ["Shipyard", project?.shipyard_name ?? "—", ""],
      ].map(([label, val, unit]) => (
        <div key={label} style={{ padding: "14px 20px", borderRight: `1px solid ${T.border}` }}>
          <div style={{ fontSize: 9, color: T.muted, letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: 6 }}>{label}</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: T.text }}>
            {val}<span style={{ fontSize: 11, color: T.muted, marginLeft: 4 }}>{unit}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Gantt Tab ────────────────────────────────────────────────────────────────
function GanttTab({ projectId }) {
  const [collapsed, setCollapsed] = useState({});
  const { data, error, loading, lastAt } = usePolling(
    useCallback(() => get(`/projects/${projectId}/gantt`), [projectId])
  );

  if (loading) return <div style={{ padding: 24, color: T.muted, fontSize: 12 }}>Fetching Gantt data…</div>;
  if (error)   return <ErrorBanner msg={error} />;

  const phases = data?.phases ?? [];

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 0 16px" }}>
        <div style={{ display: "flex", gap: 20 }}>
          {Object.entries(SMAP).map(([k, v]) => (
            <span key={k} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, color: T.muted }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: v.color }} />
              {v.label}
            </span>
          ))}
        </div>
        <LastRefresh at={lastAt} />
      </div>

      {phases.length === 0 && <EmptyState msg="No phases yet. Add phases via POST /api/v1/projects/{id}/phases" />}

      {phases.map((phase, pi) => (
        <Card key={phase.id} style={{ marginBottom: 12 }}>
          <div
            onClick={() => setCollapsed(c => ({ ...c, [phase.id]: !c[phase.id] }))}
            style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 14px", background: "linear-gradient(90deg, #0d2040, #0c1220)", cursor: "pointer", borderBottom: `1px solid ${T.border}` }}
          >
            <span style={{ color: T.cyan, fontSize: 10 }}>{collapsed[phase.id] ? "▶" : "▼"}</span>
            <span style={{ fontSize: 10, letterSpacing: "0.16em", textTransform: "uppercase", fontWeight: 700, color: T.cyan }}>
              PHASE {pi + 1}: {phase.name}
            </span>
            <span style={{ marginLeft: "auto" }}>
              <ProgressBar pct={phase.overall_progress_pct} status="in_progress" />
            </span>
          </div>

          {!collapsed[phase.id] && (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
              <thead>
                <tr>
                  <Th>#</Th>
                  <Th style={{ minWidth: 180 }}>Stage</Th>
                  <Th>Planned Start</Th>
                  <Th>Planned End</Th>
                  <Th>Actual Start</Th>
                  <Th>Actual End</Th>
                  <Th>Baseline Start</Th>
                  <Th>Baseline End</Th>
                  <Th>Pln Dur</Th>
                  <Th>Act Dur</Th>
                  <Th>Status</Th>
                  <Th>Progress</Th>
                  <Th>Deviation</Th>
                  <Th style={{ minWidth: 130 }}>Comments</Th>
                </tr>
              </thead>
              <tbody>
                {(phase.stages ?? []).map((s, i) => {
                  const dev = DEVMAP[s.deviation_status] ?? {};
                  return (
                    <tr key={s.id}
                      style={{ background: i % 2 === 0 ? T.s1 : T.bg }}
                      onMouseEnter={e => e.currentTarget.style.background = T.s3}
                      onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? T.s1 : T.bg}
                    >
                      <Td style={{ color: T.muted, fontSize: 10 }}>{s.order}</Td>
                      <Td style={{ fontWeight: 500 }}>{s.name}</Td>
                      <Td style={{ color: T.muted, fontFamily: "monospace" }}>{s.planned_start_date ?? "—"}</Td>
                      <Td style={{ color: T.muted, fontFamily: "monospace" }}>{s.planned_end_date ?? "—"}</Td>
                      <Td style={{ color: s.actual_start_date ? T.text : T.dim, fontFamily: "monospace" }}>{s.actual_start_date ?? "—"}</Td>
                      <Td style={{ color: s.actual_end_date   ? T.text : T.dim, fontFamily: "monospace" }}>{s.actual_end_date   ?? "—"}</Td>
                      <Td style={{ color: s.baseline_start_date ? T.cyan : T.dim, fontFamily: "monospace" }}>{s.baseline_start_date ?? "—"}</Td>
                      <Td style={{ color: s.baseline_end_date   ? T.cyan : T.dim, fontFamily: "monospace" }}>{s.baseline_end_date   ?? "—"}</Td>
                      <Td style={{ color: T.muted }}>{s.planned_duration_days != null ? `${s.planned_duration_days}d` : "—"}</Td>
                      <Td style={{ color: T.muted }}>{s.actual_duration_days  != null ? `${s.actual_duration_days}d`  : "—"}</Td>
                      <Td><StatusBadge status={s.status} /></Td>
                      <Td style={{ minWidth: 110 }}><ProgressBar pct={s.progress_pct} status={s.status} /></Td>
                      <Td>
                        {s.deviation_status ? (
                          <span style={{ fontSize: 9, fontWeight: 700, color: dev.color, background: `${dev.color}15`, padding: "2px 7px", borderRadius: 2, border: `1px solid ${dev.color}30` }}>
                            {s.deviation_days != null ? `${s.deviation_days > 0 ? "+" : ""}${s.deviation_days}d` : dev.label}
                          </span>
                        ) : <span style={{ color: T.dim }}>—</span>}
                      </Td>
                      <Td style={{ color: T.muted, fontSize: 10, fontStyle: "italic", maxWidth: 160 }}>{s.comments || "—"}</Td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Card>
      ))}
    </div>
  );
}

// ─── Baseline Tab ─────────────────────────────────────────────────────────────
function BaselineTab({ projectId }) {
  const { data: report, error: repErr, loading: repLoad, lastAt: repAt } =
    usePolling(useCallback(() => get(`/projects/${projectId}/baselines/report`), [projectId]));
  const { data: baselines, error: blErr, loading: blLoad } =
    usePolling(useCallback(() => get(`/projects/${projectId}/baselines`), [projectId]));

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>

      {/* Active Baseline */}
      <Card>
        <SectionHead title="Active Baseline">
          <LastRefresh at={repAt} />
        </SectionHead>
        {repLoad ? <EmptyState msg="Loading…" /> : repErr ? <ErrorBanner msg={repErr} /> : !report?.active_baseline ? (
          <EmptyState msg="No baseline set yet. Use POST /baselines/initial to set one." />
        ) : (
          <div style={{ padding: 16, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {[
              ["Status",    <span style={{ color: T.green, fontWeight: 700, fontSize: 10, letterSpacing: "0.1em", textTransform: "uppercase" }}>ACTIVE</span>],
              ["Version",   `v${report.active_baseline.version_number}`],
              ["Set At",    report.active_baseline.set_at ? new Date(report.active_baseline.set_at).toLocaleString() : "—"],
              ["Notes",     report.active_baseline.notes || "—"],
            ].map(([label, val]) => (
              <div key={label} style={{ background: T.s2, border: `1px solid ${T.border}`, borderRadius: 3, padding: "10px 14px" }}>
                <div style={{ fontSize: 8, color: T.muted, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: 4 }}>{label}</div>
                <div style={{ fontSize: 12, color: T.text }}>{val}</div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Baseline History */}
      <Card>
        <SectionHead title="Baseline Versions" count={baselines?.length} />
        {blLoad ? <EmptyState msg="Loading…" /> : blErr ? <ErrorBanner msg={blErr} /> : !baselines?.length ? (
          <EmptyState msg="No baseline history." />
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr><Th>#</Th><Th>Set At</Th><Th>Active</Th><Th>Notes</Th></tr></thead>
            <tbody>
              {baselines.map((b, i) => (
                <tr key={b.id} style={{ background: i % 2 === 0 ? T.s1 : T.bg }}>
                  <Td>v{b.version_number}</Td>
                  <Td style={{ fontFamily: "monospace", fontSize: 10 }}>{b.set_at ? new Date(b.set_at).toLocaleString() : "—"}</Td>
                  <Td>{b.is_active ? <span style={{ color: T.green, fontSize: 10, fontWeight: 700 }}>● ACTIVE</span> : <span style={{ color: T.muted, fontSize: 10 }}>—</span>}</Td>
                  <Td style={{ color: T.muted, fontSize: 10 }}>{b.notes || "—"}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {/* Deviation Summary */}
      <Card style={{ gridColumn: "1 / -1" }}>
        <SectionHead title="Stage Deviation vs Baseline" />
        {repLoad ? <EmptyState msg="Loading…" /> : repErr ? <ErrorBanner msg={repErr} /> : !report?.stage_deviations?.length ? (
          <EmptyState msg="Set a baseline first to see deviation data." />
        ) : (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 0, borderBottom: `1px solid ${T.border}` }}>
              {[
                ["On Baseline", report.deviation_summary?.on_baseline ?? 0, T.cyan],
                ["Ahead",       report.deviation_summary?.ahead       ?? 0, T.green],
                ["Delayed",     report.deviation_summary?.delayed      ?? 0, T.red],
              ].map(([label, count, color]) => (
                <div key={label} style={{ padding: "12px 20px", borderRight: `1px solid ${T.border}`, textAlign: "center" }}>
                  <div style={{ fontSize: 24, fontWeight: 700, color }}>{count}</div>
                  <div style={{ fontSize: 9, color: T.muted, letterSpacing: "0.1em", textTransform: "uppercase" }}>{label}</div>
                </div>
              ))}
            </div>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead><tr><Th>Stage</Th><Th>Baseline End</Th><Th>Planned End</Th><Th>Deviation</Th><Th>Status</Th></tr></thead>
              <tbody>
                {report.stage_deviations.map((d, i) => {
                  const dev = DEVMAP[d.deviation_status] ?? {};
                  return (
                    <tr key={d.stage_id} style={{ background: i % 2 === 0 ? T.s1 : T.bg }}>
                      <Td style={{ fontWeight: 500 }}>{d.stage_name}</Td>
                      <Td style={{ fontFamily: "monospace", color: T.muted }}>{d.baseline_end_date ?? "—"}</Td>
                      <Td style={{ fontFamily: "monospace", color: T.muted }}>{d.planned_end_date  ?? "—"}</Td>
                      <Td>
                        {d.deviation_days != null
                          ? <span style={{ color: dev.color, fontWeight: 700, fontSize: 10 }}>{d.deviation_days > 0 ? "+" : ""}{d.deviation_days}d</span>
                          : "—"}
                      </Td>
                      <Td>
                        {d.deviation_status
                          ? <span style={{ fontSize: 9, fontWeight: 700, color: dev.color, background: `${dev.color}15`, padding: "2px 8px", borderRadius: 2 }}>{dev.label}</span>
                          : "—"}
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </>
        )}
      </Card>
    </div>
  );
}

// ─── Audit Tab ────────────────────────────────────────────────────────────────
function AuditTab({ projectId }) {
  const { data, error, loading, lastAt } =
    usePolling(useCallback(() => get(`/projects/${projectId}/audit`), [projectId]));

  const entries = Array.isArray(data) ? data : [];

  return (
    <Card>
      <SectionHead title="Audit Trail" count={entries.length}>
        <LastRefresh at={lastAt} />
      </SectionHead>
      {loading ? <EmptyState msg="Loading…" /> : error ? <ErrorBanner msg={error} /> : !entries.length ? (
        <EmptyState msg="No audit entries yet. Approve a change request to generate entries." />
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <Th>#</Th><Th>Date</Th><Th>Changed By</Th><Th>Change Type</Th>
              <Th>Reason</Th><Th>Schedule Impact</Th><Th>Comments</Th><Th>Approved By</Th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e, i) => {
              const typeColors = { scope_change: T.red, delay: T.amber, initial_baseline: T.cyan, cost_change: T.green };
              const tc = typeColors[e.change_type] ?? T.slate;
              return (
                <tr key={e.id} style={{ background: i % 2 === 0 ? T.s1 : T.bg }}>
                  <Td style={{ color: T.muted }}>{e.sequence_number}</Td>
                  <Td style={{ fontFamily: "monospace", fontSize: 10, color: T.muted }}>{e.occurred_at ? new Date(e.occurred_at).toLocaleString() : "—"}</Td>
                  <Td>{e.changed_by_name ?? e.changed_by_id?.slice(0, 8) ?? "—"}</Td>
                  <Td>
                    <span style={{ fontSize: 9, fontWeight: 700, color: tc, background: `${tc}15`, padding: "2px 8px", borderRadius: 2, border: `1px solid ${tc}30`, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                      {(e.change_type ?? "").replace(/_/g, " ")}
                    </span>
                  </Td>
                  <Td style={{ color: T.muted, fontSize: 10, maxWidth: 200 }}>{e.reason || "—"}</Td>
                  <Td style={{ color: e.schedule_impact_days > 0 ? T.red : e.schedule_impact_days < 0 ? T.green : T.muted, fontWeight: 700 }}>
                    {e.schedule_impact_days != null ? `${e.schedule_impact_days > 0 ? "+" : ""}${e.schedule_impact_days}d` : "N/A"}
                  </Td>
                  <Td style={{ color: T.muted, fontSize: 10, fontStyle: "italic" }}>{e.stakeholder_comments || "—"}</Td>
                  <Td style={{ color: T.text }}>{e.approved_by_name ?? e.approved_by_id?.slice(0, 8) ?? "—"}</Td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Card>
  );
}

// ─── Change Requests Tab ──────────────────────────────────────────────────────
function ChangeRequestsTab({ projectId }) {
  const { data, error, loading, lastAt } =
    usePolling(useCallback(() => get(`/projects/${projectId}/change-requests`), [projectId]));

  const crs = Array.isArray(data) ? data : [];

  const crStatusColors = { pending: T.amber, approved: T.green, rejected: T.red };

  return (
    <Card>
      <SectionHead title="Change Requests" count={crs.length}>
        <LastRefresh at={lastAt} />
      </SectionHead>
      {loading ? <EmptyState msg="Loading…" /> : error ? <ErrorBanner msg={error} /> : !crs.length ? (
        <EmptyState msg="No change requests yet. Submit one via POST /change-requests." />
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <Th>Type</Th><Th>Reason</Th><Th>Schedule Impact</Th>
              <Th>Status</Th><Th>Submitted</Th><Th>Reviewer Comments</Th>
            </tr>
          </thead>
          <tbody>
            {crs.map((cr, i) => {
              const sc = crStatusColors[cr.status] ?? T.slate;
              return (
                <tr key={cr.id} style={{ background: i % 2 === 0 ? T.s1 : T.bg }}>
                  <Td>
                    <span style={{ fontSize: 9, fontWeight: 700, color: T.cyan, background: T.cyanBg, padding: "2px 8px", borderRadius: 2, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                      {(cr.change_type ?? "").replace(/_/g, " ")}
                    </span>
                  </Td>
                  <Td style={{ color: T.muted, fontSize: 10, maxWidth: 220 }}>{cr.reason}</Td>
                  <Td style={{ color: cr.schedule_impact_days > 0 ? T.red : cr.schedule_impact_days < 0 ? T.green : T.muted, fontWeight: 700 }}>
                    {cr.schedule_impact_days != null ? `${cr.schedule_impact_days > 0 ? "+" : ""}${cr.schedule_impact_days}d` : "—"}
                  </Td>
                  <Td>
                    <span style={{ fontSize: 9, fontWeight: 700, color: sc, background: `${sc}15`, padding: "2px 8px", borderRadius: 2, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                      {cr.status}
                    </span>
                  </Td>
                  <Td style={{ fontFamily: "monospace", fontSize: 10, color: T.muted }}>{cr.submitted_at ? new Date(cr.submitted_at).toLocaleString() : "—"}</Td>
                  <Td style={{ color: T.muted, fontSize: 10, fontStyle: "italic" }}>{cr.reviewer_comments || "—"}</Td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Card>
  );
}

// ─── Notifications Tab ────────────────────────────────────────────────────────
function NotificationsTab({ projectId }) {
  const { data, error, loading, lastAt } =
    usePolling(useCallback(() => get(`/projects/${projectId}/notifications`), [projectId]));

  const logs = Array.isArray(data) ? data : [];

  const ntColors = {
    baseline_set:                T.cyan,
    baseline_reset:              T.cyan,
    baseline_change:             T.amber,
    delay_notification:          T.red,
    stage_blocked:               T.red,
    change_request_submitted:    T.amber,
    change_request_approved:     T.green,
    change_request_rejected:     T.red,
  };

  return (
    <Card>
      <SectionHead title="Notification Log" count={logs.length}>
        <LastRefresh at={lastAt} />
      </SectionHead>
      {loading ? <EmptyState msg="Loading…" /> : error ? <ErrorBanner msg={error} /> : !logs.length ? (
        <EmptyState msg="No notifications yet. They are generated automatically on baseline/stage events." />
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr><Th>Date</Th><Th>Type</Th><Th>Stakeholder</Th><Th>Role</Th><Th>Comments</Th></tr>
          </thead>
          <tbody>
            {logs.map((n, i) => {
              const nc = ntColors[n.notification_type] ?? T.slate;
              return (
                <tr key={n.id} style={{ background: i % 2 === 0 ? T.s1 : T.bg }}>
                  <Td style={{ fontFamily: "monospace", fontSize: 10, color: T.muted }}>{n.notified_at ? new Date(n.notified_at).toLocaleString() : "—"}</Td>
                  <Td>
                    <span style={{ fontSize: 9, fontWeight: 700, color: nc, background: `${nc}15`, padding: "2px 8px", borderRadius: 2, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                      {(n.notification_type ?? "").replace(/_/g, " ")}
                    </span>
                  </Td>
                  <Td>{n.stakeholder_name ?? n.stakeholder_id?.slice(0, 8) ?? "—"}</Td>
                  <Td style={{ color: T.muted, fontSize: 10 }}>{(n.role_at_time_of_notification ?? "").replace(/_/g, " ")}</Td>
                  <Td style={{ color: T.muted, fontSize: 10, fontStyle: "italic" }}>{n.comments || "—"}</Td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Card>
  );
}

// ─── Stakeholders Tab ─────────────────────────────────────────────────────────
function StakeholdersTab({ projectId }) {
  const { data: all, error: allErr, loading: allLoad, lastAt } =
    usePolling(useCallback(() => get("/stakeholders"), []));
  const { data: proj, error: projErr, loading: projLoad } =
    usePolling(useCallback(() => get(`/projects/${projectId}/stakeholders`), [projectId]));

  const projStakeholders = Array.isArray(proj) ? proj : [];
  const allStakeholders  = Array.isArray(all)  ? all  : [];

  const projIds = new Set(projStakeholders.map(ps => ps.stakeholder_id));
  const enriched = projStakeholders.map(ps => ({
    ...ps,
    stakeholder: allStakeholders.find(s => s.id === ps.stakeholder_id),
  }));

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
      <Card>
        <SectionHead title="Project Team" count={enriched.length}>
          <LastRefresh at={lastAt} />
        </SectionHead>
        {(allLoad || projLoad) ? <EmptyState msg="Loading…" /> :
          (allErr || projErr) ? <ErrorBanner msg={allErr || projErr} /> :
          !enriched.length ? <EmptyState msg="No stakeholders assigned to this project." /> : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr><Th>Name</Th><Th>Email</Th><Th>Role</Th><Th>Assigned</Th></tr></thead>
            <tbody>
              {enriched.map((ps, i) => (
                <tr key={ps.id} style={{ background: i % 2 === 0 ? T.s1 : T.bg }}>
                  <Td style={{ fontWeight: 500 }}>{ps.stakeholder?.full_name ?? "—"}</Td>
                  <Td style={{ color: T.muted, fontSize: 10 }}>{ps.stakeholder?.email ?? "—"}</Td>
                  <Td>
                    <span style={{ fontSize: 9, color: T.cyan, background: T.cyanBg, padding: "2px 8px", borderRadius: 2, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                      {(ps.role ?? "").replace(/_/g, " ")}
                    </span>
                  </Td>
                  <Td style={{ fontFamily: "monospace", fontSize: 10, color: T.muted }}>{ps.assigned_at ? new Date(ps.assigned_at).toLocaleDateString() : "—"}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card>
        <SectionHead title="All System Stakeholders" count={allStakeholders.length} />
        {allLoad ? <EmptyState msg="Loading…" /> : allErr ? <ErrorBanner msg={allErr} /> : !allStakeholders.length ? (
          <EmptyState msg="No stakeholders in system yet." />
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr><Th>Name</Th><Th>Email</Th><Th>On Project</Th><Th>Active</Th></tr></thead>
            <tbody>
              {allStakeholders.map((s, i) => (
                <tr key={s.id} style={{ background: i % 2 === 0 ? T.s1 : T.bg }}>
                  <Td style={{ fontWeight: 500 }}>{s.full_name}</Td>
                  <Td style={{ color: T.muted, fontSize: 10 }}>{s.email}</Td>
                  <Td>{projIds.has(s.id) ? <span style={{ color: T.green, fontSize: 10, fontWeight: 700 }}>✓ YES</span> : <span style={{ color: T.muted, fontSize: 10 }}>—</span>}</Td>
                  <Td>{s.is_active ? <span style={{ color: T.green, fontSize: 10 }}>Active</span> : <span style={{ color: T.red, fontSize: 10 }}>Inactive</span>}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}

// ─── Phases Tab ───────────────────────────────────────────────────────────────
function PhasesTab({ projectId }) {
  const { data, error, loading, lastAt } =
    usePolling(useCallback(() => get(`/projects/${projectId}/phases`), [projectId]));
  const phases = Array.isArray(data) ? data : [];

  return (
    <Card>
      <SectionHead title="Phases" count={phases.length}>
        <LastRefresh at={lastAt} />
      </SectionHead>
      {loading ? <EmptyState msg="Loading…" /> : error ? <ErrorBanner msg={error} /> : !phases.length ? (
        <EmptyState msg="No phases configured." />
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr><Th>Order</Th><Th>Name</Th><Th>Description</Th><Th>Progress</Th><Th>Planned Start</Th><Th>Planned End</Th></tr></thead>
          <tbody>
            {phases.sort((a, b) => a.order - b.order).map((p, i) => (
              <tr key={p.id} style={{ background: i % 2 === 0 ? T.s1 : T.bg }}>
                <Td style={{ color: T.cyan, fontWeight: 700 }}>{p.order}</Td>
                <Td style={{ fontWeight: 500 }}>{p.name}</Td>
                <Td style={{ color: T.muted, fontSize: 10 }}>{p.description || "—"}</Td>
                <Td style={{ minWidth: 110 }}><ProgressBar pct={p.overall_progress_pct} status="in_progress" /></Td>
                <Td style={{ fontFamily: "monospace", color: T.muted }}>{p.planned_start_date ?? "—"}</Td>
                <Td style={{ fontFamily: "monospace", color: T.muted }}>{p.planned_end_date   ?? "—"}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

// ─── Dependencies Tab ─────────────────────────────────────────────────────────
function DepsTab({ projectId }) {
  const { data, error, loading, lastAt } =
    usePolling(useCallback(() => get(`/projects/${projectId}/stages/dependencies`), [projectId]));
  const deps = Array.isArray(data) ? data : [];

  return (
    <Card>
      <SectionHead title="Stage Dependencies" count={deps.length}>
        <LastRefresh at={lastAt} />
      </SectionHead>
      {loading ? <EmptyState msg="Loading…" /> : error ? <ErrorBanner msg={error} /> : !deps.length ? (
        <EmptyState msg="No dependencies configured." />
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr><Th>Predecessor Stage</Th><Th></Th><Th>Successor Stage</Th><Th>Type</Th><Th>Created</Th></tr></thead>
          <tbody>
            {deps.map((d, i) => (
              <tr key={d.id} style={{ background: i % 2 === 0 ? T.s1 : T.bg }}>
                <Td style={{ color: T.cyan, fontSize: 10, fontFamily: "monospace" }}>{d.predecessor_stage_id?.slice(0, 12)}…</Td>
                <Td style={{ color: T.muted, textAlign: "center" }}>→</Td>
                <Td style={{ color: T.cyan, fontSize: 10, fontFamily: "monospace" }}>{d.successor_stage_id?.slice(0, 12)}…</Td>
                <Td>
                  <span style={{ fontSize: 9, color: T.amber, background: T.amberBg, padding: "2px 8px", borderRadius: 2, textTransform: "uppercase" }}>
                    {(d.dependency_type ?? "").replace(/_/g, " ")}
                  </span>
                </Td>
                <Td style={{ fontFamily: "monospace", fontSize: 10, color: T.muted }}>{d.created_at ? new Date(d.created_at).toLocaleString() : "—"}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

// ─── Root App ─────────────────────────────────────────────────────────────────
const TABS = [
  { id: "gantt",    label: "▦ Gantt Chart"      },
  { id: "baseline", label: "◈ Baseline"          },
  { id: "changes",  label: "⊙ Change Requests"   },
  { id: "audit",    label: "◎ Audit Trail"       },
  { id: "notifs",   label: "◻ Notifications"     },
  { id: "people",   label: "◉ Stakeholders"      },
  { id: "phases",   label: "⊞ Phases"            },
  { id: "deps",     label: "→ Dependencies"      },
];

export default function App() {
  const [project, setProject] = useState(null);
  const [tab, setTab]         = useState("gantt");
  const [tick, setTick]       = useState(0);

  // Global 5-second tick indicator
  useEffect(() => {
    const t = setInterval(() => setTick(x => x + 1), POLL_MS);
    return () => clearInterval(t);
  }, []);

  const [countdown, setCountdown] = useState(POLL_MS / 1000);
  useEffect(() => {
    setCountdown(POLL_MS / 1000);
    const t = setInterval(() => setCountdown(c => c > 1 ? c - 1 : POLL_MS / 1000), 1000);
    return () => clearInterval(t);
  }, [tick]);

  return (
    <div style={{ fontFamily: "'IBM Plex Mono', 'Courier New', monospace", background: T.bg, minHeight: "100vh", color: T.text }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: ${T.bg}; }
        ::-webkit-scrollbar-thumb { background: ${T.border}; border-radius: 3px; }
        @keyframes pulse {
          0%   { box-shadow: 0 0 0 0 rgba(52,211,153,0.6); }
          70%  { box-shadow: 0 0 0 6px rgba(52,211,153,0); }
          100% { box-shadow: 0 0 0 0 rgba(52,211,153,0); }
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
      `}</style>

      {/* Header */}
      <div style={{ background: "linear-gradient(135deg, #0d1b30 0%, #07090f 70%)", borderBottom: `1px solid ${T.border}` }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 28px 0" }}>
          <div>
            <div style={{ fontSize: 9, letterSpacing: "0.2em", color: T.cyan, textTransform: "uppercase", marginBottom: 4 }}>
              Oceanic Shipyards Pvt Ltd
            </div>
            <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: "0.06em", color: T.text }}>
              HULL <span style={{ color: T.cyan }}>FABRICATION</span> & ASSEMBLY
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
            {/* Countdown */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, background: T.s2, border: `1px solid ${T.border}`, padding: "6px 14px", borderRadius: 3 }}>
              <svg width={14} height={14} viewBox="0 0 14 14" style={{ animation: "spin 5s linear infinite", flexShrink: 0 }}>
                <circle cx={7} cy={7} r={5.5} fill="none" stroke={T.border} strokeWidth={1.5} />
                <circle cx={7} cy={7} r={5.5} fill="none" stroke={T.cyan} strokeWidth={1.5}
                  strokeDasharray={`${2 * Math.PI * 5.5 * (1 - countdown / (POLL_MS / 1000))} ${2 * Math.PI * 5.5}`}
                  strokeLinecap="round" transform="rotate(-90 7 7)" />
              </svg>
              <span style={{ fontSize: 9, color: T.cyan, letterSpacing: "0.1em" }}>REFRESH IN {countdown}s</span>
            </div>
            <PulseIndicator active={true} />
          </div>
        </div>

        {/* Project selector */}
        <div style={{ padding: "12px 28px", borderTop: `1px solid ${T.border2}`, marginTop: 12 }}>
          <div style={{ fontSize: 9, color: T.muted, letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: 8 }}>Select Project</div>
          <ProjectSelector onSelect={setProject} selected={project} />
        </div>

        {/* KPIs */}
        {project && <KpiBar project={project} />}

        {/* Tabs */}
        {project && (
          <div style={{ display: "flex", padding: "0 28px", borderTop: `1px solid ${T.border2}` }}>
            {TABS.map(t => (
              <button key={t.id} onClick={() => setTab(t.id)} style={{
                padding: "10px 18px", border: "none", background: "none", cursor: "pointer",
                fontSize: 10, letterSpacing: "0.1em", textTransform: "uppercase", fontFamily: "inherit",
                color: tab === t.id ? T.cyan : T.muted,
                borderBottom: `2px solid ${tab === t.id ? T.cyan : "transparent"}`,
                marginBottom: -1, transition: "all 0.2s",
              }}>{t.label}</button>
            ))}
          </div>
        )}
      </div>

      {/* Content */}
      <div style={{ padding: "20px 28px", maxWidth: "100%", overflowX: "auto" }}>
        {!project ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: 300, gap: 14, color: T.muted }}>
            <div style={{ fontSize: 40, opacity: 0.15 }}>⚓</div>
            <div style={{ fontSize: 12, letterSpacing: "0.08em" }}>Select a project above to begin</div>
            <div style={{ fontSize: 10, color: T.dim }}>No projects? Create one via POST /api/v1/projects</div>
          </div>
        ) : (
          <>
            {tab === "gantt"    && <GanttTab           projectId={project.id} />}
            {tab === "baseline" && <BaselineTab         projectId={project.id} />}
            {tab === "changes"  && <ChangeRequestsTab   projectId={project.id} />}
            {tab === "audit"    && <AuditTab            projectId={project.id} />}
            {tab === "notifs"   && <NotificationsTab    projectId={project.id} />}
            {tab === "people"   && <StakeholdersTab     projectId={project.id} />}
            {tab === "phases"   && <PhasesTab           projectId={project.id} />}
            {tab === "deps"     && <DepsTab             projectId={project.id} />}
          </>
        )}
      </div>

      <div style={{ position: "fixed", bottom: 16, right: 20, fontSize: 60, opacity: 0.025, pointerEvents: "none" }}>⚓</div>
    </div>
  );
}
