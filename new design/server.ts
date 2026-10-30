import express, { Request, Response, NextFunction } from 'express';
import cookieParser from 'cookie-parser';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = 3000;
const SESSION_COOKIE_NAME = 'mi_fins_session';
const BUSINESS_TIMEZONE = 'Asia/Kolkata';

app.use(express.json());
app.use(cookieParser());

// --- In-Memory State & Types ---
interface User {
  id: string;
  user_id: string;
  email: string;
  display_name: string;
  role: 'manager' | 'staff';
  is_active: boolean;
  password_hash: string;
}

interface Customer {
  id: string;
  name: string;
  phone: string;
  email: string | null;
  created_at: string;
  updated_at: string;
}

interface Enquiry {
  id: string;
  customer_id: string;
  service_type: string;
  source: string;
  status: 'New' | 'Assigned' | 'Attended' | 'Follow-ups' | 'Closed' | 'Open' | 'Lost';
  handled_by_id: string | null;
  handled_by_name: string | null;
  notes: string | null;
  outcome_reason: string | null;
  do_not_contact: boolean;
  next_follow_up_at: string | null;
  completed_follow_up_count: number;
  created_at: string;
  updated_at: string;
  deleted_at?: string | null;
  purge_at?: string | null;
}

interface FollowUpRecord {
  id: string;
  enquiry_id: string;
  completed_at: string;
  created_by_user_id: string | null;
  created_at: string;
}

interface ChangeRequest {
  id: string;
  enquiry_id: string;
  request_type: 'edit' | 'delete';
  status: 'pending' | 'approved' | 'rejected' | 'stale' | 'completed';
  original_snapshot: Record<string, unknown>;
  reason: string | null;
  decision_note: string | null;
  submitted_by_name: string | null;
  decided_by_name: string | null;
  created_at: string;
}

interface Session {
  id: string;
  user_id: string;
  csrf_token: string;
  created_at: string;
  expires_at: string;
}

// Helpers
function hashPassword(password: string): string {
  return crypto.createHash('sha256').update(password).digest('hex');
}

const DEMO_PASSWORD = 'MahiDemo-Only-2026!';
const DEMO_PASSWORD_HASH = hashPassword(DEMO_PASSWORD);

// Store
const users: Map<string, User> = new Map();
const sessions: Map<string, Session> = new Map();
const customers: Map<string, Customer> = new Map();
const enquiries: Map<string, Enquiry> = new Map();
const followUps: Map<string, FollowUpRecord> = new Map();
const changeRequests: Map<string, ChangeRequest> = new Map();

// Seed initial users
const managerUser: User = {
  id: 'u-mgr-001',
  user_id: 'demo.manager',
  email: 'demo.manager@example.com',
  display_name: 'Demo Manager',
  role: 'manager',
  is_active: true,
  password_hash: DEMO_PASSWORD_HASH,
};
const staffUser: User = {
  id: 'u-stf-001',
  user_id: 'demo.staff',
  email: 'demo.staff@example.com',
  display_name: 'Demo Staff',
  role: 'staff',
  is_active: true,
  password_hash: DEMO_PASSWORD_HASH,
};
users.set(managerUser.id, managerUser);
users.set(staffUser.id, staffUser);

// Seed Customers & Enquiries
function seedData() {
  const now = new Date();
  const isoNow = now.toISOString();

  // Helper date generators for Asia/Kolkata
  const todayStr = new Intl.DateTimeFormat('en-CA', { timeZone: BUSINESS_TIMEZONE }).format(now);
  const dueTodayIso = `${todayStr}T15:30:00+05:30`;
  const tomorrowStr = new Intl.DateTimeFormat('en-CA', { timeZone: BUSINESS_TIMEZONE }).format(
    new Date(now.getTime() + 24 * 60 * 60 * 1000)
  );
  const upcomingIso = `${tomorrowStr}T11:00:00+05:30`;
  const yesterdayStr = new Intl.DateTimeFormat('en-CA', { timeZone: BUSINESS_TIMEZONE }).format(
    new Date(now.getTime() - 24 * 60 * 60 * 1000)
  );
  const overdueIso = `${yesterdayStr}T14:00:00+05:30`;

  const initialCustomers: Customer[] = [
    {
      id: 'cust-1',
      name: 'Riya Shah',
      phone: '+91 98765 43210',
      email: 'riya.shah@example.com',
      created_at: new Date(now.getTime() - 4 * 86400000).toISOString(),
      updated_at: isoNow,
    },
    {
      id: 'cust-2',
      name: 'Arjun Mehta',
      phone: '+91 98200 12345',
      email: 'arjun.mehta@example.com',
      created_at: new Date(now.getTime() - 3 * 86400000).toISOString(),
      updated_at: isoNow,
    },
    {
      id: 'cust-3',
      name: 'Priya Sharma',
      phone: '+91 98111 22334',
      email: 'priya.sharma@example.com',
      created_at: new Date(now.getTime() - 2 * 86400000).toISOString(),
      updated_at: isoNow,
    },
    {
      id: 'cust-4',
      name: 'Rajesh Verma',
      phone: '+91 97654 32109',
      email: 'rajesh.v@example.com',
      created_at: new Date(now.getTime() - 5 * 86400000).toISOString(),
      updated_at: isoNow,
    },
    {
      id: 'cust-5',
      name: 'Ananya Patel',
      phone: '+91 98450 67890',
      email: 'ananya.patel@example.com',
      created_at: new Date(now.getTime() - 1 * 86400000).toISOString(),
      updated_at: isoNow,
    },
    {
      id: 'cust-6',
      name: 'Vikram Malhotra',
      phone: '+91 99887 76655',
      email: 'vikram.m@example.com',
      created_at: new Date(now.getTime() - 6 * 86400000).toISOString(),
      updated_at: isoNow,
    },
    {
      id: 'cust-7',
      name: 'Sunita Rao',
      phone: '+91 98333 44556',
      email: 'sunita.rao@example.com',
      created_at: new Date(now.getTime() - 7 * 86400000).toISOString(),
      updated_at: isoNow,
    },
  ];

  for (const c of initialCustomers) {
    customers.set(c.id, c);
  }

  const initialEnquiries: Enquiry[] = [
    {
      id: 'enq-1',
      customer_id: 'cust-1',
      service_type: 'Finance/Loans',
      source: 'Website',
      status: 'New',
      handled_by_id: null,
      handled_by_name: null,
      notes: null,
      outcome_reason: null,
      do_not_contact: false,
      next_follow_up_at: null,
      completed_follow_up_count: 0,
      created_at: new Date(now.getTime() - 2 * 3600000).toISOString(),
      updated_at: new Date(now.getTime() - 2 * 3600000).toISOString(),
    },
    {
      id: 'enq-2',
      customer_id: 'cust-2',
      service_type: 'Real Estate',
      source: 'Referral',
      status: 'Follow-ups',
      handled_by_id: staffUser.id,
      handled_by_name: staffUser.display_name,
      notes: 'Looking for a 3BHK flat near Cyber City. Budget approx 1.8 Cr.',
      outcome_reason: null,
      do_not_contact: false,
      next_follow_up_at: dueTodayIso,
      completed_follow_up_count: 1,
      created_at: new Date(now.getTime() - 24 * 3600000).toISOString(),
      updated_at: new Date(now.getTime() - 12 * 3600000).toISOString(),
    },
    {
      id: 'enq-3',
      customer_id: 'cust-3',
      service_type: 'Finance/Loans',
      source: 'Phone',
      status: 'Follow-ups',
      handled_by_id: staffUser.id,
      handled_by_name: staffUser.display_name,
      notes: 'Interested in balance transfer for existing home loan. Requested rate quote.',
      outcome_reason: null,
      do_not_contact: false,
      next_follow_up_at: upcomingIso,
      completed_follow_up_count: 1,
      created_at: new Date(now.getTime() - 48 * 3600000).toISOString(),
      updated_at: new Date(now.getTime() - 20 * 3600000).toISOString(),
    },
    {
      id: 'enq-4',
      customer_id: 'cust-4',
      service_type: 'Real Estate',
      source: 'Walk-in',
      status: 'Follow-ups',
      handled_by_id: staffUser.id,
      handled_by_name: staffUser.display_name,
      notes: 'Commercial shop requirement. Visited office yesterday.',
      outcome_reason: null,
      do_not_contact: false,
      next_follow_up_at: overdueIso,
      completed_follow_up_count: 0,
      created_at: new Date(now.getTime() - 72 * 3600000).toISOString(),
      updated_at: new Date(now.getTime() - 30 * 3600000).toISOString(),
    },
    {
      id: 'enq-5',
      customer_id: 'cust-5',
      service_type: 'Finance/Loans',
      source: 'Google Ads',
      status: 'Closed',
      handled_by_id: managerUser.id,
      handled_by_name: managerUser.display_name,
      notes: 'Sanction letter issued for 75L home loan with SBI.',
      outcome_reason: 'Loan disbursed successfully',
      do_not_contact: false,
      next_follow_up_at: null,
      completed_follow_up_count: 2,
      created_at: new Date(now.getTime() - 96 * 3600000).toISOString(),
      updated_at: new Date(now.getTime() - 10 * 3600000).toISOString(),
    },
    {
      id: 'enq-6',
      customer_id: 'cust-6',
      service_type: 'Real Estate',
      source: 'Website',
      status: 'Open',
      handled_by_id: staffUser.id,
      handled_by_name: staffUser.display_name,
      notes: 'Site visit scheduled for weekend.',
      outcome_reason: 'Client actively comparing two projects',
      do_not_contact: false,
      next_follow_up_at: upcomingIso,
      completed_follow_up_count: 1,
      created_at: new Date(now.getTime() - 120 * 3600000).toISOString(),
      updated_at: new Date(now.getTime() - 40 * 3600000).toISOString(),
    },
    {
      id: 'enq-7',
      customer_id: 'cust-7',
      service_type: 'Finance/Loans',
      source: 'Referral',
      status: 'Lost',
      handled_by_id: staffUser.id,
      handled_by_name: staffUser.display_name,
      notes: 'Client went with local bank offer.',
      outcome_reason: 'Better interest rate elsewhere',
      do_not_contact: false,
      next_follow_up_at: null,
      completed_follow_up_count: 1,
      created_at: new Date(now.getTime() - 140 * 3600000).toISOString(),
      updated_at: new Date(now.getTime() - 50 * 3600000).toISOString(),
    },
  ];

  for (const eq of initialEnquiries) {
    enquiries.set(eq.id, eq);
  }
}
seedData();

// Helper to format ApiEnquiry
function formatApiEnquiry(e: Enquiry) {
  const cust = customers.get(e.customer_id) || {
    id: e.customer_id,
    name: 'Unknown Customer',
    phone: '',
    email: null,
    created_at: e.created_at,
    updated_at: e.updated_at,
  };
  return {
    id: e.id,
    customer: {
      id: cust.id,
      name: cust.name,
      phone: cust.phone,
      email: cust.email,
      created_at: cust.created_at,
    },
    service_type: e.service_type,
    source: e.source,
    status: e.status,
    handled_by_id: e.handled_by_id,
    handled_by_name: e.handled_by_name,
    notes: e.notes,
    outcome_reason: e.outcome_reason,
    do_not_contact: e.do_not_contact,
    next_follow_up_at: e.next_follow_up_at,
    completed_follow_up_count: e.completed_follow_up_count,
    created_at: e.created_at,
    updated_at: e.updated_at,
  };
}

// Authentication Helpers
function getAuthenticatedUser(req: Request): { user: User; session: Session } | null {
  const token = req.cookies?.[SESSION_COOKIE_NAME];
  if (!token) return null;
  const session = sessions.get(token);
  if (!session) return null;
  if (new Date(session.expires_at).getTime() < Date.now()) {
    sessions.delete(token);
    return null;
  }
  const user = users.get(session.user_id);
  if (!user || !user.is_active) return null;
  return { user, session };
}

function requireAuth(req: Request, res: Response, next: NextFunction) {
  const auth = getAuthenticatedUser(req);
  if (!auth) {
    res.status(401).json({ detail: 'Not authenticated' });
    return;
  }
  (req as any).auth = auth;
  next();
}

function requireManager(req: Request, res: Response, next: NextFunction) {
  const auth = getAuthenticatedUser(req);
  if (!auth) {
    res.status(401).json({ detail: 'Not authenticated' });
    return;
  }
  if (auth.user.role !== 'manager') {
    res.status(403).json({ detail: 'Manager role required' });
    return;
  }
  (req as any).auth = auth;
  next();
}

// --- Auth Routes ---
app.post('/auth/login', (req: Request, res: Response) => {
  const { user_id, password } = req.body || {};
  if (!user_id || !password) {
    res.status(400).json({ detail: 'User ID and password required' });
    return;
  }
  const foundUser = Array.from(users.values()).find(
    (u) => u.user_id.toLowerCase() === String(user_id).trim().toLowerCase()
  );
  if (!foundUser || !foundUser.is_active || hashPassword(password) !== foundUser.password_hash) {
    res.status(401).json({ detail: 'Invalid user ID or password' });
    return;
  }

  const rawToken = crypto.randomBytes(32).toString('hex');
  const csrfToken = crypto.randomBytes(24).toString('hex');
  const session: Session = {
    id: rawToken,
    user_id: foundUser.id,
    csrf_token: csrfToken,
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 24 * 3600000 * 7).toISOString(),
  };
  sessions.set(rawToken, session);

  res.cookie(SESSION_COOKIE_NAME, rawToken, {
    maxAge: 7 * 24 * 3600000,
    httpOnly: true,
    sameSite: 'lax',
    path: '/',
  });

  const { password_hash, ...safeUser } = foundUser;
  res.json({
    user: safeUser,
    csrf_token: csrfToken,
  });
});

app.get('/auth/me', (req: Request, res: Response) => {
  const auth = getAuthenticatedUser(req);
  if (!auth) {
    res.status(401).json({ detail: 'Not authenticated' });
    return;
  }
  const { password_hash, ...safeUser } = auth.user;
  res.json({
    user: safeUser,
    csrf_token: auth.session.csrf_token,
  });
});

app.post('/auth/logout', (req: Request, res: Response) => {
  const token = req.cookies?.[SESSION_COOKIE_NAME];
  if (token) {
    sessions.delete(token);
  }
  res.clearCookie(SESSION_COOKIE_NAME, { path: '/' });
  res.status(204).send();
});

// --- User Management (Manager Only) ---
app.get('/users', requireManager, (req: Request, res: Response) => {
  const list = Array.from(users.values()).map(({ password_hash, ...safe }) => safe);
  res.json(list);
});

app.post('/users', requireManager, (req: Request, res: Response) => {
  const { user_id, email, password, display_name } = req.body || {};
  if (!user_id || !email || !password) {
    res.status(400).json({ detail: 'user_id, email, and password required' });
    return;
  }
  const cleanId = String(user_id).trim().toLowerCase();
  const cleanEmail = String(email).trim().toLowerCase();
  const exists = Array.from(users.values()).some(
    (u) => u.user_id === cleanId || u.email.toLowerCase() === cleanEmail
  );
  if (exists) {
    res.status(409).json({ detail: 'User ID or email is already in use' });
    return;
  }
  const newUser: User = {
    id: `u-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    user_id: cleanId,
    email: cleanEmail,
    display_name: display_name || cleanId,
    role: 'staff',
    is_active: true,
    password_hash: hashPassword(password),
  };
  users.set(newUser.id, newUser);
  const { password_hash, ...safe } = newUser;
  res.status(201).json(safe);
});

app.patch('/users/:id/status', requireManager, (req: Request, res: Response) => {
  const targetUser = users.get(req.params.id);
  if (!targetUser || targetUser.role !== 'staff') {
    res.status(404).json({ detail: 'Staff account not found' });
    return;
  }
  targetUser.is_active = Boolean(req.body.is_active);
  if (!targetUser.is_active) {
    // Clear sessions
    for (const [k, sess] of sessions.entries()) {
      if (sess.user_id === targetUser.id) sessions.delete(k);
    }
  }
  const { password_hash, ...safe } = targetUser;
  res.json(safe);
});

// --- Customers ---
app.get('/customers', requireAuth, (req: Request, res: Response) => {
  const list = Array.from(customers.values()).map((c) => ({
    id: c.id,
    name: c.name,
    phone: c.phone,
    email: c.email,
    created_at: c.created_at,
  }));
  res.json(list);
});

app.post('/customers/:id/link', requireAuth, (req: Request, res: Response) => {
  res.json({ success: true });
});

// --- Enquiries ---
app.get('/enquiries', requireAuth, (req: Request, res: Response) => {
  const activeEnquiries = Array.from(enquiries.values())
    .filter((e) => !e.deleted_at)
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .map(formatApiEnquiry);

  res.json({
    items: activeEnquiries,
    total: activeEnquiries.length,
    limit: 100,
    offset: 0,
  });
});

app.get('/enquiries/deleted', requireAuth, (req: Request, res: Response) => {
  const deleted = Array.from(enquiries.values())
    .filter((e) => !!e.deleted_at)
    .map((e) => ({
      ...formatApiEnquiry(e),
      deleted_at: e.deleted_at!,
      purge_at: e.purge_at || new Date(Date.now() + 30 * 86400000).toISOString(),
    }));

  res.json({
    items: deleted,
    total: deleted.length,
    limit: 100,
    offset: 0,
  });
});

app.post('/enquiries', requireAuth, (req: Request, res: Response) => {
  const { customer, service_type, source } = req.body || {};
  if (!customer?.name || !customer?.phone || !service_type || !source) {
    res.status(400).json({ detail: 'Missing required customer or enquiry fields' });
    return;
  }

  // Find or create customer
  let cust = Array.from(customers.values()).find(
    (c) => c.phone.replace(/\D/g, '') === customer.phone.replace(/\D/g, '')
  );
  const now = new Date().toISOString();

  if (!cust) {
    cust = {
      id: `cust-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      name: customer.name.trim(),
      phone: customer.phone.trim(),
      email: customer.email?.trim() || null,
      created_at: now,
      updated_at: now,
    };
    customers.set(cust.id, cust);
  }

  const newEnquiry: Enquiry = {
    id: `enq-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    customer_id: cust.id,
    service_type: service_type.trim(),
    source: source.trim(),
    status: 'New',
    handled_by_id: null,
    handled_by_name: null,
    notes: null,
    outcome_reason: null,
    do_not_contact: false,
    next_follow_up_at: null,
    completed_follow_up_count: 0,
    created_at: now,
    updated_at: now,
  };
  enquiries.set(newEnquiry.id, newEnquiry);
  res.status(201).json(formatApiEnquiry(newEnquiry));
});

app.post('/public/enquiries', (req: Request, res: Response) => {
  const { customer, service_type, source } = req.body || {};
  if (!customer?.name || !customer?.phone) {
    res.status(400).json({ detail: 'Missing customer info' });
    return;
  }
  const now = new Date().toISOString();
  let cust = Array.from(customers.values()).find(
    (c) => c.phone.replace(/\D/g, '') === customer.phone.replace(/\D/g, '')
  );
  if (!cust) {
    cust = {
      id: `cust-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      name: customer.name.trim(),
      phone: customer.phone.trim(),
      email: customer.email?.trim() || null,
      created_at: now,
      updated_at: now,
    };
    customers.set(cust.id, cust);
  }

  const newEnquiry: Enquiry = {
    id: `enq-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    customer_id: cust.id,
    service_type: service_type || 'General',
    source: source || 'Website',
    status: 'New',
    handled_by_id: null,
    handled_by_name: null,
    notes: null,
    outcome_reason: null,
    do_not_contact: false,
    next_follow_up_at: null,
    completed_follow_up_count: 0,
    created_at: now,
    updated_at: now,
  };
  enquiries.set(newEnquiry.id, newEnquiry);
  res.status(202).json({ status: 'accepted', enquiry_id: newEnquiry.id });
});

// Claim enquiry
app.post('/enquiries/:id/claim', requireAuth, (req: Request, res: Response) => {
  const auth = (req as any).auth;
  const eq = enquiries.get(req.params.id);
  if (!eq) {
    res.status(404).json({ detail: 'Enquiry not found' });
    return;
  }
  if (eq.handled_by_id && eq.handled_by_id !== auth.user.id) {
    res.status(409).json({ detail: 'This enquiry has already been claimed by another staff member.' });
    return;
  }
  eq.handled_by_id = auth.user.id;
  eq.handled_by_name = auth.user.display_name;
  if (eq.status === 'New') {
    eq.status = 'Assigned';
  }
  eq.updated_at = new Date().toISOString();
  res.json(formatApiEnquiry(eq));
});

// Update enquiry status
app.patch('/enquiries/:id/status', requireAuth, (req: Request, res: Response) => {
  const eq = enquiries.get(req.params.id);
  if (!eq) {
    res.status(404).json({ detail: 'Enquiry not found' });
    return;
  }
  const { status, outcome_reason, do_not_contact } = req.body;
  if (status) eq.status = status;
  if (outcome_reason !== undefined) eq.outcome_reason = outcome_reason;
  if (do_not_contact !== undefined) eq.do_not_contact = Boolean(do_not_contact);
  eq.updated_at = new Date().toISOString();
  res.json(formatApiEnquiry(eq));
});

// Save contact notes and follow up
app.put('/enquiries/:id/contact', requireAuth, (req: Request, res: Response) => {
  const eq = enquiries.get(req.params.id);
  if (!eq) {
    res.status(404).json({ detail: 'Enquiry not found' });
    return;
  }
  const { notes, next_follow_up_at } = req.body;
  if (notes !== undefined) eq.notes = notes;
  if (next_follow_up_at !== undefined) eq.next_follow_up_at = next_follow_up_at;
  eq.status = 'Follow-ups';
  eq.updated_at = new Date().toISOString();
  res.json(formatApiEnquiry(eq));
});

// Schedule follow-up
app.put('/enquiries/:id/follow-up', requireAuth, (req: Request, res: Response) => {
  const eq = enquiries.get(req.params.id);
  if (!eq) {
    res.status(404).json({ detail: 'Enquiry not found' });
    return;
  }
  eq.next_follow_up_at = req.body.next_follow_up_at || null;
  eq.updated_at = new Date().toISOString();
  res.json(formatApiEnquiry(eq));
});

// Record completed follow-up
app.post('/enquiries/:id/follow-ups', requireAuth, (req: Request, res: Response) => {
  const auth = (req as any).auth;
  const eq = enquiries.get(req.params.id);
  if (!eq) {
    res.status(404).json({ detail: 'Enquiry not found' });
    return;
  }
  const recordId = `fu-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
  const now = new Date().toISOString();
  followUps.set(recordId, {
    id: recordId,
    enquiry_id: eq.id,
    completed_at: now,
    created_by_user_id: auth.user.id,
    created_at: now,
  });
  eq.completed_follow_up_count = (eq.completed_follow_up_count || 0) + 1;
  eq.status = 'Closed';
  eq.updated_at = now;
  res.json({ id: recordId });
});

// List follow up history
app.get('/enquiries/:id/follow-ups', requireAuth, (req: Request, res: Response) => {
  const items = Array.from(followUps.values())
    .filter((f) => f.enquiry_id === req.params.id)
    .sort((a, b) => new Date(b.completed_at).getTime() - new Date(a.completed_at).getTime());
  res.json({ items, total: items.length, limit: 100, offset: 0 });
});

// Follow-ups buckets
app.get('/follow-ups', requireAuth, (req: Request, res: Response) => {
  const bucket = req.query.bucket as 'due-today' | 'upcoming' | 'overdue';
  const now = new Date();
  const todayStr = new Intl.DateTimeFormat('en-CA', { timeZone: BUSINESS_TIMEZONE }).format(now);

  const active = Array.from(enquiries.values()).filter(
    (e) => !e.deleted_at && e.status === 'Follow-ups' && e.next_follow_up_at
  );

  const matched = active.filter((e) => {
    const fDate = new Date(e.next_follow_up_at!);
    const fDayStr = new Intl.DateTimeFormat('en-CA', { timeZone: BUSINESS_TIMEZONE }).format(fDate);
    if (bucket === 'due-today') {
      return fDayStr === todayStr;
    } else if (bucket === 'upcoming') {
      return fDayStr > todayStr;
    } else if (bucket === 'overdue') {
      return fDayStr < todayStr;
    }
    return true;
  });

  res.json({
    items: matched.map(formatApiEnquiry),
    total: matched.length,
    limit: 100,
    offset: 0,
    bucket,
  });
});

// --- Change Requests (Approvals) ---
app.post('/enquiries/:id/change-requests', requireAuth, (req: Request, res: Response) => {
  const auth = (req as any).auth;
  const eq = enquiries.get(req.params.id);
  if (!eq) {
    res.status(404).json({ detail: 'Enquiry not found' });
    return;
  }
  const requestId = `cr-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
  const cr: ChangeRequest = {
    id: requestId,
    enquiry_id: eq.id,
    request_type: req.body.request_type || 'delete',
    status: 'pending',
    original_snapshot: formatApiEnquiry(eq),
    reason: req.body.reason || null,
    decision_note: null,
    submitted_by_name: auth.user.display_name,
    decided_by_name: null,
    created_at: new Date().toISOString(),
  };
  changeRequests.set(requestId, cr);
  res.json(cr);
});

app.get('/enquiries/:id/change-requests', requireAuth, (req: Request, res: Response) => {
  const cr = Array.from(changeRequests.values()).find(
    (c) => c.enquiry_id === req.params.id && (c.status === 'pending' || c.status === 'approved')
  );
  res.json(cr || null);
});

app.get('/change-requests', requireAuth, (req: Request, res: Response) => {
  const statusFilter = req.query.status as string;
  let items = Array.from(changeRequests.values());
  if (statusFilter) {
    items = items.filter((c) => c.status === statusFilter);
  }
  res.json({
    items,
    total: items.length,
    limit: 100,
    offset: 0,
  });
});

app.patch('/change-requests/:id', requireManager, (req: Request, res: Response) => {
  const auth = (req as any).auth;
  const cr = changeRequests.get(req.params.id);
  if (!cr) {
    res.status(404).json({ detail: 'Change request not found' });
    return;
  }
  const { decision, decision_note } = req.body;
  cr.status = decision === 'approve' ? 'approved' : 'rejected';
  cr.decision_note = decision_note || null;
  cr.decided_by_name = auth.user.display_name;
  res.json(cr);
});

app.post('/change-requests/:id/confirm-deletion', requireAuth, (req: Request, res: Response) => {
  const cr = changeRequests.get(req.params.id);
  if (!cr) {
    res.status(404).json({ detail: 'Change request not found' });
    return;
  }
  cr.status = 'completed';
  const eq = enquiries.get(cr.enquiry_id);
  if (eq) {
    const now = new Date();
    eq.deleted_at = now.toISOString();
    eq.purge_at = new Date(now.getTime() + 30 * 86400000).toISOString();
  }
  res.json(cr);
});

app.post('/enquiries/:id/restore', requireAuth, (req: Request, res: Response) => {
  const eq = enquiries.get(req.params.id);
  if (!eq) {
    res.status(404).json({ detail: 'Enquiry not found' });
    return;
  }
  eq.deleted_at = null;
  eq.purge_at = null;
  eq.updated_at = new Date().toISOString();
  res.json(formatApiEnquiry(eq));
});

app.delete('/enquiries/:id/permanent', requireManager, (req: Request, res: Response) => {
  const eq = enquiries.get(req.params.id);
  if (!eq) {
    res.status(404).json({ detail: 'Enquiry not found' });
    return;
  }
  enquiries.delete(eq.id);
  for (const [k, c] of changeRequests.entries()) {
    if (c.enquiry_id === eq.id) changeRequests.delete(k);
  }
  res.json({ enquiry_id: eq.id, customer_deleted: false, permanently_deleted: true });
});

// --- Health ---
app.get('/health', (req: Request, res: Response) => {
  res.json({ status: 'ok' });
});

app.get('/health/database', (req: Request, res: Response) => {
  res.json({
    status: 'ok',
    database: 'ok',
    business_timezone: BUSINESS_TIMEZONE,
  });
});

// --- Vite / Frontend Serving ---
async function startServer() {
  if (process.env.NODE_ENV === 'production') {
    app.use(express.static(path.resolve(__dirname, 'dist')));
    app.get('*', (req: Request, res: Response) => {
      res.sendFile(path.resolve(__dirname, 'dist', 'index.html'));
    });
  } else {
    const { createServer: createViteServer } = await import('vite');
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`[MI FINS CRM] Server running at http://0.0.0.0:${PORT}`);
  });
}

startServer().catch((err) => {
  console.error('Failed to start server:', err);
  process.exit(1);
});
