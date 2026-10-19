(() => {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  // Prefix for reverse-proxy mounts (e.g. /pub/jp-xxx/1/); local root stays "/".
  const APP_BASE = (window.__APP_BASE__ || "/").replace(/\/?$/, "/");
  function apiUrl(path) {
    const p = String(path || "").replace(/^\//, "");
    return APP_BASE + p;
  }

  let pollTimer = null;
  let activeRunId = null;
  let activeLogKey = "live";
  let previewRunId = null;
  let previewCache = { path: "", text: "", trajData: null };
  let trajViewMode = "chat"; // chat | json
  let leaderboardMode = "swe_20filter";

  function switchTab(name) {
    $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
    $$(".panel").forEach((p) => p.classList.toggle("active", p.id === `panel-${name}`));
    const wide = name === "tables" || name === "files";
    document.querySelector(".page")?.classList.toggle("page-wide", wide);
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

  const ROUTER_HELP = {
    tag:
      "<strong>tag</strong>：小模型在思考中发出控制标记后，把后续推理交给大模型。" +
      "需配置 LLM；配合下方 OFFLOAD_MODE 决定接力方式。",
    entropy:
      "<strong>entropy</strong>：根据思考 token 的熵判断难度；超过阈值则整段交给大模型重写。" +
      "需配置 LLM；不使用 OFFLOAD_MODE。",
    slm_only:
      "<strong>slm_only</strong>：仅跑小模型，不调用大模型、不注入 offload 协议。" +
      "用于下界基线；LLM / ADAPTER_PORT / OFFLOAD_MODE 均不显示。",
  };
  const OFFLOAD_HELP = {
    handoff:
      "<strong>handoff</strong>（常用）：保留小模型已生成内容，用 &lt;part_think&gt; 交给大模型从断点续写。",
    rewrite:
      "<strong>rewrite</strong>：丢弃小模型本轮输出，由大模型按原问题整段重新生成。",
    keep:
      "<strong>keep</strong>：保留小模型文本并让大模型续写，但不走 part_think 协议。",
  };

  function syncRouterHelp() {
    const help = $("#router-help");
    if (!help) return;
    const router = $("#router-select")?.value || "tag";
    const mode = $("#offload-mode-select")?.value || "handoff";
    const parts = [ROUTER_HELP[router] || ""];
    if (router === "tag") parts.push(OFFLOAD_HELP[mode] || "");
    help.innerHTML = parts.filter(Boolean).join("<br>");
  }

  function syncRouterFields() {
    const router = $("#router-select")?.value || "tag";
    const slmOnly = router === "slm_only";
    const isTag = router === "tag";

    const fs = $("#llm-fieldset");
    if (fs) {
      fs.hidden = slmOnly;
      fs.style.opacity = "1";
    }

    const adapterLabel = $("#adapter-port-label");
    if (adapterLabel) adapterLabel.hidden = slmOnly;

    const offloadLabel = $("#offload-mode-label");
    if (offloadLabel) {
      offloadLabel.hidden = slmOnly || !isTag;
      offloadLabel.classList.toggle("is-slm-only-hidden", slmOnly || !isTag);
      offloadLabel.style.setProperty(
        "display",
        slmOnly || !isTag ? "none" : "",
        "important"
      );
    }
    const offloadSelect = $("#offload-mode-select");
    if (offloadSelect) {
      offloadSelect.disabled = slmOnly || !isTag;
      if (slmOnly) offloadSelect.value = "handoff";
    }
    ["llm-base-url", "llm-model", "llm-api-key"].forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.required = !slmOnly;
    });
    syncRouterHelp();
  }

  function syncSlmSource() {
    const source =
      document.querySelector('input[name="slm_source"]:checked')?.value || "local";
    const local = $("#slm-local-fields");
    const remote = $("#slm-remote-fields");
    if (local) local.hidden = source !== "local";
    if (remote) remote.hidden = source !== "remote";
    syncSlmBackend();
  }

  function syncSlmBackend() {
    const backend = $("#slm-backend")?.value || "vllm";
    $$(".backend-vllm").forEach((el) => {
      el.hidden = backend !== "vllm";
    });
    $$(".backend-sglang").forEach((el) => {
      el.hidden = backend !== "sglang";
    });
  }

  $("#mode-select")?.addEventListener("change", syncModeFields);
  $("#router-select")?.addEventListener("change", syncRouterFields);
  $("#offload-mode-select")?.addEventListener("change", syncRouterHelp);
  $$('input[name="slm_source"]').forEach((el) => {
    el.addEventListener("change", syncSlmSource);
  });
  $("#slm-backend")?.addEventListener("change", syncSlmBackend);
  syncModeFields();
  syncRouterFields();
  syncSlmSource();

  $$(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const name = btn.dataset.tab;
      switchTab(name);
      if (name === "tables") loadLeaderboard(leaderboardMode);
      if (name === "files") loadHistory();
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
  $("#btn-refresh-tables")?.addEventListener("click", () => loadLeaderboard(leaderboardMode));
  $("#btn-sync-result")?.addEventListener("click", async () => {
    if (!previewRunId) {
      alert("先选择左侧一个 run");
      return;
    }
    try {
      const res = await fetch(
        apiUrl(`/api/runs/${encodeURIComponent(previewRunId)}/sync_result`),
        { method: "POST" }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "sync failed");
      if (previewRunId) await showResults(previewRunId);
    } catch (ex) {
      alert(String(ex));
    }
  });
  $$("#leaderboard-tabs .lb-tab").forEach((btn) => {
    btn.addEventListener("click", () => loadLeaderboard(btn.dataset.mode));
  });
  $("#btn-view-results")?.addEventListener("click", () => {
    switchTab("files");
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
    const slmSource =
      (fd.get("slm_source") || "local").toString() === "remote" ? "remote" : "local";
    const modelPath = slmSource === "local" ? (fd.get("model_path") || "").trim() : "";
    const slmBaseUrl = slmSource === "remote" ? (fd.get("slm_base_url") || "").trim() : "";
    const slmModel = slmSource === "remote" ? (fd.get("slm_model") || "").trim() : "";
    const slmApiKey =
      slmSource === "remote" ? (fd.get("slm_api_key") || "dummy").trim() : "dummy";
    const body = {
      mode: (fd.get("mode") || "swe_20filter").toString(),
      cluster: (fd.get("cluster") || "us").toString(),
      router_mode: router,
      offload_mode: (fd.get("offload_mode") || "handoff").toString(),
      model_path: modelPath,
      slm_base_url: slmBaseUrl,
      slm_model: slmModel,
      slm_api_key: slmApiKey,
      llm_base_url: router === "slm_only" ? "" : (fd.get("llm_base_url") || "").trim(),
      llm_model: router === "slm_only" ? "" : (fd.get("llm_model") || "").trim(),
      llm_api_key: router === "slm_only" ? "" : (fd.get("llm_api_key") || "").trim(),
      adapter_port: Number(fd.get("adapter_port") || 18027),
      slm_backend: (fd.get("slm_backend") || "vllm").toString(),
      slm_port: Number(fd.get("slm_port") || fd.get("vllm_port") || 8007),
      vllm_port: Number(fd.get("slm_port") || fd.get("vllm_port") || 8007),
      vllm_extra_args: (fd.get("vllm_extra_args") || "").toString().trim(),
      sglang_extra_args: (fd.get("sglang_extra_args") || "").toString().trim(),
      workers: Number(fd.get("workers") || 4),
      harness_workers: Number(fd.get("harness_workers") || 8),
      step_limit: Number(fd.get("step_limit") || 150),
      n_concurrent: nConcurrentRaw === "" ? null : Number(nConcurrentRaw),
      n_tasks: (fd.get("n_tasks") || "").toString().trim(),
      deepswe_tasks: (fd.get("deepswe_tasks") || "").trim(),
      tb_dataset: (fd.get("tb_dataset") || "").trim(),
      cuda_visible_devices: (fd.get("cuda_visible_devices") || "0").trim(),
      run_id: (fd.get("run_id") || "").trim(),
      resume: fd.get("resume") === "1" || fd.get("resume") === "on",
    };

    if (body.resume && !body.run_id) {
      err.textContent = "勾选 resume 时必须填写已有 RUN_ID";
      err.hidden = false;
      return;
    }

    if (slmSource === "local") {
      if (!body.model_path) {
        err.textContent = "请填写 MODEL_PATH（本地权重目录）";
        err.hidden = false;
        return;
      }
    } else if (!body.slm_base_url || !body.slm_model) {
      err.textContent = "远程 SLM 需要填写 SLM_BASE_URL 与 SLM_MODEL";
      err.hidden = false;
      return;
    }

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
      const res = await fetch(apiUrl("/api/runs"), {
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
      const resumeTag = data.resumed ? " · resume" : "";
      $("#progress-run-id").textContent =
        `${data.run_id} · ${body.mode} · ${body.router_mode}${resumeTag}`;
      if (data.resumed) {
        const phaseEl = $("#progress-phase");
        if (phaseEl) phaseEl.textContent = `正在 resume ${data.run_id}`;
      }
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
      const res = await fetch(apiUrl(`/api/runs/${encodeURIComponent(runId)}`));
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

  async function loadLeaderboard(mode) {
    if (mode) leaderboardMode = mode;
    $$("#leaderboard-tabs .lb-tab").forEach((b) => {
      b.classList.toggle("active", b.dataset.mode === leaderboardMode);
    });
    const thead = $("#leaderboard-table thead");
    const tbody = $("#leaderboard-table tbody");
    const empty = $("#leaderboard-empty");
    if (!thead || !tbody) return;
    thead.innerHTML = "";
    tbody.innerHTML = `<tr><td class="muted">加载中…</td></tr>`;
    if (empty) empty.hidden = true;
    try {
      const res = await fetch(
        apiUrl(`/api/leaderboard?mode=${encodeURIComponent(leaderboardMode)}`)
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "leaderboard failed");
      const cols = data.columns || [];
      const rows = data.rows || [];
      if (!cols.length) {
        tbody.innerHTML = "";
        if (empty) {
          empty.hidden = false;
          empty.textContent = data.error || "该 mode 暂无行";
        }
        return;
      }
      thead.innerHTML = `<tr>${cols.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr>`;
      if (!rows.length) {
        tbody.innerHTML = "";
        if (empty) {
          empty.hidden = false;
          empty.textContent = "该 mode 暂无行";
        }
        return;
      }
      tbody.innerHTML = rows
        .map((r) => {
          const highlight =
            previewRunId && (r["模型"] === previewRunId || r.model === previewRunId)
              ? " class=\"lb-hl\""
              : "";
          return `<tr${highlight}>${cols
            .map((c) => `<td>${escapeHtml(r[c] ?? "")}</td>`)
            .join("")}</tr>`;
        })
        .join("");
    } catch (ex) {
      tbody.innerHTML = `<tr><td class="error">${escapeHtml(String(ex))}</td></tr>`;
    }
  }

  async function loadHistory() {
    const list = $("#run-list");
    list.innerHTML = "<li class='muted'>加载中…</li>";
    try {
      const res = await fetch(apiUrl("/api/runs"));
      const data = await res.json();
      const runs = data.runs || [];
      if (!runs.length) {
        list.innerHTML = "<li class='muted'>暂无 run</li>";
        return;
      }
      list.innerHTML = "";
      for (const r of runs) {
        const li = document.createElement("li");
        li.dataset.runId = r.run_id;
        if (previewRunId && previewRunId === r.run_id) li.classList.add("active");
        li.innerHTML = `
          <span class="id">${escapeHtml(r.run_id)}</span>
          <span class="phase-badge ${escapeHtml(r.phase || "")}">${escapeHtml(r.phase || "—")}</span>
          <span class="meta">${escapeHtml(r.mode || "")} · ${escapeHtml(r.router_mode || "")}<br>${escapeHtml(r.updated_at || "")}</span>
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

  function renderMetricsSummary(st, metrics, metricsRow) {
    const mode = st.mode || metrics.mode || "—";
    const router = st.router_mode || metrics.router_mode || "—";
    const off = st.offload_mode || metrics.offload_mode || "—";
    const offLabel = router === "slm_only" ? "—" : off || "—";
    const meta = `mode ${escapeHtml(mode)} · router ${escapeHtml(router)} · offload_mode ${escapeHtml(offLabel)}`;
    let rowHtml = "";
    if (metricsRow) {
      const cells = String(metricsRow)
        .replace(/^\|/, "")
        .replace(/\|$/, "")
        .split("|")
        .map((c) => c.trim());
      const headers = [
        "模型",
        mode === "terminal" || mode === "deepswe" ? "正确率" : "正确数",
        "调用率",
        "轮次调用率",
        "调用次数",
        "总轮次",
        "SLM prompt",
        "SLM output",
        "LLM input",
        "LLM output",
        "slm_cost",
        "llm_cost",
        "cost_sum",
      ];
      rowHtml = `<div class="metrics-table-wrap"><table class="metrics-mini"><thead><tr>${headers
        .map((h) => `<th>${h}</th>`)
        .join("")}</tr></thead><tbody><tr>${cells
        .map((c) => `<td>${escapeHtml(c)}</td>`)
        .join("")}</tr></tbody></table></div>`;
    } else if (metrics && metrics.score) {
      rowHtml = `<div class="muted mono">${escapeHtml(metrics.score)} · 调用率 ${escapeHtml(
        String(metrics.call_rate || "—")
      )} · 轮次调用率 ${escapeHtml(String(metrics.turn_call_rate || "—"))}</div>`;
    }
    return `<div class="run-meta-line">${meta}</div>${rowHtml}`;
  }

  async function showResults(runId) {
    previewRunId = runId;
    previewCache = { path: "", text: "", trajData: null };
    $$("#run-list li").forEach((li) => {
      li.classList.toggle("active", li.dataset.runId === runId);
    });
    const title = $("#result-title");
    if (title) {
      title.textContent = runId;
      title.classList.remove("muted");
    }
    $("#result-summary").textContent = "加载中…";
    $("#file-tree").innerHTML = "";
    $("#preview-path").textContent = "点击左侧文件预览";
    $("#traj-view-toggle").hidden = true;
    $("#preview-body").innerHTML =
      '<p class="muted">左侧按文件夹选文件；轨迹可在「format / JSON」间切换。</p>';
    try {
      const res = await fetch(apiUrl(`/api/runs/${encodeURIComponent(runId)}/results`));
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "failed");
      const st = data.status || {};
      const metrics = data.metrics || {};
      if (st.mode && ["swe_20filter", "swe", "terminal", "deepswe"].includes(st.mode)) {
        leaderboardMode = st.mode;
      }
      $("#result-summary").innerHTML = renderMetricsSummary(st, metrics, data.metrics_row);
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
      const url = apiUrl(
        `/api/runs/${encodeURIComponent(runId)}/files/${filePath
          .split("/")
          .map(encodeURIComponent)
          .join("/")}`
      );
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
