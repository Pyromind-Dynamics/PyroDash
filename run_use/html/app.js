(() => {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  let pollTimer = null;
  let activeRunId = null;
  let activeLogKey = "eval";

  function switchTab(name) {
    $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
    $$(".panel").forEach((p) => p.classList.toggle("active", p.id === `panel-${name}`));
  }

  $$(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      switchTab(btn.dataset.tab);
      if (btn.dataset.tab === "history") loadHistory();
    });
  });

  $$(".log-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      activeLogKey = btn.dataset.log;
      $$(".log-tab").forEach((t) => t.classList.toggle("active", t === btn));
      if (activeRunId) pollOnce(activeRunId);
    });
  });

  $("#btn-refresh")?.addEventListener("click", loadHistory);
  $("#btn-view-results")?.addEventListener("click", () => {
    switchTab("history");
    loadHistory().then(() => {
      if (activeRunId) showResults(activeRunId);
    });
  });

  $("#run-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = $("#form-error");
    err.hidden = true;
    const fd = new FormData(e.target);
    const body = {
      mode: "swe_20filter",
      router_mode: fd.get("router_mode"),
      offload_mode: fd.get("offload_mode"),
      model_path: (fd.get("model_path") || "").trim(),
      slm_base_url: (fd.get("slm_base_url") || "").trim(),
      slm_model: (fd.get("slm_model") || "").trim(),
      slm_api_key: (fd.get("slm_api_key") || "dummy").trim(),
      llm_base_url: (fd.get("llm_base_url") || "").trim(),
      llm_model: (fd.get("llm_model") || "").trim(),
      llm_api_key: (fd.get("llm_api_key") || "").trim(),
      adapter_port: Number(fd.get("adapter_port") || 18027),
      vllm_port: Number(fd.get("vllm_port") || 8007),
      workers: Number(fd.get("workers") || 4),
      harness_workers: Number(fd.get("harness_workers") || 8),
      cuda_visible_devices: (fd.get("cuda_visible_devices") || "0").trim(),
      run_id: (fd.get("run_id") || "").trim(),
    };

    const btn = $("#btn-start");
    btn.disabled = true;
    try {
      const res = await fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || res.statusText || "start failed");
      }
      activeRunId = data.run_id;
      $("#progress").hidden = false;
      $("#progress-done").hidden = true;
      $("#progress-run-id").textContent = data.run_id;
      startPolling(data.run_id);
    } catch (ex) {
      err.textContent = String(ex.message || ex);
      err.hidden = false;
    } finally {
      btn.disabled = false;
    }
  });

  function startPolling(runId) {
    if (pollTimer) clearInterval(pollTimer);
    pollOnce(runId);
    pollTimer = setInterval(() => pollOnce(runId), 2500);
  }

  async function pollOnce(runId) {
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
      if (!res.ok) return;
      const data = await res.json();
      const phase = data.phase || data.status?.phase || "unknown";
      const badge = $("#progress-phase");
      badge.textContent = phase;
      badge.className = `phase-badge ${phase}`;
      $("#progress-message").textContent = data.status?.message || "";
      const logText = (data.logs && data.logs[activeLogKey]) || "";
      const pre = $("#progress-log");
      const atBottom = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 40;
      pre.textContent = logText || "(empty)";
      if (atBottom) pre.scrollTop = pre.scrollHeight;

      if (phase === "done" || phase === "failed") {
        $("#progress-done").hidden = false;
        if (pollTimer) {
          clearInterval(pollTimer);
          pollTimer = null;
        }
      }
    } catch (_) {
      /* ignore transient poll errors */
    }
  }

  async function loadHistory() {
    const list = $("#run-list");
    list.innerHTML = "<li class='muted'>加载中…</li>";
    try {
      const res = await fetch("/api/runs");
      const data = await res.json();
      const runs = data.runs || [];
      if (!runs.length) {
        list.innerHTML = "<li class='muted'>暂无 run</li>";
        return;
      }
      list.innerHTML = "";
      for (const r of runs) {
        const li = document.createElement("li");
        li.innerHTML = `
          <span class="id">${escapeHtml(r.run_id)}</span>
          <span class="phase-badge ${escapeHtml(r.phase || "")}">${escapeHtml(r.phase || "—")}</span>
          <span class="muted">${escapeHtml(r.router_mode || "")} · ${escapeHtml(r.updated_at || "")}</span>
        `;
        li.addEventListener("click", () => showResults(r.run_id));
        list.appendChild(li);
      }
    } catch (ex) {
      list.innerHTML = `<li class="error">${escapeHtml(String(ex))}</li>`;
    }
  }

  async function showResults(runId) {
    const detail = $("#result-detail");
    detail.hidden = false;
    $("#result-title").textContent = runId;
    $("#result-summary").textContent = "加载中…";
    $("#result-files").innerHTML = "";
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(runId)}/results`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "failed");
      const s = data.summary || {};
      const st = data.status || {};
      const parts = [
        `<div><strong>phase</strong> ${escapeHtml(st.phase || "—")}</div>`,
        `<div><strong>router</strong> ${escapeHtml(st.router_mode || "—")}</div>`,
        `<div><strong>preds</strong> ${s.preds_exists ? "yes" : "no"}${s.preds_path ? ` (${escapeHtml(s.preds_path)})` : ""}</div>`,
      ];
      if (s.resolved != null || s.total != null) {
        parts.push(
          `<div><strong>resolved</strong> ${s.resolved ?? "?"} / ${s.total ?? "?"}</div>`
        );
      }
      if (s.primary_report) {
        parts.push(`<div><strong>report</strong> ${escapeHtml(s.primary_report)}</div>`);
      }
      $("#result-summary").innerHTML = parts.join("");

      const files = data.files || [];
      const ul = $("#result-files");
      if (!files.length) {
        ul.innerHTML = "<li class='muted'>无文件</li>";
      } else {
        ul.innerHTML = files
          .map(
            (f) =>
              `<li><a href="/api/runs/${encodeURIComponent(runId)}/files/${encodeURI(f)}" target="_blank" rel="noopener">${escapeHtml(f)}</a></li>`
          )
          .join("");
      }
    } catch (ex) {
      $("#result-summary").innerHTML = `<span class="error">${escapeHtml(String(ex))}</span>`;
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
})();
