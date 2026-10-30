import { FormEvent, useState } from "react";

type LoginPageProps = {
  onLogin: (userId: string, password: string) => Promise<void>;
  error: string;
  busy: boolean;
};

export default function LoginPage({ onLogin, error, busy }: LoginPageProps) {
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [demoAccount, setDemoAccount] = useState("");

  function selectDemoAccount(value: string) {
    setDemoAccount(value);
    setUserId(value);
    setPassword(value ? "MahiDemo-Only-2026!" : "");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onLogin(userId.trim(), password);
  }

  return (
    <main className="login-shell">
      <section className="login-card">
        <div className="login-brand">
          <div className="brand-mark">M</div>
          <div className="brand-text">
            <strong>MI FINS</strong>
            <small>Mahi Homes &amp; Finance CRM</small>
          </div>
        </div>
        
        <div className="login-header">
          <p className="eyebrow">STAFF WORKSPACE</p>
          <h1>Welcome back</h1>
          <p className="login-copy">Sign in with your staff credentials to manage enquiries and follow-ups.</p>
        </div>

        <form onSubmit={submit} className="login-form">
          {import.meta.env.DEV && (
            <div className="demo-accounts-box">
              <label htmlFor="demo-account">Quick Demo Accounts</label>
              <div className="demo-chip-group">
                <button
                  type="button"
                  className={`demo-chip ${demoAccount === "demo.manager" ? "active" : ""}`}
                  onClick={() => selectDemoAccount("demo.manager")}
                >
                  <span className="demo-chip-role">Manager</span>
                  <span className="demo-chip-name">demo.manager</span>
                </button>
                <button
                  type="button"
                  className={`demo-chip ${demoAccount === "demo.staff" ? "active" : ""}`}
                  onClick={() => selectDemoAccount("demo.staff")}
                >
                  <span className="demo-chip-role">Staff</span>
                  <span className="demo-chip-name">demo.staff</span>
                </button>
              </div>
              <p className="demo-account-note">Local test accounts with pre-configured access permissions.</p>
            </div>
          )}

          <div className="form-field">
            <label htmlFor="user-id">User ID</label>
            <input
              id="user-id"
              name="user_id"
              autoComplete="username"
              autoCapitalize="none"
              placeholder="e.g. demo.manager"
              required
              minLength={3}
              maxLength={50}
              value={userId}
              onChange={(event) => setUserId(event.target.value)}
            />
          </div>

          <div className="form-field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              placeholder="••••••••••••"
              required
              maxLength={128}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>

          {error && <p className="login-error" role="alert">{error}</p>}

          <button className="primary login-submit" type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in to workspace"}
          </button>
        </form>

        <p className="login-footnote">
          Need access or password reset? Contact your Workspace Manager.
        </p>
      </section>
    </main>
  );
}
