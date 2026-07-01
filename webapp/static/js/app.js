const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

const initData = tg?.initData || "";
const API_BASE = "";

const STRINGS = {
  ru: {
    support_title: "Поддержка", profile_title: "Профиль", tariffs_title: "Тарифы",
    tab_support: "Поддержка", tab_profile: "Профиль", tab_tariffs: "Тарифы",
    new_ticket: "+ Новый тикет", no_tickets: "У вас пока нет тикетов.",
    category_placeholder: "Тема обращения", subject_placeholder: "Кратко опишите тему",
    message_placeholder: "Опишите проблему...", send: "Отправить",
    reply_placeholder: "Ваше сообщение...", fill_required: "Заполните тему и сообщение",
    status_open: "Открыт", status_in_progress: "В работе", status_closed: "Закрыт",
    subscription_active: "Активная подписка", tariff: "Тариф", expires: "Действует до",
    config_link: "Ссылка на конфиг", copy: "Копировать", copied: "Скопировано",
    no_subscription: "У вас нет активной подписки.", balance: "Баланс рефералки",
    referral_invited: "Приглашено", referral_earned: "Заработано",
    qr_title: "QR-код конфига", no_tariffs: "Тарифы недоступны.",
    buy_btn: "Купить", per_day: "дн.", unlimited: "Безлимит",
    traffic: "Трафик", promo_title: "Промокод (необязательно)",
    promo_apply: "Применить", promo_ok: "✅ Скидка {d}% — итого {p} ₽",
    promo_err: "❌ Промокод недействителен", pay_title: "Способ оплаты",
    pay_btn: "Оплатить через", pay_checking: "⏳ Проверяем оплату...",
    pay_success: "✅ Оплата прошла! Обновите профиль.", pay_fail: "❌ Оплата не подтверждена",
    pay_open: "Открыть страницу оплаты",
  },
  en: {
    support_title: "Support", profile_title: "Profile", tariffs_title: "Plans",
    tab_support: "Support", tab_profile: "Profile", tab_tariffs: "Plans",
    new_ticket: "+ New ticket", no_tickets: "You have no tickets yet.",
    category_placeholder: "Topic", subject_placeholder: "Briefly describe the topic",
    message_placeholder: "Describe the issue...", send: "Send",
    reply_placeholder: "Your message...", fill_required: "Fill in the subject and message",
    status_open: "Open", status_in_progress: "In progress", status_closed: "Closed",
    subscription_active: "Active subscription", tariff: "Plan", expires: "Expires",
    config_link: "Config link", copy: "Copy", copied: "Copied",
    no_subscription: "You have no active subscription.", balance: "Referral balance",
    referral_invited: "Invited", referral_earned: "Earned",
    qr_title: "Config QR code", no_tariffs: "No plans available.",
    buy_btn: "Buy", per_day: "d.", unlimited: "Unlimited",
    traffic: "Traffic", promo_title: "Promo code (optional)",
    promo_apply: "Apply", promo_ok: "✅ Discount {d}% — total {p} RUB",
    promo_err: "❌ Promo code invalid", pay_title: "Payment method",
    pay_btn: "Pay via", pay_checking: "⏳ Checking payment...",
    pay_success: "✅ Payment confirmed! Refresh profile.", pay_fail: "❌ Payment not confirmed",
    pay_open: "Open payment page",
  },
};

let locale = "ru";
let config = { categories: [], brand_name: "VPN", accent_color: "#2481cc", logo_url: null };
let me = null;
let tariffs = [];
let payMethods = [];
let activeBuy = { tariffId: null, promoId: null, discountAmount: 0, finalPrice: 0, paymentId: null };

function tr(key, vars) {
  let s = (STRINGS[locale] && STRINGS[locale][key]) || STRINGS.ru[key] || key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, v);
  return s;
}

const views = {
  profile: document.getElementById("profileView"),
  list: document.getElementById("ticketListView"),
  newTicket: document.getElementById("newTicketView"),
  thread: document.getElementById("ticketThreadView"),
  tariffs: document.getElementById("tariffsView"),
  buy: document.getElementById("buyView"),
};
const title = document.getElementById("title");
const backBtn = document.getElementById("backBtn");
const tabSupport = document.getElementById("tabSupport");
const tabTariffs = document.getElementById("tabTariffs");
const tabProfile = document.getElementById("tabProfile");

let currentTicketId = null;
let activeTab = "support";

function showView(name) {
  for (const v of Object.values(views)) v.hidden = true;
  views[name].hidden = false;
  backBtn.hidden = ["list", "profile", "tariffs"].includes(name);
}

function setActiveTab(tab) {
  activeTab = tab;
  tabSupport.classList.toggle("active", tab === "support");
  tabTariffs.classList.toggle("active", tab === "tariffs");
  tabProfile.classList.toggle("active", tab === "profile");
}

async function apiFetch(path, options) {
  options = options || {};
  const headers = options.body instanceof FormData
    ? { "X-Telegram-Init-Data": initData }
    : { "X-Telegram-Init-Data": initData, "Content-Type": "application/json" };
  const resp = await fetch(API_BASE + path, Object.assign({}, options, { headers: Object.assign({}, headers, options.headers || {}) }));
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
  if (config.logo_url) { logo.src = config.logo_url; logo.hidden = false; }
  document.getElementById("tabSupportLabel").textContent = tr("tab_support");
  document.getElementById("tabTariffsLabel").textContent = tr("tab_tariffs");
  document.getElementById("tabProfileLabel").textContent = tr("tab_profile");
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s != null ? s : "";
  return div.innerHTML;
}

// ─── Profile ───────────────────────────────────────────────────────────────

function renderSubscriptionCard() {
  const card = document.getElementById("subscriptionCard");
  const qrCard = document.getElementById("qrCard");
  const sub = me && me.subscription;
  if (!sub) {
    card.innerHTML = "<p style='opacity:.6'>" + tr("no_subscription") + "</p>";
    qrCard.hidden = true;
    return;
  }
  const expires = new Date(sub.expires_at).toLocaleString();
  card.innerHTML = "<div class='sub-title'>" + tr("subscription_active") + "</div>" +
    "<div class='sub-row'><span>" + tr("tariff") + "</span><b>" + escapeHtml(sub.tariff_name || "—") + "</b></div>" +
    "<div class='sub-row'><span>" + tr("expires") + "</span><b>" + expires + "</b></div>" +
    (sub.subscription_url ? "<div class='sub-link' style='margin-top:10px'>" +
      "<input type='text' readonly id='configLinkInput' value='" + escapeHtml(sub.subscription_url) + "'>" +
      "<button id='copyLinkBtn' class='secondary-btn'>" + tr("copy") + "</button></div>" : "");

  const copyBtn = document.getElementById("copyLinkBtn");
  if (copyBtn) {
    copyBtn.onclick = function() {
      navigator.clipboard.writeText(sub.subscription_url).then(function() {
        copyBtn.textContent = tr("copied");
        setTimeout(function() { copyBtn.textContent = tr("copy"); }, 1500);
      });
    };
  }

  if (sub.subscription_url) {
    qrCard.hidden = false;
    document.getElementById("qrTitle").textContent = tr("qr_title");
    const container = document.getElementById("qrContainer");
    container.innerHTML = "";
    if (window.QRCode) {
      new QRCode(container, { text: sub.subscription_url, width: 200, height: 200, correctLevel: QRCode.CorrectLevel.M });
    }
  } else {
    qrCard.hidden = true;
  }
}

function renderBalanceCard() {
  const card = document.getElementById("balanceCard");
  card.innerHTML = "<div class='sub-title'>" + tr("balance") + "</div>" +
    "<div class='sub-row'><span>" + tr("balance") + "</span><b>" + me.balance + "</b></div>" +
    "<div class='sub-row'><span>" + tr("referral_invited") + "</span><b>" + me.referral_count + "</b></div>" +
    "<div class='sub-row'><span>" + tr("referral_earned") + "</span><b>" + me.referral_earned + "</b></div>";
}

async function renderProfile() {
  title.textContent = tr("profile_title");
  showView("profile");
  if (!me) me = await apiFetch("/api/me");
  renderSubscriptionCard();
  renderBalanceCard();
}

// ─── Support ───────────────────────────────────────────────────────────────

async function renderTicketList() {
  title.textContent = tr("support_title");
  showView("list");
  document.getElementById("newTicketBtn").textContent = tr("new_ticket");
  const tickets = await apiFetch("/api/tickets");
  const list = document.getElementById("ticketList");
  list.innerHTML = "";
  if (tickets.length === 0) {
    list.innerHTML = "<p style='opacity:.6'>" + tr("no_tickets") + "</p>";
    return;
  }
  for (const tk of tickets) {
    const el = document.createElement("div");
    el.className = "ticket-item";
    const cat = tk.category ? escapeHtml(tk.category) + " · " : "";
    el.innerHTML = "<div class='subject'>#" + tk.id + " " + escapeHtml(tk.subject) + "</div>" +
      "<div class='meta'>" + cat + statusLabel(tk.status) + " · " + new Date(tk.updated_at).toLocaleString() + "</div>";
    el.onclick = function() { openTicket(tk.id); };
    list.appendChild(el);
  }
}

function renderMessage(m) {
  const el = document.createElement("div");
  el.className = "msg " + m.sender_type;
  let html = m.text ? "<div>" + escapeHtml(m.text) + "</div>" : "";
  if (m.attachment_url) {
    if (m.attachment_type === "photo") html += "<img src='" + m.attachment_url + "'>";
    else html += "<div><a href='" + m.attachment_url + "' target='_blank' style='color:inherit'>📎 файл</a></div>";
  }
  el.innerHTML = html;
  return el;
}

async function openTicket(id) {
  currentTicketId = id;
  showView("thread");
  const ticket = await apiFetch("/api/tickets/" + id);
  title.textContent = "#" + id + " " + ticket.subject;
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
  const sel = document.getElementById("categorySelect");
  sel.innerHTML = "<option value=''>" + tr("category_placeholder") + "</option>" +
    config.categories.map(function(c) { return "<option value='" + c.id + "'>" + escapeHtml(c.title) + "</option>"; }).join("");
  document.getElementById("subjectInput").placeholder = tr("subject_placeholder");
  document.getElementById("subjectInput").value = "";
  document.getElementById("messageInput").placeholder = tr("message_placeholder");
  document.getElementById("messageInput").value = "";
  document.getElementById("fileInput").value = "";
  document.getElementById("submitTicketBtn").textContent = tr("send");
}

document.getElementById("newTicketBtn").onclick = fillNewTicketForm;

document.getElementById("submitTicketBtn").onclick = async function() {
  const subject = document.getElementById("subjectInput").value.trim();
  const message = document.getElementById("messageInput").value.trim();
  const categoryId = document.getElementById("categorySelect").value;
  const file = document.getElementById("fileInput").files[0];
  if (!subject || !message) { if (tg) tg.showAlert(tr("fill_required")); return; }
  const form = new FormData();
  form.append("subject", subject); form.append("message", message);
  if (categoryId) form.append("category_id", categoryId);
  if (file) form.append("file", file);
  const ticket = await apiFetch("/api/tickets", { method: "POST", body: form });
  await openTicket(ticket.id);
};

document.getElementById("sendReplyBtn").onclick = async function() {
  const input = document.getElementById("replyInput");
  const fileInput = document.getElementById("replyFileInput");
  const message = input.value.trim();
  const file = fileInput.files[0];
  if (!message && !file) return;
  const form = new FormData();
  form.append("message", message || "");
  if (file) form.append("file", file);
  await apiFetch("/api/tickets/" + currentTicketId + "/messages", { method: "POST", body: form });
  input.value = ""; fileInput.value = "";
  await openTicket(currentTicketId);
};

// ─── Tariffs & Buy ─────────────────────────────────────────────────────────

async function renderTariffs() {
  title.textContent = tr("tariffs_title");
  showView("tariffs");
  if (!tariffs.length) tariffs = await apiFetch("/api/tariffs");
  const list = document.getElementById("tariffList");
  list.innerHTML = "";
  if (!tariffs.length) {
    list.innerHTML = "<p style='opacity:.6'>" + tr("no_tariffs") + "</p>";
    return;
  }
  tariffs.forEach(function(t) {
    const el = document.createElement("div");
    el.className = "ticket-item";
    const traffic = t.traffic_limit_gb ? t.traffic_limit_gb + " GB" : tr("unlimited");
    el.innerHTML = "<div class='subject'>" + escapeHtml(t.name) + "</div>" +
      "<div class='meta'>" + t.price + " ₽ · " + t.duration_days + " " + tr("per_day") + " · " + tr("traffic") + ": " + traffic + "</div>" +
      (t.description ? "<div class='meta' style='margin-top:4px;opacity:.8'>" + escapeHtml(t.description) + "</div>" : "") +
      "<button class='primary-btn' style='margin-top:10px;width:auto;padding:8px 20px'>" + tr("buy_btn") + "</button>";
    el.querySelector(".primary-btn").onclick = function(e) { e.stopPropagation(); openBuy(t); };
    list.appendChild(el);
  });
}

async function openBuy(tariff) {
  if (!payMethods.length) payMethods = await apiFetch("/api/payment-methods-list");
  activeBuy = { tariffId: tariff.id, promoId: null, discountAmount: 0, finalPrice: tariff.price, paymentId: null };

  title.textContent = escapeHtml(tariff.name);
  showView("buy");

  document.getElementById("buyTariffInfo").innerHTML =
    "<div class='sub-title'>" + escapeHtml(tariff.name) + "</div>" +
    "<div class='sub-row'><span>Цена</span><b id='buyPrice'>" + tariff.price + " ₽</b></div>" +
    "<div class='sub-row'><span>" + tr("expires") + "</span><b>" + tariff.duration_days + " " + tr("per_day") + "</b></div>";
  document.getElementById("promoTitle").textContent = tr("promo_title");
  document.getElementById("applyPromoBtn").textContent = tr("promo_apply");
  document.getElementById("promoInput").value = "";
  document.getElementById("promoResult").textContent = "";
  document.getElementById("payMethodTitle").textContent = tr("pay_title");
  document.getElementById("payStatus").textContent = "";

  const pmList = document.getElementById("payMethodList");
  pmList.innerHTML = "";
  payMethods.forEach(function(m) {
    const btn = document.createElement("button");
    btn.className = "primary-btn";
    btn.style.marginBottom = "8px";
    btn.textContent = tr("pay_btn") + " " + m.title;
    btn.onclick = function() { startPayment(m.code); };
    pmList.appendChild(btn);
  });
}

document.getElementById("applyPromoBtn").onclick = async function() {
  const code = document.getElementById("promoInput").value.trim();
  if (!code) return;
  const resEl = document.getElementById("promoResult");
  try {
    const form = new FormData();
    form.append("code", code.toUpperCase());
    form.append("tariff_id", activeBuy.tariffId);
    const res = await apiFetch("/api/validate-promo", { method: "POST", body: form });
    activeBuy.promoId = res.promo_id;
    activeBuy.discountAmount = res.discount_amount;
    activeBuy.finalPrice = res.final_price;
    resEl.style.color = "green";
    resEl.textContent = tr("promo_ok", { d: res.discount_percent, p: res.final_price });
    document.getElementById("buyPrice").textContent = res.final_price + " ₽";
  } catch(e) {
    resEl.style.color = "red";
    resEl.textContent = tr("promo_err");
  }
};

async function startPayment(providerCode) {
  const statusEl = document.getElementById("payStatus");
  statusEl.textContent = "⏳ Создаём счёт...";
  try {
    const form = new FormData();
    form.append("tariff_id", activeBuy.tariffId);
    form.append("provider", providerCode);
    form.append("promo_code", document.getElementById("promoInput").value.trim().toUpperCase());
    const res = await apiFetch("/api/payments", { method: "POST", body: form });
    activeBuy.paymentId = res.payment_id;

    if (providerCode === "stars" && res.invoice_link && tg) {
      tg.openInvoice(res.invoice_link, async function(status) {
        if (status === "paid") {
          statusEl.textContent = tr("pay_checking");
          await pollPayment();
        } else {
          statusEl.textContent = tr("pay_fail");
        }
      });
    } else if (res.pay_url) {
      statusEl.innerHTML = "<a href='" + escapeHtml(res.pay_url) + "' target='_blank' style='color:var(--accent)'>" + tr("pay_open") + "</a>";
      startPolling();
    }
  } catch(e) {
    statusEl.textContent = "❌ " + e.message;
  }
}

var _pollTimer = null;
function startPolling() {
  if (_pollTimer) clearInterval(_pollTimer);
  var attempts = 0;
  _pollTimer = setInterval(async function() {
    attempts++;
    if (attempts > 36) { clearInterval(_pollTimer); return; }
    try {
      const r = await apiFetch("/api/payments/" + activeBuy.paymentId + "/check");
      if (r.status === "paid") {
        clearInterval(_pollTimer);
        document.getElementById("payStatus").textContent = tr("pay_success");
        me = null;
      }
    } catch(e) {}
  }, 5000);
}

async function pollPayment() {
  const statusEl = document.getElementById("payStatus");
  for (var i = 0; i < 10; i++) {
    await new Promise(function(r) { setTimeout(r, 2000); });
    try {
      const r = await apiFetch("/api/payments/" + activeBuy.paymentId + "/check");
      if (r.status === "paid") { statusEl.textContent = tr("pay_success"); me = null; return; }
    } catch(e) {}
  }
  statusEl.textContent = tr("pay_fail");
}

// ─── Navigation ────────────────────────────────────────────────────────────

backBtn.onclick = function() {
  if (activeTab === "profile") renderProfile();
  else if (activeTab === "tariffs") renderTariffs();
  else renderTicketList();
};
tabSupport.onclick = function() { setActiveTab("support"); renderTicketList(); };
tabTariffs.onclick = function() { setActiveTab("tariffs"); renderTariffs(); };
tabProfile.onclick = function() { setActiveTab("profile"); renderProfile(); };

// ─── Init ──────────────────────────────────────────────────────────────────

async function init() {
  config = await apiFetch("/api/config");
  locale = config.locale || "ru";
  document.documentElement.lang = locale;
  applyBranding();
  await renderTicketList();
}

init();
