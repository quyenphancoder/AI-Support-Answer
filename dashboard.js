let locals = [],
  remote = [],
  syncing = null;
const $ = (id) => document.getElementById(id);
const LOCAL_PAGE_SIZE = 50;
let localPage = 1;
function el(tag, cls, text) {
  const n = document.createElement(tag);
  n.className = cls;
  n.textContent = text;
  return n;
}
async function api(url, options) {
  const r = await fetch(url, options);
  const data = await r.json();
  if (!r.ok) throw Error(data.error || "Request failed");
  return data;
}
function message(id, text) {
  $(id).replaceChildren(el("p", "rounded border border-dashed border-slate-300 p-4 text-sm text-slate-500", text));
}
async function syncArticle(filename) {
  if (syncing !== null) return;
  syncing = filename;
  draw();
  $("sync-status").textContent = "Syncing " + filename + " to OpenAI…";
  try {
    const result = await api("/api/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename }),
    });
    $("sync-status").textContent = result.skipped
      ? filename + " is already synced."
      : filename + " synced successfully.";
    await refresh();
  } catch (e) {
    $("sync-status").textContent = e.message;
  } finally {
    syncing = null;
    draw();
  }
}
function renderSyncStatus(job) {
  if (!job || job.status === "idle") return;
  if (job.status === "running") {
    $("sync-status").textContent = job.operation === "scrape" ? "Scrape all is running in the background..." : "Sync all is running in the background...";
    return;
  }
  if (job.status === "success") {
    const r = job.result || {};
    $("sync-status").textContent = job.operation === "scrape"
      ? `Scrape all completed: ${r.scraped || 0} articles saved locally.`
      :
      `Sync all completed: ${r.selected || 0} selected, ` +
      `${r.added || 0} added, ${r.updated || 0} updated, ${r.skipped || 0} skipped.`;
    return;
  }
  $("sync-status").textContent = job.error || job.message || "Sync all failed.";
}
async function pollSyncStatus() {
  try {
    const job = await api("/api/sync-status");
    renderSyncStatus(job);
    if (job.status === "running") {
      syncing = "__all__";
      draw();
      setTimeout(pollSyncStatus, 2500);
    } else if (job.status !== "idle") {
      syncing = null;
      await refresh();
      // The terminal state has been displayed and the lists are refreshed.
      // Stop polling until the next explicit sync or page load.
      draw();
    }
  } catch (e) {
    syncing = null;
    $("sync-status").textContent = e.message;
    draw();
  }
}
async function syncAll() {
  if (syncing !== null) return;
  syncing = "__all__";
  $("sync-all").disabled = true;
  draw();
  $("sync-status").textContent = "Starting background sync all...";
  try {
    const job = await api("/api/sync-all", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ limit: 0 }),
    });
    renderSyncStatus(job);
    setTimeout(pollSyncStatus, 1500);
  } catch (e) {
    syncing = null;
    $("sync-status").textContent = e.message;
    draw();
  }
}
async function scrapeAll() {
  if (syncing !== null) return;
  syncing = "__scrape__";
  $("scrape-all").disabled = true;
  $("sync-status").textContent = "Starting background scrape all...";
  try {
    const job = await api("/api/scrape-all", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ limit: 0 }) });
    renderSyncStatus(job);
    setTimeout(pollSyncStatus, 1500);
  } catch (e) {
    syncing = null;
    $("sync-status").textContent = e.message;
    draw();
  }
}
function draw() {
  const q = $("search").value.toLowerCase();
  for (const [id, rows] of [
    ["local", locals],
    ["store", remote],
  ]) {
    const filtered = rows.filter((r) =>
      [r.title, r.filename, r.id].join(" ").toLowerCase().includes(q),
    );
    $(id + "-count").textContent = `(${filtered.length}/${rows.length})`;
    $(id).replaceChildren();
    let visible = filtered;
    if (id === "local") {
      const pages = Math.max(1, Math.ceil(filtered.length / LOCAL_PAGE_SIZE));
      localPage = Math.min(localPage, pages);
      const start = (localPage - 1) * LOCAL_PAGE_SIZE;
      visible = filtered.slice(start, start + LOCAL_PAGE_SIZE);
      $("local-page-info").textContent = filtered.length
        ? `${start + 1}–${start + visible.length} of ${filtered.length} · Page ${localPage} of ${pages}`
        : "0 articles";
      $("local-prev").disabled = localPage <= 1;
      $("local-next").disabled = localPage >= pages;
    }
    if (!filtered.length) {
      message(
        id,
        rows.length ? "No matching documents." : "No documents to display.",
      );
      continue;
    }
    for (const r of visible) {
    const row = el("div", "flex items-center gap-3 rounded border border-slate-200 bg-white p-3 shadow-sm", ""),
        info = el("div", "min-w-0 flex-1", "");
      info.append(
        el("div", "font-medium", r.title || r.filename),
        el(
          "div",
          "text-xs text-slate-500",
          `${r.filename}${r.id ? " · " + r.id : ""} · ${(r.bytes / 1024).toFixed(1)} KB`,
        ),
      );
      row.append(info, el("span", "ml-auto shrink-0 whitespace-nowrap rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600", r.sync || r.status));
      if (id === "local") {
        const b = el("button", "rounded bg-slate-200 px-3 py-1 text-sm hover:bg-slate-300", "View");
        b.onclick = () => preview(r.filename);
        row.append(b);
        const s = el(
          "button",
          "rounded bg-emerald-600 px-3 py-1 text-sm text-white hover:bg-emerald-700 disabled:opacity-50",
          syncing === r.filename ? "Syncing…" : "Sync",
        );
        s.disabled = syncing !== null;
        s.onclick = () => syncArticle(r.filename);
        row.append(s);
      }
      $(id).append(row);
    }
  }
}
async function preview(name) {
  $("preview-title").textContent = name;
  $("content").textContent = "Loading…";
  $("preview").showModal();
  try {
    $("content").textContent = (
      await api("/api/article?name=" + encodeURIComponent(name))
    ).content;
  } catch (e) {
    $("content").textContent = e.message;
  }
}
async function refresh() {
  $("refresh").disabled = true;
  $("scrape-all").disabled = syncing !== null;
  $("sync-all").disabled = syncing !== null;
  message("local", "Loading local files…");
  message("store", "Loading OpenAI files…");
  const results = await Promise.allSettled([
    api("/api/local"),
    api("/api/store"),
  ]);
  locals = results[0].status === "fulfilled" ? results[0].value.articles : [];
  remote = results[1].status === "fulfilled" ? results[1].value.files : [];
  draw();
  if (results[0].status === "rejected")
    message("local", results[0].reason.message);
  if (results[1].status === "fulfilled") {
    const d = results[1].value;
    $("store-info").textContent = d.store_id
      ? `${d.name || "Vector store"} · ${d.store_id}`
      : "No store configured";
    if (d.message) message("store", d.message);
  } else {
    $("store-info").textContent = "Live store unavailable";
    message("store", results[1].reason.message);
  }
  $("refresh").disabled = false;
  $("scrape-all").disabled = syncing !== null;
  $("sync-all").disabled = syncing !== null;
}
$("search").oninput = () => {
  localPage = 1;
  draw();
  $("local").scrollTop = 0;
};
$("local-prev").onclick = () => {
  localPage = Math.max(1, localPage - 1);
  draw();
  $("local").scrollTop = 0;
};
$("local-next").onclick = () => {
  localPage += 1;
  draw();
  $("local").scrollTop = 0;
};
$("refresh").onclick = refresh;
$("scrape-all").onclick = scrapeAll;
$("sync-all").onclick = syncAll;
$("close").onclick = () => $("preview").close();
refresh().then(pollSyncStatus);

let chatBusy = false;
const suggestions = [
  "How do I add a YouTube video?",
  "How do I create a playlist?",
  "How do I schedule content on my screens?",
];
function setChatOpen(open) {
  $("chat-panel").hidden = !open;
  $("chat-toggle").setAttribute("aria-expanded", String(open));
  if (open) $("chat-input").focus();
  else $("chat-toggle").focus();
}
function chatBubble(text, kind) {
  const bubble = el("p", kind === "user"
    ? "ml-8 rounded bg-emerald-100 p-2 text-sm"
    : "mr-8 rounded bg-slate-100 p-2 text-sm", text);
  $("chat-messages").append(bubble);
  bubble.scrollIntoView({ block: "nearest" });
  return bubble;
}
function renderAnswer(node, text) {
  // Render plain text safely and make HTTP(S) source URLs clickable.
  node.replaceChildren();
  for (const part of text.split(/(https?:\/\/[^\s<>\[\]]+)/g)) {
    if (/^https?:\/\//.test(part)) {
      const url = part.replace(/[).,;]+$/, "");
      const link = el("a", "", url);
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      node.append(link, document.createTextNode(part.slice(url.length)));
    } else node.append(document.createTextNode(part));
  }
}
async function sendChat(question) {
  question = question.trim();
  if (!question || chatBusy) return;
  chatBusy = true;
  $("chat-input").value = "";
  $("chat-send").disabled = true;
  document
    .querySelectorAll("#chat-suggestions button")
    .forEach((b) => (b.disabled = true));
  chatBubble(question, "user");
  const pending = chatBubble("Searching your documents…", "bot");
  try {
    const result = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    renderAnswer(pending, result.answer);
  } catch (error) {
    pending.textContent = error.message;
    pending.classList.add("error");
  } finally {
    chatBusy = false;
    $("chat-send").disabled = false;
    document
      .querySelectorAll("#chat-suggestions button")
      .forEach((b) => (b.disabled = false));
    pending.scrollIntoView({ block: "nearest" });
  }
}
for (const question of suggestions) {
  const button = el("button", "w-full rounded bg-slate-100 p-2 text-left text-xs hover:bg-slate-200", question);
  button.type = "button";
  button.onclick = () => sendChat(question);
  $("chat-suggestions").append(button);
}
$("chat-toggle").onclick = () => setChatOpen($("chat-panel").hidden);
$("chat-close").onclick = () => setChatOpen(false);
$("chat-form").onsubmit = (event) => {
  event.preventDefault();
  sendChat($("chat-input").value);
};
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("chat-panel").hidden) setChatOpen(false);
});
