const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

const initData = tg?.initData || "";
const API_BASE = "";

const STRINGS = {
  ru: {
    support_title: "Поддержка", profile_title: "Профиль",
    tab_support: "Поддержка", tab_profile: "Профиль",
    new_ticket: "+ Новый тикет", no_tickets: "У вас пока нет тикетов.",
    category_placeholder: "Тема обращения", subject_placeholder: "Кратко опишите тему",
    message_placeholder: "Опишите проблему...", send: "Отправить",
    reply_placeholder: "Ваше сообщение...", fill_required: "Заполните тему и сообщение",
    status_open: "Открыт", status_in_progress: "В работе", status_closed: "Закрыт",
    subscription_active: "Активная подписка", tariff: "Тариф", expires: "Действует до",
    config_link: "Ссылка на конфиг", copy: "Копировать", copied: "Скопировано",
    no_subscription: "У вас нет активной подписки.", balance: "Баланс рефералки",
    referral_invited: "Приглашено", referral_earned: "Заработано",
  },
  en: {
    support_title: "Support", profile_title: "Profile",
    tab_support: "Support", tab_profile: "Profile",
    new_ticket: "+ New ticket", no_tickets: "You have no tickets yet.",
    category_placeholder: "Topic", subject_placeholder: "Briefly describe the topic",
    message_placeholder: "Describe the issue...", send: "Send",
    reply_placeholder: "Your message...", fill_required: "Fill in the subject and message",
    status_open: "Open", status_in_progress: "In progress", status_closed: "Closed",
    subscription_active: "Active subscription", tariff: "Plan", expires: "Expires",
    config_link: "Config link", copy: "Copy", copied: "Copied",
    no_subscription: "You have no active subscription.", balance: "Referral balance",
    referral_invited: "Invited", referral_earned: "Earned",
  },
};

let locale = "ru";
let config = { categories: [], brand_name: "Поддержка", accent_color: "#2481cc", logo_url: null };
let me = null;

function tr(key) {
  return (STRINGS[locale] && STRINGS[locale][key]) || STRINGS.ru[key] || key;
}

const views = {
  profile: document.getElementById("profileView"),
  list: document.getElementById("ticketListView"),
  newTicket: document.getElementById("newTicketView"),
  thread: document.getElementById("ticketThreadView"),
};
const title = document.getElementById("title");
const backBtn = document.getElementById("backBtn");
const tabSupport = document.getElementById("tabSupport");
const tabProfile = document.getElementById("tabProfile");

let currentTicketId = null;
let activeTab = "support";

function showView(name) {
  for (const v of Object.values(views)) v.hidden = true;
  views[name].hidden = false;
  backBtn.hidden = name === "list" || name === "profile";
}

function setActiveTab(tab) {
  activeTab = tab;
  tabSupport.classList.toggle("active", tab === "support");
  tabProfile.classList.toggle("active", tab === "profile");
}

async function apiFetch(path, options = {}) {
  const headers = options.body instanceof FormData
    ? { "X-Telegram-Init-Data": initData }
    : { "X-Telegram-Init-Data": initData, "Content-Type": "application/json" };
  const resp = await fetch(API_BASE + path, { ...options, headers: { ...headers, ...(options.headers || {}) } });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

function statusLabel(status) {
  return { open: tr("status_open"), in_progress: tr("status_in_progress"), closed: tr("status_closed") }[status] || status;
}

function applyBranding() {
  document.documentElement.style.setProperty("--accent", config.accent_color || "#2481cc");
  document.title = config.brand_name || tr("support_title");
  const logo = document.getElementById("brandLogo");
  if (config.logo_url) {
    logo.src = config.logo_url;
    logo.hidden = false;
  }
  document.getElementById("tabSupportLabel").textContent = tr("tab_support");
  document.getElementById("tabProfileLabel").textContent = tr("tab_profile");
}

function renderSubscriptionCard() {
  const card = document.getElementById("subscriptionCard");
  const sub = me?.subscription;
  if (!sub) {
    card.innerHTML = `<p style="opacity:.6">${tr("no_subscription")}</p>`;
    return;
  }
  const expires = new Date(sub.expires_at).toLocaleString();
  card.innerHTML = `
    <div class="sub-title">${tr("subscription_active")}</div>
    <div class="sub-row"><span>${tr("tariff")}</span><b>${escapeHtml(sub.tariff_name || "—")}</b></div>
    <div class="sub-row"><span>${tr("expires")}</span><b>${expires}</b></div>
    ${sub.subscription_url ? `
      <div class="sub-link">
        <input type="text" readonly value="${escapeHtml(sub.subscription_url)}" id="configLinkInput">
        <button id="copyLinkBtn" class="secondary-btn">${tr("copy")}</button>
      </div>` : ""}
  `;
  const copyBtn = document.getElementById("copyLinkBtn");
  if (copyBtn) {
    copyBtn.onclick = async () => {
      await navigator.clipboard.writeText(sub.subscription_url);
      copyBtn.textContent = tr("copied");
      setTimeout(() => { copyBtn.textContent = tr("copy"); }, 1500);
    };
  }
}

function renderBalanceCard() {
  const card = document.getElementById("balanceCard");
  card.innerHTML = `
    <div class="sub-title">${tr("balance")}</div>
    <div class="sub-row"><span>${tr("balance")}</span><b>${me.balance}</b></div>
    <div class="sub-row"><span>${tr("referral_invited")}</span><b>${me.referral_count}</b></div>
    <div class="sub-row"><span>${tr("referral_earned")}</span><b>${me.referral_earned}</b></div>
  `;
}

async function renderProfile() {
  title.textContent = tr("profile_title");
  showView("profile");
  if (!me) me = await apiFetch("/api/me");
  renderSubscriptionCard();
  renderBalanceCard();
}

async function renderTicketList() {
  title.textContent = tr("support_title");
  showView("list");
  document.getElementById("newTicketBtn").textContent = tr("new_ticket");
  const tickets = await apiFetch("/api/tickets");
  const list = document.getElementById("ticketList");
  list.innerHTML = "";
  if (tickets.length === 0) {
    list.innerHTML = `<p style="opacity:.6">${tr("no_tickets")}</p>`;
    return;
  }
  for (const tk of tickets) {
    const el = document.createElement("div");
    el.className = "ticket-item";
    const categoryLabel = tk.category ? `${escapeHtml(tk.category)} · ` : "";
    el.innerHTML = `<div class="subject">#${tk.id} ${escapeHtml(tk.subject)}</div><div class="meta">${categoryLabel}${statusLabel(tk.status)} · ${new Date(tk.updated_at).toLocaleString()}</div>`;
    el.onclick = () => openTicket(tk.id);
    list.appendChild(el);
  }
}

function renderMessage(m) {
  const el = document.createElement("div");
  el.className = `msg ${m.sender_type}`;
  let html = m.text ? `<div>${escapeHtml(m.text)}</div>` : "";
  if (m.attachment_url) {
    if (m.attachment_type === "photo") {
      html += `<img src="${m.attachment_url}">`;
    } else {
      html += `<div><a href="${m.attachment_url}" target="_blank" style="color:inherit">📎 файл</a></div>`;
    }
  }
  el.innerHTML = html;
  return el;
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s ?? "";
  return div.innerHTML;
}

async function openTicket(id) {
  currentTicketId = id;
  showView("thread");
  const ticket = await apiFetch(`/api/tickets/${id}`);
  title.textContent = `#${id} ${ticket.subject}`;
  document.getElementById("ticketStatus").textContent = statusLabel(ticket.status);
  const list = document.getElementById("messagesList");
  list.innerHTML = "";
  for (const m of ticket.messages) list.appendChild(renderMessage(m));
  list.scrollTop = list.scrollHeight;
  document.getElementById("replyInput").placeholder = tr("reply_placeholder");
}

function fillNewTicketForm() {
  title.textContent = tr("new_ticket");
  showView("newTicket");
  const select = document.getElementById("categorySelect");
  select.innerHTML = `<option value="">${tr("category_placeholder")}</option>` +
    config.categories.map(c => `<option value="${c.id}">${escapeHtml(c.title)}</option>`).join("");
  document.getElementById("subjectInput").placeholder = tr("subject_placeholder");
  document.getElementById("subjectInput").value = "";
  document.getElementById("messageInput").placeholder = tr("message_placeholder");
  document.getElementById("messageInput").value = "";
  document.getElementById("fileInput").value = "";
  document.getElementById("submitTicketBtn").textContent = tr("send");
}

document.getElementById("newTicketBtn").onclick = fillNewTicketForm;

document.getElementById("submitTicketBtn").onclick = async () => {
  const subject = document.getElementById("subjectInput").value.trim();
  const message = document.getElementById("messageInput").value.trim();
  const categoryId = document.getElementById("categorySelect").value;
  const file = document.getElementById("fileInput").files[0];
  if (!subject || !message) {
    tg?.showAlert(tr("fill_required"));
    return;
  }
  const form = new FormData();
  form.append("subject", subject);
  form.append("message", message);
  if (categoryId) form.append("category_id", categoryId);
  if (file) form.append("file", file);
  const ticket = await apiFetch("/api/tickets", { method: "POST", body: form });
  await openTicket(ticket.id);
};

document.getElementById("sendReplyBtn").onclick = async () => {
  const input = document.getElementById("replyInput");
  const fileInput = document.getElementById("replyFileInput");
  const message = input.value.trim();
  const file = fileInput.files[0];
  if (!message && !file) return;
  const form = new FormData();
  form.append("message", message || "");
  if (file) form.append("file", file);
  await apiFetch(`/api/tickets/${currentTicketId}/messages`, { method: "POST", body: form });
  input.value = "";
  fileInput.value = "";
  await openTicket(currentTicketId);
};

backBtn.onclick = () => (activeTab === "profile" ? renderProfile() : renderTicketList());
tabSupport.onclick = () => { setActiveTab("support"); renderTicketList(); };
tabProfile.onclick = () => { setActiveTab("profile"); renderProfile(); };

async function init() {
  config = await apiFetch("/api/config");
  locale = config.locale || "ru";
  document.documentElement.lang = locale;
  applyBranding();
  await renderTicketList();
}

init();
