(() => {
  const I18N = {
    en: {
      skip: "Skip to content",
      nav_method: "Method",
      nav_results: "Results",
      nav_cases: "Cases",
      nav_resources: "Resources",
      hero_title: "Small models ask for help — only when it counts.",
      hero_lead:
        "Token-level offload with <|llm_offload|>. Near LLM quality, a fraction of the cloud bill.",
      cta_hf: "Hugging Face · pyromind",
      cta_pyromind: "PyroMind Console",
      cta_reproduce: "Reproduce on PyroMind",
      cta_github: "View on GitHub",
      method_label: "How it works",
      method_title: "Train the small model to ask — then stitch the stream",
      method_desc:
        "No external router. No LLM retraining. Progressive training teaches Ms when to emit <|llm_offload|>; at inference, the Collaborate Engine suspends, relays, and merges the two streams.",
      tab_training: "Training",
      tab_inference: "Inference",
      training_title: "Three-stage progressive training",
      training_desc:
        "Data prep filters easy/hard samples and inserts control tags. Then: embed τ_off, cold-start offload SFT, and GRPO with a cost-aware reward.",
      stage1_title: "Control-token embedding",
      stage1_desc:
        "LoRA on embed_tokens + lm_head, then keep only the τ_off embedding row so Ms can express offload intent.",
      stage2_title: "Offload cold-start",
      stage2_desc:
        "Offload SFT teaches when and how to emit <|llm_offload|> on hard steps while keeping easy steps local.",
      stage3_title: "GRPO enhancement",
      stage3_desc:
        "With Ml frozen, optimize R = R_accuracy − λ · R_efficiency so quality and cloud cost move together.",
      training_caption:
        "Data preparation → embedding-layer train → offload SFT → GRPO → trained Ms.",
      inference_title: "Collaborative inference architecture",
      inference_desc:
        "Ms (Qwen3.5-4B / vLLM) streams until τ_off. The engine packs Cs, one-shot relays to frozen Ml (GLM-5.2), then returns the stitched stream Os ‖ OL.",
      inf1_title: "Collaborate Engine",
      inf1_desc:
        "State machine · stream merge · offload detect — the only place that stitches the two sides.",
      inf2_title: "Token-level self-routing",
      inf2_desc:
        "On τ_off: suspend Ms, Pack(Cs), then one-shot relay q + Cs to the large-model API.",
      inf3_title: "Stitched stream",
      inf3_desc:
        "User sees one continuous answer: small-model prefix plus large-model completion.",
      inference_caption:
        "User ↔ Collaborate Engine ↔ Ms / Ml, with token-level offload and stream merge.",
      results_label: "Results",
      results_title: "A tunable quality–cost Pareto frontier",
      results_desc:
        "On five math benchmarks (Minerva, GSM8K, Olympiad, AIME25, AIME24), PyroDash with Qwen3.5-4B + GLM-5.2 breaks the usual trade-off.",
      metric1: "Avg. accuracy (λ=0.05) — above GLM-5.2 alone",
      metric2: "Cost cut vs. pure cloud (λ=0.6)",
      metric3: "LLM token ratio at the low-cost operating point",
      fig_caption:
        "Five-benchmark total cost vs. average accuracy. PyroDash (λ=0.05) exceeds GLM-5.2 accuracy; λ=0.6 drops cost from $49.37 to $1.79.",
      th_method: "Method",
      cases_label: "Case study",
      cases_title: "Where the small model gets stuck — and asks",
      cases_desc:
        "Six benchmark cases: Qwen-only, GLM-only, and PyroDash offload (SLM + LLM stitched). Pick a case from the sidebar.",
      sidebar_title: "Cases",
      sidebar_model_title: "Model",
      q_label: "Question",
      gt_label: "Answer",
      qwen_label: "Qwen response",
      glm_label: "GLM response",
      offload_label: "Offload relay (SLM + LLM)",
      legend_qwen: "Qwen3.5-4B",
      legend_glm: "GLM-5.2",
      legend_slm: "Offload · SLM",
      legend_llm: "Offload · LLM",
      legend_token: "<|llm_offload|>",
      badge_offload: "with offload",
      badge_noffload: "no offload",
      resources_label: "Resources",
      resources_title: "Paper, data, and one-click reproduce",
      res_console: "One-click evaluation",
      res_dataset: "Training dataset on Hugging Face",
      res_hf: "Models & datasets",
      res_eval: "Math evaluation code",
      cite_title: "Citation",
      copy: "Copy",
      copied: "Copied",
      footer: "© 2026 PyroMind Dynamics · PyroDash",
      lang_btn: "中文",
    },
    zh: {
      skip: "跳到正文",
      nav_method: "方法",
      nav_results: "结果",
      nav_cases: "案例",
      nav_resources: "资源",
      hero_title: "小模型只在关键时刻向大模型求助。",
      hero_lead:
        "通过 <|llm_offload|> 做 Token 级 offload：质量逼近纯大模型，云端账单大幅下降。",
      cta_hf: "Hugging Face · pyromind",
      cta_pyromind: "PyroMind 控制台",
      cta_reproduce: "在 PyroMind 一键复现",
      cta_github: "查看 GitHub",
      method_label: "工作原理",
      method_title: "先教会小模型求助，再在流式推理中拼接",
      method_desc:
        "无需外接 Router，无需重训大模型。渐进式训练教会 Ms 何时发出 <|llm_offload|>；推理时 Collaborate Engine 负责挂起、接力与双端流拼接。",
      tab_training: "训练",
      tab_inference: "推理",
      training_title: "三阶段渐进式训练",
      training_desc:
        "数据准备先过滤 easy/hard 并插入控制符；随后训练 τ_off 嵌入、Offload SFT 冷启动，再用带成本项的 GRPO 强化。",
      stage1_title: "控制符嵌入层训练",
      stage1_desc:
        "对 embed_tokens + lm_head 做 LoRA，再只保留 τ_off 嵌入行，让 Ms 具备 offload 表达能力。",
      stage2_title: "Offload 冷启动",
      stage2_desc: "Offload SFT 教会模型在难题关键步骤输出 <|llm_offload|>，简单题仍本地完成。",
      stage3_title: "GRPO 强化",
      stage3_desc:
        "冻结 Ml，优化 R = R_accuracy − λ · R_efficiency，让质量与云端成本协同推进。",
      training_caption:
        "数据准备 → 嵌入层训练 → Offload SFT → GRPO → 得到 trained Ms。",
      inference_title: "协作推理架构",
      inference_desc:
        "Ms（Qwen3.5-4B / vLLM）流式输出直至 τ_off；引擎打包 Cs，一次性接力给冻结的 Ml（GLM-5.2），再返回拼接流 Os ‖ OL。",
      inf1_title: "Collaborate Engine",
      inf1_desc: "状态机 · 流合并 · offload 检测 — 双端拼接只发生在这里。",
      inf2_title: "Token 级自路由",
      inf2_desc: "检测到 τ_off 后挂起 Ms、Pack(Cs)，再把 q + Cs 一次性发给大模型 API。",
      inf3_title: "拼接输出流",
      inf3_desc: "用户看到的是连续答案：小模型前缀 + 大模型补全。",
      inference_caption:
        "User ↔ Collaborate Engine ↔ Ms / Ml：Token 级 offload 与流式拼接。",
      results_label: "实验结果",
      results_title: "可调节的质量–成本帕累托前沿",
      results_desc:
        "在 Minerva、GSM8K、Olympiad、AIME25、AIME24 五项数学基准上，Qwen3.5-4B + GLM-5.2 的 PyroDash 打破常规权衡。",
      metric1: "平均准确率（λ=0.05）— 高于单独 GLM-5.2",
      metric2: "相对纯云端费用降幅（λ=0.6）",
      metric3: "低成本工作点的 LLM Token 占比",
      fig_caption:
        "五基准合计费用 vs 平均准确率。PyroDash（λ=0.05）准确率超过 GLM-5.2；λ=0.6 将费用从 $49.37 降至 $1.79。",
      th_method: "方法",
      cases_label: "案例",
      cases_title: "小模型卡住的地方——以及它如何求助",
      cases_desc:
        "六个 benchmark 案例：Qwen 独立回复、GLM 独立回复，以及 PyroDash offload 拼接（SLM + LLM）。点击侧边栏切换案例。",
      sidebar_title: "案例列表",
      sidebar_model_title: "模型结果",
      q_label: "Question",
      gt_label: "Answer",
      qwen_label: "Qwen 回复",
      glm_label: "GLM 回复",
      offload_label: "Offload 接力（SLM + LLM）",
      legend_qwen: "Qwen3.5-4B",
      legend_glm: "GLM-5.2",
      legend_slm: "Offload · SLM",
      legend_llm: "Offload · LLM",
      legend_token: "<|llm_offload|>",
      badge_offload: "含 offload",
      badge_noffload: "无 offload",
      resources_label: "相关资源",
      resources_title: "论文、数据与一键复现",
      res_console: "一键评测",
      res_dataset: "Hugging Face 训练数据",
      res_hf: "模型与数据集",
      res_eval: "数学评测代码",
      cite_title: "引用",
      copy: "复制",
      copied: "已复制",
      footer: "© 2026 PyroMind Dynamics · PyroDash",
      lang_btn: "EN",
    },
  };

  const OFFLOAD = "<|llm_offload|>";
  const CASE_KEYS = [
    "relay-off-r__glm-r__sft-f__qwen-f",
    "relay-off-r__glm-f__sft-f__qwen-f",
    "relay-off-r__glm-f__sft-r__qwen-f",
    "relay-noff-r__glm-r__sft-r__qwen-r",
  ];
  let lang = localStorage.getItem("pyrodash-lang") || "en";
  let cases = [];
  let activeCase = 0;
  let activeModel = "qwen";

  const MODEL_META = {
    qwen: { tag: "Qwen", tagClass: "tag-qwen", streamClass: "stream-qwen", titleKey: "qwen_label" },
    glm: { tag: "GLM", tagClass: "tag-glm", streamClass: "stream-glm", titleKey: "glm_label" },
    offload: { tag: "Offload", tagClass: "tag-offload", streamClass: "stream-offload", titleKey: "offload_label" },
  };

  function applyI18n() {
    const dict = I18N[lang] || I18N.en;
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      if (dict[key] != null) el.textContent = dict[key];
    });
    const toggle = document.getElementById("lang-toggle");
    if (toggle) toggle.textContent = dict.lang_btn;
  }

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function formatText(text) {
    let html = escapeHtml(text);
    html = html.replace(
      /&lt;(\/?redacted_thinking|think)&gt;/gi,
      '<span class="think-tag">&lt;$1&gt;</span>'
    );
    return html;
  }

  function highlightToken(text) {
    const parts = text.split(OFFLOAD);
    if (parts.length === 1) return formatText(text);
    return parts
      .map((part, i) => {
        const chunk = formatText(part);
        return i < parts.length - 1
          ? `${chunk}<span class="offload-token">${escapeHtml(OFFLOAD)}</span>`
          : chunk;
      })
      .join("");
  }

  function getLlmContinuation(raw, completed) {
    if (!completed) return "";
    if (!raw || raw === completed) return "";
    if (!raw.includes(OFFLOAD)) return "";

    const slmBody = raw.replace(OFFLOAD, "").trim();
    const compBody = completed.replace(/^<think>/i, "");
    const idx = compBody.indexOf(slmBody);
    if (idx >= 0) return compBody.slice(idx + slmBody.length);

    const tail = slmBody.slice(-100);
    const tailIdx = completed.indexOf(tail);
    if (tailIdx >= 0) return completed.slice(tailIdx + tail.length);
    return completed;
  }

  function buildOffloadHtml(relay) {
    const raw = relay?.raw_response || "";
    const completed = relay?.completed_response || "";
    if (!raw && !completed) return "";

    if (!raw.includes(OFFLOAD)) {
      return `<span class="seg-slm">${highlightToken(completed || raw)}</span>`;
    }

    const llmPart = getLlmContinuation(raw, completed);
    return `<span class="seg-slm">${highlightToken(raw)}</span><span class="seg-llm">${formatText(llmPart)}</span>`;
  }

  function extractLastBoxed(text) {
    const src = String(text || "");
    let last = null;
    const marker = "\\boxed{";
    let i = 0;
    while (i < src.length) {
      const start = src.indexOf(marker, i);
      if (start < 0) break;
      let depth = 0;
      let j = start + marker.length - 1;
      for (; j < src.length; j++) {
        const ch = src[j];
        if (ch === "{") depth += 1;
        else if (ch === "}") {
          depth -= 1;
          if (depth === 0) {
            last = src.slice(start + marker.length, j);
            break;
          }
        }
      }
      i = start + marker.length;
    }
    return last;
  }

  function normalizeAnswer(text) {
    return String(text || "")
      .replace(/\$+/g, "")
      .replace(/\\left|\\right/g, "")
      .replace(/\\,/g, "")
      .replace(/\\ /g, "")
      .replace(/[{}]/g, "")
      .replace(/\s+/g, "")
      .replace(/,/g, "")
      .toLowerCase();
  }

  function answersMatch(pred, gt) {
    if (pred == null || pred === "") return false;
    const a = normalizeAnswer(pred);
    const b = normalizeAnswer(gt);
    if (!a || !b) return false;
    if (a === b) return true;
    const na = Number(a);
    const nb = Number(b);
    return Number.isFinite(na) && Number.isFinite(nb) && na === nb;
  }

  function computeVerdicts(item) {
    const gt = extractLastBoxed(item.answer) || item.answer;
    const qwenPred = extractLastBoxed(item.qwen_response?.completed_response);
    const glmPred = extractLastBoxed(item.glm_response?.completed_response);
    const relayPred = extractLastBoxed(item.relay_response?.completed_response);
    return {
      qwen: answersMatch(qwenPred, gt),
      glm: answersMatch(glmPred, gt),
      offload: answersMatch(relayPred, gt),
    };
  }

  function flattenCases(data) {
    const list = [];
    CASE_KEYS.forEach((key) => {
      (data[key] || []).forEach((item) => {
        list.push({
          ...item,
          category: key,
          hasOffload: key.includes("relay-off"),
          verdicts: computeVerdicts(item),
        });
      });
    });
    return list;
  }

  function updateModelVerdictUI(c) {
    const verdicts = c?.verdicts || {};
    document.querySelectorAll(".case-sidebar-item[data-model]").forEach((btn) => {
      const model = btn.getAttribute("data-model");
      const ok = verdicts[model];
      btn.classList.toggle("is-wrong", ok === false);
      btn.classList.toggle("is-correct", ok === true);
      btn.removeAttribute("data-verdict");
      if (ok === true) btn.setAttribute("data-verdict", "correct");
      if (ok === false) btn.setAttribute("data-verdict", "wrong");
    });
  }

  function renderModelResult() {
    const c = cases[activeCase];
    if (!c) return;

    const dict = I18N[lang] || I18N.en;
    const meta = MODEL_META[activeModel];
    const resultEl = document.getElementById("case-result");
    const tagEl = document.getElementById("case-result-tag");
    const titleEl = document.getElementById("case-result-title");
    const wrong = c.verdicts?.[activeModel] === false;
    const correct = c.verdicts?.[activeModel] === true;
    const verdictClass = wrong ? " is-wrong" : correct ? " is-correct" : "";
    const labelEl = document.getElementById("case-result-label");

    tagEl.textContent = meta.tag;
    tagEl.className = `result-tag ${meta.tagClass}${verdictClass}`;
    titleEl.textContent = dict[meta.titleKey] || meta.titleKey;
    if (labelEl) labelEl.className = verdictClass.trim();
    // Bottom stream keeps model accent colors (no verdict class)
    resultEl.className = `case-stream ${meta.streamClass}`;

    updateModelVerdictUI(c);

    if (activeModel === "qwen") {
      resultEl.innerHTML = formatText(c.qwen_response?.completed_response || "");
    } else if (activeModel === "glm") {
      resultEl.innerHTML = formatText(c.glm_response?.completed_response || "");
    } else {
      resultEl.innerHTML = buildOffloadHtml(c.relay_response);
    }
  }

  function renderCase(i) {
    const c = cases[i];
    if (!c) return;
    activeCase = i;

    document.querySelectorAll(".case-tab").forEach((btn, idx) => {
      btn.setAttribute("aria-selected", idx === i ? "true" : "false");
    });

    document.getElementById("case-title").textContent =
      `${c.dataset || "case"} · #${c.idx ?? i}`;
    document.getElementById("case-question").textContent = c.question || "";
    document.getElementById("case-answer").textContent = c.answer || "";
    renderModelResult();
  }

  function buildTabs() {
    const tabs = document.getElementById("case-tabs");
    const dict = I18N[lang] || I18N.en;
    tabs.innerHTML = "";
    cases.forEach((c, i) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "case-tab";
      btn.setAttribute("role", "tab");
      btn.setAttribute("aria-selected", i === activeCase ? "true" : "false");
      const badge = c.hasOffload ? dict.badge_offload : dict.badge_noffload;
      btn.textContent = `${c.dataset || "case"} #${c.idx ?? i} · ${badge}`;
      btn.addEventListener("click", () => renderCase(i));
      tabs.appendChild(btn);
    });
  }

  function setupModelSidebar() {
    document.querySelectorAll(".case-sidebar-item[data-model]").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeModel = btn.getAttribute("data-model");
        document.querySelectorAll(".case-sidebar-item[data-model]").forEach((b) => {
          b.setAttribute("aria-current", b === btn ? "true" : "false");
        });
        renderModelResult();
      });
    });
  }

  async function loadCases() {
    try {
      const res = await fetch("data/case_0.json");
      const data = await res.json();
      cases = flattenCases(data);
      if (!cases.length) return;
      buildTabs();
      setupModelSidebar();
      renderCase(0);
    } catch (err) {
      console.warn("Failed to load cases", err);
    }
  }

  function setupReveal() {
    const nodes = document.querySelectorAll(".reveal");
    if (!("IntersectionObserver" in window)) {
      nodes.forEach((n) => n.classList.add("is-visible"));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("is-visible");
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );
    nodes.forEach((n) => io.observe(n));
  }

  function setupNav() {
    const nav = document.querySelector(".site-nav");
    const onScroll = () => {
      nav.classList.toggle("is-scrolled", window.scrollY > 12);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  function setupLang() {
    const toggle = document.getElementById("lang-toggle");
    toggle.addEventListener("click", () => {
      lang = lang === "en" ? "zh" : "en";
      localStorage.setItem("pyrodash-lang", lang);
      applyI18n();
      buildTabs();
      renderModelResult();
    });
  }

  function setupCopy() {
    const btn = document.getElementById("copy-cite");
    const pre = document.getElementById("cite-text");
    btn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(pre.textContent);
        const dict = I18N[lang];
        btn.textContent = dict.copied;
        setTimeout(() => {
          btn.textContent = dict.copy;
        }, 1400);
      } catch {
        /* ignore */
      }
    });
  }

  function setupMethodTabs() {
    const tabs = document.querySelectorAll(".method-tab");
    const panels = document.querySelectorAll(".method-panel");
    if (!tabs.length) return;

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const key = tab.getAttribute("data-method");
        tabs.forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
        panels.forEach((panel) => {
          panel.hidden = panel.getAttribute("data-method") !== key;
        });
      });
    });
  }

  applyI18n();
  setupLang();
  setupNav();
  setupReveal();
  setupCopy();
  setupMethodTabs();
  loadCases();
})();
