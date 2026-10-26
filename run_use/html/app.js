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
  let previewCache = { path: "", text: "", trajData: null, traces: null };
  let fileTreeTimer = null;
  let openFileKey = "";
  let trajViewMode = "chat"; // chat | json | raw
  let trajFoldMode = "close"; // close | open
  let leaderboardMode = "swe_20filter";
  let leaderboardSection = "slm_only";
  let leaderboardLlm = "all";
  let leaderboardSelectMode = false;
  const SWE_FILTER_MODES = new Set(["swe_20filter", "swe"]);
  const TAB_LS_KEY = "pyrodash_run_use_ui";
  let applyingRoute = false;

  function switchTab(name) {
    $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
    $$(".panel").forEach((p) => p.classList.toggle("active", p.id === `panel-${name}`));
    const wide = name === "tables" || name === "files";
    document.querySelector(".page")?.classList.toggle("page-wide", wide);
  }

  function writeRoute(tab, runId) {
    if (applyingRoute) return;
    const t = tab || $(".tab.active")?.dataset.tab || "run";
    const rid = t === "files" ? String(runId || previewRunId || "") : "";
    const hash = t === "files" && rid ? `#files/${encodeURIComponent(rid)}` : `#${t}`;
    if (location.hash !== hash) {
      history.replaceState(null, "", `${location.pathname}${location.search}${hash}`);
    }
    try {
      localStorage.setItem(TAB_LS_KEY, JSON.stringify({ tab: t, runId: rid }));
    } catch {
      /* ignore */
    }
  }

  function parseRoute() {
    const raw = (location.hash || "").replace(/^#/, "");
    if (raw) {
      const parts = raw.split("/");
      const tab = parts[0];
      if (tab === "files") {
        let runId = parts.slice(1).join("/");
        try {
          runId = decodeURIComponent(runId);
        } catch {
          /* keep */
        }
        return { tab: "files", runId };
      }
      if (tab === "tables" || tab === "run") return { tab, runId: "" };
    }
    try {
      const saved = JSON.parse(localStorage.getItem(TAB_LS_KEY) || "{}");
      if (saved.tab === "run" || saved.tab === "tables" || saved.tab === "files") {
        return { tab: saved.tab, runId: saved.runId || "" };
      }
    } catch {
      /* ignore */
    }
    return { tab: "run", runId: "" };
  }

  async function applyRoute(route) {
    applyingRoute = true;
    try {
      switchTab(route.tab);
      if (route.tab === "tables") await loadLeaderboard(leaderboardMode);
      if (route.tab === "files") {
        await loadHistory();
        if (route.runId) await showResults(route.runId);
      }
    } finally {
      applyingRoute = false;
      writeRoute(route.tab, route.runId);
    }
  }

  const SWE20_FILTER =
    "astropy__astropy-14182|astropy__astropy-14508|django__django-10999|django__django-12262|django__django-13023|django__django-14122|django__django-15268|django__django-16136|django__django-16631|matplotlib__matplotlib-26208|pydata__xarray-3677|pydata__xarray-4094|pylint-dev__pylint-6528|pytest-dev__pytest-6202|scikit-learn__scikit-learn-14894|sphinx-doc__sphinx-10449|sphinx-doc__sphinx-9591|sympy__sympy-13551|sympy__sympy-14531|sympy__sympy-17139";
  const SWE20_FILTER_LINE = `--filter ${SWE20_FILTER}`;

  function syncMiniExtraFilter() {
    const box = $("#mini-extra-args");
    if (!box) return;
    const mode = $("#mode-select")?.value || "swe_20filter";
    const lines = box.value.replace(/\r\n/g, "\n").split("\n");
    const isSelector = (line) => {
      const text = line.trim();
      return text.startsWith("--filter") || text.startsWith("--slice");
    };
    if (mode === "swe") {
      const next = lines.filter((line) => line.trim() !== SWE20_FILTER_LINE);
      box.value = next.join("\n").replace(/\n+$/, "");
      return;
    }
    if (mode === "swe_20filter" && !lines.some(isSelector)) {
      const body = box.value.replace(/\s+$/, "");
      box.value = body ? `${body}\n${SWE20_FILTER_LINE}` : SWE20_FILTER_LINE;
    }
  }

  function syncModeFields() {
    const mode = $("#mode-select")?.value || "swe_20filter";
    const isSwe = mode === "swe" || mode === "swe_20filter";
    const isDeep = mode === "deepswe";
    const isTerm = mode === "terminal";
    syncMiniExtraFilter();
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
      "仍走 adapter（可改 ADAPTER_PORT）。LLM / OFFLOAD_MODE 不显示。",
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
    if (adapterLabel) adapterLabel.hidden = false;

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

  const ENV_LS_KEY = "pyrodash_run_use_python_envs";

  function loadSavedEnvs() {
    try {
      return JSON.parse(localStorage.getItem(ENV_LS_KEY) || "{}") || {};
    } catch {
      return {};
    }
  }

  function saveEnvs(vllmEnv, harnessPython) {
    try {
      localStorage.setItem(
        ENV_LS_KEY,
        JSON.stringify({ vllm_env: vllmEnv, harness_python: harnessPython })
      );
    } catch {
      /* ignore quota */
    }
  }

  async function initPythonEnvFields() {
    const vllmInput = $("#vllm-env");
    const harnessInput = $("#harness-python");
    const hint = $("#env-detect-hint");
    const list = $("#conda-env-suggestions");
    if (!vllmInput || !harnessInput) return;

    const saved = loadSavedEnvs();
    let remoteDefaults = { vllm_env: "", harness_python: "" };
    let suggestions = [];
    try {
      const res = await fetch(apiUrl("/api/envs"));
      const data = await res.json();
      suggestions = Array.isArray(data.envs) ? data.envs : [];
      remoteDefaults = data.defaults || remoteDefaults;
    } catch {
      /* offline / old server */
    }

    if (list) {
      list.innerHTML = suggestions
        .map((p) => `<option value="${escapeHtml(p)}"></option>`)
        .join("");
    }

    if (!vllmInput.value) {
      vllmInput.value = saved.vllm_env || remoteDefaults.vllm_env || "";
    }
    if (!harnessInput.value) {
      harnessInput.value = saved.harness_python || remoteDefaults.harness_python || "";
    }

    if (hint) {
      const n = suggestions.length;
      hint.textContent = n
        ? `已扫描到 ${n} 个 conda 环境，可下拉选择或直接粘贴路径。上次填写会保存在本机浏览器。`
        : "未扫描到 conda envs；请直接填写环境目录或 python 路径。上次填写会保存在本机浏览器。";
    }
  }

  $("#mode-select")?.addEventListener("change", syncModeFields);
  $("#btn-stop")?.addEventListener("click", () => stopRun($("#btn-stop")?.dataset.runId || activeRunId));
  $("#router-select")?.addEventListener("change", syncRouterFields);
  $("#offload-mode-select")?.addEventListener("change", syncRouterHelp);
  $$('input[name="slm_source"]').forEach((el) => {
    el.addEventListener("change", syncSlmSource);
  });
  $("#slm-backend")?.addEventListener("change", syncSlmBackend);
  syncModeFields();
  syncRouterFields();
  syncSlmSource();
  initPythonEnvFields();

  $$(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const name = btn.dataset.tab;
      switchTab(name);
      writeRoute(name, name === "files" ? previewRunId : "");
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
  function setLeaderboardSelectMode(on) {
    leaderboardSelectMode = !!on;
    const delBtn = $("#btn-delete-tables");
    const confirmBtn = $("#btn-confirm-delete-tables");
    const cancelBtn = $("#btn-cancel-delete-tables");
    if (delBtn) delBtn.hidden = leaderboardSelectMode;
    if (confirmBtn) confirmBtn.hidden = !leaderboardSelectMode;
    if (cancelBtn) cancelBtn.hidden = !leaderboardSelectMode;
    loadLeaderboard(leaderboardMode);
  }
  $("#btn-delete-tables")?.addEventListener("click", () => setLeaderboardSelectMode(true));
  $("#btn-cancel-delete-tables")?.addEventListener("click", () => setLeaderboardSelectMode(false));
  $("#btn-confirm-delete-tables")?.addEventListener("click", async () => {
    const models = $$("#leaderboard-tables .lb-check:checked")
      .map((el) => String(el.value || "").trim())
      .filter(Boolean);
    if (!models.length) {
      alert("请先勾选要删除的行");
      return;
    }
    if (
      !confirm(
        `确定从表中删除选中的 ${models.length} 行？\n（只删对比表行，不删 output 目录）`
      )
    ) {
      return;
    }
    try {
      const res = await fetch(apiUrl("/api/leaderboard/rows/delete"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: leaderboardMode, models }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "delete failed");
      leaderboardSelectMode = false;
      const delBtn = $("#btn-delete-tables");
      const confirmBtn = $("#btn-confirm-delete-tables");
      const cancelBtn = $("#btn-cancel-delete-tables");
      if (delBtn) delBtn.hidden = false;
      if (confirmBtn) confirmBtn.hidden = true;
      if (cancelBtn) cancelBtn.hidden = true;
      await loadLeaderboard();
    } catch (ex) {
      alert(String(ex));
    }
  });
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
  $$("#leaderboard-subtabs .lb-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      leaderboardSection = btn.dataset.section || "all";
      loadLeaderboard(leaderboardMode);
    });
  });
  $$("#leaderboard-llm-tabs .lb-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      leaderboardLlm = btn.dataset.llm || "all";
      loadLeaderboard(leaderboardMode);
    });
  });
  $("#leaderboard-tables")?.addEventListener("click", (ev) => {
    if (ev.target.closest(".lb-check")) return;
    const btn = ev.target.closest(".lb-model");
    if (!btn) return;
    openRunFromLeaderboard(btn.dataset.runId);
  });
  $("#leaderboard-tables")?.addEventListener("change", (ev) => {
    const t = ev.target;
    if (!(t instanceof HTMLInputElement)) return;
    if (t.classList.contains("lb-check-all")) {
      $$("#leaderboard-tables .lb-check").forEach((el) => {
        el.checked = t.checked;
      });
    }
  });
  $("#btn-view-results")?.addEventListener("click", () => {
    switchTab("files");
    const rid = activeRunId || previewRunId || "";
    writeRoute("files", rid);
    loadHistory().then(() => {
      if (rid) showResults(rid);
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
    const vllmEnv = (fd.get("vllm_env") || "").toString().trim();
    const harnessPython = (fd.get("harness_python") || "").toString().trim();
    const body = {
      mode: (fd.get("mode") || "swe_20filter").toString(),
      cluster: (fd.get("cluster") || "us").toString(),
      router_mode: router,
      offload_mode: router === "slm_only" ? "—" : (fd.get("offload_mode") || "handoff").toString(),
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
      mini_extra_args: (fd.get("mini_extra_args") || "").toString().trim(),
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
      vllm_env: vllmEnv,
      harness_python: harnessPython,
    };

    if (body.resume && !body.run_id) {
      err.textContent = "勾选 resume 时必须填写已有 RUN_ID";
      err.hidden = false;
      return;
    }

    if (!body.vllm_env) {
      err.textContent = "请填写 vLLM 环境路径（conda env 目录）";
      err.hidden = false;
      return;
    }
    if (!body.harness_python) {
      err.textContent = "请填写 SWE harness 环境路径（含 swebench / mini-extra 的 conda env 或 python）";
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
      saveEnvs(body.vllm_env, body.harness_python);
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

  function isRunningPhase(phase) {
    return phase === "starting_adapter" || phase === "evaluating";
  }

  async function stopRun(runId) {
    if (!runId) return;
    if (!window.confirm(`停止 ${runId}？已完成的题目会保留，之后可以 resume。`)) return;
    const res = await fetch(apiUrl(`/api/runs/${encodeURIComponent(runId)}/stop`), {
      method: "POST",
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data.detail;
      window.alert(typeof detail === "string" ? detail : JSON.stringify(detail || res.statusText));
      return;
    }
    if (activeRunId === runId) pollOnce(runId);
    loadHistory();
  }

  function startPolling(runId) {
    if (pollTimer) clearInterval(pollTimer);
    activeLogKey = "live";
    $$(".log-tab").forEach((t) => t.classList.toggle("active", t.dataset.log === "live"));
    const stopBtn = $("#btn-stop");
    if (stopBtn) {
      stopBtn.hidden = false;
      stopBtn.disabled = false;
      stopBtn.dataset.runId = runId;
    }
    pollOnce(runId);
    pollTimer = setInterval(() => pollOnce(runId), 1000);
  }

  function renderInstanceProgress(progress, phase) {
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
    const finished = phase === "done" || phase === "stopped" || phase === "failed";
    let pct = "";
    let width = 0;
    if (total && total > 0) {
      width = Math.min(100, Math.round((done / total) * 100));
      pct = `${width}%`;
    } else if (done > 0 && finished) {
      width = 100;
      pct = "100%";
    } else if (done > 0) {
      width = Math.min(96, 8 + done * 4);
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
      renderInstanceProgress(data.progress, phase);
      const stopBtn = $("#btn-stop");
      if (stopBtn && stopBtn.dataset.runId === runId) {
        stopBtn.hidden = !isRunningPhase(phase);
      }

      const logText = (data.logs && data.logs[activeLogKey]) || "";
      const pre = $("#progress-log");
      const atBottom = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 40;
      pre.textContent = logText || "(empty)";
      if (atBottom) pre.scrollTop = pre.scrollHeight;

      if (phase === "done" || phase === "failed" || phase === "stopped") {
        const doneBox = $("#progress-done");
        doneBox.hidden = false;
        const doneText = doneBox.querySelector("p");
        if (doneText) {
          doneText.textContent =
            phase === "stopped"
              ? "已停止。已完成的题目还在，勾选 resume 并填写同一个 RUN_ID 可以续跑。"
              : "评测结束。可在「历史结果」查看摘要与文件。";
        }
        if (pollTimer) {
          clearInterval(pollTimer);
          pollTimer = null;
        }
      }
    } catch (_) {
      /* ignore */
    }
  }

  function modelCell(val, runIds) {
    const name = String(val ?? "");
    if (name && runIds.has(name)) {
      return `<td><button type="button" class="lb-model" data-run-id="${escapeHtml(name)}">${escapeHtml(name)}</button></td>`;
    }
    return `<td>${escapeHtml(name)}</td>`;
  }

  function leaderboardTableHtml(cols, rows, runIds) {
    const select = leaderboardSelectMode;
    const body = rows
      .map((r) => {
        const modelName = r["模型"] ?? r.model ?? "";
        const highlight =
          previewRunId && modelName === previewRunId ? " class=\"lb-hl\"" : "";
        const check = select
          ? `<td class="lb-check-cell"><input type="checkbox" class="lb-check" value="${escapeHtml(modelName)}" /></td>`
          : "";
        const cells = cols
          .map((c) => {
            const val = r[c] ?? "";
            if (c === "模型") return modelCell(val, runIds);
            return `<td>${escapeHtml(val)}</td>`;
          })
          .join("");
        return `<tr${highlight}>${check}${cells}</tr>`;
      })
      .join("");
    const checkHead = select
      ? `<th class="lb-check-cell"><input type="checkbox" class="lb-check-all" title="全选" /></th>`
      : "";
    return `<table class="leaderboard-table"><thead><tr>${checkHead}${cols
      .map((c) => `<th>${escapeHtml(c)}</th>`)
      .join("")}</tr></thead><tbody>${body}</tbody></table>`;
  }

  function sectionKey(title) {
    const t = String(title || "").toLowerCase();
    if (t.includes("entropy")) return "entropy";
    if (t.includes("tag")) return "tag";
    if (t.includes("slm") || t.includes("非 offload")) return "slm_only";
    return "";
  }

  function rowLlmFamily(row) {
    const raw = row?.LLM ?? row?.llm_family ?? row?.llm ?? "";
    const s = String(raw || "").trim();
    if (s === "v4.1") return "v4.1";
    if (s === "v4") return "v4";
    return "—";
  }

  function filterRowsByLlm(rows) {
    if (leaderboardLlm === "all") return rows || [];
    return (rows || []).filter((r) => rowLlmFamily(r) === leaderboardLlm);
  }

  async function loadLeaderboard(mode) {
    if (mode) leaderboardMode = mode;
    $$("#leaderboard-tabs .lb-tab").forEach((b) => {
      b.classList.toggle("active", b.dataset.mode === leaderboardMode);
    });
    const filters = $("#leaderboard-filters");
    const llmTabs = $("#leaderboard-llm-tabs");
    const showFilters = SWE_FILTER_MODES.has(leaderboardMode);
    if (filters) filters.hidden = !showFilters;
    // slm_only 不用 LLM，隐藏 LLM 过滤（该维视为 all）
    const hideLlm = showFilters && leaderboardSection === "slm_only";
    if (llmTabs) llmTabs.hidden = hideLlm;
    $$("#leaderboard-subtabs .lb-tab").forEach((b) => {
      b.classList.toggle("active", b.dataset.section === leaderboardSection);
    });
    $$("#leaderboard-llm-tabs .lb-tab").forEach((b) => {
      b.classList.toggle("active", b.dataset.llm === leaderboardLlm);
    });
    const host = $("#leaderboard-tables");
    const empty = $("#leaderboard-empty");
    if (!host) return;
    host.innerHTML = `<p class="muted" style="margin:0.6rem 0.75rem">加载中…</p>`;
    if (empty) empty.hidden = true;
    try {
      const [lbRes, runsRes] = await Promise.all([
        fetch(apiUrl(`/api/leaderboard?mode=${encodeURIComponent(leaderboardMode)}`)),
        fetch(apiUrl("/api/runs")),
      ]);
      const data = await lbRes.json();
      if (!lbRes.ok) throw new Error(data.detail || "leaderboard failed");
      const runsData = runsRes.ok ? await runsRes.json() : { runs: [] };
      const runIds = new Set((runsData.runs || []).map((r) => r.run_id));
      const cols = data.columns || [];
      let sections =
        data.sections && data.sections.length
          ? data.sections
          : [{ title: "", rows: data.rows || [] }];
      if (showFilters) {
        if (leaderboardSection !== "all") {
          const picked = sections.filter(
            (s) => sectionKey(s.title) === leaderboardSection
          );
          sections = picked.length ? picked : [];
        }
        const applyLlm = leaderboardSection !== "slm_only";
        sections = sections
          .map((sec) => ({
            ...sec,
            rows: applyLlm ? filterRowsByLlm(sec.rows || []) : sec.rows || [],
          }))
          .filter((sec) => (sec.rows || []).length > 0);
      }
      const totalRows = sections.reduce((n, s) => n + ((s.rows || []).length), 0);
      if (!cols.length || !totalRows) {
        host.innerHTML = "";
        if (empty) {
          empty.hidden = false;
          empty.textContent = data.error || "该筛选下暂无行";
        }
        return;
      }
      host.innerHTML = sections
        .map((sec) => {
          const title = sec.title
            ? `<div class="lb-section-title">${escapeHtml(sec.title)}</div>`
            : "";
          return `${title}${leaderboardTableHtml(cols, sec.rows || [], runIds)}`;
        })
        .join("");
    } catch (ex) {
      host.innerHTML = `<p class="error" style="margin:0.6rem 0.75rem">${escapeHtml(String(ex))}</p>`;
    }
  }

  async function openRunFromLeaderboard(runId) {
    const id = String(runId || "").trim();
    if (!id) return;
    switchTab("files");
    await loadHistory();
    const found = $(`#run-list li[data-run-id="${CSS.escape(id)}"]`);
    if (!found) {
      alert(`没有同名目录 ${id}`);
      return;
    }
    await showResults(id);
    writeRoute("files", id);
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
        const stopBtn = isRunningPhase(r.phase)
          ? `<button type="button" class="btn danger small" data-stop="${escapeHtml(r.run_id)}">停止</button>`
          : "";
        li.innerHTML = `
          <span class="id">${escapeHtml(r.run_id)}</span>
          <span class="phase-badge ${escapeHtml(r.phase || "")}">${escapeHtml(r.phase || "—")}</span>
          <span class="meta">${escapeHtml(r.mode || "")} · ${escapeHtml(r.router_mode || "")}<br>${escapeHtml(r.updated_at || "")}</span>
          ${stopBtn}
        `;
        li.addEventListener("click", () => {
          showResults(r.run_id);
          writeRoute("files", r.run_id);
        });
        li.querySelector("[data-stop]")?.addEventListener("click", (ev) => {
          ev.stopPropagation();
          stopRun(r.run_id);
        });
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

  function captureTreeState(container) {
    const collapsed = new Set();
    const known = new Set();
    container.querySelectorAll(".tree-dir").forEach((el) => {
      const dirPath = el.dataset.dir;
      if (!dirPath) return;
      known.add(dirPath);
      if (el.classList.contains("collapsed")) collapsed.add(dirPath);
    });
    const active =
      container.querySelector(".tree-file .tree-row.active")?.dataset.path ||
      previewCache.path ||
      "";
    return { collapsed, known, active };
  }

  function renderFileTree(container, tree, runId, state) {
    container.innerHTML = "";
    if (!tree || (!Object.keys(tree.children).length && !tree.files.length)) {
      container.innerHTML = '<p class="muted">无文件</p>';
      return;
    }

    function renderNode(node, parentEl, depth, prefix) {
      const dirNames = Object.keys(node.children).sort();
      for (const name of dirNames) {
        const child = node.children[name];
        const dirPath = prefix ? `${prefix}/${name}` : name;
        const dirEl = document.createElement("div");
        dirEl.className = "tree-dir";
        dirEl.dataset.dir = dirPath;
        const known = Boolean(state && state.known && state.known.has(dirPath));
        const collapsed = known ? state.collapsed.has(dirPath) : depth >= 2;
        if (collapsed) dirEl.classList.add("collapsed");

        const row = document.createElement("button");
        row.type = "button";
        row.className = "tree-row";
        row.innerHTML = `<span class="tree-twist">${collapsed ? "▸" : "▾"}</span><span class="tree-icon">📁</span><span class="tree-name">${escapeHtml(name)}</span>`;
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
        renderNode(child, kids, depth + 1, dirPath);
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
        if (state && state.active && f.path === state.active) row.classList.add("active");
        row.addEventListener("click", () => {
          $$("#file-tree .tree-row.active").forEach((b) => b.classList.remove("active"));
          row.classList.add("active");
          previewFile(runId, f.path);
        });
        fileEl.appendChild(row);
        parentEl.appendChild(fileEl);
      }
    }

    renderNode(tree, container, 0, "");
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

  function stopFileTreeRefresh() {
    if (fileTreeTimer) {
      clearInterval(fileTreeTimer);
      fileTreeTimer = null;
    }
  }

  async function loadRunFiles(runId, resetPreview) {
    if (resetPreview) {
      previewCache = { path: "", text: "", trajData: null, traces: null };
      openFileKey = "";
      $("#result-summary").textContent = "加载中…";
      $("#file-tree").innerHTML = "";
      $("#preview-path").textContent = "点击左侧文件预览";
      $("#traj-view-toggle").hidden = true;
      $("#preview-body").innerHTML =
        '<p class="muted">左侧选 run 与文件；轨迹可在「format / JSON / raw」间切换。</p>';
    }
    const res = await fetch(apiUrl(`/api/runs/${encodeURIComponent(runId)}/results`));
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "failed");
    const st = data.status || {};
    const metrics = data.metrics || {};
    if (st.mode && ["swe_20filter", "swe", "terminal", "deepswe"].includes(st.mode)) {
      leaderboardMode = st.mode;
    }
    const files = data.files || [];
    const key = files.join("\n");
    const treeState = resetPreview ? null : captureTreeState($("#file-tree"));
    $("#result-summary").innerHTML = renderMetricsSummary(st, metrics, data.metrics_row);
    if (resetPreview || key !== openFileKey) {
      openFileKey = key;
      renderFileTree($("#file-tree"), pathsToTree(files), runId, treeState);
    }
    return st.phase || "";
  }

  function watchFileTree(runId, phase) {
    stopFileTreeRefresh();
    if (!isRunningPhase(phase)) return;
    fileTreeTimer = setInterval(async () => {
      if (previewRunId !== runId) {
        stopFileTreeRefresh();
        return;
      }
      try {
        const phaseNow = await loadRunFiles(runId, false);
        if (!isRunningPhase(phaseNow)) stopFileTreeRefresh();
      } catch (_) {
        /* 下一次再试，不清掉当前预览 */
      }
    }, 3000);
  }

  async function showResults(runId) {
    previewRunId = runId;
    stopFileTreeRefresh();
    $$("#run-list li").forEach((li) => {
      li.classList.toggle("active", li.dataset.runId === runId);
    });
    const title = $("#result-title");
    if (title) {
      title.textContent = runId;
      title.classList.remove("muted");
    }
    try {
      const phase = await loadRunFiles(runId, true);
      watchFileTree(runId, phase);
    } catch (ex) {
      $("#result-summary").innerHTML = `<span class="error">${escapeHtml(String(ex))}</span>`;
    }
  }

  function syncTrajToggles() {
    $$("#traj-view-toggle [data-view]").forEach((b) => {
      b.classList.toggle("active", b.dataset.view === trajViewMode);
    });
    $$("#traj-fold-toggle [data-fold]").forEach((b) => {
      b.classList.toggle("active", b.dataset.fold === trajFoldMode);
    });
    const fold = $("#traj-fold-toggle");
    if (fold) fold.hidden = trajViewMode === "json";
  }

  function setTrajViewMode(mode) {
    trajViewMode = mode;
    syncTrajToggles();
    if (previewCache.trajData) renderTrajPreview();
  }

  function setTrajFoldMode(mode) {
    trajFoldMode = mode === "open" ? "open" : "close";
    syncTrajToggles();
    const bubbles = $$("#preview-body details.chat-bubble");
    if (bubbles.length) {
      bubbles.forEach((el) => {
        el.open = trajFoldMode === "open";
      });
      return;
    }
    if (previewCache.trajData && trajViewMode === "chat") renderTrajPreview();
  }

  $$("#traj-view-toggle [data-view]").forEach((btn) => {
    btn.addEventListener("click", () => setTrajViewMode(btn.dataset.view));
  });
  $$("#traj-fold-toggle [data-fold]").forEach((btn) => {
    btn.addEventListener("click", () => setTrajFoldMode(btn.dataset.fold));
  });

  function renderTrajPreview() {
    const body = $("#preview-body");
    const data = previewCache.trajData;
    if (!data) return;
    if (trajViewMode === "json") {
      const pretty = JSON.stringify(data, null, 2);
      body.innerHTML = `<pre class="preview-raw">${escapeHtml(pretty.slice(0, 500000))}</pre>`;
    } else if (trajViewMode === "raw") {
      body.innerHTML = renderTrajChat(data, previewCache.traces || []);
    } else {
      body.innerHTML = renderTrajChat(data);
    }
    syncTrajToggles();
  }

  function runFileUrl(runId, filePath) {
    return apiUrl(
      `/api/runs/${encodeURIComponent(runId)}/files/${filePath
        .split("/")
        .map(encodeURIComponent)
        .join("/")}`
    );
  }

  function firstUserText(traj) {
    for (const m of traj.messages || []) {
      if (String(m.role || "").toLowerCase() !== "user") continue;
      return typeof m.content === "string" ? m.content : JSON.stringify(m.content || "");
    }
    return "";
  }

  function flattenText(s) {
    return String(s || "").replace(/\s+/g, " ").trim();
  }

  function pickTraceTurns(traj, rows) {
    const iid = String(traj.instance_id || "").toLowerCase();
    const user = flattenText(firstUserText(traj));
    const bySid = new Map();
    for (const r of rows) {
      const sid = r.sid || "_";
      if (!bySid.has(sid)) bySid.set(sid, []);
      bySid.get(sid).push(r);
    }
    let best = [];
    let bestScore = -1;
    for (const turns of bySid.values()) {
      const task = flattenText(turns[0]?.task || "");
      let score = 0;
      if (iid && task.toLowerCase().includes(iid)) score += 8;
      if (task && user.includes(task)) score += 10;
      const distinctive = task
        .replace(/^<pr_description>\s*/i, "")
        .replace(/^consider the following pr description:\s*/i, "")
        .trim();
      if (distinctive.length >= 12) {
        const needle = distinctive.slice(0, 40);
        if (user.toLowerCase().includes(needle.toLowerCase())) score += 12;
      }
      if (score > bestScore) {
        bestScore = score;
        best = turns;
      }
    }
    if (bestScore <= 0) return [];
    return [...best].sort((a, b) => (a.turn || 0) - (b.turn || 0));
  }

  function annotateTraceTurns(traj, turns) {
    const kinds = [];
    let i = 0;
    for (const m of traj.messages || []) {
      const role = String(m.role || "").toLowerCase();
      const content = typeof m.content === "string" ? m.content : "";
      if (role === "assistant") {
        kinds[i] = "assistant";
        i += 1;
      } else if (role === "user" && /no tool calls found/i.test(content)) {
        kinds[i] = "no_tool";
        i += 1;
      }
    }
    return turns.map((t, idx) => ({ ...t, trajKind: kinds[idx] || "" }));
  }

  async function fetchJsonl(runId, filePath) {
    const res = await fetch(runFileUrl(runId, filePath));
    if (!res.ok) return [];
    const text = await res.text();
    return text
      .split("\n")
      .filter(Boolean)
      .map((line) => {
        try {
          return JSON.parse(line);
        } catch {
          return null;
        }
      })
      .filter(Boolean);
  }

  async function loadTurnTrace(runId, traj) {
    const paths = [
      "logs/adapter_stats/turn_trace.jsonl",
      "logs/adapter_stats/token_usage/turn_trace.jsonl",
    ];
    let picked = [];
    for (const p of paths) {
      try {
        const rows = await fetchJsonl(runId, p);
        picked = pickTraceTurns(traj, rows);
        if (picked.length) break;
      } catch {
        /* try next */
      }
    }
    if (!picked.length) return [];
    try {
      const usageRows = await fetchJsonl(runId, "logs/adapter_stats/turns.jsonl");
      const byTurn = new Map();
      for (const row of usageRows) {
        if (row.sid !== picked[0].sid) continue;
        byTurn.set(row.turn, row);
      }
      picked = picked.map((t) => {
        const u = byTurn.get(t.turn);
        return u
          ? {
              ...t,
              slm_prompt_tokens: u.slm_prompt_tokens,
              slm_completion_tokens: u.slm_completion_tokens,
              llm_prompt_tokens: u.llm_prompt_tokens,
              llm_completion_tokens: u.llm_completion_tokens,
            }
          : t;
      });
    } catch {
      /* tokens optional */
    }
    return annotateTraceTurns(traj, picked);
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

      previewCache = { path: filePath, text, trajData: null, traces: null };

      if (filePath.endsWith(".traj.json")) {
        try {
          previewCache.trajData = JSON.parse(text);
        } catch {
          body.innerHTML = `<pre class="preview-raw">${escapeHtml(text.slice(0, 200000))}</pre>`;
          return;
        }
        previewCache.traces = await loadTurnTrace(runId, previewCache.trajData);
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

  function clipOneLine(s, n = 80) {
    const t = String(s || "").replace(/\s+/g, " ").trim();
    if (!t) return "";
    return t.length > n ? `${t.slice(0, n)}…` : t;
  }

  function messageBlob(m) {
    const content =
      typeof m.content === "string"
        ? m.content
        : m.content != null
          ? JSON.stringify(m.content)
          : "";
    return [
      m.reasoning_content || "",
      m.thinking || "",
      content,
      m.tool_calls ? JSON.stringify(m.tool_calls) : "",
    ].join("\n");
  }

  function messageUsage(m) {
    const extra = m && m.extra && typeof m.extra === "object" ? m.extra : {};
    const nested = extra.response && extra.response.usage;
    if (nested && typeof nested === "object") return nested;
    if (m && m.usage && typeof m.usage === "object") return m.usage;
    return {};
  }

  function messageHasOffload(m) {
    if (!m || typeof m !== "object") return false;
    if (String(m.role || "").toLowerCase() !== "assistant") return false;
    const usage = messageUsage(m);
    return Number(usage.llm_prompt_tokens || 0) > 0 || Number(usage.llm_completion_tokens || 0) > 0;
  }

  function toolCallBits(m) {
    const names = [];
    const cmds = [];
    for (const tc of m.tool_calls || []) {
      const fn = tc.function || {};
      if (fn.name) names.push(fn.name);
      let args = fn.arguments;
      if (typeof args === "string") {
        try {
          args = JSON.parse(args);
        } catch {
          args = { command: args };
        }
      }
      if (args && typeof args === "object" && args.command) cmds.push(String(args.command));
    }
    return { names, cmds };
  }

  function isNoToolUser(m) {
    const role = String(m.role || "").toLowerCase();
    const content = typeof m.content === "string" ? m.content : "";
    return role === "user" && /no tool calls found/i.test(content);
  }

  function bubbleSummary(m) {
    const role = String(m.role || "unknown").toUpperCase();
    const bits = [role];
    const content =
      typeof m.content === "string"
        ? m.content
        : m.content != null
          ? JSON.stringify(m.content)
          : "";
    if (role === "ASSISTANT") {
      const { names, cmds } = toolCallBits(m);
      if (names.length) bits.push(names.join(","));
      if (cmds.length) bits.push(clipOneLine(cmds.join(" | ")));
      else bits.push(clipOneLine(m.reasoning_content || m.thinking || content));
    } else if (role === "TOOL") {
      /* summary stays "TOOL" */
    } else {
      bits.push(clipOneLine(content || m.reasoning_content || ""));
    }
    return bits.filter(Boolean).join(" · ");
  }

  function renderChatBubble(m, openAttr) {
    const role = m.role || "unknown";
    const parts = [];
    const reasoning = m.reasoning_content || m.thinking || "";
    const content =
      typeof m.content === "string" ? m.content : m.content != null ? JSON.stringify(m.content, null, 2) : "";
    if (reasoning) {
      parts.push(
        `<div class="chat-section-label">reasoning</div><div class="chat-text">${highlightOffload(reasoning)}</div>`
      );
    }
    if (content) {
      parts.push(
        `<div class="chat-section-label">content</div><div class="chat-text">${highlightOffload(content)}</div>`
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
        `<div class="chat-section-label">tool_call_id</div><div class="chat-text">${escapeHtml(m.tool_call_id)}</div>`
      );
    }
    if (!parts.length) {
      parts.push(`<div class="chat-text muted">(empty)</div>`);
    }
    const off = messageHasOffload(m);
    const badge = off ? `<span class="offload-badge">OFFLOAD</span>` : "";
    const offCls = off ? " has-offload" : "";
    return `<details class="chat-bubble role-${escapeHtml(role)}${offCls}"${openAttr}><summary class="chat-summary"><span class="chat-summary-text">${escapeHtml(
      bubbleSummary(m)
    )}</span>${badge}</summary><div class="chat-body">${parts.join("")}</div></details>`;
  }

  function shouldShowRawTrace(t, m) {
    if (!t) return false;
    if (t.trajKind === "no_tool" || isNoToolUser(m)) return true;
    if (t.offloaded) return true;
    const blob = [t.slm_raw, t.slm_thinking, t.slm_output].join("\n");
    return blob.includes("<|llm_offload|>");
  }

  function renderRawBubble(t, openAttr) {
    const bits = ["ASSISTANT", "RAW"];
    if (t.offload_n != null) bits.push(`N=${t.offload_n}`);
    if (t.trajKind === "no_tool") bits.push("no tool call");
    if (t.slm_completion_tokens != null || t.slm_prompt_tokens != null) {
      bits.push(`slm ${t.slm_prompt_tokens || 0}/${t.slm_completion_tokens || 0}`);
    }
    bits.push(clipOneLine(t.slm_raw || t.slm_thinking || t.slm_output || ""));
    const parts = [];
    if (t.slm_raw) {
      parts.push(
        `<div class="chat-section-label">slm_raw</div><div class="chat-text">${highlightOffload(t.slm_raw)}</div>`
      );
    } else {
      if (t.slm_thinking) {
        parts.push(
          `<div class="chat-section-label">slm_thinking</div><div class="chat-text">${highlightOffload(t.slm_thinking)}</div>`
        );
      }
      if (t.slm_output) {
        parts.push(
          `<div class="chat-section-label">slm_output</div><div class="chat-text">${highlightOffload(t.slm_output)}</div>`
        );
      }
    }
    if (!parts.length) {
      parts.push(`<div class="chat-text muted">(empty SLM output)</div>`);
    }
    const noTool = t.trajKind === "no_tool";
    const off = Boolean(t.offloaded);
    const badges = [`<span class="offload-badge raw-flag">RAW</span>`];
    if (off) badges.push(`<span class="offload-badge">OFFLOAD</span>`);
    if (noTool) badges.push(`<span class="offload-badge raw-fail-badge">NO TOOL</span>`);
    const cls = `chat-bubble role-assistant raw-turn${off ? " has-offload" : ""}${noTool ? " raw-no-tool" : ""}`;
    return `<details class="${cls}"${openAttr}><summary class="chat-summary"><span class="chat-summary-text">${escapeHtml(
      bits.filter(Boolean).join(" · ")
    )}</span>${badges.join("")}</summary><div class="chat-body">${parts.join("")}</div></details>`;
  }

  function renderTrajChat(data, traces) {
    const msgs = Array.isArray(data.messages) ? data.messages : [];
    const assistantMsgs = msgs.filter((m) => String(m.role || "").toLowerCase() === "assistant");
    const offloadCount = assistantMsgs.filter(messageHasOffload).length;
    const insertRaw = Array.isArray(traces);
    const meta = [];
    if (data.instance_id) meta.push(`instance: ${escapeHtml(data.instance_id)}`);
    if (data.info?.exit_status) meta.push(`exit: ${escapeHtml(String(data.info.exit_status))}`);
    meta.push(`${msgs.length} messages`);
    if (assistantMsgs.length) {
      const pct = ((offloadCount / assistantMsgs.length) * 100).toFixed(1);
      meta.push(`${offloadCount}/${assistantMsgs.length} assistant offload (${pct}%)`);
    } else {
      meta.push(`${offloadCount} offload`);
    }
    const head = `<p class="muted mono chat-meta">${meta.join(" · ")}</p>`;

    if (!msgs.length) {
      return `${head}<p class="muted">无 messages</p><pre class="preview-raw">${escapeHtml(
        JSON.stringify(data, null, 2).slice(0, 200000)
      )}</pre>`;
    }

    const openAttr = trajFoldMode === "open" ? " open" : "";
    let traceI = 0;
    const bubbles = msgs
      .map((m) => {
        let extra = "";
        if (insertRaw) {
          const role = String(m.role || "").toLowerCase();
          if (role === "assistant" || isNoToolUser(m)) {
            const t = traces[traceI];
            traceI += 1;
            if (shouldShowRawTrace(t, m)) extra = renderRawBubble(t, openAttr);
          }
        }
        return extra + renderChatBubble(m, openAttr);
      })
      .join("");

    const unmatched =
      insertRaw && !traces.length
        ? `<p class="muted">没有匹配到 adapter turn_trace，轨迹按 format 显示。可打开 logs/adapter_stats/turn_trace.jsonl。</p>`
        : "";
    return `${head}${unmatched}<div class="chat-thread">${bubbles}</div>`;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  window.addEventListener("hashchange", () => {
    if (applyingRoute) return;
    applyRoute(parseRoute());
  });
  applyRoute(parseRoute());
})();
