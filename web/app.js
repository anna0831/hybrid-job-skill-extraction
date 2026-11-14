(function () {
  "use strict";

  const DEMO_JOBS = {
    data_engineer: {
      job_title: "資料工程師",
      job_description:
        "【工作內容】\n1. 負責企業級 ETL 資料管線開發與維運，使用 Python 與 SQL 進行資料清理與轉換。\n2. 建置雲端資料倉儲於 GCP (Google Cloud Platform) 與 BigQuery，並以 Docker 容器化部署服務。\n3. 與機器學習團隊協作進行特徵工程與資料品質監控。\n【福利制度】\n享勞健保、年度員工健康檢查與旅遊補助。",
      job_skills: "資料處理、資料庫程式設計",
      computer_tools: "Python, SQL, Docker",
    },
    semiconductor: {
      job_title: "半導體製程工程師",
      job_description:
        "【工作內容】\n1. 負責晶圓製程良率分析與異常排除，運用 SPC 統計製程管制監控機台參數。\n2. 執行工程製程控制、實驗設計 (DOE) 與量測數據判讀。\n3. 撰寫 SOP 與跨部門協調產線改善。",
      job_skills: "製程規劃、品質管理",
      computer_tools: "Excel, Minitab",
    },
    admin: {
      job_title: "行政人員",
      job_description:
        "【工作內容】\n1. 協助公司文件檔案歸檔、會議紀錄與日常行政庶務。\n2. 彙整每月營運報表、客戶資料更新維護與請款單核對。\n3. 協助訪客接待與電話轉接。",
      job_skills: "行政事務處理、文件管理",
      computer_tools: "Microsoft Office, Excel, Word",
    },
    welfare_trap: {
      job_title: "品牌行銷專員",
      job_description:
        "【公司簡介】\n我們重視 ESG 永續發展與氣候變遷、經濟發展議題，致力成為產業領導品牌。\n【員工福利】\n提供優於勞基法之團體保險、勞健保、年度健康檢查與三節禮金。\n【工作內容】\n1. 為整復推拿品牌製作社群貼文文案與宣傳短影片。\n2. 規劃數位廣告投放與社群媒體經營。",
      job_skills: "社群行銷",
      computer_tools: "",
    },
  };

  let currentMode = "dataset";
  let lastPayload = null;
  let datasetsByCity = {};

  const healthStatusBadge = document.getElementById("healthStatusBadge");
  const healthDetails = document.getElementById("healthDetails");
  const errorBanner = document.getElementById("errorBanner");
  const noticeBanner = document.getElementById("noticeBanner");

  const tabDatasetBtn = document.getElementById("tabDatasetBtn");
  const tabSingleBtn = document.getElementById("tabSingleBtn");
  const tabUploadBtn = document.getElementById("tabUploadBtn");

  const datasetPanel = document.getElementById("datasetPanel");
  const singlePanel = document.getElementById("singlePanel");
  const uploadPanel = document.getElementById("uploadPanel");

  const citySelect = document.getElementById("citySelect");
  const monthSelect = document.getElementById("monthSelect");
  const datasetMetaBox = document.getElementById("datasetMetaBox");

  const jobTitleInput = document.getElementById("jobTitle");
  const jobDescInput = document.getElementById("jobDesc");
  const jobSkillsInput = document.getElementById("jobSkills");
  const computerToolsInput = document.getElementById("computerTools");
  const xlsxFileInput = document.getElementById("xlsxFileInput");

  const analyzeBtn = document.getElementById("analyzeBtn");
  const clearBtn = document.getElementById("clearBtn");
  const downloadXlsxBtn = document.getElementById("downloadXlsxBtn");

  const resultsSection = document.getElementById("resultsSection");
  const skillDetailsSection = document.getElementById("skillDetailsSection");
  const batchResultDetails = document.getElementById("batchResultDetails");
  const skillScopeHeading = document.getElementById("skillScopeHeading");
  const skillTableHeading = document.getElementById("skillTableHeading");
  const skillChips = document.getElementById("skillChips");
  const jobSearchInput = document.getElementById("jobSearchInput");
  const jobSortSelect = document.getElementById("jobSortSelect");
  const prevJobBtn = document.getElementById("prevJobBtn");
  const nextJobBtn = document.getElementById("nextJobBtn");
  const showAllSkillsBtn = document.getElementById("showAllSkillsBtn");

  let lastBatchData = null;
  let selectedJobId = null;

  function showError(msg) {
    errorBanner.textContent = msg;
    errorBanner.classList.remove("hidden");
  }

  function clearError() {
    errorBanner.textContent = "";
    errorBanner.classList.add("hidden");
  }

  function showNotice(msg) {
    if (!msg) {
      noticeBanner.textContent = "";
      noticeBanner.classList.add("hidden");
      return;
    }
    noticeBanner.textContent = msg;
    noticeBanner.classList.remove("hidden");
  }

  function escapeHtml(str) {
    return String(str == null ? "" : str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function loadHealth() {
    try {
      const resp = await fetch("/api/health");
      const data = await resp.json();
      if (data.ready) {
        healthStatusBadge.textContent = "系統就緒（11/11 AC + Rules）";
        healthStatusBadge.className = "badge badge-ok";
        healthDetails.textContent =
          `詞庫：${data.lexicon_version}（${data.skill_count} 項技能）｜` +
          `十大分類：${data.grouped_version}｜程式版本：${data.code_version}`;
      } else {
        healthStatusBadge.textContent = "詞庫尚未建置";
        healthStatusBadge.className = "badge badge-warn";
        healthDetails.textContent = data.error || "請先產生 11/11 Web 詞庫檔";
      }
    } catch (err) {
      healthStatusBadge.textContent = "無法連線後端 API";
      healthStatusBadge.className = "badge badge-warn";
      healthDetails.textContent = String(err);
    }
  }

  function updateMonthOptions() {
    const city = citySelect.value;
    const list = datasetsByCity[city] || [];
    if (list.length === 0) {
      monthSelect.innerHTML = `<option value="">無可用月份</option>`;
      datasetMetaBox.textContent = "目前沒有可用的資料集。";
      return;
    }
    monthSelect.innerHTML = list
      .map((ds) => `<option value="${escapeHtml(ds.dataset_id)}">${escapeHtml(ds.year_month)}</option>`)
      .join("");
    updateDatasetMetaBox();
  }

  function getDatasetButtonLabel(ds) {
    if (!ds) return "分析選定資料集";
    const count = Number(ds.sample_size || 0);
    if (ds.access_level === "sanitized_demo") {
      return `分析 ${count} 筆示範職缺`;
    }
    if (count >= 100) {
      return "抽取並分析 100 筆職缺";
    }
    return `分析 ${count} 筆職缺`;
  }

  function updateDatasetMetaBox() {
    const city = citySelect.value;
    const dsId = monthSelect.value;
    const ds = (datasetsByCity[city] || []).find((x) => x.dataset_id === dsId);
    if (!ds) {
      datasetMetaBox.textContent = "請選擇縣市與資料月份。";
      if (currentMode === "dataset") {
        analyzeBtn.textContent = "分析選定資料集";
      }
      return;
    }
    const isDemo = ds.access_level === "sanitized_demo";
    const lessNote =
      ds.sample_size < 100
        ? `（注意：實際可分析僅 ${ds.sample_size} 筆，少於 100 筆）`
        : "";
    const accessLabel = isDemo
      ? "脫敏示範資料（非完整 100 筆正式研究資料）"
      : "研究授權資料集";
    datasetMetaBox.innerHTML =
      `<strong>資料集名稱：</strong>${escapeHtml(ds.city)}（<code>${escapeHtml(ds.dataset_id)}</code>）｜` +
      `<strong>資料月份：</strong>${escapeHtml(ds.year_month)}<br/>` +
      `<strong>實際可分析筆數：</strong>${ds.sample_size} 筆（母體 ${ds.raw_job_count} 筆／篩選去重 ${ds.available_job_count} 筆，固定 seed=${ds.sample_seed}）${escapeHtml(lessNote)}<br/>` +
      `<strong>資料性質：</strong>${escapeHtml(accessLabel)}｜<strong>來源檔案：</strong>${escapeHtml(ds.source_filename)}｜<strong>篩選規則：</strong>${escapeHtml(ds.role_filter_rule || "排除兼職")}`;

    if (currentMode === "dataset") {
      analyzeBtn.textContent = getDatasetButtonLabel(ds);
    }
  }

  async function loadDatasets() {
    try {
      const resp = await fetch("/api/datasets");
      const data = await resp.json();
      datasetsByCity = data.cities || {};
      const cityNames = Object.keys(datasetsByCity);
      if (cityNames.length === 0) {
        citySelect.innerHTML = `<option value="">尚無可用縣市</option>`;
        monthSelect.innerHTML = `<option value="">尚無可用月份</option>`;
        datasetMetaBox.textContent = data.error || "尚未建立 dataset_manifest.json。";
        return;
      }
      citySelect.innerHTML = cityNames
        .map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`)
        .join("");
      updateMonthOptions();
    } catch (err) {
      datasetMetaBox.textContent = `載入資料集清單失敗：${err}`;
    }
  }

  function switchMode(mode) {
    currentMode = mode;
    clearError();
    showNotice("");
    tabDatasetBtn.classList.toggle("active", mode === "dataset");
    tabSingleBtn.classList.toggle("active", mode === "single");
    tabUploadBtn.classList.toggle("active", mode === "upload");

    datasetPanel.classList.toggle("hidden", mode !== "dataset");
    singlePanel.classList.toggle("hidden", mode !== "single");
    uploadPanel.classList.toggle("hidden", mode !== "upload");

    if (mode === "dataset") {
      const city = citySelect.value;
      const dsId = monthSelect.value;
      const ds = (datasetsByCity[city] || []).find((x) => x.dataset_id === dsId);
      analyzeBtn.textContent = getDatasetButtonLabel(ds);
    } else if (mode === "upload") {
      analyzeBtn.textContent = "分析上傳的 Excel 職缺";
    } else {
      analyzeBtn.textContent = "開始分析";
    }
  }

  function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const res = String(reader.result || "");
        const idx = res.indexOf(",");
        resolve(idx >= 0 ? res.slice(idx + 1) : res);
      };
      reader.onerror = () => reject(new Error("讀取檔案失敗。"));
      reader.readAsDataURL(file);
    });
  }

  async function buildRequest() {
    if (currentMode === "dataset") {
      const dsId = monthSelect.value;
      if (!dsId) {
        throw new Error("請先選擇有效的縣市與資料月份。");
      }
      return {
        endpoint: "/api/extract",
        payload: { dataset_id: dsId, mode: "fixed", count: 100 },
      };
    }
    if (currentMode === "upload") {
      const file = xlsxFileInput.files && xlsxFileInput.files[0];
      if (!file) {
        throw new Error("請先選擇要上傳的 .xlsx 檔案。");
      }
      const b64 = await fileToBase64(file);
      return {
        endpoint: "/api/extract/xlsx-upload",
        payload: { filename: file.name, content_base64: b64 },
      };
    }
    const payload = {
      job_title: jobTitleInput.value.trim(),
      job_description: jobDescInput.value,
      job_skills: jobSkillsInput.value.trim(),
      computer_tools: computerToolsInput.value.trim(),
    };
    if (!payload.job_title && !payload.job_description.trim()) {
      throw new Error("請輸入職缺名稱或工作內容。");
    }
    return { endpoint: "/api/extract", payload };
  }

  function setKpis(items) {
    items.forEach((item, idx) => {
      const n = idx + 1;
      const lbl = document.getElementById(`kpiLabel${n}`);
      const val = document.getElementById(`kpiVal${n}`);
      if (lbl) lbl.textContent = item.label;
      if (val) val.textContent = item.value;
    });
  }

  function buildGroupSummaryFromSkills(skills) {
    const map = {};
    (skills || []).forEach((s) => {
      const code = s.Skill_group10_code;
      const name = code != null ? (s.Skill_group10 || "待分類") : "待分類";
      const key = code != null ? `G${code}` : "UNMAPPED";
      if (!map[key]) {
        map[key] = {
          Skill_group10_code: code,
          Skill_group10: name,
          "技能數": 0,
          _sort: code != null ? Number(code) : 999,
        };
      }
      map[key]["技能數"] += 1;
    });
    return Object.values(map).sort((a, b) => a._sort - b._sort);
  }

  function renderGroupChart(groups) {
    const chartEl = document.getElementById("groupChart");
    if (!groups || groups.length === 0) {
      chartEl.innerHTML = `<div class="empty-state">未擷取到技能，無 G1–G10 分類分布。</div>`;
      return;
    }
    const maxCnt = Math.max(...groups.map((g) => g["技能數"] || 1), 1);
    chartEl.innerHTML = groups
      .map((g) => {
        const code = g.Skill_group10_code != null ? `G${g.Skill_group10_code}` : "待分類";
        const label = `${code} ${g.Skill_group10 || "待分類"}`;
        const cnt = g["技能數"] || 0;
        const pct = Math.round((cnt / maxCnt) * 100);
        return `
          <div class="chart-row">
            <div><strong>${escapeHtml(label)}</strong></div>
            <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
            <div>${cnt} 項</div>
          </div>`;
      })
      .join("");
  }

  function renderSkillDetails(skills, scopeLabel, showJobPrefix = false) {
    skillScopeHeading.textContent = `技能分類分布（G1–G10）— ${scopeLabel}`;
    skillTableHeading.textContent = `技能明細表（${skills.length} 筆）— ${scopeLabel}`;

    const groups = buildGroupSummaryFromSkills(skills);
    renderGroupChart(groups);

    if (!skills || skills.length === 0) {
      skillChips.innerHTML = "";
      document.getElementById("skillsTableBody").innerHTML =
        `<tr><td colspan="7"><div class="empty-state">未擷取到技能。</div></td></tr>`;
      return;
    }

    const uniqueChips = [];
    const seenChip = new Set();
    skills.forEach((s) => {
      const key = s.SKILL_ID || s.SKILL_NAME_ZH || s.SKILL_NAME;
      if (!seenChip.has(key)) {
        seenChip.add(key);
        uniqueChips.push(s);
      }
    });
    skillChips.innerHTML = uniqueChips
      .slice(0, 60)
      .map((s) => {
        const zh = s.SKILL_NAME_ZH || s.SKILL_NAME || "";
        const gCode = s.Skill_group10_code != null ? `G${s.Skill_group10_code}` : "待分類";
        return `<span class="skill-chip ${s.Is_AI_Skill ? "is-ai" : ""}">${escapeHtml(zh)} <span style="opacity:0.7;">(${escapeHtml(gCode)})</span></span>`;
      })
      .join("");

    const tbody = document.getElementById("skillsTableBody");
    tbody.innerHTML = skills
      .map((s) => {
        const zh = s.SKILL_NAME_ZH || s.SKILL_NAME || "";
        const en = s.SKILL_NAME && s.SKILL_NAME !== zh ? `<div class="mono">${escapeHtml(s.SKILL_NAME)}</div>` : "";
        const jobTag = showJobPrefix && s.ID ? `<div style="font-size:0.78rem;color:#5a677a;">[${escapeHtml(s.ID)}] ${escapeHtml(s["104職位名稱"] || "")}</div>` : "";
        const catText = [s.Category, s.Subcategory].filter(Boolean).join(" / ") || "—";
        const gLabel =
          s.Skill_group10_code != null
            ? `G${s.Skill_group10_code} ${escapeHtml(s.Skill_group10)}`
            : "待分類";
        const amb = s.Ambiguity_note
          ? `<div style="font-size:0.78rem;color:#9a3412;">${escapeHtml(s.Ambiguity_note)}</div>`
          : "";
        const aiTag = s.Is_AI_Skill ? `<span class="badge badge-ai">AI 技能</span>` : "否";
        return `
          <tr>
            <td>${jobTag}<strong>${escapeHtml(zh)}</strong>${en}</td>
            <td class="mono">${escapeHtml(s.SKILL_ID || "")}</td>
            <td style="font-size:0.85rem;">${escapeHtml(catText)}</td>
            <td><span class="badge badge-g">${gLabel}</span>${amb}</td>
            <td>${aiTag}</td>
            <td>${escapeHtml(s.MATCHED_FROM || "")}<div style="font-size:0.78rem;color:#5a677a;">${escapeHtml(s.match_type || "")}</div></td>
            <td style="max-width:300px;font-size:0.84rem;">${escapeHtml(s.evidence_snippet || "")}</td>
          </tr>`;
      })
      .join("");
  }

  function renderSingleResult(data) {
    lastBatchData = null;
    selectedJobId = null;
    skillDetailsSection.classList.remove("hidden");
    batchResultDetails.classList.add("hidden");

    const stats = data.stats || {};
    const skills = data.skills || [];
    const hasSkills = skills.length > 0 ? 1 : 0;
    setKpis([
      { label: "職缺總數", value: 1 },
      { label: "有技能職缺數", value: hasSkills },
      { label: "零技能職缺數", value: 1 - hasSkills },
      { label: "技能紀錄總數", value: stats.total_skills ?? skills.length },
      { label: "命中的 G1–G10 分類數", value: stats.matched_group_count ?? 0 },
      { label: "AI 技能數", value: stats.ai_skill_count ?? 0 },
    ]);

    const title = (data.job && data.job["104職位名稱"]) || "單篇職缺";
    renderSkillDetails(skills, title, false);

    const mergedAudit = [...(data.audit_records || [])];
    const seenAudit = new Set(mergedAudit.map((r) => `${r.SKILL_ID}|${r.matched_term}|${r.decision}`));
    (data.excluded_candidates || []).forEach((ex) => {
      const k = `${ex.SKILL_ID}|${ex.matched_term}|exclude`;
      if (!seenAudit.has(k)) {
        seenAudit.add(k);
        mergedAudit.push({
          "104職位名稱": title,
          SKILL_ID: ex.SKILL_ID || "",
          matched_term: ex.matched_term || "",
          decision: "exclude",
          reason: ex.reason || "",
          evidence_snippet: ex.evidence_snippet || "",
        });
      }
    });
    renderAuditTable(mergedAudit);
  }

  function getFilteredSortedBatchJobs() {
    if (!lastBatchData) return [];
    const q = (jobSearchInput ? jobSearchInput.value : "").trim().toLowerCase();
    const sortBy = jobSortSelect ? jobSortSelect.value : "default";
    let list = [...(lastBatchData.jobs || [])];
    if (q) {
      list = list.filter((j) => {
        const idStr = String(j.ID || "").toLowerCase();
        const titleStr = String(j["104職位名稱"] || "").toLowerCase();
        return idStr.includes(q) || titleStr.includes(q);
      });
    }
    if (sortBy === "skills_desc") {
      list.sort((a, b) => (b["技能數"] || 0) - (a["技能數"] || 0));
    } else if (sortBy === "skills_asc") {
      list.sort((a, b) => (a["技能數"] || 0) - (b["技能數"] || 0));
    }
    return list;
  }

  function renderBatchJobRows() {
    if (!lastBatchData) return;
    const filtered = getFilteredSortedBatchJobs();
    const tbody = document.getElementById("batchJobsTableBody");
    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state">沒有符合搜尋條件的職缺。</div></td></tr>`;
      return;
    }
    tbody.innerHTML = filtered
      .map((j) => {
        const isActive = selectedJobId != null && String(j.ID) === String(selectedJobId);
        const zeroText = j["是否命中技能"] ? "否" : "是（未擷取到技能）";
        return `
          <tr class="batch-job-row ${isActive ? "active-job" : ""}" data-job-id="${escapeHtml(j.ID)}">
            <td class="mono">${escapeHtml(j.ID)}</td>
            <td>${escapeHtml(j["資料月份"] || "")}</td>
            <td><strong>${escapeHtml(j["104職位名稱"])}</strong></td>
            <td>${j["技能數"]}</td>
            <td>${zeroText}</td>
          </tr>`;
      })
      .join("");

    tbody.querySelectorAll(".batch-job-row").forEach((tr) => {
      tr.addEventListener("click", () => {
        selectBatchJob(tr.getAttribute("data-job-id"));
      });
    });
  }

  function selectBatchJob(jobId) {
    if (!lastBatchData) return;
    selectedJobId = jobId;
    renderBatchJobRows();

    const allSkills = lastBatchData.skills_long || [];
    if (!jobId) {
      const totalJobs = (lastBatchData.jobs || []).length;
      renderSkillDetails(allSkills, `全批 ${totalJobs} 筆職缺彙總`, true);
      return;
    }
    const job = (lastBatchData.jobs || []).find((j) => String(j.ID) === String(jobId));
    const jobSkills = allSkills.filter((s) => String(s.ID) === String(jobId));
    const label = job ? `${job.ID} ${job["104職位名稱"]}` : String(jobId);
    renderSkillDetails(jobSkills, label, false);
  }

  function stepBatchJob(delta) {
    const filtered = getFilteredSortedBatchJobs();
    if (filtered.length === 0) return;
    if (selectedJobId == null) {
      selectBatchJob(filtered[0].ID);
      return;
    }
    const idx = filtered.findIndex((j) => String(j.ID) === String(selectedJobId));
    const nextIdx = idx < 0 ? 0 : Math.max(0, Math.min(filtered.length - 1, idx + delta));
    selectBatchJob(filtered[nextIdx].ID);
  }

  function renderBatchResult(data) {
    lastBatchData = data;
    skillDetailsSection.classList.remove("hidden");
    batchResultDetails.classList.remove("hidden");

    const stats = data.stats || {};
    const allSkills = data.skills_long || [];
    const matchedGroupCount = buildGroupSummaryFromSkills(allSkills).filter((g) => g.Skill_group10_code != null).length;

    setKpis([
      { label: "職缺總數", value: stats.job_count ?? 0 },
      { label: "有技能職缺數", value: stats.jobs_with_skills ?? 0 },
      { label: "零技能職缺數", value: stats.zero_skill_jobs ?? 0 },
      { label: "技能紀錄總數", value: stats.total_skill_records ?? allSkills.length },
      { label: "命中的 G1–G10 分類數", value: matchedGroupCount },
      { label: "AI 技能數", value: stats.total_ai_skill_records ?? 0 },
    ]);

    if (data.notice) {
      showNotice(data.notice);
    }

    const jobs = data.jobs || [];
    selectedJobId = jobs.length > 0 ? jobs[0].ID : null;
    if (jobSearchInput) jobSearchInput.value = "";
    if (jobSortSelect) jobSortSelect.value = "default";
    renderBatchJobRows();
    if (selectedJobId != null) {
      selectBatchJob(selectedJobId);
    } else {
      renderSkillDetails([], "無職缺", false);
    }

    renderAuditTable(data.audit_records || []);
  }

  function renderAuditTable(records) {
    const auditBlock = document.getElementById("auditBlock");
    const tbody = document.getElementById("auditTableBody");
    if (!records || records.length === 0) {
      auditBlock.classList.add("hidden");
      tbody.innerHTML = "";
      return;
    }
    auditBlock.classList.remove("hidden");
    tbody.innerHTML = records
      .map((r) => `
        <tr>
          <td><div>${escapeHtml(r["104職位名稱"] || "")}</div><div class="mono">${escapeHtml(r.SKILL_ID || "")}</div></td>
          <td>${escapeHtml(r.matched_term || "")}</td>
          <td><span class="badge badge-warn">${escapeHtml(r.decision || "")}</span></td>
          <td>${escapeHtml(r.reason || "")}</td>
          <td style="max-width:280px;font-size:0.84rem;">${escapeHtml(r.evidence_snippet || "")}</td>
        </tr>`)
      .join("");
  }

  async function runAnalyze() {
    clearError();
    showNotice("");
    let reqInfo;
    try {
      reqInfo = await buildRequest();
    } catch (err) {
      showError(err.message);
      return;
    }

    analyzeBtn.disabled = true;
    analyzeBtn.textContent = "分析中…";
    try {
      const resp = await fetch(reqInfo.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(reqInfo.payload),
      });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || `API 錯誤 (${resp.status})`);
      }
      lastPayload = reqInfo.payload;
      resultsSection.classList.remove("hidden");
      downloadXlsxBtn.classList.remove("hidden");
      if (data.mode === "batch") {
        renderBatchResult(data);
      } else {
        renderSingleResult(data);
      }
    } catch (err) {
      showError(err.message || "分析失敗，請稍後再試。");
    } finally {
      analyzeBtn.disabled = false;
      switchMode(currentMode);
    }
  }

  async function downloadExcel() {
    if (!lastPayload) return;
    clearError();
    downloadXlsxBtn.disabled = true;
    downloadXlsxBtn.textContent = "產生 Excel 中…";
    try {
      const resp = await fetch("/api/export/xlsx", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(lastPayload),
      });
      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.detail || `匯出失敗 (${resp.status})`);
      }
      const blob = await resp.blob();
      const disp = resp.headers.get("Content-Disposition") || "";
      const match = disp.match(/filename="([^"]+)"/);
      const filename = match ? match[1] : "104_skill_extraction.xlsx";

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      showError(err.message || "下載 Excel 失敗。");
    } finally {
      downloadXlsxBtn.disabled = false;
      downloadXlsxBtn.textContent = "下載完整分析報告 (.xlsx)";
    }
  }

  document.querySelectorAll("[data-demo]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const demo = DEMO_JOBS[btn.getAttribute("data-demo")];
      if (!demo) return;
      switchMode("single");
      jobTitleInput.value = demo.job_title;
      jobDescInput.value = demo.job_description;
      jobSkillsInput.value = demo.job_skills;
      computerToolsInput.value = demo.computer_tools;
      clearError();
    });
  });

  citySelect.addEventListener("change", updateMonthOptions);
  monthSelect.addEventListener("change", updateDatasetMetaBox);
  if (jobSearchInput) jobSearchInput.addEventListener("input", renderBatchJobRows);
  if (jobSortSelect) jobSortSelect.addEventListener("change", renderBatchJobRows);
  if (prevJobBtn) prevJobBtn.addEventListener("click", () => stepBatchJob(-1));
  if (nextJobBtn) nextJobBtn.addEventListener("click", () => stepBatchJob(1));
  if (showAllSkillsBtn) showAllSkillsBtn.addEventListener("click", () => selectBatchJob(null));
  tabDatasetBtn.addEventListener("click", () => switchMode("dataset"));
  tabSingleBtn.addEventListener("click", () => switchMode("single"));
  tabUploadBtn.addEventListener("click", () => switchMode("upload"));
  analyzeBtn.addEventListener("click", runAnalyze);
  downloadXlsxBtn.addEventListener("click", downloadExcel);
  clearBtn.addEventListener("click", () => {
    jobTitleInput.value = "";
    jobDescInput.value = "";
    jobSkillsInput.value = "";
    computerToolsInput.value = "";
    if (xlsxFileInput) xlsxFileInput.value = "";
    lastPayload = null;
    resultsSection.classList.add("hidden");
    downloadXlsxBtn.classList.add("hidden");
    clearError();
    showNotice("");
  });

  loadHealth();
  loadDatasets();
})();
