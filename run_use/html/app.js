(() => {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  let pollTimer = null;
  let activeRunId = null;
  let activeLogKey = "live";
  let previewRunId = null;
  let previewCache = { path: "", text: "", trajData: null };
  let trajViewMode = "chat"; // chat | json

  function switchTab(name) {
    $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
    $$(".panel").forEach((p) => p.classList.toggle("active", p.id === `panel-${name}`));
    document.querySelector(".page")?.classList.toggle("page-wide", name === "history");
  }

  function syncModeFields() {
    const mode = $("#mode-select")?.value || "swe_20filter";
    const isSwe = mode === "swe" || mode === "swe_20filter";
    const isDeep = mode === "deepswe";
    const isTerm = mode === "terminal";
    $$(".mode-swe").forEach((el) => {
      el.hidden = !isSwe;
    });
    $$(".mode-agent").forEach((el) => {
      el.hidden = isSwe;
    });
    $$(".mode-deepswe").forEach((el) => {
      el.hidden = !isDeep;
    });
    $$(".mode-terminal").forEach((el) => {
      el.hidden = !isTerm;
    });
  }

  function syncRouterFields() {
    const router = $("#router-select")?.value || "tag";
    const slmOnly = router === "slm_only";
    const fs = $("#llm-fieldset");
    if (fs) fs.style.opacity = slmOnly ? "0.55" : "1";
    const offloadLabel = $("#offload-mode-label");
    if (offloadLabel) {
      offloadLabel.hidden = slmOnly;
      offloadLabel.style.display = slmOnly ? "none" : "";
    }
    const offloadSelect = $("#offload-mode-select");
    if (offloadSelect) offloadSelect.disabled = slmOnly;
    ["llm-base-url", "llm-model", "llm-api-key"].forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.required = !slmOnly;
      el.placeholder = slmOnly ? "(slm_only: optional)" : el.placeholder;
    });
  }

  $("#mode-select")?.addEventListener("change", syncModeFields);
  $("#router-select")?.addEventListener("change", syncRouterFields);
  syncModeFields();
  syncRouterFields();

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
    const nConcurrentRaw = (fd.get("n_concurrent") || "").toString().trim();
    const router = (fd.get("router_mode") || "tag").toString();
    const body = {
      mode: (fd.get("mode") || "swe_20filter").toString(),
      router_mode: router,
      offload_mode: (fd.get("offload_mode") || "handoff").toString(),
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
      n_concurrent: nConcurrentRaw === "" ? null : Number(nConcurrentRaw),
      n_tasks: (fd.get("n_tasks") || "").toString().trim(),
      deepswe_tasks: (fd.get("deepswe_tasks") || "").trim(),
      tb_dataset: (fd.get("tb_dataset") || "").trim(),
      cuda_visible_devices: (fd.get("cuda_visible_devices") || "0").trim(),
      run_id: (fd.get("run_id") || "").trim(),
    };

    if (router !== "slm_only") {
      if (!body.llm_base_url || !body.llm_api_key || !body.llm_model) {
        err.textContent = "tag/entropy 模式需要填写 LLM_BASE_URL / LLM_MODEL / LLM_API_KEY";
        err.hidden = false;
        return;
      }
    }

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
        const detail = data.detail;
        throw new Error(
          typeof detail === "string" ? detail : JSON.stringify(detail || res.statusText)
        );
      }
      activeRunId = data.run_id;
      $("#progress").hidden = false;
      $("#progress-done").hidden = true;
      $("#progress-run-id").textContent = `${data.run_id} · ${body.mode} · ${body.router_mode}`;
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
    activeLogKey = "live";
    $$(".log-tab").forEach((t) => t.classList.toggle("active", t.dataset.log === "live"));
    pollOnce(runId);
    pollTimer = setInterval(() => pollOnce(runId), 1000);
  }

  function renderInstanceProgress(progress) {
    const box = $("#instance-progress");
    if (!box) return;
    if (!progress || (!progress.done && !progress.total && !progress.label)) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    $("#instance-progress-label").textContent = progress.label || `${progress.done || 0} done`;
    const done = Number(progress.done) || 0;
    const total = progress.total != null ? Number(progress.total) : null;
    let pct = "";
    let width = 0;
    if (total && total > 0) {
      width = Math.min(100, Math.round((done / total) * 100));
      pct = `${width}%`;
    } else if (done > 0) {
      width = Math.min(100, 8 + done * 4);
      pct = `${done} done`;
    }
    $("#instance-progress-pct").textContent = pct;
    $("#instance-progress-fill").style.width = `${width}%`;
    const completed = progress.completed || [];
    const tail = completed.slice(-12);
    $("#instance-progress-list").textContent = tail.length
      ? `completed: ${tail.join(", ")}`
      : "";
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
      const mode = data.status?.mode || "";
      $("#progress-message").textContent = [mode, data.status?.message || ""]
        .filter(Boolean)
        .join(" · ");
      renderInstanceProgress(data.progress);

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
      /* ignore */
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
          <span class="muted">${escapeHtml(r.mode || "")} · ${escapeHtml(r.router_mode || "")} · ${escapeHtml(r.updated_at || "")}</span>
        `;
        li.addEventListener("click", () => showResults(r.run_id));
        list.appendChild(li);
      }
    } catch (ex) {
      list.innerHTML = `<li class="error">${escapeHtml(String(ex))}</li>`;
    }
  }

  function pathsToTree(paths) {
    const root = { name: "", children: {}, files: [] };
    for (const full of paths) {
      const parts = full.split("/").filter(Boolean);
      let node = root;
      for (let i = 0; i < parts.length; i++) {
        const part = parts[i];
        const isFile = i === parts.length - 1;
        if (isFile) {
          node.files.push({ name: part, path: full });
        } else {
          if (!node.children[part]) {
            node.children[part] = { name: part, children: {}, files: [] };
          }
          node = node.children[part];
        }
      }
    }
    return root;
  }

  function renderFileTree(container, tree, runId) {
    container.innerHTML = "";
    if (!tree || (!Object.keys(tree.children).length && !tree.files.length)) {
      container.innerHTML = '<p class="muted">无文件</p>';
      return;
    }

    function renderNode(node, parentEl, depth) {
      const dirNames = Object.keys(node.children).sort();
      for (const name of dirNames) {
        const child = node.children[name];
        const dirEl = document.createElement("div");
        dirEl.className = "tree-dir";
        // Expand top 2 levels by default
        if (depth >= 2) dirEl.classList.add("collapsed");

        const row = document.createElement("button");
        row.type = "button";
        row.className = "tree-row";
        row.innerHTML = `<span class="tree-twist">${depth >= 2 ? "▸" : "▾"}</span><span class="tree-icon">📁</span><span class="tree-name">${escapeHtml(name)}</span>`;
        row.addEventListener("click", (e) => {
          e.stopPropagation();
          dirEl.classList.toggle("collapsed");
          const twist = row.querySelector(".tree-twist");
          if (twist) twist.textContent = dirEl.classList.contains("collapsed") ? "▸" : "▾";
        });
        dirEl.appendChild(row);

        const kids = document.createElement("div");
        kids.className = "tree-children";
        dirEl.appendChild(kids);
        parentEl.appendChild(dirEl);
        renderNode(child, kids, depth + 1);
      }

      const files = [...node.files].sort((a, b) => a.name.localeCompare(b.name));
      for (const f of files) {
        const fileEl = document.createElement("div");
        fileEl.className = "tree-file";
        const row = document.createElement("button");
        row.type = "button";
        row.className = "tree-row";
        row.title = f.path;
        row.dataset.path = f.path;
        const icon = f.name.endsWith(".traj.json") ? "💬" : "📄";
        row.innerHTML = `<span class="tree-twist"></span><span class="tree-icon">${icon}</span><span class="tree-name">${escapeHtml(f.name)}</span>`;
        row.addEventListener("click", () => {
          $$("#file-tree .tree-row.active").forEach((b) => b.classList.remove("active"));
          row.classList.add("active");
          previewFile(runId, f.path);
        });
        fileEl.appendChild(row);
        parentEl.appendChild(fileEl);
      }
    }

    renderNode(tree, container, 0);
  }

  async function showResults(runId) {
    const detail = $("#result-detail");
    detail.hidden = false;
    previewRunId = runId;
    previewCache = { path: "", text: "", trajData: null };
    $("#result-title").textContent = runId;
    $("#result-summary").textContent = "加载中…";
    $("#file-tree").innerHTML = "";
    $("#preview-path").textContent = "点击左侧文件预览";
    $("#traj-view-toggle").hidden = true;
    $("#preview-body").innerHTML =
      '<p class="muted">左侧按文件夹选文件；轨迹可在「对话 / JSON」间切换。</p>';
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(runId)}/results`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "failed");
      const s = data.summary || {};
      const st = data.status || {};
      const parts = [
        `<div><strong>mode</strong> ${escapeHtml(st.mode || data.eval_dir || "—")}</div>`,
        `<div><strong>phase</strong> ${escapeHtml(st.phase || "—")}</div>`,
        `<div><strong>router</strong> ${escapeHtml(st.router_mode || "—")}</div>`,
      ];
      if (s.preds_exists != null) {
        parts.push(
          `<div><strong>preds</strong> ${s.preds_exists ? "yes" : "no"}${s.preds_path ? ` (${escapeHtml(s.preds_path)})` : ""}</div>`
        );
      }
      if (s.resolved != null || s.total != null) {
        parts.push(`<div><strong>resolved</strong> ${s.resolved ?? "?"} / ${s.total ?? "?"}</div>`);
      }
      if (s.primary_report) {
        parts.push(`<div><strong>report</strong> ${escapeHtml(s.primary_report)}</div>`);
      }
      if (s.reward_mean != null) {
        parts.push(`<div><strong>reward_mean</strong> ${s.reward_mean}</div>`);
      }
      if (s.n_trials != null) {
        parts.push(`<div><strong>n_trials</strong> ${s.n_trials}</div>`);
      }
      $("#result-summary").innerHTML = parts.join("");

      renderFileTree($("#file-tree"), pathsToTree(data.files || []), runId);
    } catch (ex) {
      $("#result-summary").innerHTML = `<span class="error">${escapeHtml(String(ex))}</span>`;
    }
  }

  function setTrajViewMode(mode) {
    trajViewMode = mode;
    $$("#traj-view-toggle .traj-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.view === mode);
    });
    if (previewCache.trajData) {
      renderTrajPreview();
    }
  }

  $$("#traj-view-toggle .traj-btn").forEach((btn) => {
    btn.addEventListener("click", () => setTrajViewMode(btn.dataset.view));
  });

  function renderTrajPreview() {
    const body = $("#preview-body");
    const data = previewCache.trajData;
    if (!data) return;
    if (trajViewMode === "json") {
      const pretty = JSON.stringify(data, null, 2);
      body.innerHTML = `<pre class="preview-raw">${escapeHtml(pretty.slice(0, 500000))}</pre>`;
    } else {
      body.innerHTML = renderTrajChat(data);
    }
  }

  async function previewFile(runId, filePath) {
    $("#preview-path").textContent = filePath;
    const body = $("#preview-body");
    const toggle = $("#traj-view-toggle");
    body.innerHTML = '<p class="muted">加载中…</p>';
    toggle.hidden = true;
    try {
      const url = `/api/runs/${encodeURIComponent(runId)}/files/${filePath
        .split("/")
        .map(encodeURIComponent)
        .join("/")}`;
      const res = await fetch(url);
      const text = await res.text();
      if (!res.ok) throw new Error(text || res.statusText);

      previewCache = { path: filePath, text, trajData: null };

      if (filePath.endsWith(".traj.json")) {
        try {
          previewCache.trajData = JSON.parse(text);
        } catch {
          body.innerHTML = `<pre class="preview-raw">${escapeHtml(text.slice(0, 200000))}</pre>`;
          return;
        }
        toggle.hidden = false;
        setTrajViewMode(trajViewMode || "chat");
        return;
      }

      if (filePath.endsWith(".json") || filePath.endsWith(".jsonl")) {
        try {
          if (filePath.endsWith(".jsonl")) {
            const lines = text.split("\n").filter(Boolean).slice(0, 200);
            const pretty = lines
              .map((l) => {
                try {
                  return JSON.stringify(JSON.parse(l), null, 2);
                } catch {
                  return l;
                }
              })
              .join("\n---\n");
            body.innerHTML = `<pre class="preview-raw">${escapeHtml(pretty.slice(0, 400000))}</pre>`;
          } else {
            const pretty = JSON.stringify(JSON.parse(text), null, 2);
            body.innerHTML = `<pre class="preview-raw">${escapeHtml(pretty.slice(0, 400000))}</pre>`;
          }
          return;
        } catch {
          /* fall through */
        }
      }

      const clipped = text.length > 400000 ? `${text.slice(0, 400000)}\n\n… truncated …` : text;
      body.innerHTML = `<pre class="preview-raw">${escapeHtml(clipped)}</pre>`;
    } catch (ex) {
      body.innerHTML = `<p class="error">${escapeHtml(String(ex))}</p>`;
    }
  }

  function highlightOffload(text) {
    const esc = escapeHtml(text || "");
    // After escape: <|llm_offload|>N</|llm_offload|> → &lt;|llm_offload|&gt;N&lt;|/llm_offload|&gt;
    return esc
      .replace(
        /&lt;\|llm_offload\|&gt;(\d)&lt;\|\/llm_offload\|&gt;/g,
        '<span class="offload-token">&lt;|llm_offload|&gt;$1&lt;|/llm_offload|&gt;</span>'
      )
      .replace(/&lt;\|llm_offload\|&gt;(\d)/g, '<span class="offload-token">&lt;|llm_offload|&gt;$1</span>')
      .replace(/&lt;\|\/llm_offload\|&gt;/g, '<span class="offload-token">&lt;|/llm_offload|&gt;</span>');
  }

  function renderTrajChat(data) {
    const msgs = Array.isArray(data.messages) ? data.messages : [];
    const meta = [];
    if (data.instance_id) meta.push(`instance: ${escapeHtml(data.instance_id)}`);
    if (data.info?.exit_status) meta.push(`exit: ${escapeHtml(String(data.info.exit_status))}`);
    const head = meta.length
      ? `<p class="muted mono" style="margin:0 0 0.75rem">${meta.join(" · ")}</p>`
      : "";

    if (!msgs.length) {
      return `${head}<p class="muted">无 messages</p><pre class="preview-raw">${escapeHtml(
        JSON.stringify(data, null, 2).slice(0, 200000)
      )}</pre>`;
    }

    const bubbles = msgs
      .map((m) => {
        const role = m.role || "unknown";
        const parts = [];
        const reasoning = m.reasoning_content || m.thinking || "";
        const content = typeof m.content === "string" ? m.content : m.content != null ? JSON.stringify(m.content, null, 2) : "";
        if (reasoning) {
          parts.push(
            `<div class="chat-section-label">reasoning</div><div class="chat-text">${highlightOffload(
              reasoning
            )}</div>`
          );
        }
        if (content) {
          parts.push(
            `<div class="chat-section-label">content</div><div class="chat-text">${highlightOffload(
              content
            )}</div>`
          );
        }
        if (m.tool_calls && m.tool_calls.length) {
          parts.push(
            `<div class="chat-section-label">tool_calls</div><div class="chat-text">${highlightOffload(
              JSON.stringify(m.tool_calls, null, 2)
            )}</div>`
          );
        }
        if (m.tool_call_id) {
          parts.push(
            `<div class="chat-section-label">tool_call_id</div><div class="chat-text">${escapeHtml(
              m.tool_call_id
            )}</div>`
          );
        }
        if (!parts.length) {
          parts.push(`<div class="chat-text muted">(empty)</div>`);
        }
        return `<div class="chat-bubble role-${escapeHtml(role)}"><div class="chat-role">${escapeHtml(
          role
        )}</div>${parts.join("")}</div>`;
      })
      .join("");

    return `${head}<div class="chat-thread">${bubbles}</div>`;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
})();
