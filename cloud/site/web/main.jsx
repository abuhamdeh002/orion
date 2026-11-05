import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./site.css";

const path = location.pathname;
const page = path.startsWith("/admin") ? "admin" : path.startsWith("/app") ? "portal" : path.startsWith("/privacy") || path.startsWith("/terms") || path.startsWith("/refunds") ? "policy" : "landing";

function Nav() {
  return (
    <header className="nav">
      <a className="mark" href="/">ORION</a>
      <nav>
        <a href="#product">Product</a>
        <a href="#pricing">Pricing</a>
        <a href="#questions">Questions</a>
        <a href="/app">Portal</a>
        <a className="btn" href="/admin">Admin</a>
      </nav>
    </header>
  );
}

const LINES = [
  ["orion", "Yeah?"],
  ["you", "Open the calendar."],
  ["orion", "Outlook is open. Google Calendar is not signed in on this PC."],
  ["you", "What's 12 times 12?"],
  ["orion", "That's 144."],
];

function LiveDeck() {
  const [cursor, setCursor] = useState(0);
  const [clock, setClock] = useState("");
  useEffect(() => {
    const tick = setInterval(() => setCursor((value) => (value + 1) % LINES.length), 1800);
    const time = setInterval(() => setClock(new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })), 1000);
    setClock(new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }));
    return () => { clearInterval(tick); clearInterval(time); };
  }, []);
  const visible = [0, 1, 2].map((offset) => LINES[(cursor + offset) % LINES.length]);
  return (
    <div className="deck">
      <div className="deck-top"><span className="pulse" /> Listening <span>{clock}</span></div>
      <div className="stage">
        <span className="ring r1" />
        <span className="ring r2" />
        <span className="ring r3" />
        <div className="orb" />
      </div>
      <div className="thread">
        {visible.map(([who, text]) => <div className={`bubble ${who}`} key={text}>{text}</div>)}
      </div>
    </div>
  );
}

function Landing() {
  const [email, setEmail] = useState("");
  const [note, setNote] = useState("");
  useEffect(() => {
    const nodes = document.querySelectorAll(".reveal");
    const seen = new IntersectionObserver((entries) => {
      entries.forEach((entry) => { if (entry.isIntersecting) entry.target.classList.add("in"); });
    }, { threshold: 0.18 });
    nodes.forEach((node) => seen.observe(node));
    return () => seen.disconnect();
  }, []);
  async function buy(plan) {
    setNote("Checkout needs a Stripe price and secret key on the site worker. Until then, issue a license from the admin dashboard.");
    const response = await fetch("/api/checkout", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plan, email }) }).catch(() => null);
    const body = response ? await response.json().catch(() => ({})) : {};
    if (body.url) location.href = body.url;
  }
  return (
    <>
      <Nav />
      <section className="hero">
        <div>
          <div className="kicker">Windows agent · Android companion</div>
          <h1>Speak to the PC. Take it with you.</h1>
          <p className="lede">ORION stays on your machine, answers in a calm voice, and lets a paired phone open apps, hear reminders, and reach the PC when you leave the house.</p>
          <div className="row">
            <a className="btn" href="#pricing">See pricing</a>
            <a className="ghost" href="/app">Open the portal</a>
          </div>
          <div className="stats">
            <div><b>On the PC</b><span>Voice, apps, music, calendar</span></div>
            <div><b>On the phone</b><span>Talk, screenshot, lock</span></div>
            <div><b>PIN</b><span>Shutdown still asks first</span></div>
          </div>
        </div>
        <LiveDeck />
      </section>
      <section className="band" id="product">
        <div className="split">
          <div>
            <div className="kicker">How it runs</div>
            <h2>Three places. One voice.</h2>
            <ol className="steps">
              <li><b>The PC</b><span>ORION listens in the room and does the simple things immediately.</span></li>
              <li><b>The phone</b><span>Hold to talk. The same voice answers. The side key on a Samsung can open it.</span></li>
              <li><b>Away from home</b><span>Cloud carries the connection. The words stay on the machine.</span></li>
            </ol>
          </div>
          <div className="phone" aria-hidden="true">
            <div className="phone-bar"><span /> ORION</div>
            <p className="phone-status">PC online</p>
            <div className="bubble">Yeah?</div>
            <div className="bubble you">Lock the machine.</div>
            <div className="bubble">Locked.</div>
            <div className="hold">Hold to talk</div>
          </div>
        </div>
        <div className="grid" style={{ marginTop: 28 }}>
          <article className="card"><h3>Voice on the PC</h3><p>Wake it, ask for the time, the weather, an app, or the music. The simple requests never wait on a model.</p></article>
          <article className="card"><h3>The phone</h3><p>Hold to talk, see a screenshot, lock the machine, and get the briefing when you are away from the desk.</p></article>
          <article className="card"><h3>Yours</h3><p>The conversation stays on the PC. The relay only carries the live connection. Shutdown still asks for the PIN.</p></article>
        </div>
      </section>
      <section className="band reveal" id="pricing">
        <h2>Pricing</h2>
        <div className="form">
          <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Email for the license" />
        </div>
        <div className="grid">
          <article className="price"><span className="kicker">Once</span><strong>Lifetime</strong><p>The PC agent and phone use on your own Wi-Fi.</p><button className="btn" onClick={() => buy("lifetime")}>Buy lifetime</button></article>
          <article className="price featured"><span className="kicker">Monthly</span><strong>Cloud</strong><p>Reach the PC from anywhere. Notifications follow the phone.</p><button className="btn" onClick={() => buy("cloud")}>Start Cloud</button></article>
          <article className="price"><span className="kicker">Both</span><strong>Bundle</strong><p>Lifetime on the PC, Cloud for the road.</p><button className="ghost" onClick={() => buy("bundle")}>Buy the bundle</button></article>
        </div>
        <p className="err">{note}</p>
      </section>
      <section className="band reveal" id="questions">
        <h2>Questions</h2>
        <details open><summary>Does Cloud see what I say?</summary><p>No. The relay forwards the live session. Chat is not stored in the admin dashboard.</p></details>
        <details><summary>Why is the Android app not on the Play Store?</summary><p>Play rejects the call and SMS access this version uses. The portal serves a signed APK.</p></details>
        <details><summary>What if I only want the PC?</summary><p>Lifetime is enough. Cloud is only the path from outside your network.</p></details>
      </section>
      <footer className="foot">
        <span>ORION</span>
        <span><a href="/privacy">Privacy</a> · <a href="/terms">Terms</a> · <a href="/refunds">Refunds</a> · <a href="/admin">Admin</a></span>
      </footer>
    </>
  );
}

function Portal() {
  const [email, setEmail] = useState("");
  const [record, setRecord] = useState(null);
  const [miss, setMiss] = useState("");
  // After checkout Stripe sends the buyer here with ?session_id=cs_..., which is what unlocks the key.
  const session = new URLSearchParams(window.location.search).get("session_id");
  async function fetchRecord(query) {
    setMiss("");
    const response = await fetch(`/api/portal?${query}`);
    const body = await response.json();
    if (!body.found) {
      setRecord(null);
      setMiss(body.error || "No active license found.");
      return;
    }
    setRecord(body);
  }
  useEffect(() => {
    if (session) fetchRecord(`session_id=${encodeURIComponent(session)}`);
  }, [session]);
  async function look(event) {
    event.preventDefault();
    await fetchRecord(`email=${encodeURIComponent(email)}`);
  }
  return (
    <>
      <Nav />
      <section className="band">
        <div className="kicker">Customer</div>
        <h1>Your copy</h1>
        <form className="form" onSubmit={look}>
          <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Email on the license" />
          <button className="btn" type="submit">Look up</button>
        </form>
        <p className="err">{miss}</p>
        {record && (
          <article className="card">
            <span className="pill">{record.plan}</span>
            <p>Cloud {record.cloud ? "on" : "off"} · {record.devices.length} device{record.devices.length === 1 ? "" : "s"}</p>
            <p className="key">{record.license}</p>
          </article>
        )}
        <div className="grid" style={{ marginTop: 22 }}>
          <article className="card"><h3>Windows</h3><p>Run <span className="key">dist\ORION\ORION.exe</span>. First launch asks for the key. No key means a 14-day trial.</p><a className="ghost" href="http://127.0.0.1:8765/">Open the PC deck</a></article>
          <article className="card"><h3>Android</h3><p>The S24 Ultra project is in <span className="key">android/</span>. It needs Android Studio before there is an APK to install.</p></article>
          <article className="card"><h3>Side key</h3><p>On the Samsung: Settings, Advanced features, Side key, double press, open ORION.</p></article>
        </div>
      </section>
    </>
  );
}

function Policy() {
  const kind = path.replace("/", "");
  const copy = {
    privacy: "ORION stores the license, the device name, and the billing email. It does not store chat in the cloud. The relay keeps the last 50 notifications so a phone can catch up. Revoke a device from the admin dashboard.",
    terms: "A lifetime license is for the household's PCs. Cloud is the monthly remote connection. Shutdown and sending a message still require the confirmation already built into the agent.",
    refunds: "A lifetime purchase can be refunded within 14 days. Cloud cancels at the end of the period already paid.",
  };
  return <><Nav /><section className="band"><h1>{kind}</h1><p className="lede">{copy[kind]}</p></section></>;
}

function Admin() {
  const [token, setToken] = useState(sessionStorage.getItem("orion-admin") || "");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [needsSetup, setNeedsSetup] = useState(false);
  const [state, setState] = useState(null);
  const [tab, setTab] = useState("overview");

  async function api(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...(options.headers || {}) },
    });
    const body = await response.json();
    if (response.status === 401 && body.locked) {
      sessionStorage.removeItem("orion-admin");
      setToken("");
    }
    return body;
  }

  async function load(current = token) {
    const response = await fetch("/api/admin/state", { headers: { Authorization: `Bearer ${current}` } });
    const body = await response.json();
    if (body.needsSetup) setNeedsSetup(true);
    if (response.ok) setState(body);
  }

  useEffect(() => { load(); }, []);

  async function unlock(event) {
    event.preventDefault();
    const body = await api("/api/admin/session", { method: "POST", body: JSON.stringify({ pin }) });
    if (!body.ok) { setError(body.error || "Could not unlock."); return; }
    sessionStorage.setItem("orion-admin", body.token);
    setToken(body.token);
    setNeedsSetup(false);
    setState(body);
  }

  if (!token) {
    return (
      <div className="lock">
        <form onSubmit={unlock}>
          <div className="kicker">ORION</div>
          <h2>{needsSetup ? "Set the admin PIN" : "Admin"}</h2>
          <p className="lede">{needsSetup ? "This PIN stays on this PC. It is not a customer password." : "Enter the PIN for this machine."}</p>
          <input type="password" value={pin} onChange={(event) => setPin(event.target.value)} placeholder="PIN" />
          <div className="row"><button className="btn" type="submit">{needsSetup ? "Create PIN" : "Unlock"}</button></div>
          <p className="err">{error}</p>
        </form>
      </div>
    );
  }

  if (!state) return <p className="band">Loading the dashboard…</p>;
  return (
    <div className="shell">
      <aside className="side">
        <div className="mark">ORION</div>
        {["overview", "customers", "devices", "flags", "notes", "audit"].map((item) => (
          <button key={item} className={tab === item ? "on" : ""} onClick={() => setTab(item)}>{item}</button>
        ))}
        <a href="/">Site</a>
      </aside>
      <main className="main">
        <div className="pane" key={tab}>
        {tab === "overview" && <Overview state={state} />}
        {tab === "customers" && <Customers state={state} api={api} reload={() => load(token)} />}
        {tab === "devices" && <Devices state={state} api={api} reload={() => load(token)} />}
        {tab === "flags" && <Flags state={state} api={api} reload={() => load(token)} />}
        {tab === "notes" && <Notes state={state} api={api} reload={() => load(token)} />}
        {tab === "audit" && <Audit state={state} />}
        </div>
      </main>
    </div>
  );
}

function Overview({ state }) {
  const cards = [
    ["Customers", state.metrics.customers],
    ["Active", state.metrics.active],
    ["Lifetime", state.metrics.lifetime],
    ["Cloud MRR", `$${state.metrics.mrr}`],
    ["Recorded revenue", `$${state.metrics.revenue}`],
    ["Devices", state.devices.length],
  ];
  return (
    <>
      <h2>Overview</h2>
      <div className="split">
        <div className="metrics">
          {cards.map(([label, value]) => <article className="card metric" key={label}><span className="kicker">{label}</span><b>{value}</b></article>)}
        </div>
        <article className="card agent">
          <span className="kicker">This PC</span>
          <h3 className={state.health?.online ? "ok" : "bad"}>{state.health?.online ? "Agent online" : "Agent offline"}</h3>
          <p>{state.health?.online ? `${state.health.provider}. License: ${state.health.license}.` : "Nothing is answering on port 8765."}</p>
          <a className="ghost" href="http://127.0.0.1:8765/">Open the deck</a>
        </article>
      </div>
      <h3>Recent activity</h3>
      {state.audit.length === 0 ? <p className="empty">Nothing has happened yet. Issue a license under Customers.</p> : (
        <table><tbody>{state.audit.slice(0, 6).map((item, index) => <tr key={index}><td>{item.at.slice(11, 19)}</td><td>{item.action.replaceAll("_", " ")}</td><td>{item.detail}</td></tr>)}</tbody></table>
      )}
    </>
  );
}

function Customers({ state, api, reload }) {
  const [email, setEmail] = useState("");
  const [plan, setPlan] = useState("lifetime");
  const [amount, setAmount] = useState("149");
  const [error, setError] = useState("");
  async function add(event) {
    event.preventDefault();
    const body = await api("/api/admin/customers", { method: "POST", body: JSON.stringify({ email, plan, amount: Number(amount), monthly: plan === "lifetime" ? 0 : 12 }) });
    if (!body.ok) { setError(body.error); return; }
    setEmail("");
    setError("");
    reload();
  }
  return (
    <>
      <h2>Customers</h2>
      <form className="form" onSubmit={add}>
        <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="email" />
        <select value={plan} onChange={(event) => setPlan(event.target.value)}><option>lifetime</option><option>cloud</option><option>bundle</option></select>
        <input value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="amount" />
        <button className="btn" type="submit">Issue license</button>
      </form>
      <p className="err">{error}</p>
      <table>
        <thead><tr><th>Email</th><th>Plan</th><th>Status</th><th>License</th><th></th></tr></thead>
        <tbody>
          {state.customers.map((item) => (
            <tr key={item.id}>
              <td>{item.email}</td>
              <td><span className="pill">{item.plan}</span></td>
              <td className={item.status === "active" ? "ok" : "bad"}>{item.status}</td>
              <td className="key">{item.license || "revoked"}</td>
              <td>
                <button className="ghost" onClick={async () => { await api(`/api/admin/customers/${item.id}/extend`, { method: "POST", body: JSON.stringify({ days: 30 }) }); reload(); }}>Extend 30d</button>
                <button className="ghost" onClick={async () => { await api(`/api/admin/customers/${item.id}/revoke`, { method: "POST", body: "{}" }); reload(); }}>Revoke</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {state.customers.length === 0 && <p className="empty">No customers yet. Type an email above and issue a license.</p>}
    </>
  );
}

function Devices({ state, api, reload }) {
  const [customer, setCustomer] = useState(state.customers[0]?.id || "");
  const [name, setName] = useState("S24 Ultra");
  return (
    <>
      <h2>Devices</h2>
      <form className="form" onSubmit={async (event) => { event.preventDefault(); await api("/api/admin/devices", { method: "POST", body: JSON.stringify({ customer, name, kind: "phone" }) }); reload(); }}>
        <select value={customer} onChange={(event) => setCustomer(event.target.value)}>
          {state.customers.map((item) => <option key={item.id} value={item.id}>{item.email}</option>)}
        </select>
        <input value={name} onChange={(event) => setName(event.target.value)} />
        <button className="btn" type="submit">Pair device</button>
      </form>
      <table>
        <tbody>
          {state.devices.map((item) => (
            <tr key={item.id}>
              <td>{item.name}</td><td>{item.email}</td><td className={item.revoked ? "bad" : "ok"}>{item.revoked ? "revoked" : "active"}</td>
              <td><button className="ghost" onClick={async () => { await api(`/api/admin/devices/${item.id}/revoke`, { method: "POST", body: "{}" }); reload(); }}>Revoke</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      {state.customers.length === 0 && <p className="empty">Add a customer before pairing a phone.</p>}
      {state.devices.length === 0 && state.customers.length > 0 && <p className="empty">No phones paired yet.</p>}
    </>
  );
}

function Flags({ state, api, reload }) {
  return (
    <>
      <h2>Flags</h2>
      {Object.entries(state.flags).map(([name, enabled]) => (
        <p key={name}><button className="ghost" onClick={async () => { await api("/api/admin/flags", { method: "POST", body: JSON.stringify({ name, enabled: !enabled }) }); reload(); }}>{enabled ? "On" : "Off"}</button> {name}</p>
      ))}
    </>
  );
}

function Notes({ state, api, reload }) {
  const [customer, setCustomer] = useState(state.customers[0]?.id || "");
  const [text, setText] = useState("");
  return (
    <>
      <h2>Notes</h2>
      <form className="form" onSubmit={async (event) => { event.preventDefault(); await api(`/api/admin/customers/${customer}/note`, { method: "POST", body: JSON.stringify({ text }) }); setText(""); reload(); }}>
        <select value={customer} onChange={(event) => setCustomer(event.target.value)}>{state.customers.map((item) => <option key={item.id} value={item.id}>{item.email}</option>)}</select>
        <textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="Support note. Not a chat transcript." />
        <button className="btn" type="submit">Save note</button>
      </form>
      {state.notes.length === 0 && <p className="empty">No notes. These are support notes, not conversations.</p>}
      {state.notes.map((item) => <article className="card" key={item.id}><b>{item.customer}</b><p>{item.text}</p></article>)}
    </>
  );
}

function Audit({ state }) {
  return (
    <>
      <h2>Audit</h2>
      <table><tbody>{state.audit.map((item, index) => <tr key={index}><td>{item.at}</td><td>{item.action}</td><td>{item.detail}</td></tr>)}</tbody></table>
    </>
  );
}

const screens = { landing: Landing, portal: Portal, admin: Admin, policy: Policy };
const Screen = screens[page];
createRoot(document.getElementById("root")).render(<StrictMode><Screen /></StrictMode>);
