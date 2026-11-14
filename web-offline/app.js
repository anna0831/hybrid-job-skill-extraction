(function () {
  "use strict";

  const EXPECTED_GROUP10 = window.Engine1114Offline.EXPECTED_GROUP10;
  let jiebaInstance = null;
  let engine = null;
  let lastResult = null;
  let filteredBatchJobs = [];
  let selectedJobIndex = -1;

  const engineStatusBadge = document.getElementById("engineStatusBadge");
  const versionBar = document.getElementById("versionBar");
  const lexiconFileInput = document.getElementById("lexiconFileInput");
  const lexiconLoadMsg = document.getElementById("lexiconLoadMsg");
  const errorBanner = document.getElementById("errorBanner");

  const tabSingle = document.getElementById("tabSingle");
  const tabBatch = document.getElementById("tabBatch");
  const singlePanel = document.getElementById("singlePanel");
  const batchPanel = document.getElementById("batchPanel");

  const singleJobId = document.getElementById("singleJobId");
  const singleTitle = document.getElementById("singleTitle");
  const singleDesc = document.getElementById("singleDesc");
  const singleSkills = document.getElementById("singleSkills");
  const singleTools = document.getElementById("singleTools");
  const runSingleBtn = document.getElementById("runSingleBtn");
  const fillSampleBtn = document.getElementById("fillSampleBtn");

  const xlsxFileInput = document.getElementById("xlsxFileInput");
  const exportXlsxBtn = document.getElementById("exportXlsxBtn");
  const exportSingleXlsxBtn = document.getElementById("exportSingleXlsxBtn");
  const batchLoadInfo = document.getElementById("batchLoadInfo");

  const resultsSection = document.getElementById("resultsSection");
  const batchExplorer = document.getElementById("batchExplorer");
  const batchSearchInput = document.getElementById("batchSearchInput");
  const prevJobBtn = document.getElementById("prevJobBtn");
  const nextJobBtn = document.getElementById("nextJobBtn");
  const batchPosLabel = document.getElementById("batchPosLabel");
  const batchJobsBody = document.getElementById("batchJobsBody");

  const groupChart = document.getElementById("groupChart");
  const detailTitle = document.getElementById("detailTitle");
  const zeroSkillMsg = document.getElementById("zeroSkillMsg");
  const skillsDetailBody = document.getElementById("skillsDetailBody");
  const auditBody = document.getElementById("auditBody");

  function showError(msg) {
    if (!msg) {
      errorBanner.classList.add("hidden");
      errorBanner.textContent = "";
    } else {
      errorBanner.textContent = msg;
      errorBanner.classList.remove("hidden");
    }
  }

  function escapeHtml(str) {
    return String(str == null ? "" : str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function sha256Hex(arrayBuffer) {
    if (!window.crypto || !window.crypto.subtle) return "Unknown";
    const hashBuf = await window.crypto.subtle.digest("SHA-256", arrayBuffer);
    return Array.from(new Uint8Array(hashBuf))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  }

  async function gunzipArrayBuffer(arrayBuffer) {
    if (typeof DecompressionStream === "undefined") {
      throw new Error("目前瀏覽器不支援 DecompressionStream('gzip')，請使用最新版 Chrome。");
    }
    const ds = new DecompressionStream("gzip");
    const stream = new Blob([arrayBuffer]).stream().pipeThrough(ds);
    const outBuf = await new Response(stream).arrayBuffer();
    return new TextDecoder("utf-8").decode(outBuf);
  }

  function updateVersionBar(info) {
    const lexSha = info.lexicon_sha256 && info.lexicon_sha256 !== "Unknown"
      ? info.lexicon_sha256.slice(0, 12)
      : "Unknown";
    const g11cSha = info.g11c_sha256 && info.g11c_sha256 !== "Unknown"
      ? info.g11c_sha256.slice(0, 12)
      : "Unknown";
    versionBar.textContent =
      `Engine Version：${info.engine_version}｜` +
      `Lexicon Version：${info.lexicon_version}｜` +
      `Lexicon SHA256：${lexSha}｜` +
      `G11c SHA256：${g11cSha}｜` +
      `Skill Count：${info.skill_count}｜` +
      `AI Label Review Status：${info.ai_label_review_status}`;
  }

  async function ensureJiebaReady() {
    if (!jiebaInstance) {
      jiebaInstance = new window.JiebaLite();
      await jiebaInstance.initFromBase64(window.__JIEBA_GZ_B64);
    }
    if (!engine) {
      engine = new window.Engine1114Offline.WebSkillEngineOffline(jiebaInstance, window.__RULES_1114_DATA);
    }
  }

  lexiconFileInput.addEventListener("change", async (ev) => {
    const file = ev.target.files && ev.target.files[0];
    if (!file) return;
    showError("");
    engineStatusBadge.textContent = "載入詞庫與建置 AC 自動機中...";
    engineStatusBadge.className = "badge badge-warn";
    lexiconLoadMsg.textContent = `正在讀取 ${file.name}...`;

    try {
      await ensureJiebaReady();
      const buf = await file.arrayBuffer();
      const fileSha = await sha256Hex(buf);
      let jsonStr;
      if (file.name.toLowerCase().endsWith(".gz")) {
        jsonStr = await gunzipArrayBuffer(buf);
      } else {
        jsonStr = new TextDecoder("utf-8").decode(buf);
      }
      const bundle = JSON.parse(jsonStr);
      engine.loadBundleObject(bundle, fileSha);
      const info = engine.healthInfo();
      updateVersionBar(info);
      engineStatusBadge.textContent = "離線引擎就緒（11/14 AC + Rules）";
      engineStatusBadge.className = "badge badge-ok";
      lexiconLoadMsg.textContent = `已載入 ${file.name}（${info.skill_count} 項技能）`;
      runSingleBtn.disabled = false;
      xlsxFileInput.disabled = false;
    } catch (err) {
      engineStatusBadge.textContent = "詞庫載入失敗";
      engineStatusBadge.className = "badge badge-err";
      lexiconLoadMsg.textContent = "載入失敗";
      showError(`詞庫載入錯誤：${err.message || err}`);
    }
  });

  tabSingle.addEventListener("click", () => {
    tabSingle.classList.add("active");
    tabBatch.classList.remove("active");
    singlePanel.classList.remove("hidden");
    batchPanel.classList.add("hidden");
  });

  tabBatch.addEventListener("click", () => {
    tabBatch.classList.add("active");
    tabSingle.classList.remove("active");
    batchPanel.classList.remove("hidden");
    singlePanel.classList.add("hidden");
  });

  fillSampleBtn.addEventListener("click", () => {
    singleJobId.value = "SAMPLE_1114_01";
    singleTitle.value = "雲端資料工程師";
    singleDesc.value =
      "【員工福利】提供團體保險、年度健康檢查與豐富員工福利。\n" +
      "【工作內容】負責 GCP 雲端資料管線與 Python 自動化腳本開發，使用 BigQuery 與 SQL。\n" +
      "無需 Java 經驗，不用會 PHP。另需注意公司介紹不計入技能。";
    singleSkills.value = "Python、資料分析";
    singleTools.value = "GCP、Excel";
  });

  function renderKpis(summary, jobs, skillsLong) {
    document.getElementById("kpiJobs").textContent = summary.total_jobs;
    document.getElementById("kpiWithSkills").textContent = summary.jobs_with_skills;
    document.getElementById("kpiZeroSkills").textContent = summary.zero_skill_jobs;
    document.getElementById("kpiSkillsTotal").textContent = summary.total_skill_records;
    const hitGroups = new Set(skillsLong.map((s) => s.Skill_group10_code).filter((c) => c != null));
    document.getElementById("kpiGroups").textContent = hitGroups.size;
    document.getElementById("kpiAiSkills").textContent = summary.ai_skill_records;
  }

  function renderGroupChart(skillsLong) {
    const counts = new Map();
    for (let c = 1; c <= 10; c++) counts.set(`G${c} ${EXPECTED_GROUP10[c]}`, 0);
    let pending = 0;
    for (const s of skillsLong) {
      const code = s.Skill_group10_code;
      if (code != null && EXPECTED_GROUP10[code]) {
        const key = `G${code} ${EXPECTED_GROUP10[code]}`;
        counts.set(key, (counts.get(key) || 0) + 1);
      } else {
        pending++;
      }
    }
    if (pending > 0) counts.set("待分類", pending);
    const maxVal = Math.max(1, ...counts.values());
    groupChart.innerHTML = Array.from(counts.entries())
      .map(([label, cnt]) => {
        const pct = Math.round((cnt / maxVal) * 100);
        return `
          <div class="bar-row">
            <div class="bar-label">${escapeHtml(label)}</div>
            <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
            <div class="bar-count">${cnt}</div>
          </div>`;
      })
      .join("");
  }

  function renderSkillAndAuditTables(skills, auditRecords, titleText) {
    detailTitle.textContent = titleText;
    if (skills.length === 0) {
      zeroSkillMsg.classList.remove("hidden");
    } else {
      zeroSkillMsg.classList.add("hidden");
    }
    skillsDetailBody.innerHTML = skills
      .map((s) => {
        const gLabel = s.Skill_group10_code != null
          ? `G${s.Skill_group10_code} ${s.Skill_group10}`
          : (s.Skill_group10 || "待分類");
        const aiBadge = s.Is_AI_Skill ? '<span class="pill pill-ai">AI 候選</span>' : "否";
        return `
          <tr>
            <td>${escapeHtml(s.ID)}</td>
            <td><strong>${escapeHtml(s.SKILL_NAME_ZH || s.SKILL_NAME)}</strong><br><span class="subtitle">${escapeHtml(s.SKILL_NAME)}</span></td>
            <td><code>${escapeHtml(s.SKILL_ID)}</code></td>
            <td>${escapeHtml(s.Category_Name)} / ${escapeHtml(s.Subcategory_Name)}</td>
            <td>${escapeHtml(gLabel)}</td>
            <td>${aiBadge}</td>
            <td><span class="pill">${escapeHtml(s.MATCHED_FROM)}</span></td>
            <td>${escapeHtml(s.evidence_snippet)}</td>
          </tr>`;
      })
      .join("");

    auditBody.innerHTML = auditRecords.length === 0
      ? '<tr><td colspan="7" class="subtitle">無 Audit 排除或查核紀錄</td></tr>'
      : auditRecords
          .map((a) => {
            const cls = a.decision === "exclude" ? "pill-excl" : "pill-keep";
            return `
              <tr>
                <td>${escapeHtml(a.ID)}</td>
                <td><span class="pill ${cls}">${escapeHtml(a.decision)}</span></td>
                <td><code>${escapeHtml(a.SKILL_ID)}</code></td>
                <td>${escapeHtml(a.SKILL_NAME_ZH)}</td>
                <td>${escapeHtml(a.matched_term)}</td>
                <td>${escapeHtml(a.reason)}</td>
                <td>${escapeHtml(a.evidence_snippet)}</td>
              </tr>`;
          })
          .join("");
  }

  function selectBatchJob(idx) {
    if (!filteredBatchJobs.length) return;
    selectedJobIndex = Math.max(0, Math.min(idx, filteredBatchJobs.length - 1));
    const job = filteredBatchJobs[selectedJobIndex];
    batchPosLabel.textContent = `第 ${selectedJobIndex + 1} / ${filteredBatchJobs.length} 筆`;
    prevJobBtn.disabled = selectedJobIndex <= 0;
    nextJobBtn.disabled = selectedJobIndex >= filteredBatchJobs.length - 1;

    Array.from(batchJobsBody.querySelectorAll("tr")).forEach((tr, i) => {
      tr.classList.toggle("selected", i === selectedJobIndex);
    });

    const jobSkills = lastResult.skills_long.filter((s) => s.ID === job.ID);
    const jobAudit = lastResult.audit_records.filter((a) => a.ID === job.ID);
    renderSkillAndAuditTables(jobSkills, jobAudit, `技能明細表 — ${job.ID}（${job["104職位名稱"]}）`);
  }

  function renderBatchTable() {
    const q = batchSearchInput.value.trim().toLowerCase();
    filteredBatchJobs = lastResult.jobs.filter((j) =>
      !q || j.ID.toLowerCase().includes(q) || j["104職位名稱"].toLowerCase().includes(q)
    );
    batchJobsBody.innerHTML = filteredBatchJobs
      .map((j, idx) => `
        <tr class="batch-row" data-idx="${idx}">
          <td>${idx + 1}</td>
          <td><code>${escapeHtml(j.ID)}</code></td>
          <td>${escapeHtml(j["104職位名稱"])}</td>
          <td>${j["技能數"]}</td>
          <td>${j["AI技能數"]}</td>
        </tr>`)
      .join("");

    Array.from(batchJobsBody.querySelectorAll("tr")).forEach((tr) => {
      tr.addEventListener("click", () => selectBatchJob(Number(tr.dataset.idx)));
    });
    if (filteredBatchJobs.length > 0) {
      selectBatchJob(0);
    } else {
      batchPosLabel.textContent = "第 0 / 0 筆";
      renderSkillAndAuditTables([], [], "技能明細表（無符合搜尋結果）");
    }
  }

  runSingleBtn.addEventListener("click", () => {
    showError("");
    try {
      const payload = {
        ID: singleJobId.value.trim() || "SINGLE_001",
        "104職位名稱": singleTitle.value,
        "職位描述": singleDesc.value,
        "工作技能": singleSkills.value,
        "電腦工具": singleTools.value,
      };
      lastResult = engine.extractBatchRecords([payload]);
      resultsSection.classList.remove("hidden");
      batchExplorer.classList.add("hidden");
      exportSingleXlsxBtn.classList.remove("hidden");
      renderKpis(lastResult.summary, lastResult.jobs, lastResult.skills_long);
      renderGroupChart(lastResult.skills_long);
      renderSkillAndAuditTables(lastResult.skills_long, lastResult.audit_records, `技能明細表 — ${payload.ID}`);
    } catch (err) {
      showError(`擷取失敗：${err.message || err}`);
    }
  });

  xlsxFileInput.addEventListener("change", async (ev) => {
    const file = ev.target.files && ev.target.files[0];
    if (!file) return;
    showError("");
    batchLoadInfo.classList.remove("hidden");
    batchLoadInfo.textContent = `正在離線解析與擷取 ${file.name}...`;

    try {
      const buf = await file.arrayBuffer();
      const rawRecords = await window.XlsxLite.readXlsxRecords(buf);
      lastResult = engine.extractBatchRecords(rawRecords);
      batchLoadInfo.textContent =
        `已讀取 ${lastResult.summary.input_rows} 列（排除兼職 ${lastResult.summary.excluded_part_time} 列），` +
        `完成分析 ${lastResult.summary.total_jobs} 筆職缺（上限 100 筆）。`;
      resultsSection.classList.remove("hidden");
      batchExplorer.classList.remove("hidden");
      exportSingleXlsxBtn.classList.add("hidden");
      exportXlsxBtn.disabled = false;

      renderKpis(lastResult.summary, lastResult.jobs, lastResult.skills_long);
      renderGroupChart(lastResult.skills_long);
      renderBatchTable();
    } catch (err) {
      batchLoadInfo.classList.add("hidden");
      showError(`Excel 解析失敗：${err.message || err}`);
    }
  });

  batchSearchInput.addEventListener("input", renderBatchTable);
  prevJobBtn.addEventListener("click", () => selectBatchJob(selectedJobIndex - 1));
  nextJobBtn.addEventListener("click", () => selectBatchJob(selectedJobIndex + 1));

  async function downloadResultXlsx() {
    if (!lastResult) return;
    const sheets = [
      {
        name: "Skills_Long",
        headers: [
          "ID", "資料月份", "104職位名稱", "SKILL_ID", "SKILL_NAME", "SKILL_NAME_ZH",
          "Category_Name", "Subcategory_Name", "Skill_group10_code", "Skill_group10",
          "Is_AI_Skill", "MATCHED_FROM", "matched_term", "evidence_snippet",
        ],
        rows: lastResult.skills_long.map((s) => [
          s.ID, s["資料月份"], s["104職位名稱"], s.SKILL_ID, s.SKILL_NAME, s.SKILL_NAME_ZH,
          s.Category_Name, s.Subcategory_Name,
          s.Skill_group10_code == null ? "" : s.Skill_group10_code,
          s.Skill_group10, s.Is_AI_Skill, s.MATCHED_FROM, s.matched_term, s.evidence_snippet,
        ]),
      },
      {
        name: "Group10_Summary",
        headers: ["ID", "Skill_group10_code", "Skill_group10", "Skill_Count", "AI_Skill_Count", "Matched_Skills"],
        rows: lastResult.group10_summary.map((g) => [
          g.ID, g.Skill_group10_code == null ? "" : g.Skill_group10_code,
          g.Skill_group10, g.Skill_Count, g.AI_Skill_Count, g.Matched_Skills,
        ]),
      },
      {
        name: "Jobs",
        headers: ["ID", "資料月份", "104職位名稱", "技能數", "AI技能數", "是否命中技能"],
        rows: lastResult.jobs.map((j) => [
          j.ID, j["資料月份"], j["104職位名稱"], j["技能數"], j["AI技能數"], j["是否命中技能"],
        ]),
      },
      {
        name: "Audit",
        headers: ["ID", "資料月份", "104職位名稱", "decision", "SKILL_ID", "SKILL_NAME_ZH", "matched_term", "source_field", "reason", "evidence_snippet"],
        rows: lastResult.audit_records.map((a) => [
          a.ID, a["資料月份"], a["104職位名稱"], a.decision, a.SKILL_ID, a.SKILL_NAME_ZH,
          a.matched_term, a.source_field, a.reason, a.evidence_snippet,
        ]),
      },
    ];
    const bytes = await window.XlsxLite.writeMultiSheetXlsx(sheets);
    const blob = new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `offline_skill_extraction_${new Date().toISOString().slice(0, 10)}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  exportXlsxBtn.addEventListener("click", downloadResultXlsx);
  exportSingleXlsxBtn.addEventListener("click", downloadResultXlsx);
})();

