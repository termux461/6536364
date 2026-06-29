const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

const initData = tg?.initData || "";
const API_BASE = "";

const views = {
  list: document.getElementById("ticketListView"),
  newTicket: document.getElementById("newTicketView"),
  thread: document.getElementById("ticketThreadView"),
};
const title = document.getElementById("title");
const backBtn = document.getElementById("backBtn");

let currentTicketId = null;

function showView(name) {
  for (const v of Object.values(views)) v.hidden = true;
  views[name].hidden = false;
  backBtn.hidden = name === "list";
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
  return { open: "Открыт", in_progress: "В работе", closed: "Закрыт" }[status] || status;
}

async function renderTicketList() {
  title.textContent = "Поддержка";
  showView("list");
  const tickets = await apiFetch("/api/tickets");
  const list = document.getElementById("ticketList");
  list.innerHTML = "";
  if (tickets.length === 0) {
    list.innerHTML = '<p style="opacity:.6">У вас пока нет тикетов.</p>';
    return;
  }
  for (const tk of tickets) {
    const el = document.createElement("div");
    el.className = "ticket-item";
    el.innerHTML = `<div class="subject">#${tk.id} ${tk.subject}</div><div class="meta">${statusLabel(tk.status)} · ${new Date(tk.updated_at).toLocaleString()}</div>`;
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
  div.textContent = s;
  return div.innerHTML;
}

async function openTicket(id) {
  currentTicketId = id;
  title.textContent = `Тикет #${id}`;
  showView("thread");
  const ticket = await apiFetch(`/api/tickets/${id}`);
  document.getElementById("ticketStatus").textContent = statusLabel(ticket.status);
  const list = document.getElementById("messagesList");
  list.innerHTML = "";
  for (const m of ticket.messages) list.appendChild(renderMessage(m));
  list.scrollTop = list.scrollHeight;
}

document.getElementById("newTicketBtn").onclick = () => {
  title.textContent = "Новый тикет";
  showView("newTicket");
  document.getElementById("subjectInput").value = "";
  document.getElementById("messageInput").value = "";
  document.getElementById("fileInput").value = "";
};

document.getElementById("submitTicketBtn").onclick = async () => {
  const subject = document.getElementById("subjectInput").value.trim();
  const message = document.getElementById("messageInput").value.trim();
  const file = document.getElementById("fileInput").files[0];
  if (!subject || !message) {
    tg?.showAlert("Заполните тему и сообщение");
    return;
  }
  const form = new FormData();
  form.append("subject", subject);
  form.append("message", message);
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

backBtn.onclick = () => renderTicketList();

renderTicketList();
