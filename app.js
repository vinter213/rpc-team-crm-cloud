const RPC = {
  apiUrl: "https://rpc-team-crm.onrender.com"
};

function $(id) {
  return document.getElementById(id);
}

function setResult(el, type, text) {
  if (!el) return;
  el.classList.remove("ok", "err");
  if (type) el.classList.add(type);
  el.textContent = text;
}

async function rpcFetch(path, options = {}) {
  const url = RPC.apiUrl.replace(/\/$/, "") + path;
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {})
  };

  const res = await fetch(url, { ...options, headers });
  const text = await res.text();

  let data;
  try { data = JSON.parse(text); }
  catch { data = text; }

  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${typeof data === "string" ? data : JSON.stringify(data)}`);
  }

  return data;
}

/* ORDER FORM */
(function initOrderForm() {
  const form = $("orderForm");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const box = $("orderResult");

    const payload = {
      client_name: $("clientName").value.trim(),
      contact: $("clientContact").value.trim(),
      service: $("service").value,
      price: $("price").value.trim(),
      deadline: $("deadline").value.trim(),
      source: $("source").value,
      description: $("description").value.trim(),
      status: "Новый",
      created_from: "rpc-order-site"
    };

    if (!payload.client_name || !payload.contact) {
      setResult(box, "err", "Заполни имя и контакт.");
      return;
    }

    setResult(box, "", "Отправляю заказ...");

    const endpoints = ["/orders", "/api/orders", "/create-order", "/order"];

    let lastError = null;
    for (const ep of endpoints) {
      try {
        await rpcFetch(ep, {
          method: "POST",
          body: JSON.stringify(payload)
        });
        setResult(box, "ok", "Заказ отправлен. Мы скоро свяжемся с тобой.");
        form.reset();
        return;
      } catch (err) {
        lastError = err;
      }
    }

    setResult(box, "err", "Не получилось отправить заказ. Проверь сервер или endpoint. " + (lastError?.message || ""));
  });
})();

/* WORKER REGISTER */
(function initWorkerForm() {
  const form = $("workerForm");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const box = $("workerResult");

    const payload = {
      name: $("wName").value.trim(),
      phone: $("wPhone").value.trim(),
      telegram: $("wTelegram").value.trim(),
      discord: $("wDiscord").value.trim(),
      specialty: $("wSpecialty").value,
      portfolio: $("wPortfolio").value.trim(),
      comment: $("wComment").value.trim(),
      approved: false,
      active: false,
      status: "pending",
      source: "worker-register-site"
    };

    if (!payload.name) {
      setResult(box, "err", "Введи имя или ник.");
      return;
    }

    setResult(box, "", "Отправляю заявку owner...");

    const endpoints = [
      "/worker/register",
      "/workers/register",
      "/api/worker/register",
      "/worker-requests"
    ];

    let lastError = null;
    for (const ep of endpoints) {
      try {
        const data = await rpcFetch(ep, {
          method: "POST",
          body: JSON.stringify(payload)
        });

        const id = data?.worker_id || data?.id || data?._id || payload.name;
        localStorage.setItem("rpc_worker_id", String(id));
        localStorage.setItem("rpc_worker_name", payload.name);

        setResult(box, "ok", `Заявка отправлена. Твой ID: ${id}. Теперь жди подтверждения владельца.`);
        form.reset();
        return;
      } catch (err) {
        lastError = err;
      }
    }

    setResult(box, "err", "Не получилось отправить заявку. Нужно добавить worker endpoint на сервер. " + (lastError?.message || ""));
  });
})();

/* WORKER STATUS */
(function initWorkerStatus() {
  const btn = $("checkWorkerBtn");
  if (!btn) return;

  const input = $("workerIdInput");
  const saved = localStorage.getItem("rpc_worker_id") || localStorage.getItem("rpc_worker_name") || "";
  if (saved) input.value = saved;

  btn.addEventListener("click", async () => {
    const box = $("statusResult");
    const id = input.value.trim();

    if (!id) {
      setResult(box, "err", "Введи ID или имя.");
      return;
    }

    setResult(box, "", "Проверяю...");

    const endpoints = [
      `/worker/status/${encodeURIComponent(id)}`,
      `/workers/${encodeURIComponent(id)}/status`,
      `/api/worker/status/${encodeURIComponent(id)}`,
      `/worker/me?id=${encodeURIComponent(id)}`
    ];

    let lastError = null;
    for (const ep of endpoints) {
      try {
        const data = await rpcFetch(ep);
        const raw = data?.approved ?? data?.active ?? data?.status;
        const approved = raw === true || ["true", "1", "approved", "active", "yes"].includes(String(raw).toLowerCase());

        if (approved) {
          setResult(box, "ok", "Одобрено. Owner подтвердил тебя как работника RPC.");
        } else {
          setResult(box, "", "Заявка ещё ждёт подтверждения owner.");
        }
        return;
      } catch (err) {
        lastError = err;
      }
    }

    setResult(box, "err", "Не получилось проверить статус. " + (lastError?.message || ""));
  });
})();

/* OWNER WORKERS */
function workerId(w) {
  return w.id || w._id || w.worker_id || w.username || w.name || w.phone || "unknown";
}

function workerApproved(w) {
  const raw = w.approved ?? w.active ?? w.status;
  return raw === true || ["true", "1", "approved", "active", "yes"].includes(String(raw).toLowerCase());
}

(function initOwnerWorkers() {
  const btn = $("refreshWorkersBtn");
  const list = $("workersList");
  if (!btn || !list) return;

  async function loadWorkers() {
    list.textContent = "Загружаю...";
    const ownerKey = $("ownerKeyInput")?.value?.trim() || "";

    const endpoints = [
      "/admin/worker-requests",
      "/admin/workers",
      "/workers",
      "/users",
      "/admin/users"
    ];

    let workers = [];
    let lastError = null;

    for (const ep of endpoints) {
      try {
        const data = await rpcFetch(ep, {
          headers: {
            "X-RPC-Owner": "true",
            "X-RPC-No-Login": "true",
            "X-RPC-Owner-Key": ownerKey
          }
        });

        workers = Array.isArray(data)
          ? data
          : data.workers || data.users || data.items || data.data || [];
        break;
      } catch (err) {
        lastError = err;
      }
    }

    if (!Array.isArray(workers)) workers = [];

    $("statTotal").textContent = workers.length;
    $("statPending").textContent = workers.filter(w => !workerApproved(w)).length;
    $("statApproved").textContent = workers.filter(w => workerApproved(w)).length;

    if (!workers.length) {
      list.innerHTML = `<div class="worker-item">Заявок нет или сервер ещё не отдаёт workers endpoint.<br><br>${lastError ? lastError.message : ""}</div>`;
      return;
    }

    list.innerHTML = workers.map(w => {
      const id = workerId(w);
      const approved = workerApproved(w);
      const json = JSON.stringify(w, null, 2).replaceAll("<", "&lt;").replaceAll(">", "&gt;");
      return `
        <article class="worker-item">
          <h3>${w.name || w.username || "Worker"} ${approved ? "✅" : "⏳"}</h3>
          <div class="worker-meta">
            <b>ID:</b> ${id}<br>
            <b>Телефон:</b> ${w.phone || "—"}<br>
            <b>Telegram:</b> ${w.telegram || "—"}<br>
            <b>Discord:</b> ${w.discord || "—"}<br>
            <b>Специализация:</b> ${w.specialty || w.role || "worker"}<br>
            <b>Статус:</b> ${approved ? "Одобрен" : "Ждёт подтверждения"}
            <details><summary>JSON</summary><pre>${json}</pre></details>
          </div>
          <div class="worker-actions">
            <button class="action-btn approve" data-action="approve" data-id="${id}">Одобрить</button>
            <button class="action-btn reject" data-action="reject" data-id="${id}">Отклонить</button>
            <button class="action-btn disable" data-action="disable" data-id="${id}">Отключить</button>
            <button class="action-btn role" data-action="role-worker" data-id="${id}">Worker</button>
            <button class="action-btn role" data-action="role-manager" data-id="${id}">Manager</button>
          </div>
        </article>
      `;
    }).join("");
  }

  async function workerAction(action, id, button) {
    const ownerKey = $("ownerKeyInput")?.value?.trim() || "";
    const actions = {
      approve: {
        body: {},
        endpoints: [`/admin/workers/${id}/approve`, `/workers/${id}/approve`, `/admin/users/${id}/approve`]
      },
      reject: {
        body: {},
        endpoints: [`/admin/workers/${id}/reject`, `/workers/${id}/reject`, `/admin/users/${id}/reject`]
      },
      disable: {
        body: {},
        endpoints: [`/admin/workers/${id}/disable`, `/workers/${id}/disable`, `/admin/users/${id}/disable`]
      },
      "role-worker": {
        body: { role: "worker" },
        endpoints: [`/admin/workers/${id}/role`, `/workers/${id}/role`]
      },
      "role-manager": {
        body: { role: "manager" },
        endpoints: [`/admin/workers/${id}/role`, `/workers/${id}/role`]
      }
    };

    const cfg = actions[action];
    if (!cfg) return;

    button.textContent = "Делаю...";
    let lastError = null;

    for (const ep of cfg.endpoints) {
      try {
        await rpcFetch(ep, {
          method: "POST",
          headers: {
            "X-RPC-Owner": "true",
            "X-RPC-No-Login": "true",
            "X-RPC-Owner-Key": ownerKey
          },
          body: JSON.stringify(cfg.body)
        });
        await loadWorkers();
        return;
      } catch (err) {
        lastError = err;
      }
    }

    alert("Не получилось выполнить действие. Нужен endpoint на сервере.\n\n" + (lastError?.message || ""));
    button.textContent = "Ошибка";
  }

  btn.addEventListener("click", loadWorkers);
  list.addEventListener("click", (e) => {
    const b = e.target;
    if (!b.matches("button[data-action]")) return;
    workerAction(b.dataset.action, b.dataset.id, b);
  });

  loadWorkers();
})();
