import { FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { ApiChangeRequest, ApiCustomer, ApiDeletedEnquiry, ApiEnquiry, ApiError, ApiNotification, ApiUser, FollowUpBucket, api } from "./api";
import LoginPage from "./LoginPage";

type View = "Overview" | "Enquiries" | "Follow-ups" | "Customers" | "Reports" | "Settings";
type Role = "Manager" | "Staff";
type Status = "New" | "Assigned" | "Attended" | "Follow-ups" | "Closed" | "Open" | "Lost";
type Enquiry = { id:string; customerId:string; name:string; initials:string; phone:string; email:string; service:string; source:string; handledBy:string; handledById:string|null; status:Status; notes:string; outcomeReason:string|null; doNotContact:boolean; received:string; createdAt:string; nextFollowUpAt:string|null; followUpCount:number; priority?:boolean };

const businessTimeZone = "Asia/Kolkata";
function formatBusinessDate(value:string|null,timeZone=businessTimeZone){return value?new Intl.DateTimeFormat("en-IN",{timeZone,dateStyle:"medium",timeStyle:"short"}).format(new Date(value)):"Not scheduled"}
function businessInputValue(value:string|null,timeZone=businessTimeZone){if(!value)return "";const parts=new Intl.DateTimeFormat("en-CA",{timeZone,year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).formatToParts(new Date(value));const get=(name:string)=>parts.find(part=>part.type===name)?.value??"";return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`}
function businessDateInputToIso(value:string,timeZone:string){if(!value)return null;const [date,time]=value.split("T"),[year,month,day]=date.split("-").map(Number),[hour,minute]=time.split(":").map(Number);const wallTimeAsUtc=Date.UTC(year,month-1,day,hour,minute);const parts=new Intl.DateTimeFormat("en-CA",{timeZone,year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",second:"2-digit",hourCycle:"h23"}).formatToParts(new Date(wallTimeAsUtc));const get=(name:string)=>Number(parts.find(part=>part.type===name)?.value??0);const representedUtc=Date.UTC(get("year"),get("month")-1,get("day"),get("hour"),get("minute"),get("second"));return new Date(wallTimeAsUtc-(representedUtc-wallTimeAsUtc)).toISOString()}
function toEnquiry(row:ApiEnquiry,timeZone=businessTimeZone):Enquiry{return{id:row.id,customerId:row.customer.id,name:row.customer.name,initials:row.customer.name.split(/\s+/).map(part=>part[0]).join("").slice(0,2).toUpperCase(),phone:row.customer.phone,email:row.customer.email??"",service:row.service_type,source:row.source,handledBy:row.handled_by_name??"—",handledById:row.handled_by_id,status:row.status,notes:row.notes??"",outcomeReason:row.outcome_reason,doNotContact:row.do_not_contact,received:formatBusinessDate(row.created_at,timeZone),createdAt:row.created_at,nextFollowUpAt:row.next_follow_up_at,followUpCount:row.completed_follow_up_count,priority:!!row.next_follow_up_at&&new Date(row.next_follow_up_at).getTime()<Date.now()}}
function suggestedFollowUp(timeZone:string){return businessInputValue(new Date(Date.now()+2*24*60*60*1000).toISOString(),timeZone)}

function Icon({name,size=18}:{name:string;size?:number}) {
  const p:Record<string,ReactNode>={grid:<><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,inbox:<><path d="M4 5h16v14H4z"/><path d="M4 14h4l2 3h4l2-3h4"/></>,clock:<><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,users:<><circle cx="9" cy="8" r="3"/><path d="M3 19c0-3.3 2.7-6 6-6s6 2.7 6 6M16 5.5a3 3 0 0 1 0 5.5M17 13c2.4.5 4 2.7 4 5"/></>,chart:<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>,settings:<><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 1 1-14 0 7 7 0 0 1 14 0M12 2v3M12 19v3M2 12h3M19 12h3"/></>,search:<><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,plus:<path d="M12 5v14M5 12h14"/>,filter:<path d="M4 6h16M7 12h10M10 18h4"/>,bell:<><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/></>,menu:<path d="M4 7h16M4 12h16M4 17h16"/>,close:<path d="m6 6 12 12M18 6 6 18"/>,phone:<path d="M5 4h4l2 5-3 2c1.3 2.7 2.9 4.3 5.8 5.3l1.7-3.1 4.5 2.3V20c-9.5 1-17-6.5-15-16Z"/>,mail:<><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m4 7 8 6 8-6"/></>,note:<><path d="M5 3h14v18H5z"/><path d="M8 8h8M8 12h8M8 16h5"/></>,chevron:<path d="m9 18 6-6-6-6"/>,sun:<><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19"/></>,moon:<path d="M20 15.5A8 8 0 0 1 8.5 4 8 8 0 1 0 20 15.5Z"/>,check:<path d="m5 12 4 4L19 6"/>,lock:<><rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></>};
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>{p[name]}</svg>;
}
const nav:{label:View;icon:string}[]=[{label:"Overview",icon:"grid"},{label:"Enquiries",icon:"inbox"},{label:"Follow-ups",icon:"clock"},{label:"Customers",icon:"users"},{label:"Reports",icon:"chart"},{label:"Settings",icon:"settings"}];
function Avatar({initials}:{initials:string}){return <span className="avatar">{initials}</span>}
function StatusPill({status}:{status:Status}){return <span className={`status s-${status.toLowerCase().replace("-","")}`}><i/>{status}</span>}
function Person({e}:{e:Enquiry}){return <div className="person"><Avatar initials={e.initials}/><div><strong>{e.name}</strong><small>{e.email}</small></div></div>}

function PageHead({eyebrow,title,copy,action}:{eyebrow:string;title:string;copy:string;action?:ReactNode}){
  return (
    <header className="page-head">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{copy}</p>
      </div>
      {action}
    </header>
  );
}

function EnquiryTable({rows,onOpen}:{rows:Enquiry[];onOpen:(e:Enquiry)=>void}) {
  return (
    <>
      <div className="table-wrap desktop-table-wrap">
        <table>
          <thead>
            <tr>
              <th>Customer</th>
              <th>Contact</th>
              <th>Service</th>
              <th>Handled by</th>
              <th>Status</th>
              <th>Received</th>
              <th>Next follow-up</th>
              <th aria-label="Open" />
            </tr>
          </thead>
          <tbody>
            {rows.length ? rows.map(e => (
              <tr key={e.id} onClick={() => onOpen(e)}>
                <td><Person e={e}/></td>
                <td>
                  <span className="contact-phone">{e.phone}</span>
                  <small>{e.email || "No email"}</small>
                </td>
                <td>
                  <span className="service-name">{e.service}</span>
                  <small>{e.source}</small>
                </td>
                <td><span className="handler-name">{e.handledBy}</span></td>
                <td><StatusPill status={e.status}/></td>
                <td className="date-cell">{e.received}</td>
                <td className={`date-cell ${e.priority ? "due" : ""}`}>
                  {formatBusinessDate(e.nextFollowUpAt)}
                </td>
                <td className="action-cell"><Icon name="chevron" size={16}/></td>
              </tr>
            )) : (
              <tr><td colSpan={8} className="empty-cell">No records yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mobile-card-list">
        {rows.length ? rows.map(e => (
          <article key={e.id} className="mobile-lead-card" onClick={() => onOpen(e)}>
            <div className="mobile-lead-header">
              <Person e={e} />
              <StatusPill status={e.status} />
            </div>
            <div className="mobile-lead-details">
              <div className="mobile-lead-row">
                <span className="mobile-lead-label">Phone</span>
                <span className="mobile-lead-value">{e.phone}</span>
              </div>
              <div className="mobile-lead-row">
                <span className="mobile-lead-label">Service</span>
                <span className="mobile-lead-value">{e.service} · {e.source}</span>
              </div>
              <div className="mobile-lead-row">
                <span className="mobile-lead-label">Handler</span>
                <span className="mobile-lead-value">{e.handledBy}</span>
              </div>
              <div className="mobile-lead-row">
                <span className="mobile-lead-label">Next follow-up</span>
                <span className={`mobile-lead-value ${e.priority ? "due" : ""}`}>
                  {formatBusinessDate(e.nextFollowUpAt)}
                </span>
              </div>
            </div>
            <div className="mobile-lead-footer">
              <span className="mobile-lead-date">Received {e.received}</span>
              <span className="mobile-lead-action">
                Open <Icon name="chevron" size={14}/>
              </span>
            </div>
          </article>
        )) : (
          <div className="empty-cell">No records yet.</div>
        )}
      </div>
    </>
  );
}

function SummaryBreakdown({title,rows,by="source"}:{title:string;rows:Enquiry[];by?:"source"|"status"}){
  const counts = rows.reduce<Record<string,number>>((result,row)=>{
    const label = by === "source" ? row.source : row.status;
    result[label] = (result[label] ?? 0) + 1;
    return result;
  }, {});
  const entries = Object.entries(counts).sort((a,b) => b[1] - a[1]);
  const palette = ["#01a9ac", "#0ac282", "#fe9365", "#fe5d70", "#4099ff", "#7e22ce", "#10b981"];
  return (
    <article className="panel source-card">
      <div className="panel-head">
        <div>
          <h2>{title}</h2>
          <p>Enquiries in the current CRM view</p>
        </div>
        <span className="panel-badge">{rows.length} total</span>
      </div>
      {entries.length ? (
        <div className="summary-breakdown">
          {entries.map(([label,count], idx) => {
            const pct = Math.max(4, Math.round((count / (rows.length || 1)) * 100));
            const barColor = palette[idx % palette.length];
            return (
              <div className="summary-row" key={label}>
                <span title={label}>{label}</span>
                <div className="progress">
                  <i style={{width: `${pct}%`, background: barColor}}/>
                </div>
                <strong>{count} <small>({pct}%)</small></strong>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="empty-chart">No records yet.</div>
      )}
    </article>
  );
}

function Overview({rows,dueCount,onOpen,setView,onNew}:{rows:Enquiry[];dueCount:number;onOpen:(e:Enquiry)=>void;setView:(v:View)=>void;onNew:()=>void}) {
  const metrics = [
    [String(rows.filter(e => e.status === "New").length), "New enquiries", "Awaiting team pickup", "inbox", "c-teal"],
    [String(rows.filter(e => ["Assigned", "Attended", "Follow-ups"].includes(e.status)).length), "Handled enquiries", "In active client pipeline", "users", "c-green"],
    [String(dueCount), "Follow-ups due", "Scheduled for today", "clock", "c-salmon"],
    [String(rows.filter(e => e.status === "Closed").length), "Closed enquiries", "Successfully completed", "chart", "c-red"]
  ];
  return (
    <>
      <PageHead
        eyebrow="DASHBOARD"
        title="Workspace Overview"
        copy="Monitor customer inquiries, team activity, and pipeline performance."
        action={<button className="primary" onClick={onNew}><Icon name="plus"/>New enquiry</button>}
      />
      <section className="metrics">
        {metrics.map(m => (
          <article className={`metric bg-${m[4]}`} key={m[1]}>
            <div className="metric-header">
              <div>
                <p>{m[1]}</p>
                <strong>{m[0]}</strong>
              </div>
              <span className="metric-icon"><Icon name={m[3]} size={24}/></span>
            </div>
            <div className="metric-footer">
              <small>{m[2]}</small>
            </div>
          </article>
        ))}
      </section>
      <section className="split-grid">
        <SummaryBreakdown title="Enquiries by source" rows={rows}/>
        <SummaryBreakdown title="Enquiry outcomes" rows={rows.filter(e => ["Closed", "Open", "Lost"].includes(e.status))} by="status"/>
      </section>
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Recent enquiries</h2>
            <p>Latest enquiries across all channels</p>
          </div>
          <button className="text-button" onClick={() => setView("Enquiries")}>
            View all enquiries <Icon name="chevron" size={14}/>
          </button>
        </div>
        <EnquiryTable rows={rows.slice(0, 5)} onOpen={onOpen}/>
      </section>
    </>
  );
}

function Enquiries({rows,onOpen,onNew,loading,error}:{rows:Enquiry[];onOpen:(e:Enquiry)=>void;onNew:()=>void;loading:boolean;error:string}) {
  const [q,setQ] = useState("");
  const [status,setStatus] = useState("All statuses");
  const [service,setService] = useState("All services");

  const filtered = useMemo(() => rows.filter(e => {
    const term = q.toLowerCase();
    const matchesSearch = (e.name + e.phone + e.email).toLowerCase().includes(term);
    const matchesStatus = status === "All statuses" || e.status === status;
    const matchesService = service === "All services" || e.service === service;
    return matchesSearch && matchesStatus && matchesService;
  }), [rows, q, status, service]);

  return (
    <>
      <PageHead
        eyebrow="LEAD MANAGEMENT"
        title="Enquiries"
        copy="All staff can view leads. Pick an available enquiry to claim it for follow-up."
        action={<button className="primary" onClick={onNew}><Icon name="plus"/>New enquiry</button>}
      />
      {error && <p className="error" role="alert">{error}</p>}
      <section className="panel">
        <div className="tabs">
          <button className="active">All Enquiries <span>{filtered.length}</span></button>
        </div>
        <div className="filters">
          <label className="search">
            <Icon name="search" size={18}/>
            <input
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder="Search by customer name, phone, or email…"
            />
          </label>
          <div className="filters-row">
            <select aria-label="Status filter" value={status} onChange={e => setStatus(e.target.value)}>
              <option>All statuses</option>
              <option>New</option>
              <option>Assigned</option>
              <option>Attended</option>
              <option>Follow-ups</option>
              <option>Closed</option>
              <option>Open</option>
              <option>Lost</option>
            </select>
            <select aria-label="Service filter" value={service} onChange={e => setService(e.target.value)}>
              <option>All services</option>
              <option>Real Estate</option>
              <option>Finance/Loans</option>
            </select>
          </div>
          <span className="records-count">
            {loading ? "Loading enquiries…" : `${filtered.length} of ${rows.length} loaded`}
          </span>
        </div>
        <EnquiryTable rows={filtered} onOpen={onOpen}/>
      </section>
    </>
  );
}

function FollowUps({onOpen,onCompleted,csrfToken,onToast,timeZone,revision,role,userId}:{onOpen:(e:Enquiry)=>void;onCompleted:(enquiry:Enquiry)=>void;csrfToken:string;onToast:(message:string)=>void;timeZone:string;revision:number;role:Role;userId:string}) {
  const [groups,setGroups] = useState<Record<FollowUpBucket,Enquiry[]>>({overdue:[],"due-today":[],upcoming:[]});
  const [loading,setLoading] = useState(true);
  const [error,setError] = useState("");
  const [calendar,setCalendar] = useState(false);
  const [month,setMonth] = useState(() => businessInputValue(new Date().toISOString(), timeZone).slice(0, 7));
  const [rescheduling,setRescheduling] = useState<string|null>(null);
  const [scheduledValue,setScheduledValue] = useState("");
  const [saving,setSaving] = useState(false);

  async function load(){
    setLoading(true);
    setError("");
    try {
      const [overdue,due,upcoming] = await Promise.all([
        api.listFollowUps("overdue"),
        api.listFollowUps("due-today"),
        api.listFollowUps("upcoming")
      ]);
      setGroups({
        overdue: overdue.items.map(row => toEnquiry(row, timeZone)),
        "due-today": due.items.map(row => toEnquiry(row, timeZone)),
        upcoming: upcoming.items.map(row => toEnquiry(row, timeZone))
      });
    } catch(e) {
      setError(e instanceof Error ? e.message : "Could not load follow-ups");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load() }, [timeZone, revision]);

  async function complete(enquiry:Enquiry){
    setSaving(true);
    try {
      await api.completeFollowUp(enquiry.id, csrfToken);
      onCompleted(enquiry);
      onToast("Enquiry follow-up completed and closed");
      await load();
    } catch(e) {
      setError(e instanceof Error ? e.message : "Could not complete follow-up");
    } finally {
      setSaving(false);
    }
  }

  async function saveSchedule(enquiry:Enquiry){
    if(!scheduledValue) return;
    setSaving(true);
    try {
      await api.scheduleFollowUp(enquiry.id, businessDateInputToIso(scheduledValue, timeZone), csrfToken);
      setRescheduling(null);
      onToast("Follow-up rescheduled successfully");
      await load();
    } catch(e) {
      setError(e instanceof Error ? e.message : "Could not reschedule follow-up");
    } finally {
      setSaving(false);
    }
  }

  const all = [...groups.upcoming, ...groups.overdue, ...groups["due-today"]];
  const [year, monthNumber] = month.split("-").map(Number);
  const daysInMonth = new Date(year, monthNumber, 0).getDate();
  const firstDay = new Date(year, monthNumber - 1, 1).getDay();
  const monthLabel = new Intl.DateTimeFormat("en-IN", { timeZone, month: "long", year: "numeric" }).format(new Date(`${month}-15T12:00:00+05:30`));
  const dayItems = (day:number) => all.filter(item => item.nextFollowUpAt && businessInputValue(item.nextFollowUpAt, timeZone).slice(0, 10) === `${month}-${String(day).padStart(2, "0")}`);

  return (
    <>
      <PageHead
        eyebrow="WORK QUEUE"
        title="Follow-ups"
        copy="Stay on top of every scheduled customer contact and follow-up call."
        action={
          <button className="secondary" onClick={() => setCalendar(v => !v)}>
            <Icon name="clock"/>{calendar ? "Switch to list view" : "Calendar view"}
          </button>
        }
      />
      <p className="timezone-note">All dates and deadlines are coordinated in {timeZone}.</p>
      {error && <p className="error" role="alert">{error}</p>}
      {loading ? (
        <section className="panel empty-chart">Loading follow-ups…</section>
      ) : calendar ? (
        <section className="panel calendar-panel">
          <div className="calendar-heading">
            <button
              className="secondary"
              onClick={() => setMonth(val => {
                const [y, m] = val.split("-").map(Number);
                const d = new Date(y, m - 2, 1);
                return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
              })}
            >
              Previous month
            </button>
            <h2>{monthLabel}</h2>
            <div style={{display: "flex", gap: "10px", alignItems: "center"}}>
              <input
                aria-label="Calendar month"
                type="month"
                value={month}
                onChange={e => setMonth(e.target.value)}
              />
              <button
                className="secondary"
                onClick={() => setMonth(val => {
                  const [y, m] = val.split("-").map(Number);
                  const d = new Date(y, m, 1);
                  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
                })}
              >
                Next month
              </button>
            </div>
          </div>
          <div className="calendar-grid">
            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map(day => (
              <strong key={day}>{day}</strong>
            ))}
            {Array.from({length: firstDay}, (_, index) => (
              <span className="calendar-blank" key={`blank-${index}`}/>
            ))}
            {Array.from({length: daysInMonth}, (_, index) => {
              const day = index + 1;
              const items = dayItems(day);
              return (
                <div className="calendar-day" key={day}>
                  <b>{day}</b>
                  {items.map(item => (
                    <button
                      key={item.id}
                      onClick={() => onOpen(item)}
                      title={`${item.name} · ${formatBusinessDate(item.nextFollowUpAt, timeZone)}`}
                    >
                      {item.name}
                    </button>
                  ))}
                </div>
              );
            })}
          </div>
        </section>
      ) : (
        <div className="follow-grid">
          {([["Upcoming", groups.upcoming], ["Overdue", groups.overdue], ["Due today", groups["due-today"]]] as const).map((group, index) => (
            <section className="follow-column" key={group[0]}>
              <div className="follow-title">
                <i className={`tone t${index}`}/>
                <h2>{group[0]}</h2>
                <span>{group[1].length}</span>
              </div>
              {group[1].length === 0 ? (
                <p className="empty-message">No {group[0].toLowerCase()} follow-ups.</p>
              ) : (
                group[1].map(enquiry => {
                  const canHandle = role === "Manager" || enquiry.handledById === userId;
                  return (
                    <article className="follow-card" key={enquiry.id}>
                      <div className="follow-card-head">
                        <Person e={enquiry}/>
                        <StatusPill status={enquiry.status}/>
                      </div>
                      <p>
                        <Icon name="clock"/>
                        <span>{formatBusinessDate(enquiry.nextFollowUpAt, timeZone)}</span>
                      </p>
                      <p>
                        <Icon name="inbox"/>
                        <span>{enquiry.service} · {enquiry.source}</span>
                      </p>
                      {rescheduling === enquiry.id && (
                        <div className="reschedule-form">
                          <label>
                            New scheduled time ({timeZone})
                            <input
                              type="datetime-local"
                              value={scheduledValue}
                              onChange={e => setScheduledValue(e.target.value)}
                            />
                          </label>
                          <div className="reschedule-actions">
                            <button className="secondary" onClick={() => setRescheduling(null)}>
                              Cancel
                            </button>
                            <button
                              className="primary"
                              disabled={saving || !scheduledValue}
                              onClick={() => void saveSchedule(enquiry)}
                            >
                              Save time
                            </button>
                          </div>
                        </div>
                      )}
                      <div className="follow-actions">
                        {canHandle ? (
                          <>
                            <button disabled={saving} onClick={() => void complete(enquiry)}>
                              Complete
                            </button>
                            <button onClick={() => {
                              setRescheduling(enquiry.id);
                              setScheduledValue(businessInputValue(enquiry.nextFollowUpAt, timeZone));
                            }}>
                              Reschedule
                            </button>
                          </>
                        ) : (
                          <small>Handled by {enquiry.handledBy}</small>
                        )}
                        <button className="icon-button" onClick={() => onOpen(enquiry)} title="View lead details">
                          <Icon name="chevron"/>
                        </button>
                      </div>
                    </article>
                  );
                })
              )}
            </section>
          ))}
        </div>
      )}
    </>
  );
}

function Customers({rows,onOpen}:{rows:Enquiry[];onOpen:(e:Enquiry)=>void}){
  const [customers,setCustomers] = useState<ApiCustomer[]>([]);
  const [loading,setLoading] = useState(true);
  const [error,setError] = useState("");
  const [status,setStatus] = useState("All");

  useEffect(() => {
    let active = true;
    api.listCustomers()
      .then(items => { if(active) { setCustomers(items); setError("") } })
      .catch(reason => { if(active) setError(reason instanceof Error ? reason.message : "Could not load customers") })
      .finally(() => { if(active) setLoading(false) });
    return () => { active = false };
  }, []);

  const eligible = rows.filter(row => status === "All" || row.status === status);
  const countFor = (value:string) => value === "All" ? customers.length : rows.filter(row => row.status === value).length;
  const customerRows = customers.reduce<{customer:ApiCustomer;enquiry:Enquiry|null}[]>((result, customer) => {
    const matched = eligible.filter(row => row.customerId === customer.id);
    if(matched.length) {
      result.push(...matched.map(enquiry => ({ customer, enquiry })));
    } else if(status === "All") {
      result.push({ customer, enquiry: null });
    }
    return result;
  }, []);

  return (
    <>
      <PageHead
        eyebrow="RELATIONSHIPS"
        title="Customers"
        copy="Customer records linked to independent enquiries and interaction histories."
      />
      <section className="panel">
        <div className="tabs">
          {["All", "Closed", "Open", "Lost"].map(value => (
            <button
              key={value}
              className={status === value ? "active" : ""}
              onClick={() => setStatus(value)}
            >
              {value === "All" ? "All customers" : `${value} enquiries`}
              <span>{countFor(value)}</span>
            </button>
          ))}
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        {loading ? (
          <p className="empty-message">Loading customers…</p>
        ) : (
          <>
            <div className="table-wrap desktop-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Customer</th>
                    <th>Phone</th>
                    <th>Email</th>
                    <th>Enquiry status</th>
                    <th>Service</th>
                    <th>Handled by</th>
                    <th aria-label="Open" />
                  </tr>
                </thead>
                <tbody>
                  {customerRows.length ? customerRows.map(({customer, enquiry}) => (
                    <tr
                      key={`${customer.id}-${enquiry?.id ?? "none"}`}
                      onClick={() => enquiry && onOpen(enquiry)}
                    >
                      <td><strong>{customer.name}</strong></td>
                      <td>{customer.phone}</td>
                      <td>{customer.email ?? "—"}</td>
                      <td>{enquiry ? <StatusPill status={enquiry.status}/> : "No active enquiry"}</td>
                      <td>{enquiry?.service ?? "—"}</td>
                      <td>{enquiry?.handledBy ?? "—"}</td>
                      <td className="action-cell">
                        {enquiry && <Icon name="chevron" size={16}/>}
                      </td>
                    </tr>
                  )) : (
                    <tr><td colSpan={7} className="empty-cell">No customers in this view.</td></tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="mobile-card-list">
              {customerRows.length ? customerRows.map(({customer, enquiry}) => (
                <article
                  key={`${customer.id}-${enquiry?.id ?? "none"}`}
                  className="mobile-lead-card"
                  onClick={() => enquiry && onOpen(enquiry)}
                >
                  <div className="mobile-lead-header">
                    <div>
                      <strong>{customer.name}</strong>
                      <small style={{display: "block", color: "var(--muted)", marginTop: "2px"}}>
                        {customer.phone}
                      </small>
                    </div>
                    {enquiry && <StatusPill status={enquiry.status} />}
                  </div>
                  <div className="mobile-lead-details">
                    <div className="mobile-lead-row">
                      <span className="mobile-lead-label">Email</span>
                      <span className="mobile-lead-value">{customer.email || "—"}</span>
                    </div>
                    <div className="mobile-lead-row">
                      <span className="mobile-lead-label">Service</span>
                      <span className="mobile-lead-value">{enquiry?.service || "—"}</span>
                    </div>
                    <div className="mobile-lead-row">
                      <span className="mobile-lead-label">Handler</span>
                      <span className="mobile-lead-value">{enquiry?.handledBy || "—"}</span>
                    </div>
                  </div>
                  {enquiry && (
                    <div className="mobile-lead-footer">
                      <span className="mobile-lead-date">Tap to view enquiry</span>
                      <span className="mobile-lead-action">Open <Icon name="chevron" size={14}/></span>
                    </div>
                  )}
                </article>
              )) : (
                <div className="empty-cell">No customers in this view.</div>
              )}
            </div>
          </>
        )}
      </section>
    </>
  );
}

function Reports({role,rows,onOpen}:{role:Role;rows:Enquiry[];onOpen:(e:Enquiry)=>void}){
  if(role !== "Manager") return <AccessNotice/>;
  const outcomes:Status[] = ["New","Assigned","Attended","Follow-ups","Closed","Open","Lost"];
  const services = rows.reduce<Record<string,number>>((counts, row) => {
    counts[row.service] = (counts[row.service] ?? 0) + 1;
    return counts;
  }, {});
  const byStatus = rows.reduce<Record<string,number>>((counts, row) => {
    counts[row.status] = (counts[row.status] ?? 0) + 1;
    return counts;
  }, {});

  return (
    <>
      <PageHead
        eyebrow="CRM PERFORMANCE"
        title="CRM reports"
        copy="Real-time breakdown of enquiry outcomes, service lines, and lead channels."
      />
      <section className="metrics report-metrics">
        {outcomes.map(outcome => (
          <article className="metric" key={outcome}>
            <strong>{byStatus[outcome] ?? 0}</strong>
            <p>{outcome} enquiries</p>
            <small>Active CRM records</small>
          </article>
        ))}
      </section>
      <section className="split-grid">
        <SummaryBreakdown title="Enquiries by lead source" rows={rows}/>
        <article className="panel source-card">
          <div className="panel-head">
            <div>
              <h2>Enquiries by service line</h2>
              <p>Breakdown across business domains</p>
            </div>
          </div>
          <div className="summary-breakdown">
            {Object.entries(services).length ? Object.entries(services).map(([label, count]) => {
              const pct = Math.max(4, Math.round((count / Math.max(rows.length, 1)) * 100));
              return (
                <div className="summary-row" key={label}>
                  <span>{label}</span>
                  <div className="progress">
                    <i style={{width: `${pct}%`}}/>
                  </div>
                  <strong>{count}</strong>
                </div>
              );
            }) : (
              <p className="empty-message">No service data yet.</p>
            )}
          </div>
        </article>
      </section>
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Recent CRM activity</h2>
            <p>Latest enquiries across all active service lines</p>
          </div>
        </div>
        <EnquiryTable rows={rows.slice(0, 10)} onOpen={onOpen}/>
      </section>
      <p className="security-note">
        <Icon name="lock"/>Manager role verified. Comprehensive reporting and audit data active.
      </p>
    </>
  );
}

function AccessNotice(){
  return (
    <section className="panel access">
      <span><Icon name="lock" size={26}/></span>
      <h1>Manager Access Required</h1>
      <p>This operational section is reserved for accounts with the Manager role.</p>
    </section>
  );
}

function NewEnquiryModal({onClose,onCreate,busy,error}:{onClose:()=>void;onCreate:(payload:{customer:{name:string;phone:string;email?:string};service_type:string;source:string})=>Promise<void>;busy:boolean;error:string}){
  const [phone,setPhone]=useState("");
  const [phoneTooLong,setPhoneTooLong]=useState(false);
  const [email,setEmail]=useState("");

  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const submittedEmail = String(form.get("email") ?? "").trim();
    await onCreate({
      customer: {
        name: String(form.get("name")).trim(),
        phone,
        ...(submittedEmail ? { email: submittedEmail } : {})
      },
      service_type: String(form.get("service_type")),
      source: String(form.get("source"))
    });
  }

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <section
        className="new-enquiry-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-enquiry-title"
        onMouseDown={e => e.stopPropagation()}
      >
        <div className="panel-head">
          <div>
            <p className="eyebrow">NEW RECORD</p>
            <h2 id="new-enquiry-title">Create customer enquiry</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close dialog">
            <Icon name="close"/>
          </button>
        </div>
        <form className="new-enquiry-form" onSubmit={submit}>
          <label>
            Customer name
            <input name="name" required minLength={2} maxLength={120} placeholder="e.g. Rahul Sharma" autoFocus/>
          </label>
          <label>
            Phone number
            <input
              name="phone"
              type="tel"
              inputMode="numeric"
              autoComplete="tel-national"
              required
              pattern="[0-9]{10}"
              title="Enter exactly 10 digits."
              value={phone}
              onChange={event => {
                const digits = event.target.value.replace(/\D/g, "");
                setPhoneTooLong(digits.length > 10);
                setPhone(digits.slice(0, 10));
              }}
              placeholder="10-digit phone number"
              aria-invalid={phoneTooLong || (phone.length > 0 && phone.length !== 10)}
              aria-describedby="new-enquiry-phone-hint"
            />
            <small id="new-enquiry-phone-hint" className={phoneTooLong || (phone.length > 0 && phone.length !== 10) ? "field-hint warning" : "field-hint"} aria-live="polite">
              {phoneTooLong ? "Maximum 10 digits. Extra digits were removed." : phone.length > 0 && phone.length < 10 ? `Enter ${10 - phone.length} more digit${phone.length === 9 ? "" : "s"}.` : "Enter exactly 10 digits."}
            </small>
          </label>
          <label>
            Email address (optional)
            <input
              name="email"
              type="email"
              maxLength={320}
              value={email}
              onChange={event => setEmail(event.target.value)}
              placeholder="e.g. rahul@example.com"
              aria-invalid={email.length > 0 && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())}
              aria-describedby="new-enquiry-email-hint"
            />
            <small id="new-enquiry-email-hint" className={email.length > 0 && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()) ? "field-hint warning" : "field-hint"} aria-live="polite">
              {email.length > 0 && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()) ? "Enter a valid email address, or leave this field blank." : "Optional. We’ll check the address format when provided."}
            </small>
          </label>
          <label>
            Service category
            <select name="service_type" required>
              <option>Real Estate</option>
              <option>Finance/Loans</option>
            </select>
          </label>
          <label>
            Lead source
            <select name="source" required>
              <option>Phone</option>
              <option>Referral</option>
              <option>Website</option>
              <option>Walk-in</option>
              <option>Other</option>
            </select>
          </label>
          {error && <p className="error" role="alert">{error}</p>}
          <div className="form-footer">
            <button className="secondary" type="button" onClick={onClose}>
              Cancel
            </button>
            <button className="primary" disabled={busy}>
              {busy ? "Saving record…" : "Create enquiry"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function DeletionApprovals({rows,csrfToken,onToast,onDeleted,onRestored}:{rows:Enquiry[];csrfToken:string;onToast:(message:string)=>void;onDeleted:(enquiryId:string)=>void;onRestored:(row:ApiEnquiry)=>void}) {
  const [requests,setRequests] = useState<ApiChangeRequest[]>([]);
  const [deleted,setDeleted] = useState<ApiDeletedEnquiry[]>([]);
  const [selected,setSelected] = useState<ApiChangeRequest|null>(null);
  const [permanentTarget,setPermanentTarget] = useState<ApiDeletedEnquiry|null>(null);
  const [loading,setLoading] = useState(true);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");

  async function load(showLoading=true){
    if(showLoading) setLoading(true);
    setError("");
    try {
      const [pendingPage, approvedPage, deletedPage] = await Promise.all([
        api.listChangeRequests("pending"),
        api.listChangeRequests("approved"),
        api.listDeletedEnquiries()
      ]);
      setRequests([...pendingPage.items, ...approvedPage.items].filter(item => item.request_type === "delete"));
      setDeleted(deletedPage.items);
    } catch(problem) {
      setError(problem instanceof Error ? problem.message : "Could not load deletion requests");
    } finally {
      if(showLoading) setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(false), 15000);
    return () => window.clearInterval(timer);
  }, []);

  async function decide(decision:"approve"|"reject"){
    if(!selected) return;
    setBusy(true);
    setError("");
    try {
      if(selected.status === "approved"){
        await api.confirmEnquiryDeletion(selected.id, csrfToken);
        onDeleted(selected.enquiry_id);
      } else {
        const result = await api.decideChangeRequest(selected.id, decision, csrfToken);
        if(result.status === "completed") onDeleted(selected.enquiry_id);
      }
      setSelected(null);
      onToast(decision === "reject" ? "Deletion request rejected" : "Enquiry removed from active pipeline");
      await load();
    } catch(problem) {
      setError(problem instanceof Error ? problem.message : "Could not process deletion request");
    } finally {
      setBusy(false);
    }
  }

  async function restore(item:ApiDeletedEnquiry){
    setBusy(true);
    setError("");
    try {
      const row = await api.restoreDeletedEnquiry(item.id, csrfToken);
      onRestored(row);
      onToast("Enquiry restored to active records");
      await load();
    } catch(problem) {
      setError(problem instanceof Error ? problem.message : "Could not restore enquiry");
    } finally {
      setBusy(false);
    }
  }

  async function purge(item:ApiDeletedEnquiry){
    setBusy(true);
    setError("");
    try {
      const result = await api.permanentlyDeleteEnquiry(item.id, csrfToken);
      onDeleted(item.id);
      setPermanentTarget(null);
      onToast(result.customer_deleted ? "Enquiry and unused customer permanently deleted" : "Enquiry permanently erased");
      await load();
    } catch(problem) {
      setError(problem instanceof Error ? problem.message : "Could not permanently delete enquiry");
    } finally {
      setBusy(false);
    }
  }

  const card = (request:ApiChangeRequest) => {
    const enquiry = rows.find(item => item.id === request.enquiry_id);
    return (
      <article className="deletion-request" key={request.id}>
        <div>
          <strong>{enquiry ? `${enquiry.name} · ${enquiry.service}` : `Enquiry #${request.enquiry_id.slice(0,8).toUpperCase()}`}</strong>
          <small>Requested by {request.submitted_by_name ?? "Staff"} · {formatBusinessDate(request.created_at)}</small>
        </div>
        <button className="secondary" onClick={() => { setSelected(request); setError("") }}>
          Review request
        </button>
      </article>
    );
  };

  const selectedEnquiry = selected ? rows.find(item => item.id === selected.enquiry_id) : undefined;

  return (
    <>
      <section className="panel deletion-approvals">
        <div className="panel-head">
          <div>
            <h2>Pending deletion requests ({requests.length})</h2>
            <p>Review staff removal requests and approve or reject them.</p>
          </div>
          <button className="secondary" onClick={() => void load()} disabled={loading || busy}>
            Refresh
          </button>
        </div>
        {error && !selected && !permanentTarget && <p className="error" role="alert">{error}</p>}
        {loading ? (
          <p className="empty-message">Loading deletion requests…</p>
        ) : requests.length ? (
          requests.map(card)
        ) : (
          <p className="empty-message">No enquiries currently awaiting deletion review.</p>
        )}
      </section>

      <section className="panel recoverable-deletions">
        <div className="panel-head">
          <div>
            <h2>Recently deleted enquiries</h2>
            <p>Soft-deleted records retained for 30 days before permanent erasure.</p>
          </div>
        </div>
        {loading ? (
          <p className="empty-message">Loading deleted enquiries…</p>
        ) : deleted.length ? (
          deleted.map(item => (
            <article className="deletion-request recoverable-item" key={item.id}>
              <div>
                <strong>{item.customer.name} · {item.service_type}</strong>
                <small>Deleted {formatBusinessDate(item.deleted_at)}</small>
                <small>Automatic purge: {formatBusinessDate(item.purge_at)}</small>
              </div>
              <div>
                <button className="secondary" disabled={busy} onClick={() => void restore(item)}>
                  Undo deletion
                </button>
                <button className="danger-button" disabled={busy} onClick={() => { setPermanentTarget(item); setError("") }}>
                  Delete permanently
                </button>
              </div>
            </article>
          ))
        ) : (
          <p className="empty-message">No recently deleted enquiries.</p>
        )}
      </section>

      {selected && (
        <div className="deletion-modal-backdrop" onMouseDown={() => !busy && setSelected(null)}>
          <section
            className="deletion-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="deletion-modal-title"
            onMouseDown={e => e.stopPropagation()}
          >
            <h2 id="deletion-modal-title">Confirm enquiry deletion?</h2>
            <p>
              <strong>{selectedEnquiry ? `${selectedEnquiry.name} · ${selectedEnquiry.service}` : `Enquiry #${selected.enquiry_id.slice(0,8).toUpperCase()}`}</strong> will be moved from active pipelines to the recovery archive.
            </p>
            <p>
              <strong>Requested by:</strong> {selected.submitted_by_name ?? "Staff member"}<br/>
              <strong>Reason:</strong> {selected.reason || "No explicit reason specified"}
            </p>
            {error && <p className="error" role="alert">{error}</p>}
            <div className="form-actions">
              {selected.status === "pending" && (
                <button className="secondary" disabled={busy} onClick={() => void decide("reject")}>
                  Reject request
                </button>
              )}
              <button className="danger-button" disabled={busy} onClick={() => void decide("approve")}>
                {busy ? "Processing…" : "Confirm deletion"}
              </button>
            </div>
          </section>
        </div>
      )}

      {permanentTarget && (
        <div className="deletion-modal-backdrop" onMouseDown={() => !busy && setPermanentTarget(null)}>
          <section
            className="deletion-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="permanent-delete-title"
            onMouseDown={e => e.stopPropagation()}
          >
            <h2 id="permanent-delete-title">Permanently delete enquiry record?</h2>
            <p>
              <strong>{permanentTarget.customer.name} · {permanentTarget.service_type}</strong> and its linked activity history will be permanently erased. If no other enquiries remain for this customer, the customer profile is also purged. This operation cannot be undone.
            </p>
            {error && <p className="error" role="alert">{error}</p>}
            <div className="form-actions">
              <button className="secondary" disabled={busy} onClick={() => setPermanentTarget(null)}>
                Cancel
              </button>
              <button className="danger-button" disabled={busy} onClick={() => void purge(permanentTarget)}>
                {busy ? "Erasing…" : "Permanently delete"}
              </button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}

function Settings({currentRole,rows,csrfToken,onToast,onDeleted,onRestored}:{currentRole:Role;rows:Enquiry[];csrfToken:string;onToast:(x:string)=>void;onDeleted:(enquiryId:string)=>void;onRestored:(row:ApiEnquiry)=>void}) {
  const [users,setUsers] = useState<ApiUser[]>([]);
  const [loading,setLoading] = useState(true);
  const [error,setError] = useState("");
  const [showCreate,setShowCreate] = useState(false);
  const [saving,setSaving] = useState(false);

  useEffect(() => {
    if(currentRole !== "Manager") return;
    let active = true;
    api.listUsers()
      .then(data => { if(active) { setUsers(data); setError("") } })
      .catch(e => { if(active) setError(e instanceof Error ? e.message : "Could not load staff accounts") })
      .finally(() => { if(active) setLoading(false) });
    return () => { active = false };
  }, [currentRole]);

  async function createStaff(event:FormEvent<HTMLFormElement>){
    event.preventDefault();
    const formElement = event.currentTarget;
    setSaving(true);
    setError("");
    const form = new FormData(formElement);
    try {
      const added = await api.createStaff({
        user_id: String(form.get("user_id")),
        email: String(form.get("email")),
        password: String(form.get("password"))
      }, csrfToken);
      setUsers(current => [...current, added]);
      formElement.reset();
      setShowCreate(false);
      onToast("Staff account created successfully");
    } catch(e) {
      setError(e instanceof Error ? e.message : "Could not create staff account");
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(user:ApiUser){
    try {
      const updated = await api.setStaffActive(user.id, !user.is_active, csrfToken);
      setUsers(current => current.map(item => item.id === updated.id ? updated : item));
      onToast(updated.is_active ? "Staff account enabled" : "Staff account disabled");
    } catch(e) {
      setError(e instanceof Error ? e.message : "Could not update account status");
    }
  }

  if(currentRole !== "Manager") return <AccessNotice/>;

  return (
    <>
      <PageHead
        eyebrow="TEAM ACCESS"
        title="Staff accounts"
        copy="Manage team user profiles, roles, and workspace authorization."
        action={
          <button className="primary" onClick={() => setShowCreate(v => !v)}>
            <Icon name="plus"/>{showCreate ? "Close form" : "Add staff"}
          </button>
        }
      />
      {error && <p className="error" role="alert">{error}</p>}
      {showCreate && (
        <section className="panel account-form-panel">
          <form className="account-form" onSubmit={createStaff}>
            <label>
              User ID
              <input
                name="user_id"
                required
                minLength={3}
                maxLength={50}
                pattern="[A-Za-z0-9._-]+"
                autoCapitalize="none"
                placeholder="e.g. rahul.sharma"
              />
            </label>
            <label>
              Email address
              <input
                name="email"
                type="email"
                required
                maxLength={320}
                placeholder="e.g. rahul@example.com"
              />
            </label>
            <label>
              Temporary password
              <input
                name="password"
                type="password"
                required
                minLength={12}
                maxLength={128}
                autoComplete="new-password"
                placeholder="At least 12 characters"
              />
            </label>
            <p>The temporary password is shared securely with the staff member to sign in on their workspace.</p>
            <button className="primary" disabled={saving}>
              {saving ? "Creating…" : "Create staff account"}
            </button>
          </form>
        </section>
      )}
      <section className="panel account-list-panel">
        <div className="panel-head">
          <div>
            <h2>Active team accounts</h2>
            <p>{users.length} registered workspace accounts</p>
          </div>
        </div>
        {loading ? (
          <p className="empty-message">Loading accounts…</p>
        ) : users.length === 0 ? (
          <p className="empty-message">No accounts found.</p>
        ) : (
          <div className="account-list">
            {users.map(user => (
              <article className="account-row" key={user.id}>
                <Avatar initials={user.display_name.split(/\s+/).map(p => p[0]).join("").slice(0, 2).toUpperCase()}/>
                <span>
                  <strong>{user.display_name}</strong>
                  <small>{user.user_id} · {user.email}</small>
                </span>
                <em className={user.is_active ? "account-active" : "account-inactive"}>
                  {user.is_active ? "Active" : "Disabled"}
                </em>
                {user.role === "staff" && (
                  <button className="secondary account-toggle" onClick={() => void toggleActive(user)}>
                    {user.is_active ? "Disable" : "Enable"}
                  </button>
                )}
                <small className="account-role">{user.role}</small>
              </article>
            ))}
          </div>
        )}
      </section>
      <DeletionApprovals rows={rows} csrfToken={csrfToken} onToast={onToast} onDeleted={onDeleted} onRestored={onRestored}/>
      <p className="security-note">
        <Icon name="lock"/>Staff access is validated server-side. Passwords and sessions use secure hash storage.
      </p>
    </>
  );
}

function Drawer({e,onClose,timeZone,role,userId,csrfToken,onChanged,onToast}:{e:Enquiry;onClose:()=>void;timeZone:string;role:Role;userId:string;csrfToken:string;onChanged:(row:ApiEnquiry)=>void;onToast:(message:string)=>void}){
  const [notes,setNotes] = useState(e.notes);
  const [scheduledValue,setScheduledValue] = useState(e.nextFollowUpAt ? businessInputValue(e.nextFollowUpAt, timeZone) : suggestedFollowUp(timeZone));
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");

  useEffect(() => {
    setNotes(e.notes);
    setScheduledValue(e.nextFollowUpAt ? businessInputValue(e.nextFollowUpAt, timeZone) : suggestedFollowUp(timeZone));
    setError("");
  }, [e.id, e.notes, e.nextFollowUpAt, timeZone]);

  const mine = e.handledById === userId;
  const canWork = role === "Manager" || mine;

  async function claim(){
    setBusy(true);
    setError("");
    try {
      const row = await api.claimEnquiry(e.id, csrfToken);
      onChanged(row);
      onToast("Enquiry assigned to you");
    } catch(reason) {
      if(reason instanceof ApiError && reason.status === 409) {
        try {
          const page = await api.listEnquiries();
          const latest = page.items.find(row => row.id === e.id);
          if(latest) onChanged(latest);
        } catch {}
      }
      setError(reason instanceof Error ? reason.message : "Could not claim enquiry");
    } finally {
      setBusy(false);
    }
  }

  async function saveContact(){
    if(!scheduledValue) return;
    setBusy(true);
    setError("");
    try {
      const row = await api.saveEnquiryContact(e.id, {
        notes,
        next_follow_up_at: businessDateInputToIso(scheduledValue, timeZone) ?? ""
      }, csrfToken);
      onChanged(row);
      onToast("Notes saved and follow-up scheduled");
    } catch(reason) {
      setError(reason instanceof Error ? reason.message : "Could not save contact notes");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="overlay" onMouseDown={onClose}>
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="enquiry-drawer-title"
        onMouseDown={ev => ev.stopPropagation()}
      >
        <div className="drawer-top">
          <div>
            <p className="eyebrow">ENQUIRY #{e.id.slice(0, 8).toUpperCase()}</p>
            <h2 id="enquiry-drawer-title">{e.name}</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close details panel">
            <Icon name="close"/>
          </button>
        </div>

        <div className="contact-card">
          <Person e={e}/>
          <div className="contact-links">
            <a href={`tel:${e.phone}`} className="contact-link" title="Call customer">
              <Icon name="phone" size={16}/>
              <span>{e.phone}</span>
            </a>
            {e.email && (
              <a href={`mailto:${e.email}`} className="contact-link" title="Email customer">
                <Icon name="mail" size={16}/>
                <span>{e.email}</span>
              </a>
            )}
          </div>
        </div>

        <div className="details-grid">
          <label>Service category<strong>{e.service}</strong></label>
          <label>Lead source<strong>{e.source}</strong></label>
          <label>Assigned staff<strong>{e.handledBy}</strong></label>
          <label>Current status<strong><StatusPill status={e.status}/></strong></label>
          <label>Date received<strong>{e.received}</strong></label>
          <label>Next scheduled contact<strong>{formatBusinessDate(e.nextFollowUpAt, timeZone)}</strong></label>
          <label>Completed follow-ups<strong>{e.followUpCount} calls</strong></label>
        </div>

        {role === "Staff" && e.status === "New" && !e.handledById && (
          <div className="claim-box">
            <p>This lead is open for assignment. Claiming this enquiry will assign it to your queue and enable call logging.</p>
            <button className="primary" disabled={busy} onClick={() => void claim()}>
              {busy ? "Assigning…" : "Pick enquiry"}
            </button>
          </div>
        )}

        {e.handledById && !mine && role === "Staff" && (
          <p className="assigned-notice">Assigned to team member: {e.handledBy}.</p>
        )}

        {canWork && ["Assigned", "Attended", "Follow-ups"].includes(e.status) && (
          <div className="notes">
            <h3>Log call & schedule follow-up</h3>
            <p>Record notes from the customer conversation and set the next contact date.</p>
            <label className="interaction-field">
              Call notes
              <textarea
                value={notes}
                maxLength={3000}
                rows={4}
                placeholder="Key requirements, budget, next steps discussion…"
                onChange={event => setNotes(event.target.value)}
              />
            </label>
            <label className="interaction-field">
              Next scheduled follow-up ({timeZone})
              <input
                type="datetime-local"
                value={scheduledValue}
                onChange={event => setScheduledValue(event.target.value)}
              />
            </label>
            <button
              className="primary"
              disabled={busy || !scheduledValue}
              onClick={() => void saveContact()}
            >
              {busy ? "Saving notes…" : "Save notes & schedule follow-up"}
            </button>
          </div>
        )}

        {e.notes && !(["Assigned", "Attended", "Follow-ups"].includes(e.status)) && (
          <div className="notes">
            <h3>Previous call notes</h3>
            <p>{e.notes}</p>
          </div>
        )}

        {canWork && !(["Closed", "Open", "Lost"].includes(e.status)) && (
          <OutcomeControls e={e} csrfToken={csrfToken} onChanged={onChanged} onToast={onToast}/>
        )}

        {role === "Staff" && (
          <DeletionRequestControls enquiryId={e.id} csrfToken={csrfToken} onToast={onToast}/>
        )}

        {error && <p className="error" role="alert">{error}</p>}

        <div className="notes" style={{borderBottom: "none"}}>
          <h3>Audit information</h3>
          <p>
            Completed contacts: {e.followUpCount}. Initial creation: {formatBusinessDate(e.createdAt, timeZone)}.
          </p>
        </div>
      </aside>
    </div>
  );
}

function DeletionRequestControls({enquiryId,csrfToken,onToast}:{enquiryId:string;csrfToken:string;onToast:(message:string)=>void}){
  const [request,setRequest] = useState<ApiChangeRequest|null>(null);
  const [loading,setLoading] = useState(true);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api.getEnquiryDeletionRequest(enquiryId)
      .then(value => { if(active) setRequest(value) })
      .catch(problem => { if(active) setError(problem instanceof Error ? problem.message : "Could not check deletion request status") })
      .finally(() => { if(active) setLoading(false) });
    return () => { active = false };
  }, [enquiryId]);

  async function submit(){
    setBusy(true);
    setError("");
    try {
      const created = await api.requestEnquiryDeletion(enquiryId, csrfToken);
      setRequest(created);
      onToast("Deletion request submitted for Manager review");
    } catch(problem) {
      setError(problem instanceof Error ? problem.message : "Could not submit deletion request");
    } finally {
      setBusy(false);
    }
  }

  const requestStatus = request?.status === "approved" ? "Approved — pending Manager final confirmation" : "Pending Manager approval";

  return (
    <section className="notes deletion-request-control">
      <h3>Remove enquiry</h3>
      <p>Submit a formal request to your Manager to archive or remove this enquiry.</p>
      {loading ? (
        <p className="empty-message">Checking approval status…</p>
      ) : request ? (
        <p className="assigned-notice" role="status">Status: {requestStatus}</p>
      ) : (
        <button className="danger-button" disabled={busy} onClick={() => void submit()}>
          {busy ? "Submitting…" : "Request deletion"}
        </button>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function OutcomeControls({e,csrfToken,onChanged,onToast}:{e:Enquiry;csrfToken:string;onChanged:(row:ApiEnquiry)=>void;onToast:(message:string)=>void}){
  const [outcome,setOutcome] = useState<"Closed"|"Open"|"Lost">("Open");
  const [reason,setReason] = useState(e.outcomeReason ?? "");
  const [doNotContact,setDoNotContact] = useState(false);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");

  useEffect(() => {
    setOutcome("Open");
    setReason(e.outcomeReason ?? "");
    setDoNotContact(false);
    setError("");
  }, [e.id, e.outcomeReason]);

  async function save(){
    setBusy(true);
    setError("");
    try {
      const row = await api.updateEnquiryStatus(e.id, {
        status: outcome,
        outcome_reason: reason.trim() || undefined,
        do_not_contact: outcome === "Lost" && doNotContact
      }, csrfToken);
      onChanged(row);
      onToast(`Enquiry marked as ${outcome}`);
    } catch(problem) {
      setError(problem instanceof Error ? problem.message : "Could not update enquiry outcome");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="notes outcome-form">
      <h3>Mark enquiry outcome</h3>
      <label className="interaction-field">
        Select final outcome
        <select value={outcome} onChange={event => setOutcome(event.target.value as "Closed"|"Open"|"Lost")}>
          <option value="Closed">Closed — Deal fulfilled or completed</option>
          <option value="Open">Open — Potential future prospect</option>
          <option value="Lost">Lost — Not proceeding</option>
        </select>
      </label>
      <label className="interaction-field">
        Outcome notes (optional)
        <textarea
          value={reason}
          maxLength={2000}
          rows={2}
          placeholder="Summary of closing decision or customer rationale…"
          onChange={event => setReason(event.target.value)}
        />
      </label>
      {outcome === "Lost" && (
        <label className="dnc-option">
          <input
            type="checkbox"
            checked={doNotContact}
            onChange={event => setDoNotContact(event.target.checked)}
          />
          Customer requested not to be contacted in the future (Do Not Contact)
        </label>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      <button className="secondary" disabled={busy} onClick={() => void save()}>
        {busy ? "Updating…" : "Save final outcome"}
      </button>
    </section>
  );
}

export default function App(){
  const [view,setView]=useState<View>("Overview"),[menu,setMenu]=useState(false),[selected,setSelected]=useState<Enquiry|null>(null),[profile,setProfile]=useState(false),[toast,setToast]=useState(""),[notificationsOpen,setNotificationsOpen]=useState(false);
  const [notifications,setNotifications]=useState<ApiNotification[]>([]),[unreadNotificationCount,setUnreadNotificationCount]=useState(0),[notificationsError,setNotificationsError]=useState(""),[liveNotification,setLiveNotification]=useState<ApiNotification|null>(null);
  const knownNotificationIds=useRef<Set<string>>(new Set());
  const [user,setUser]=useState<ApiUser|null>(null),[csrfToken,setCsrfToken]=useState(""),[authLoading,setAuthLoading]=useState(true),[authBusy,setAuthBusy]=useState(false),[authError,setAuthError]=useState("");
  const [enquiries,setEnquiries]=useState<Enquiry[]>([]),[dataLoading,setDataLoading]=useState(false),[dataError,setDataError]=useState(""),[dueCount,setDueCount]=useState(0),[crmRevision,setCrmRevision]=useState(0);
  const [health,setHealth]=useState<{database:string;business_timezone:string}|null>(null),[healthError,setHealthError]=useState(""),[newEnquiryOpen,setNewEnquiryOpen]=useState(false),[createBusy,setCreateBusy]=useState(false),[createError,setCreateError]=useState("");
  const timeZone=health?.business_timezone||businessTimeZone;
  const role:Role=user?.role==="manager"?"Manager":"Staff";
  const [theme,setTheme]=useState(()=>localStorage.getItem("mi-theme")||"light");
  useEffect(()=>{document.documentElement.dataset.theme=theme;localStorage.setItem("mi-theme",theme)},[theme]);
  useEffect(()=>{let active=true;api.me().then(session=>{if(active){setUser(session.user);setCsrfToken(session.csrf_token);setAuthError("")}}).catch(error=>{if(active&&(!(error instanceof ApiError)||error.status!==401))setAuthError(error instanceof Error?`Could not connect to the backend: ${error.message}`:"Could not connect to the backend")}).finally(()=>{if(active)setAuthLoading(false)});return()=>{active=false}},[]);
  useEffect(()=>{
    if(!user)return;
    let active=true;
    let initialized=false;
    const known=knownNotificationIds.current;
    async function loadNotifications(){
      try{
        const page=await api.listNotifications();
        if(!active)return;
        const fresh=initialized?page.items.filter(item=>!known.has(item.id)):[];
        page.items.forEach(item=>known.add(item.id));
        initialized=true;
        setNotifications(page.items);
        setUnreadNotificationCount(page.unread_count);
        setNotificationsError("");
        if(fresh.length){
          showLiveNotification(fresh[0]);
          if(fresh.some(item=>item.notification_type==="new_enquiry")){
            const latest=await api.listEnquiries();
            if(active)setEnquiries(latest.items.map(row=>toEnquiry(row,timeZone)));
          }
        }
      }catch(problem){if(active)setNotificationsError(problem instanceof Error?problem.message:"Could not load notifications")}
    }
    known.clear();
    void loadNotifications();
    const timer=window.setInterval(()=>void loadNotifications(),15000);
    const stream=new EventSource("/notifications/stream",{withCredentials:true});
    stream.onmessage=event=>{
      if(!active)return;
      try{
        const item=JSON.parse(event.data) as ApiNotification;
        if(known.has(item.id))return;
        known.add(item.id);
        setNotifications(current=>[item,...current.filter(value=>value.id!==item.id)].slice(0,50));
        setUnreadNotificationCount(current=>current+1);
        setNotificationsError("");
        showLiveNotification(item);
        if(item.notification_type==="new_enquiry"){
          void api.listEnquiries().then(page=>{if(active)setEnquiries(page.items.map(row=>toEnquiry(row,timeZone)))}).catch(()=>undefined);
        }
      }catch{}
    };
    return()=>{active=false;window.clearInterval(timer);stream.close()};
  },[user?.id,csrfToken,timeZone]);
  useEffect(()=>{if(!user)return;let active=true;setDataLoading(true);api.listEnquiries().then(page=>{if(active){setEnquiries(page.items.map(row=>toEnquiry(row,timeZone)));setDataError("")}}).catch(error=>{if(active)setDataError(error instanceof Error?error.message:"Could not load enquiries")}).finally(()=>{if(active)setDataLoading(false)});api.listFollowUps("due-today").then(page=>{if(active)setDueCount(page.total)}).catch(()=>{if(active)setDueCount(0)});api.databaseHealth().then(result=>{if(active){setHealth(result);setHealthError("")}}).catch(error=>{if(active){setHealth(null);setHealthError(error instanceof Error?error.message:"Database unavailable")}});return()=>{active=false}},[user?.id,timeZone]);
  const notify=(x:string)=>{setToast(x);setTimeout(()=>setToast(""),2600)};
  function showLiveNotification(item:ApiNotification){
    setLiveNotification(item);
    window.setTimeout(()=>setLiveNotification(current=>current?.id===item.id?null:current),6000);
  }
  async function openNotification(item:ApiNotification){
    setNotificationsOpen(false);
    if(!item.read_at){
      try{
        const updated=await api.markNotificationRead(item.id,csrfToken);
        setNotifications(current=>current.map(value=>value.id===updated.id?updated:value));
        setUnreadNotificationCount(current=>Math.max(0,current-1));
      }catch(problem){setNotificationsError(problem instanceof Error?problem.message:"Could not update notification")}
    }
    if(item.notification_type==="deletion_request")setView("Settings");
    else if(item.notification_type==="new_enquiry"&&item.enquiry_id){
      try{
        const page=await api.listEnquiries();
        const rows=page.items.map(row=>toEnquiry(row,timeZone));
        setEnquiries(rows);
        const enquiry=rows.find(row=>row.id===item.enquiry_id);
        setView("Enquiries");
        if(enquiry)setSelected(enquiry);
      }catch(problem){setNotificationsError(problem instanceof Error?problem.message:"Could not open enquiry")}
    }else setView("Enquiries");
  }
  async function markAllNotificationsRead(){
    try{
      await api.markAllNotificationsRead(csrfToken);
      const readAt=new Date().toISOString();
      setNotifications(current=>current.map(item=>item.read_at?item:{...item,read_at:readAt}));
      setUnreadNotificationCount(0);
    }catch(problem){setNotificationsError(problem instanceof Error?problem.message:"Could not mark notifications read")}
  }
  async function login(userId:string,password:string){setAuthBusy(true);setAuthError("");try{const session=await api.login(userId,password);setUser(session.user);setCsrfToken(session.csrf_token);setView("Overview")}catch(error){setAuthError(error instanceof Error?error.message:"Sign-in failed")}finally{setAuthBusy(false)}}
  async function logout(){try{await api.logout(csrfToken);setUser(null);setCsrfToken("");setEnquiries([]);setHealth(null);setProfile(false);setView("Overview")}catch(error){if(error instanceof ApiError&&error.status===401){setUser(null);setCsrfToken("")}else notify(error instanceof Error?error.message:"Could not sign out")}}
  async function createEnquiry(payload:{customer:{name:string;phone:string;email?:string};service_type:string;source:string}){setCreateBusy(true);setCreateError("");try{const created=await api.createEnquiry(payload,csrfToken);setEnquiries(current=>[toEnquiry(created,timeZone),...current]);setDueCount(await api.listFollowUps("due-today").then(page=>page.total).catch(()=>0));setNewEnquiryOpen(false);notify("Enquiry created")}catch(error){setCreateError(error instanceof Error?error.message:"Could not create enquiry")}finally{setCreateBusy(false)}}
  function updateEnquiry(row:ApiEnquiry){const updated=toEnquiry(row,timeZone);setEnquiries(current=>current.map(item=>item.id===updated.id?updated:item));setSelected(updated);setCrmRevision(value=>value+1);void api.listFollowUps("due-today").then(page=>setDueCount(page.total)).catch(()=>undefined)}
  function removeEnquiry(enquiryId:string){setEnquiries(current=>current.filter(item=>item.id!==enquiryId));setSelected(current=>current?.id===enquiryId?null:current);setCrmRevision(value=>value+1);void api.listFollowUps("due-today").then(page=>setDueCount(page.total)).catch(()=>undefined)}
  function restoreEnquiry(row:ApiEnquiry){const restored=toEnquiry(row,timeZone);setEnquiries(current=>[restored,...current.filter(item=>item.id!==restored.id)]);setCrmRevision(value=>value+1);void api.listFollowUps("due-today").then(page=>setDueCount(page.total)).catch(()=>undefined)}
  function closeCompletedEnquiry(enquiry:Enquiry){const closed={...enquiry,status:"Closed" as const,nextFollowUpAt:null,priority:false};setEnquiries(current=>current.map(item=>item.id===closed.id?closed:item));setSelected(current=>current?.id===closed.id?closed:current);void api.listFollowUps("due-today").then(page=>setDueCount(page.total)).catch(()=>undefined)}
  const visibleNav = nav.filter(n => n.label !== "Reports" || role === "Manager");

  if (authLoading) {
    return (
      <main className="auth-loading">
        <p>Checking authentication session…</p>
      </main>
    );
  }

  if (!user) {
    return <LoginPage onLogin={login} error={authError} busy={authBusy}/>;
  }

  const initials = user.display_name.split(/\s+/).map(part => part[0]).join("").slice(0, 2).toUpperCase();

  return (
    <div className="app">
      <aside className={`sidebar ${menu ? "open" : ""}`} aria-label="Main Navigation">
        <div className="brand">
          <div className="brand-mark">M</div>
          <div>
            <strong>MI FINS</strong>
            <small>Mahi Homes &amp; Finance</small>
          </div>
        </div>

        <nav>
          <div className="nav-group-title">MAIN NAVIGATION</div>
          {visibleNav.filter(n => ["Overview", "Enquiries", "Follow-ups", "Customers"].includes(n.label)).map(n => (
            <button
              key={n.label}
              className={view === n.label ? "active" : ""}
              onClick={() => {
                setView(n.label);
                setMenu(false);
              }}
            >
              <Icon name={n.icon} size={18}/>
              <span>{n.label}</span>
              {n.label === "Follow-ups" && dueCount > 0 && (
                <span className="nav-badge warning">{dueCount}</span>
              )}
              {n.label === "Enquiries" && enquiries.length > 0 && (
                <span className="nav-badge primary">{enquiries.length}</span>
              )}
            </button>
          ))}

          {visibleNav.some(n => ["Reports", "Settings"].includes(n.label)) && (
            <>
              <div className="nav-group-title">MANAGEMENT</div>
              {visibleNav.filter(n => ["Reports", "Settings"].includes(n.label)).map(n => (
                <button
                  key={n.label}
                  className={view === n.label ? "active" : ""}
                  onClick={() => {
                    setView(n.label);
                    setMenu(false);
                  }}
                >
                  <Icon name={n.icon} size={18}/>
                  <span>{n.label}</span>
                  {n.label === "Settings" && role !== "Manager" && <Icon name="lock" size={13}/>}
                </button>
              ))}
            </>
          )}
        </nav>

        <div className="help">
          <strong>Workspace Support</strong>
          <p>Access operational guides or reach your CRM administrator.</p>
          <button type="button" onClick={() => notify("Support centre is available at support@mifins.com")}>
            Get support
          </button>
        </div>

        <button
          className="side-profile"
          type="button"
          onClick={() => setProfile(!profile)}
          aria-expanded={profile}
          aria-label="User account menu"
        >
          <Avatar initials={initials}/>
          <span>
            <strong>{user.display_name}</strong>
            <small>{role}</small>
          </span>
          <b>···</b>
        </button>
      </aside>

      <main>
        <header className="topbar">
          <button
            className="menu-button"
            type="button"
            onClick={() => setMenu(!menu)}
            aria-label={menu ? "Close menu" : "Open navigation menu"}
          >
            <Icon name="menu"/>
          </button>

          <div className="breadcrumb">
            <Icon name="grid" size={14}/>
            <span>Home</span>
            <span className="sep">/</span>
            <strong>{view}</strong>
          </div>

          <div className="top-actions">
            <span
              className={`connection-status ${health?.database === "ok" ? "connected" : "disconnected"}`}
              title={healthError || "Live backend database connection verified"}
            >
              <i/>
              {health?.database === "ok"
                ? `Connected · ${timeZone}`
                : healthError
                ? "Database unavailable"
                : "Checking connection…"}
            </span>

            <button
              className="theme-toggle"
              type="button"
              onClick={() => setTheme(theme === "light" ? "dark" : "light")}
              title={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
            >
              <Icon name={theme === "light" ? "moon" : "sun"} size={16}/>
              <span>{theme === "light" ? "Dark" : "Light"}</span>
            </button>

            <button
              className="icon-button notification"
              type="button"
              title="Notifications"
              aria-label={`Notifications${unreadNotificationCount ? `, ${unreadNotificationCount} unread` : ""}`}
              aria-expanded={notificationsOpen}
              onClick={() => setNotificationsOpen(value=>!value)}
            >
              <Icon name="bell" size={18}/>
              {unreadNotificationCount>0&&<span className="notification-count">{unreadNotificationCount>99?"99+":unreadNotificationCount}</span>}
            </button>

            <button
              className="profile-trigger"
              type="button"
              onClick={() => setProfile(!profile)}
              aria-expanded={profile}
              aria-label="Toggle profile menu"
            >
              <Avatar initials={initials}/>
              <span className="profile-trigger-name">{user.display_name}</span>
              <Icon name="chevron" size={14}/>
            </button>
          </div>

          {notificationsOpen&&(
            <section className="notifications-menu" aria-label="Notifications">
              <div className="notifications-menu-head">
                <div><strong>Notifications</strong><small>{unreadNotificationCount} unread</small></div>
                {unreadNotificationCount>0&&<button type="button" onClick={()=>void markAllNotificationsRead()}>Mark all read</button>}
              </div>
              {notificationsError&&<p className="error notifications-error" role="alert">{notificationsError}</p>}
              <div className="notifications-list">
                {notifications.length===0?<p className="empty-message">You’re all caught up.</p>:notifications.map(item=>(
                  <button type="button" key={item.id} className={`notification-item${item.read_at?"":" unread"}`} onClick={()=>void openNotification(item)}>
                    <span className="notification-item-dot" aria-hidden="true"/>
                    <span className="notification-item-copy"><strong>{item.title}</strong><span>{item.message}</span><small>{formatBusinessDate(item.created_at,timeZone)}</small></span>
                  </button>
                ))}
              </div>
            </section>
          )}

          {profile && (
            <div className="profile-menu">
              <div>
                <Avatar initials={initials}/>
                <span>
                  <strong>{user.display_name}</strong>
                  <small>{user.email}</small>
                </span>
              </div>
              <p>Signed in as <b>{role}</b></p>
              {user.role === "manager" && (
                <button
                  type="button"
                  onClick={() => {
                    setView("Settings");
                    setProfile(false);
                  }}
                >
                  <Icon name="settings" size={16}/>
                  Staff accounts &amp; access
                </button>
              )}
              <button type="button" onClick={() => void logout()}>
                <Icon name="close" size={16}/>
                Sign out
              </button>
            </div>
          )}
        </header>

        {dataError && (
          <p className="data-banner" role="alert">
            Could not synchronize CRM data: {dataError}
          </p>
        )}

        <div className="content">
          {view === "Overview" && (
            <Overview
              rows={enquiries}
              dueCount={dueCount}
              onOpen={setSelected}
              setView={setView}
              onNew={() => {
                setCreateError("");
                setNewEnquiryOpen(true);
              }}
            />
          )}
          {view === "Enquiries" && (
            <Enquiries
              rows={enquiries}
              onOpen={setSelected}
              onNew={() => {
                setCreateError("");
                setNewEnquiryOpen(true);
              }}
              loading={dataLoading}
              error={dataError}
            />
          )}
          {view === "Follow-ups" && (
            <FollowUps
              onOpen={setSelected}
              onCompleted={closeCompletedEnquiry}
              csrfToken={csrfToken}
              onToast={notify}
              timeZone={timeZone}
              revision={crmRevision}
              role={role}
              userId={user.id}
            />
          )}
          {view === "Customers" && (
            <Customers rows={enquiries} onOpen={setSelected}/>
          )}
          {view === "Reports" && (
            <Reports role={role} rows={enquiries} onOpen={setSelected}/>
          )}
          {view === "Settings" && (
            <Settings
              currentRole={role}
              rows={enquiries}
              csrfToken={csrfToken}
              onToast={notify}
              onDeleted={removeEnquiry}
              onRestored={restoreEnquiry}
            />
          )}
        </div>

        <footer>
          <span>Privacy Policy</span>
          <span>Terms of Service</span>
          <span>Real Estate &amp; Finance CRM Platform</span>
          <b>&copy; 2026 MI FINS · Mahi Homes &amp; Finance</b>
        </footer>
      </main>

      {newEnquiryOpen && (
        <NewEnquiryModal
          onClose={() => setNewEnquiryOpen(false)}
          onCreate={createEnquiry}
          busy={createBusy}
          error={createError}
        />
      )}

      {selected && (
        <Drawer
          e={selected}
          onClose={() => setSelected(null)}
          timeZone={timeZone}
          role={role}
          userId={user.id}
          csrfToken={csrfToken}
          onChanged={updateEnquiry}
          onToast={notify}
        />
      )}

      {toast && (
        <div className="toast" role="status" aria-live="polite">
          <Icon name="check"/>
          <span>{toast}</span>
        </div>
      )}

      {liveNotification&&(
        <aside className="live-notification-toast" role="status" aria-live="polite">
          <button type="button" className="live-notification-main" onClick={()=>void openNotification(liveNotification)}>
            <span className="live-notification-icon"><Icon name="bell" size={18}/></span>
            <span className="live-notification-copy"><strong>{liveNotification.title}</strong><span>{liveNotification.message}</span><small>Just now · Click to view</small></span>
          </button>
          <button type="button" className="live-notification-close" aria-label="Dismiss notification" onClick={()=>setLiveNotification(null)}>×</button>
        </aside>
      )}

      {menu && (
        <div
          className="mobile-scrim"
          onClick={() => setMenu(false)}
          aria-hidden="true"
        />
      )}
    </div>
  );
}
