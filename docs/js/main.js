(() => {
  const I18N = {
    en: {
      skip: "Skip to content",
      nav_method: "Method",
      nav_results: "Results",
      nav_cases: "Cases",
      nav_resources: "Citation",
      hero_title:
        "A novel cost-aware, token-level paradigm for collaborative inference between SLM and LLM",
      hero_lead:
        "Token-level offload with <|llm_offload|>. Near-LLM performance with fractional LLM-only inference cost.",
      cta_hf: "Hugging Face · PyroMind",
      cta_paper: "PyroDash Paper",
      cta_pyromind: "PyroMind Console",
      cta_reproduce: "Reproduce on PyroMind",
      cta_github: "View on GitHub",
      method_label: "How it works",
      method_title: "Train the SLM to initiate queries and concatenate streams.",
      method_desc:
        "No external router. No LLM retraining. Progressive training teaches SLM when to emit <|llm_offload|>; at inference, the Collaborate Engine suspends, relays, and concatenate streams.",
      tab_training: "Training",
      tab_inference: "Inference",
      training_title: "Three-stage progressive training",
      training_desc:
        "Data preparation filters easy/hard samples and inserts control tags <|llm_offload|>. Then embed <|llm_offload|>, cold-start offload SFT, and GRPO with a cost-aware reward.",
      stage1_title: "Control-token embedding",
      stage1_desc:
        "LoRA on embed_tokens + lm_head, then keep only the <|llm_offload|> embedding row so SLM can express offload intent.",
      stage2_title: "Offload cold-start",
      stage2_desc:
        "Offload SFT teaches when and how to emit <|llm_offload|> on hard steps while keeping easy steps local.",
      stage3_title: "GRPO enhancement",
      stage3_desc:
        "With LLM frozen, optimize R = R_accuracy − λ · R_efficiency so performance and LLM-only cost move together.",
      training_caption:
        "Data preparation → embedding-layer training → offload SFT → GRPO → trained SLM.",
      inference_title: "Collaborative inference architecture",
      inference_desc:
        "SLM (Qwen3.5-4B / vLLM) streams until <|llm_offload|>. The Collaborate Engine packs context of SLM (Cs), one-shot relays to frozen LLM (GLM-5.2), then returns the concatenated stream of SLM and LLM.",
      inf1_title: "Collaborate Engine",
      inf1_desc: "Offload detect · stream concatenate — one-shot concatenate streams.",
      inf2_title: "Token-level self-routing",
      inf2_desc:
        "Upon <|llm_offload|>: suspend SLM, Pack(Cs), then one-shot relay query + Cs to the LLM API.",
      inf3_title: "Concatenated stream",
      inf3_desc: "Users always get continuous answers: SLM prefix plus LLM completion.",
      inference_caption:
        "User ↔ Collaborate Engine ↔ SLM / LLM, with token-level offload and stream concatenate.",
      results_label: "Results",
      results_title: "A tunable quality–cost Pareto frontier",
      results_desc:
        "On five math benchmarks (Minerva, GSM8K, Olympiad, AIME25, AIME24), PyroDash with Qwen3.5-4B + GLM-5.2 breaks the conventional trade-off barrier.",
      metric1: "Avg. accuracy PyroDash (λ=0.05) — outperform GLM-5.2 (LLM-only)",
      metric2: "Cost reduction PyroDash (λ=0.6) vs. GLM-5.2 (LLM-only)",
      metric3: "LLM token ratio at λ=0.6",
      fig_caption:
        "Total cost and average accuracy across five benchmarks. PyroDash (λ=0.05) outperform GLM-5.2-FP8; PyroDash (λ=0.6) reduces cost from $49.36 to $1.78.",
      th_method: "Method",
      cases_label: "Case study",
      cases_title: "Offload and relay circumstances",
      cases_desc:
        "Same problem: Once the Collaborate Engine detects the <|llm_offload|>, LLM relay starts.",
      sidebar_title: "Cases",
      sidebar_model_title: "Model",
      q_label: "Question",
      gt_label: "Answer",
      qwen_label: "Qwen response",
      glm_label: "GLM response",
      offload_label: "SLM + LLM relay",
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
      nav_resources: "Citation",
      hero_title: "面向 SLM 与 LLM 的成本感知 Token 级协同推理新范式",
      hero_lead:
        "通过 <|llm_offload|> 做 Token 级 offload：性能逼近纯大模型，推理费用仅为 LLM-only 的一小部分。",
      cta_hf: "Hugging Face · PyroMind",
      cta_paper: "PyroDash 论文",
      cta_pyromind: "PyroMind 控制台",
      cta_reproduce: "在 PyroMind 一键复现",
      cta_github: "查看 GitHub",
      method_label: "工作原理",
      method_title: "训练 SLM 发起求助，并在流式推理中拼接输出。",
      method_desc:
        "无需外接 Router，无需重训大模型。渐进式训练教会 SLM 何时发出 <|llm_offload|>；推理时 Collaborate Engine 负责挂起、接力与双端流拼接。",
      tab_training: "训练",
      tab_inference: "推理",
      training_title: "三阶段渐进式训练",
      training_desc:
        "数据准备过滤 easy/hard 样本并插入控制符 <|llm_offload|>；随后嵌入 <|llm_offload|>、Offload SFT 冷启动，再用带成本项的 GRPO 强化。",
      stage1_title: "控制符嵌入层训练",
      stage1_desc:
        "对 embed_tokens + lm_head 做 LoRA，再只保留 <|llm_offload|> 嵌入行，让 SLM 具备 offload 表达能力。",
      stage2_title: "Offload 冷启动",
      stage2_desc:
        "Offload SFT 教会模型在难题关键步骤输出 <|llm_offload|>，简单题仍本地完成。",
      stage3_title: "GRPO 强化",
      stage3_desc:
        "冻结 LLM，优化 R = R_accuracy − λ · R_efficiency，让性能与 LLM-only 成本协同推进。",
      training_caption:
        "数据准备 → 嵌入层训练 → Offload SFT → GRPO → 得到 trained SLM。",
      inference_title: "协作推理架构",
      inference_desc:
        "SLM（Qwen3.5-4B / vLLM）流式输出直至 <|llm_offload|>；Collaborate Engine 打包 SLM 上下文（Cs），一次性接力给冻结的 LLM（GLM-5.2），再返回 SLM 与 LLM 的拼接流。",
      inf1_title: "Collaborate Engine",
      inf1_desc: "Offload 检测 · 流拼接 — 一次性完成双端流拼接。",
      inf2_title: "Token 级自路由",
      inf2_desc:
        "检测到 <|llm_offload|> 后挂起 SLM、Pack(Cs)，再把 query + Cs 一次性发给 LLM API。",
      inf3_title: "拼接输出流",
      inf3_desc: "用户始终看到连续答案：SLM 前缀 + LLM 补全。",
      inference_caption:
        "User ↔ Collaborate Engine ↔ SLM / LLM：Token 级 offload 与流式拼接。",
      results_label: "实验结果",
      results_title: "可调节的质量–成本帕累托前沿",
      results_desc:
        "在 Minerva、GSM8K、Olympiad、AIME25、AIME24 五项数学基准上，Qwen3.5-4B + GLM-5.2 的 PyroDash 打破常规质量–成本权衡。",
      metric1: "PyroDash 平均准确率（λ=0.05）— 超过 GLM-5.2 (LLM-only)",
      metric2: "PyroDash 费用降幅（λ=0.6）vs. GLM-5.2 (LLM-only)",
      metric3: "λ=0.6 时的 LLM Token 占比",
      fig_caption:
        "五基准合计费用与平均准确率。PyroDash（λ=0.05）超过 GLM-5.2-FP8；PyroDash（λ=0.6）将费用从 $49.36 降至 $1.78。",
      th_method: "方法",
      cases_label: "案例",
      cases_title: "Offload 与接力场景",
      cases_desc:
        "同一问题：Collaborate Engine 检测到 <|llm_offload|> 后，启动 LLM 接力。",
      sidebar_title: "案例列表",
      sidebar_model_title: "模型",
      q_label: "Question",
      gt_label: "Answer",
      qwen_label: "Qwen 回复",
      glm_label: "GLM 回复",
      offload_label: "SLM + LLM 接力",
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
  const cases = Array.isArray(window.PYRODASH_CASES) ? window.PYRODASH_CASES : [];
  let lang = localStorage.getItem("pyrodash-lang") || "en";
  let activeCase = 0;
  let activeModel = "qwen";

  const MODEL_META = {
    qwen: { tag: "Qwen", tagClass: "tag-qwen", streamClass: "stream-qwen", titleKey: "qwen_label" },
    glm: { tag: "GLM", tagClass: "tag-glm", streamClass: "stream-glm", titleKey: "glm_label" },
    offload: { tag: "Offload", tagClass: "tag-offload", streamClass: "stream-offload", titleKey: "offload_label" },
  };

  const KATEX_OPTS = {
    delimiters: [
      { left: "$$", right: "$$", display: true },
      { left: "\\[", right: "\\]", display: true },
      { left: "\\(", right: "\\)", display: false },
      { left: "$", right: "$", display: false },
    ],
    throwOnError: false,
    strict: "ignore",
    trust: false,
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

  function protectCurrencyDollars(text) {
    const src = String(text || "");
    let out = "";
    let i = 0;
    while (i < src.length) {
      if (src.startsWith("$$", i)) {
        const end = src.indexOf("$$", i + 2);
        if (end < 0) {
          out += src.slice(i);
          break;
        }
        out += src.slice(i, end + 2);
        i = end + 2;
        continue;
      }

      if (src[i] === "$" && (i === 0 || src[i - 1] !== "\\")) {
        const close = src.indexOf("$", i + 1);
        if (close > i + 1) {
          const inner = src.slice(i + 1, close);
          const isMath = /[\\^_{}]/.test(inner);
          if (isMath) {
            out += src.slice(i, close + 1);
            i = close + 1;
            continue;
          }
        }
        const money = src.slice(i).match(/^\$\d+(?:\.\d+)?/);
        if (money) {
          out += `\\$${money[0].slice(1)}`;
          i += money[0].length;
          continue;
        }
      }

      out += src[i];
      i += 1;
    }
    return out;
  }

  function prepareMathText(text) {
    let src = protectCurrencyDollars(text);
    // Wrap bare \boxed{...} so KaTeX can render it.
    src = src.replace(/(^|[^$\\])(\\boxed\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})(?!\$)/g, "$1$$$2$$");
    return src;
  }

  function formatText(text) {
    let html = escapeHtml(prepareMathText(text));
    html = html.replace(
      /&lt;(\/?redacted_thinking|\/?think)&gt;/gi,
      '<span class="think-tag">&lt;$1&gt;</span>'
    );
    return html;
  }

  function highlightToken(text) {
    const parts = String(text || "").split(OFFLOAD);
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

  function renderLatex(el) {
    if (!el || typeof renderMathInElement !== "function") return;
    try {
      renderMathInElement(el, KATEX_OPTS);
    } catch {
      /* ignore katex errors */
    }
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
    resultEl.className = `case-stream ${meta.streamClass}`;

    updateModelVerdictUI(c);

    if (activeModel === "qwen") {
      resultEl.innerHTML = formatText(c.qwen_response?.completed_response || "");
    } else if (activeModel === "glm") {
      resultEl.innerHTML = formatText(c.glm_response?.completed_response || "");
    } else {
      resultEl.innerHTML = buildOffloadHtml(c.relay_response);
    }
    renderLatex(resultEl);
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

    const qEl = document.getElementById("case-question");
    const aEl = document.getElementById("case-answer");
    qEl.innerHTML = formatText(c.question || "");
    aEl.innerHTML = formatText(c.answer || "");
    renderLatex(qEl);
    renderLatex(aEl);
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

  function initCases() {
    if (!cases.length) {
      console.warn("No static cases found (window.PYRODASH_CASES).");
      return;
    }
    buildTabs();
    setupModelSidebar();
    renderCase(0);
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
    const sectionIds = ["method", "results", "cases", "resources"];
    const navLinks = document.querySelectorAll('.nav-links a[href^="#"]');

    const onScroll = () => {
      nav.classList.toggle("is-scrolled", window.scrollY > 12);

      let currentId = "";
      const probe = window.scrollY + window.innerHeight * 0.3;
      sectionIds.forEach((id) => {
        const el = document.getElementById(id);
        if (el && el.offsetTop <= probe) currentId = id;
      });

      const atBottom =
        window.innerHeight + window.scrollY >=
        document.documentElement.scrollHeight - 2;
      if (atBottom) currentId = sectionIds[sectionIds.length - 1];

      navLinks.forEach((link) => {
        const target = link.getAttribute("href").slice(1);
        link.classList.toggle("is-active", target === currentId);
      });
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

  function snapCtaIcons() {
    const icons = [...document.querySelectorAll(".cta-icon")];
    if (!icons.length) return;
    const state = new WeakMap();
    const tick = () => {
      icons.forEach((el) => {
        const prev = state.get(el) || { dx: 0, dy: 0 };
        const r = el.getBoundingClientRect();
        // ignore the element's own applied transform to read its natural box
        const natTop = r.top - prev.dy;
        const natLeft = r.left - prev.dx;
        const dx = Math.round(natLeft) - natLeft;
        const dy = Math.round(natTop) - natTop;
        if (Math.abs(dx - prev.dx) > 0.01 || Math.abs(dy - prev.dy) > 0.01) {
          el.style.transform = `translate(${dx}px, ${dy}px)`;
          state.set(el, { dx, dy });
        }
      });
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  applyI18n();
  setupLang();
  setupNav();
  setupReveal();
  setupCopy();
  setupMethodTabs();
  initCases();
  snapCtaIcons();
})();
