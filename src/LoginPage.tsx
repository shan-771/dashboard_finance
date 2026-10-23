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
          <span className="brand-mark">M</span>
          <span><strong>MI FINS</strong><small>Mahi Homes &amp; Finance</small></span>
        </div>
        <p className="eyebrow">STAFF WORKSPACE</p>
        <h1>Welcome back</h1>
        <p className="login-copy">Sign in with the User ID and password provided by your Manager.</p>
        <form onSubmit={submit}>
          {import.meta.env.DEV && (
            <>
              <label htmlFor="demo-account">Development demo account</label>
              <select
                id="demo-account"
                value={demoAccount}
                onChange={(event) => selectDemoAccount(event.target.value)}
              >
                <option value="">Choose an account</option>
                <option value="demo.manager">Demo Manager</option>
                <option value="demo.staff">Demo Staff</option>
              </select>
              <p className="demo-account-note">Local development only. Seed these accounts with <code>python -m app.cli create-demo-accounts</code>.</p>
            </>
          )}
          <label htmlFor="user-id">User ID</label>
          <input
            id="user-id"
            name="user_id"
            autoComplete="username"
            autoCapitalize="none"
            required
            minLength={3}
            maxLength={50}
            value={userId}
            onChange={(event) => setUserId(event.target.value)}
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            maxLength={128}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          {error && <p className="login-error" role="alert">{error}</p>}
          <button className="primary login-submit" type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="login-footnote">Need access? Ask your Manager to create a staff account.</p>
      </section>
    </main>
  );
}
