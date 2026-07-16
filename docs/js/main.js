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
      cta_reproduce: "Reproduce on PyroMind",
      cta_github: "View on GitHub",
      method_label: "How it works",
      method_title: "Introspective routing inside the generation stream",
      method_desc:
        "No external router. No LLM retraining. The small model decides mid-reasoning when to hand off — then a frozen large model completes the chain in one shot.",
      stage1_title: "Control-token embedding",
      stage1_desc:
        "Extend the vocabulary and initialize <|llm_offload|> so the SLM can express offload intent.",
      stage2_title: "Offload cold-start",
      stage2_desc:
        "SFT teaches when and how to emit the control token on hard steps while keeping easy steps local.",
      stage3_title: "GRPO with cost penalty",
      stage3_desc:
        "Jointly optimize task accuracy and large-model call cost for an adaptive quality–cost frontier.",
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
        "Question, ground-truth answer, SLM-only response, then the offload path: SLM raw_response + LLM completed_response.",
      q_label: "Question",
      gt_label: "Answer",
      alone_label: "SLM response",
      alone_hint: "initial_response",
      offload_label: "Offload relay",
      relay_hint: "relay_response",
      offload_slm_label: "SLM (before offload)",
      offload_llm_label: "LLM (after offload)",
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
      cta_reproduce: "在 PyroMind 一键复现",
      cta_github: "查看 GitHub",
      method_label: "工作原理",
      method_title: "把路由写进生成流的内省式决策",
      method_desc:
        "无需外接 Router，无需重训大模型。小模型在推理中途自行决定何时求助，冻结的大模型一次性补全推理链。",
      stage1_title: "控制符嵌入层训练",
      stage1_desc: "扩展词表并初始化 <|llm_offload|>，让小模型具备 offload 表达能力。",
      stage2_title: "Offload 冷启动",
      stage2_desc: "SFT 教会模型在难题关键步骤输出控制符，简单题仍本地完成。",
      stage3_title: "带成本惩罚的 GRPO",
      stage3_desc: "联合优化任务准确率与大模型调用成本，形成可调的质量–成本前沿。",
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
        "展示 Question、标准答案、仅小模型回复，以及 offload 路径下的 SLM raw_response 与 LLM completed_response。",
      q_label: "Question",
      gt_label: "Answer",
      alone_label: "SLM response",
      alone_hint: "initial_response",
      offload_label: "Offload relay",
      relay_hint: "relay_response",
      offload_slm_label: "SLM（offload 前）",
      offload_llm_label: "LLM（offload 后）",
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
  let lang = localStorage.getItem("pyrodash-lang") || "en";
  let cases = [];
  let activeCase = 0;

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

  function formatResponse(text) {
    let html = escapeHtml(text);
    html = html.replace(
      /&lt;\|llm_offload\|&gt;/g,
      '<span class="offload">&lt;|llm_offload|&gt;</span>'
    );
    html = html.replace(
      /&lt;(\/?think)&gt;/gi,
      '<span class="think-tag">&lt;$1&gt;</span>'
    );
    return html;
  }

  function renderCase(i) {
    const c = cases[i];
    if (!c) return;
    activeCase = i;

    document.querySelectorAll(".case-tab").forEach((btn, idx) => {
      btn.setAttribute("aria-selected", idx === i ? "true" : "false");
    });

    const slmText = c.initial_response?.completed_response || "";
    const offloadSlm = c.relay_response?.raw_response || "";
    const offloadLlm = c.relay_response?.completed_response || "";

    document.getElementById("case-dataset").textContent =
      `${c.dataset || "case"} · #${c.idx ?? i}`;
    document.getElementById("case-question").textContent = c.question || "";
    document.getElementById("case-answer").textContent = c.answer || "";
    document.getElementById("case-slm").innerHTML = formatResponse(slmText);
    document.getElementById("case-offload-slm").innerHTML =
      formatResponse(offloadSlm);
    document.getElementById("case-offload-llm").innerHTML =
      formatResponse(offloadLlm);
  }

  function buildTabs() {
    const tabs = document.getElementById("case-tabs");
    tabs.innerHTML = "";
    cases.forEach((c, i) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "case-tab";
      btn.setAttribute("role", "tab");
      btn.textContent = `${c.dataset || "case"} #${c.idx ?? i}`;
      btn.addEventListener("click", () => renderCase(i));
      tabs.appendChild(btn);
    });
  }

  async function loadCases() {
    try {
      const res = await fetch("data/case.json");
      cases = await res.json();
      if (!Array.isArray(cases) || !cases.length) return;
      buildTabs();
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

  applyI18n();
  setupLang();
  setupNav();
  setupReveal();
  setupCopy();
  loadCases();
})();
