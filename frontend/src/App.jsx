import React from 'react';
import { FaceLivenessDetector } from '@aws-amplify/ui-react-liveness';
import { Loader } from '@aws-amplify/ui-react';
import { AWS_REGION } from './amplifyConfig.js';
import {
  login,
  clearToken,
  createBoundSession,
  completeAttempt,
  searchByImage,
  enrollByImage,
  getStats,
  listUsers,
  deleteUser,
} from './api.js';

export default function App() {
  const [account, setAccount] = React.useState(null); // accountId once logged in
  const [stats, setStats] = React.useState(null);

  const refreshStats = React.useCallback(async () => {
    try {
      setStats(await getStats());
    } catch {
      setStats(null);
    }
  }, []);

  React.useEffect(() => {
    if (account) refreshStats();
  }, [account, refreshStats]);

  const onLogout = () => {
    clearToken();
    setAccount(null);
    setStats(null);
  };

  if (!account) {
    return <LoginScreen onLoggedIn={(acct) => setAccount(acct)} />;
  }

  return (
    <div style={S.page}>
      <header style={S.header}>
        <div>
          <h1 style={S.h1}>Rekognition Face Liveness + 1:N 查重 Demo</h1>
          <p style={S.sub}>
            流程：Token 鉴权 → 会话绑定 → 实时活体 → 1:N 查重 → 唯一则入库
          </p>
        </div>
        <div style={S.statBox}>
          <Stat label="Account" value={account} />
          <Stat label="Users" value={stats ? stats.userCount : '—'} />
          <Stat label="Faces" value={stats ? stats.faceCount : '—'} />
          <button style={S.btnGhost} onClick={onLogout}>登出</button>
        </div>
      </header>

      <div style={S.grid}>
        <LivenessPanel onChange={refreshStats} />
        <CollectionPanel onChange={refreshStats} />
      </div>

      <ManagePanel stats={stats} onChange={refreshStats} />

      <footer style={S.footer}>
        Collection: <code>{stats?.collectionId || '—'}</code> · 生物特征数据驻留于{' '}
        {AWS_REGION}，参考图/审计图保存在同区域 S3。
      </footer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Login screen — gate everything behind token auth
// ---------------------------------------------------------------------------
function LoginScreen({ onLoggedIn }) {
  const [token, setTokenInput] = React.useState('demo-token-alice');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const stats = await login(token.trim());
      onLoggedIn(stats.collectionId ? 'authenticated' : 'authenticated');
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={S.loginWrap}>
      <form style={S.loginCard} onSubmit={submit}>
        <h1 style={S.h1}>登录</h1>
        <p style={S.sub}>
          需要有效 Token 才能访问。Demo Token：<code>demo-token-alice</code> /{' '}
          <code>demo-token-bob</code> / <code>demo-token-carol</code>
        </p>
        <input
          style={S.loginInput}
          value={token}
          onChange={(e) => setTokenInput(e.target.value)}
          placeholder="Bearer token"
          autoFocus
        />
        <button style={{ ...S.btn, marginTop: 12 }} disabled={busy}>
          {busy ? '校验中…' : '登录'}
        </button>
        {error && <Banner tone="err">{error}</Banner>}
      </form>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div style={S.stat}>
      <div style={S.statLabel}>{label}</div>
      <div style={S.statValue}>{value}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Liveness panel
// ---------------------------------------------------------------------------
function LivenessPanel({ onChange }) {
  const [loading, setLoading] = React.useState(false);
  const [sessionId, setSessionId] = React.useState(null);
  const [attemptId, setAttemptId] = React.useState(null);
  const [result, setResult] = React.useState(null);
  const [error, setError] = React.useState(null);
  const handlingError = React.useRef(false);

  const start = async () => {
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const { sessionId, attemptId } = await createBoundSession();
      setSessionId(sessionId);
      setAttemptId(attemptId);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setLoading(false);
    }
  };

  const onAnalysisComplete = async () => {
    try {
      const data = await completeAttempt(attemptId, sessionId);
      setResult(data);
      onChange?.();
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setSessionId(null);
      setAttemptId(null);
    }
  };

  const onError = async (err) => {
    console.error('Liveness error:', err);
    if (handlingError.current) return;
    handlingError.current = true;
    setError(err?.state || String(err));
    setSessionId(null);
    setAttemptId(null);
    handlingError.current = false;
  };

  return (
    <section style={S.card}>
      <div style={S.cardHead}>
        <span style={S.stepNum}>1</span>
        <h2 style={S.h2}>实时活体检测</h2>
      </div>
      <p style={S.hint}>调起摄像头做活体挑战，通过后自动用参考图做 1:N 查重。</p>

      {!sessionId && (
        <button
          style={{ ...S.btn, ...(loading ? S.btnDisabled : {}) }}
          onClick={start}
          disabled={loading}
        >
          {loading ? '创建会话中…' : result ? '再测一次' : '开始活体检测'}
        </button>
      )}

      {loading && !sessionId && (
        <div style={S.center}>
          <Loader />
        </div>
      )}

      {sessionId && (
        <div style={S.detectorWrap}>
          <FaceLivenessDetector
            sessionId={sessionId}
            region={AWS_REGION}
            onAnalysisComplete={onAnalysisComplete}
            onError={onError}
          />
        </div>
      )}

      {error && <Banner tone="err">错误：{error}</Banner>}

      {result && (
        <div style={S.resultCard}>
          <div style={S.resultRow}>
            <Badge tone={result.isLive ? 'ok' : 'err'}>
              {result.isLive ? '活体通过' : '活体未通过'}
            </Badge>
            <span style={S.confText}>
              置信度 {result.livenessConfidence?.toFixed(2)}
            </span>
          </div>
          <Bar value={result.livenessConfidence} />

          {result.duplicate ? (
            <Banner tone="warn">
              ⚠️ 查重命中已存在用户 <code>{result.matches[0]?.userId}</code>（相似度{' '}
              {result.matches[0]?.similarity?.toFixed(2)}%）
            </Banner>
          ) : result.enrolledUserId ? (
            <Banner tone="ok">
              🆕 唯一用户，已入库 <code>{result.enrolledUserId}</code>
            </Banner>
          ) : null}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Collection panel: upload to enroll / 1:N search
// ---------------------------------------------------------------------------
function CollectionPanel({ onChange }) {
  return (
    <section style={S.card}>
      <div style={S.cardHead}>
        <span style={S.stepNum}>2</span>
        <h2 style={S.h2}>Collection 1:N 测试</h2>
      </div>
      <p style={S.hint}>用静态图片验证入库与 1:N 查重，无需摄像头。</p>

      <UploadTask
        title="入库 (先 1:N 查重，唯一才 IndexFaces)"
        action={enrollByImage}
        onDone={onChange}
        renderResult={(r) =>
          r.error ? (
            <Banner tone="err">{r.error}</Banner>
          ) : r.duplicate ? (
            <Banner tone="warn">
              ⚠️ 已存在用户 <code>{r.matches[0]?.userId}</code>（相似度{' '}
              {r.matches[0]?.similarity?.toFixed(2)}%），未重复入库。
            </Banner>
          ) : (
            <Banner tone="ok">
              🆕 已入库新用户 <code>{r.userId}</code>（faceId {short(r.faceId)}）
            </Banner>
          )
        }
      />

      <div style={S.divider} />

      <UploadTask
        title="1:N 查重 (SearchUsersByImage)"
        action={searchByImage}
        renderResult={(r) => {
          if (r.error) return <Banner tone="err">{r.error}</Banner>;
          if (!r.matched)
            return <Banner tone="muted">未匹配到任何用户（阈值 {r.threshold}%）。</Banner>;
          return (
            <div>
              <Banner tone="ok">命中 {r.matches.length} 个用户：</Banner>
              {r.matches.map((m) => (
                <div key={m.userId} style={S.matchRow}>
                  <code style={S.matchId}>{m.userId}</code>
                  <div style={S.matchBarWrap}>
                    <Bar value={m.similarity} />
                  </div>
                  <span style={S.matchPct}>{m.similarity.toFixed(2)}%</span>
                </div>
              ))}
            </div>
          );
        }}
      />
    </section>
  );
}

// A single upload task with preview + spinner + result rendering.
function UploadTask({ title, action, renderResult, onDone }) {
  const [preview, setPreview] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const [out, setOut] = React.useState(null);
  const [drag, setDrag] = React.useState(false);
  const inputRef = React.useRef(null);

  const handleFile = async (file) => {
    if (!file) return;
    setPreview(URL.createObjectURL(file));
    setBusy(true);
    setOut(null);
    try {
      const r = await action(file);
      setOut(r);
      onDone?.();
    } catch (err) {
      setOut({ error: String(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <label style={S.taskTitle}>{title}</label>
      <div
        style={{ ...S.drop, ...(drag ? S.dropActive : {}) }}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          handleFile(e.dataTransfer.files?.[0]);
        }}
      >
        {preview ? (
          <img src={preview} alt="preview" style={S.preview} />
        ) : (
          <span style={S.dropText}>点击或拖拽人脸图片到此处</span>
        )}
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          style={{ display: 'none' }}
          onChange={(e) => {
            handleFile(e.target.files?.[0]);
            e.target.value = '';
          }}
        />
      </div>
      {busy && (
        <div style={S.center}>
          <Loader />
        </div>
      )}
      {out && <div style={{ marginTop: 10 }}>{renderResult(out)}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Management panel: view / delete enrolled users
// ---------------------------------------------------------------------------
function ManagePanel({ stats, onChange }) {
  const [users, setUsers] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [deletingId, setDeletingId] = React.useState(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { users } = await listUsers();
      setUsers(users);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load, stats?.userCount]);

  const remove = async (userId) => {
    if (!window.confirm(`确认删除用户 ${userId} 及其人脸向量？此操作不可撤销。`)) return;
    setDeletingId(userId);
    setError(null);
    try {
      await deleteUser(userId);
      await load();
      onChange?.();
    } catch (e) {
      setError(String(e));
    } finally {
      setDeletingId(null);
    }
  };

  const removeAll = async () => {
    if (!window.confirm(`确认清空全部 ${users.length} 个用户？此操作不可撤销。`)) return;
    setError(null);
    for (const u of users) {
      setDeletingId(u.userId);
      try {
        await deleteUser(u.userId);
      } catch (e) {
        setError(String(e));
      }
    }
    setDeletingId(null);
    await load();
    onChange?.();
  };

  return (
    <section style={{ ...S.card, marginTop: 24 }}>
      <div style={S.cardHead}>
        <span style={S.stepNum}>3</span>
        <h2 style={S.h2}>已入库用户管理</h2>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button style={S.btnGhost} onClick={load} disabled={loading}>
            {loading ? '刷新中…' : '刷新'}
          </button>
          <button
            style={{ ...S.btnDanger, ...(users.length ? {} : S.btnDisabled) }}
            onClick={removeAll}
            disabled={!users.length || !!deletingId}
          >
            清空全部
          </button>
        </div>
      </div>
      <p style={S.hint}>反复测试会产生多个用户，可在此查看并清理。</p>

      {error && <Banner tone="err">{error}</Banner>}

      {!loading && users.length === 0 && (
        <Banner tone="muted">Collection 中暂无用户。</Banner>
      )}

      {users.length > 0 && (
        <table style={S.table}>
          <thead>
            <tr>
              <th style={S.th}>User ID</th>
              <th style={S.th}>状态</th>
              <th style={S.th}>关联人脸数</th>
              <th style={{ ...S.th, textAlign: 'right' }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.userId}>
                <td style={S.td}><code>{u.userId}</code></td>
                <td style={S.td}>
                  <Badge tone={u.status === 'ACTIVE' ? 'ok' : 'muted'}>
                    {u.status}
                  </Badge>
                </td>
                <td style={S.td}>{u.faceIds.length}</td>
                <td style={{ ...S.td, textAlign: 'right' }}>
                  <button
                    style={{ ...S.btnDangerSm, ...(deletingId === u.userId ? S.btnDisabled : {}) }}
                    onClick={() => remove(u.userId)}
                    disabled={!!deletingId}
                  >
                    {deletingId === u.userId ? '删除中…' : '删除'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

// ---- small presentational helpers ----
function Badge({ tone, children }) {
  return <span style={{ ...S.badge, ...toneStyles[tone] }}>{children}</span>;
}
function Banner({ tone, children }) {
  return <div style={{ ...S.banner, ...toneStyles[tone] }}>{children}</div>;
}
function Bar({ value = 0 }) {
  const v = Math.max(0, Math.min(100, value));
  const color = v >= 90 ? '#087443' : v >= 70 ? '#b26a00' : '#c0392b';
  return (
    <div style={S.barTrack}>
      <div style={{ ...S.barFill, width: `${v}%`, background: color }} />
    </div>
  );
}
const short = (s) => (s ? `${s.slice(0, 8)}…` : '');

const toneStyles = {
  ok: { background: '#e6f4ea', color: '#087443', borderColor: '#9ad2ae' },
  warn: { background: '#fff4e0', color: '#b26a00', borderColor: '#f0c88a' },
  err: { background: '#fdecea', color: '#c0392b', borderColor: '#f0a9a2' },
  muted: { background: '#f1f3f5', color: '#555', borderColor: '#dde1e5' },
};

const S = {
  page: { maxWidth: 1120, margin: '0 auto', padding: 24, fontFamily: 'system-ui, -apple-system, sans-serif', color: '#1a1a1a' },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 24, flexWrap: 'wrap', paddingBottom: 16, borderBottom: '2px solid #232f3e' },
  h1: { fontSize: 24, margin: '0 0 6px' },
  sub: { color: '#555', margin: 0, fontSize: 14 },
  statBox: { display: 'flex', gap: 12 },
  stat: { background: '#232f3e', color: '#fff', borderRadius: 10, padding: '8px 16px', minWidth: 72, textAlign: 'center' },
  statLabel: { fontSize: 11, opacity: 0.7, textTransform: 'uppercase', letterSpacing: 0.5 },
  statValue: { fontSize: 18, fontWeight: 700 },
  grid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginTop: 24 },
  card: { border: '1px solid #e3e6ea', borderRadius: 14, padding: 22, background: '#fff', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' },
  cardHead: { display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 },
  stepNum: { display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 26, height: 26, borderRadius: '50%', background: '#ff9900', color: '#111', fontWeight: 700, fontSize: 14 },
  h2: { fontSize: 18, margin: 0 },
  hint: { color: '#666', fontSize: 13, margin: '4px 0 16px' },
  btn: { padding: '11px 20px', fontSize: 15, fontWeight: 600, borderRadius: 8, border: 'none', background: '#ff9900', color: '#111', cursor: 'pointer', transition: 'opacity .15s' },
  btnDisabled: { opacity: 0.5, cursor: 'not-allowed' },
  btnGhost: { padding: '6px 14px', fontSize: 13, fontWeight: 600, borderRadius: 7, border: '1px solid #c7ccd1', background: '#fff', color: '#333', cursor: 'pointer' },
  btnDanger: { padding: '6px 14px', fontSize: 13, fontWeight: 600, borderRadius: 7, border: '1px solid #e0a9a2', background: '#fdecea', color: '#c0392b', cursor: 'pointer' },
  btnDangerSm: { padding: '5px 12px', fontSize: 12, fontWeight: 600, borderRadius: 6, border: '1px solid #e0a9a2', background: '#fdecea', color: '#c0392b', cursor: 'pointer' },
  table: { width: '100%', borderCollapse: 'collapse', marginTop: 12, fontSize: 14 },
  th: { textAlign: 'left', padding: '8px 10px', borderBottom: '2px solid #e3e6ea', color: '#555', fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.4 },
  td: { padding: '10px', borderBottom: '1px solid #eef0f2', verticalAlign: 'middle' },
  center: { display: 'flex', justifyContent: 'center', padding: 16 },
  detectorWrap: { marginTop: 12 },
  resultCard: { marginTop: 16, padding: 16, background: '#fafbfc', border: '1px solid #e3e6ea', borderRadius: 10 },
  resultRow: { display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 },
  confText: { color: '#333', fontSize: 14, fontWeight: 600 },
  badge: { display: 'inline-block', padding: '3px 12px', borderRadius: 999, fontSize: 13, fontWeight: 700, border: '1px solid' },
  banner: { padding: '10px 14px', borderRadius: 8, fontSize: 14, border: '1px solid', marginTop: 8 },
  barTrack: { height: 8, borderRadius: 999, background: '#e9ecef', overflow: 'hidden' },
  barFill: { height: '100%', borderRadius: 999, transition: 'width .3s' },
  taskTitle: { display: 'block', fontWeight: 600, fontSize: 14, marginBottom: 8 },
  drop: { border: '2px dashed #c7ccd1', borderRadius: 10, padding: 16, textAlign: 'center', cursor: 'pointer', background: '#fafbfc', transition: 'all .15s', minHeight: 96, display: 'flex', alignItems: 'center', justifyContent: 'center' },
  dropActive: { borderColor: '#ff9900', background: '#fff7e6' },
  dropText: { color: '#888', fontSize: 13 },
  preview: { maxHeight: 140, maxWidth: '100%', borderRadius: 8 },
  divider: { height: 1, background: '#eef0f2', margin: '20px 0' },
  matchRow: { display: 'flex', alignItems: 'center', gap: 10, marginTop: 8 },
  matchId: { fontSize: 12, minWidth: 130 },
  matchBarWrap: { flex: 1 },
  matchPct: { fontSize: 13, fontWeight: 700, minWidth: 64, textAlign: 'right' },
  footer: { marginTop: 28, paddingTop: 14, borderTop: '1px solid #eef0f2', color: '#888', fontSize: 12 },
  loginWrap: { minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'system-ui, -apple-system, sans-serif', background: '#f5f7fa' },
  loginCard: { background: '#fff', border: '1px solid #e3e6ea', borderRadius: 14, padding: 32, width: 420, boxShadow: '0 2px 10px rgba(0,0,0,0.08)' },
  loginInput: { width: '100%', padding: '10px 12px', fontSize: 14, borderRadius: 8, border: '1px solid #c7ccd1', boxSizing: 'border-box' },
};
