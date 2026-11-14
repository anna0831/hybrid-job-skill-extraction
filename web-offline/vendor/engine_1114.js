/**
 * engine_1114.js — Pure JavaScript port of 11/14 AC + Rules Skill Extraction Engine
 * Mirrors src/web_adapter.py + src/ac_rules_1114.py for 100% offline file:// execution.
 */
(function (root) {
  "use strict";

  const EXPECTED_GROUP10 = {
    1: "認知、分析與創新技能",
    2: "溝通、語言與人際技能",
    3: "個人特質、自我管理與身體能力",
    4: "財務、會計與經濟技能",
    5: "管理、商業、法遵與治理技能",
    6: "行政與一般數位技能",
    7: "營運、技職與第一線服務技能",
    8: "資訊科技、軟體、資料與AI技能",
    9: "醫療、健康與照護技能",
    10: "工程、自然科學、設計、環境與能源技能",
  };

  const SOFTWARE_CATEGORIES = new Set([17, 370, 369, 371, 372, 373, 374, 375, 376, 377, 378, 379, 380]);
  const MAX_BATCH_JOBS = 100;
  const GROUP10_SKILL_SEPARATOR = "｜";
  const STRUCTURED_FIELD_LABELS = new Set(["工作技能", "工具欄"]);
  const RE_STRUCTURED_TAG = /[^、,，]+/g;

  const ZH_CROSS_WORD_GUARD = new Set([
    "媒體", "軟體", "整理", "處理", "辦理", "準備", "具備", "個人", "恢復",
    "依照", "情感", "每年", "力量", "思維", "假日", "團體", "客人", "表現",
    "採光",
  ]);

  const JIEBA_2CHAR_WHITELIST = [
    "製程", "量試", "試作", "送樣", "首件", "稼働", "治具",
    "備料", "備件", "標案", "採購", "詢價", "驗收",
    "輪班", "物性", "化性", "採樣",
  ];

  const SYNONYM_GROUPS = [
    ["老師", "教師"],
    ["飲料", "飲品"],
    ["會客登記", "登記換證", "訪客登記"],
    ["駕駛接送", "接送任務"],
    ["車輛加油", "加油作業", "油箱加油"],
    ["打掃", "清潔"],
    ["藥品調劑", "調劑處方", "藥事調劑"],
  ];

  const PLURAL_PROTECTED = new Set([
    "windows", "news", "series", "species", "sales", "goods", "means", "arms",
    "securities", "analytics", "statistics", "logistics", "economics", "physics",
    "mathematics", "electronics", "mechanics", "graphics", "robotics", "ethics",
    "optics", "genetics", "diagnostics", "ergonomics", "dynamics", "kinetics", "acoustics",
  ]);

  const PLURAL_EXCEPTIONS = {
    caches: "cache", niches: "niche", headaches: "headache",
    movies: "movie", cookies: "cookie", calories: "calorie",
    analyses: "analysis", diagnoses: "diagnosis", hypotheses: "hypothesis",
    crises: "crisis", theses: "thesis",
  };

  const ENUM_SUFFIXES = [
    "服務", "作業", "管理", "處理", "工作", "技巧", "能力",
    "維護", "操作", "製作", "訓練", "分析", "規劃", "執行", "經驗",
  ];
  const ENUM_SUFFIX_PATTERN = ENUM_SUFFIXES.join("|");
  const ENUM_PATTERN = new RegExp(
    `([^、，,。.\\s\\d]{1,2}(?:(?:、|\\.)[^、，,。.\\s\\d]{1,2}){2,4})(${ENUM_SUFFIX_PATTERN})`,
    "g"
  );
  const BARE_CHAR_ENUM_PATTERN = /([^、，,。.\s\d])(?:、[^、，,。.\s\d]){2,}/g;
  const HAIR_ENUM_PATTERN = /((?:[剪染燙護洗造](?:、|\.)){1,4}[剪染燙護洗造])(?:服務|作業)?/g;

  const COORD_TAIL_LIST = [
    "評估", "介入", "規劃", "執行", "管理", "分析", "維護",
    "操作", "設計", "測試", "追蹤", "統計", "調配", "開發", "企劃", "教學",
  ];
  const COORD_TAIL_SET = new Set(COORD_TAIL_LIST);
  const COORD_CONJ = new Set(["與", "及", "和", "暨"]);

  const RE_ZH = /[\u4e00-\u9fff]/;
  const RE_CJK_NEARBY = /[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]/;

  function hasChinese(text) {
    return RE_ZH.test(text);
  }

  function expandSynonyms(term) {
    const results = new Set([term]);
    for (const group of SYNONYM_GROUPS) {
      for (const word of group) {
        if (term.includes(word)) {
          for (const alt of group) {
            results.add(term.split(word).join(alt));
          }
        }
      }
    }
    return results;
  }

  function normalizeFullwidthAlnum(text) {
    let out = "";
    for (let i = 0; i < text.length; i++) {
      const code = text.charCodeAt(i);
      if ((code >= 0xff10 && code <= 0xff19) || (code >= 0xff21 && code <= 0xff3a) || (code >= 0xff41 && code <= 0xff5a)) {
        out += String.fromCharCode(code - 0xfee0);
      } else if (code === 0x3000) {
        out += " ";
      } else {
        out += text[i];
      }
    }
    return out;
  }

  function normalizeAsciiHyphen(text) {
    return text.replace(/(?<=[A-Za-z0-9])-(?=[A-Za-z0-9])/g, " ");
  }

  function isLowercasedWordInEnglish(textCase, start, end) {
    if (start < 0 || end >= textCase.length) return false;
    let word = textCase.slice(start, end + 1);
    if (word.endsWith("s") && word.length > 2) word = word.slice(0, -1);
    const letters = word.replace(/[^A-Za-z]/g, "");
    if (!letters) return false;
    const isAllLower = letters === letters.toLowerCase();
    const isTitle = letters[0] === letters[0].toUpperCase() && letters.slice(1) === letters.slice(1).toLowerCase();
    if (!isAllLower && !isTitle) return false;
    const around = textCase.slice(Math.max(0, start - 6), start) + textCase.slice(end + 1, end + 7);
    return !RE_CJK_NEARBY.test(around);
  }

  function singularizeWord(word, caseWord) {
    if (word.length <= 3 || PLURAL_PROTECTED.has(word)) return word;
    if (PLURAL_EXCEPTIONS[word]) return PLURAL_EXCEPTIONS[word];
    if (caseWord) {
      if (caseWord.endsWith("s") && caseWord.length >= 3 && caseWord.slice(0, -1) === caseWord.slice(0, -1).toUpperCase() && /[A-Z]/.test(caseWord.slice(0, -1))) {
        return word.slice(0, -1);
      }
      if (caseWord === caseWord.toUpperCase() && /[A-Z]/.test(caseWord)) return word;
      if (/[a-z][A-Z]/.test(caseWord)) return word;
    }
    if (word.endsWith("ss") || word.endsWith("us") || word.endsWith("is")) return word;
    if (word.endsWith("ies")) return word.slice(0, -3) + "y";
    if (word.endsWith("sses")) return word.slice(0, -2);
    if (word.endsWith("xes") || word.endsWith("ches") || word.endsWith("shes")) return word.slice(0, -2);
    if (word.endsWith("s")) return word.slice(0, -1);
    return word;
  }

  function stemEnglishTextWithMap(text, caseText) {
    if (!text) return [text, [], []];
    const out = [];
    const startMap = [];
    const endMap = [];
    const n = text.length;
    let i = 0;
    while (i < n) {
      const ch = text[i];
      if (ch >= "a" && ch <= "z") {
        let j = i;
        while (j < n && text[j] >= "a" && text[j] <= "z") j++;
        const word = text.slice(i, j);
        const cword = (caseText != null && caseText.length === n) ? caseText.slice(i, j) : null;
        const stem = singularizeWord(word, cword);
        if (stem === word) {
          for (let k = i; k < j; k++) {
            out.push(text[k]);
            startMap.push(k);
            endMap.push(k);
          }
        } else {
          for (let pos = 0; pos < stem.length; pos++) {
            out.push(stem[pos]);
            startMap.push(i + pos);
            endMap.push(pos === stem.length - 1 ? j - 1 : i + pos);
          }
        }
        i = j;
      } else {
        out.push(ch);
        startMap.push(i);
        endMap.push(i);
        i++;
      }
    }
    return [out.join(""), startMap, endMap];
  }

  function expandCoord(text, jieba) {
    if (typeof text !== "string") return [];
    let hasConj = false;
    for (const c of COORD_CONJ) {
      if (text.includes(c)) { hasConj = true; break; }
    }
    if (!hasConj) return [];
    const tokens = jieba.cut(text);
    const expansions = [];
    for (let i = 0; i < tokens.length; i++) {
      const tok = tokens[i];
      if (COORD_TAIL_SET.has(tok) && i >= 2 && COORD_CONJ.has(tokens[i - 1])) {
        const tail1Idx = i - 2;
        if (COORD_TAIL_SET.has(tokens[tail1Idx]) && tail1Idx >= 1) {
          const prefix = tokens[tail1Idx - 1];
          if (prefix.length >= 2) expansions.push(prefix + tok);
        }
      }
    }
    return expansions;
  }

  function expandEnumeration(text, jieba) {
    if (typeof text !== "string") return "";
    let hasConj = false;
    for (const c of COORD_CONJ) {
      if (text.includes(c)) { hasConj = true; break; }
    }
    if (!text.includes("、") && !text.includes(".") && !hasConj) return text;
    const expansions = [];
    ENUM_PATTERN.lastIndex = 0;
    let m;
    while ((m = ENUM_PATTERN.exec(text)) !== null) {
      const heads = m[1].split(/、|\./);
      const suffix = m[2];
      for (const h of heads) {
        if (h && !h.endsWith(suffix)) expansions.push(h + suffix);
      }
    }
    HAIR_ENUM_PATTERN.lastIndex = 0;
    while ((m = HAIR_ENUM_PATTERN.exec(text)) !== null) {
      for (const ch of m[1].split(/、|\./)) expansions.push(ch + "髮");
    }
    if (text.includes("、")) {
      BARE_CHAR_ENUM_PATTERN.lastIndex = 0;
      while ((m = BARE_CHAR_ENUM_PATTERN.exec(text)) !== null) {
        expansions.push(m[0].split("、").join(""));
      }
    }
    expansions.push(...expandCoord(text, jieba));
    if (expansions.length > 0) return text + " " + expansions.join(" ");
    return text;
  }

  function getZhBoundaries(text, jieba) {
    const positions = new Set([0]);
    let pos = 0;
    for (const token of jieba.cut(text)) {
      pos += token.length;
      positions.add(pos);
    }
    return positions;
  }

  function isAsciiAlnum(c) {
    const code = c.charCodeAt(0);
    return (code >= 48 && code <= 57) || (code >= 65 && code <= 90) || (code >= 97 && code <= 122) || code === 95;
  }

  function isGluedListNumber(text, end) {
    if (end >= text.length) return false;
    if (text[end] < "0" || text[end] > "9") return false;
    let i = end;
    while (i < text.length && text[i] >= "0" && text[i] <= "9") i++;
    return i < text.length && ".．、)".includes(text[i]);
  }

  function isWordBoundary(text, start, end) {
    if (start > 0 && isAsciiAlnum(text[start - 1])) return false;
    if (end < text.length && isAsciiAlnum(text[end])) {
      if (!isGluedListNumber(text, end)) return false;
    }
    return true;
  }

  // Section Parsing
  const SECTION_HEADERS = [
    ["COMPANY_INTRO", /(?:【[^】]*(?:公司|品牌|集團|企業|關於)[^】]*】|\[[^\]]*(?:公司|品牌|集團|企業|關於)[^\]]*\]|◎[^◎]{0,12}(?:公司|品牌|集團|企業|關於)[^◎]{0,12}◎|(?:公司簡介|關於我們|品牌介紹|企業簡介|集團簡介)[：:])/g],
    ["WELFARE", /(?:【[^】]*(?:福利|待遇|休假|津貼|獎金|補助|活動|環境)[^】]*】|\[[^\]]*(?:福利|待遇|休假|獎金)[^\]]*\]|◎[^◎]{0,12}(?:福利|待遇|休假|津貼|獎金|補助)[^◎]{0,12}◎|(?:福利制度|員工福利|公司福利|休假制度)[：:])/g],
    ["REQUIREMENTS", /(?:【[^】]*(?:條件|資格|要求|特質|夥伴|特徵|技能|工具|經歷|學歷|加分|必備|徵求)[^】]*】|\[[^\]]*(?:條件|資格|要求|特質|技能|工具)[^\]]*\]|◎[^◎]{0,12}(?:條件|資格|要求|特質|技能|經歷|學歷|加分|必備)[^◎]{0,12}◎|(?:任職條件|具備條件|任職資格|加分條件|必要條件|應徵條件)[：:])/g],
    ["JOB_DUTIES", /(?:【[^】]*(?:工作內容|職務說明|職務內容|工作職責|主要職責|實戰|工作項目|任務|執掌|服務內容|工作執掌|工作時間|未來店長培訓|培訓服務內容)[^】]*】|\[[^\]]*(?:工作內容|職務說明|工作職責|主要職責|工作項目)[^\]]*\]|◎[^◎]{0,12}(?:工作內容|職務說明|工作職責|主要職責|工作項目|職務內容)[^◎]{0,12}◎|(?:工作內容|主要職責|職務說明|職務內容|職責內容|工作項目|工作執掌)[：:])/g],
    ["COMPANY_INTRO", /[-－—=＝~～*＊#]{2,}\s*(?:公司簡介|關於我們|公司介紹)\s*[-－—=＝~～*＊#]{2,}/g],
    ["WELFARE", /[-－—=＝~～*＊#]{2,}\s*(?:福利制度|員工福利|公司福利|薪資福利|薪資待遇)\s*[-－—=＝~～*＊#]{2,}/g],
    ["REQUIREMENTS", /[-－—=＝~～*＊#]{2,}\s*(?:任職條件|應徵條件|條件要求|任職資格|職務需求)\s*[-－—=＝~～*＊#]{2,}/g],
    ["JOB_DUTIES", /[-－—=＝~～*＊#]{2,}\s*(?:工作內容|職務內容|工作職責|職務說明|主要職責)\s*[-－—=＝~～*＊#]{2,}/g],
  ];

  const EN_SECTION_TITLES = [
    ["COMPANY_INTRO", "(?:more\\s+)?about\\s+(?:us|the\\s+company|our\\s+company|(?!(?:the|this|you|yourself|position|role|job|opportunity)\\b)(?![^】\\]:：]{0,40}\\bteam\\b)[A-Za-z][\\w&.'-]*(?:\\s+[A-Za-z][\\w&.'-]*){0,3})|who\\s+we\\s+are|(?:company|client)\\s+(?:overview|introduction|profile|description)|our\\s+(?:company|story|mission)"],
    ["WELFARE", "(?:employee\\s+|our\\s+|company\\s+)?benefits?(?:\\s*(?:&|and)\\s*perks)?|perks|what\\s+we\\s+offer|we\\s+offer|why\\s+(?:join\\s+us|us|work\\s+with\\s+us)"],
    ["REQUIREMENTS", "(?:job\\s+|basic\\s+|minimum\\s+|preferred\\s+|core\\s+|key\\s+)?(?:requirements?|qualifications?)|what\\s+we(?:'|’)?re\\s+looking\\s+for|what\\s+we\\s+are\\s+looking\\s+for|what\\s+you(?:'|’)?ll\\s+(?:bring|need)|who\\s+you\\s+are|about\\s+you|nice\\s+to\\s+haves?|must\\s+haves?|bonus\\s+points|candidate\\s+(?:profile|requirements?)|(?:the\\s+)?ideal\\s+candidate|(?:required\\s+|preferred\\s+|desir(?:ed|able)\\s+)?skills?(?:\\s*(?:&|and)\\s*experiences?)?|(?:work\\s+|relevant\\s+)?experiences?"],
    ["JOB_DUTIES", "(?:key\\s+|job\\s+|main\\s+|primary\\s+|roles?\\s*(?:&|and|/)?\\s*)?(?:responsibilities|duties|accountabilities)|what\\s+(?:this|the)\\s+(?:job|role|position)\\s+involves|(?:job|role|position)\\s+(?:description|summary|overview)|objectives?\\s+of\\s+(?:this|the)\\s+role|what\\s+you(?:'|’)?ll\\s+do|what\\s+you\\s+will\\s+do|about\\s+(?:(?:the|this)\\s+)?(?:role|job|position|opportunity)|(?:your|the)\\s+role"],
    ["GENERAL", "overview|summary"],
  ];

  for (const [secType, titles] of EN_SECTION_TITLES) {
    SECTION_HEADERS.push([
      secType,
      new RegExp(
        `(?:【\\s*(?:${titles})\\s*】|\\[\\s*(?:${titles})\\s*\\]|` +
        `(?:^|(?<=[\\n\\r。．.!！?？;；:：■●★◆▶►•*#|\\-—–)）\\u4e00-\\u9fff])|(?<=[a-z0-9])(?=[A-Z]))` +
        `[ \\t]*(?:${titles})(?:(?:\\s*/\\s*[A-Za-z][A-Za-z ]{0,25})?\\s*[：:]|(?=\\s*1[.．、)]\\s*\\S)|(?=\\s*(?:[•●■◆▶►➤・]|[*\\-]\\s))|(?<=[a-z])(?=[A-Z][a-z])))`,
        "gim"
      ),
    ]);
  }

  const RE_WELFARE_LIST_HEAD = /獎金|獎勵|勞健保|勞保|健保|勞退|尾牙|年終|津貼|補助|特休|休假|旅遊|聚餐|禮金|分紅|員工餐|宿舍/;
  const RE_ANY_BRACKET_HEADER = /【[^】]{1,25}】|\[[^\]\n]{1,25}\]/;
  const RE_LEADING_TAG_RUN = /^\s*(?:【[^】]{1,20}】\s*){2,}/;
  const RE_BARE_LIST_ITEM_1 = /(?<!\d)1[.\．、](?!\d)(?=\s{0,2}[\u4e00-\u9fffA-Za-z])/g;
  const INTRO_PHRASE_RE = /(?:集團旗下|本公司|我們是|成立於|致力於|創立於|旗下品牌|為全台|是全台|第一品牌|專業品牌|是一間|深耕|隸屬於[^。，,；;]{0,15}事業(?:群|部))/;

  function findBareDutyListStart(text) {
    RE_BARE_LIST_ITEM_1.lastIndex = 0;
    let m;
    while ((m = RE_BARE_LIST_ITEM_1.exec(text)) !== null) {
      const pos = m.index;
      if (pos > 0 && "（(「『\"'".includes(text[pos - 1])) continue;
      if (/2[.\．、]\s{0,2}[\u4e00-\u9fffA-Za-z]/.test(text.slice(pos, pos + 200))) return pos;
    }
    return null;
  }

  function parseTextSections(text) {
    if (typeof text !== "string" || !text.trim()) {
      return [{ type: "GENERAL", start: 0, end: 0, header: "" }];
    }
    let leadingRunEnd = 0;
    const mRun = RE_LEADING_TAG_RUN.exec(text);
    if (mRun) leadingRunEnd = mRun.index + mRun[0].length;

    const headers = [];
    for (const [secType, pattern] of SECTION_HEADERS) {
      pattern.lastIndex = 0;
      let m;
      while ((m = pattern.exec(text)) !== null) {
        if (m.index < leadingRunEnd && (secType === "COMPANY_INTRO" || secType === "WELFARE")) continue;
        headers.push([m.index, m.index + m[0].length, secType, m[0]]);
        if (m[0].length === 0) pattern.lastIndex++;
      }
    }
    headers.sort((a, b) => a[0] - b[0]);

    const filtered = [];
    for (const h of headers) {
      if (filtered.length === 0 || h[0] >= filtered[filtered.length - 1][1]) filtered.push(h);
    }

    if (filtered.length === 0) {
      const bareStart = findBareDutyListStart(text);
      if (bareStart !== null) {
        const out = [];
        if (bareStart > 0) {
          const introPart = text.slice(0, bareStart).trim();
          out.push({
            type: INTRO_PHRASE_RE.test(introPart) ? "COMPANY_INTRO" : "GENERAL",
            start: 0,
            end: bareStart,
            header: "[開頭前言]",
          });
        }
        out.push({ type: "JOB_DUTIES", start: bareStart, end: text.length, header: "[裸編號清單]" });
        return out;
      }
      return [{
        type: INTRO_PHRASE_RE.test(text.trim()) ? "COMPANY_INTRO" : "GENERAL",
        start: 0,
        end: text.length,
        header: "[開頭前言]",
      }];
    }

    const expanded = [];
    for (let idx = 0; idx < filtered.length; idx++) {
      const [hStart, hEnd, hType, hStr] = filtered[idx];
      expanded.push([hStart, hEnd, hType, hStr]);
      if (hType === "COMPANY_INTRO") {
        const nextStart = idx + 1 < filtered.length ? filtered[idx + 1][0] : text.length;
        const seg = text.slice(hEnd, nextStart);
        const mOther = RE_ANY_BRACKET_HEADER.exec(seg);
        if (mOther) {
          const absPos = hEnd + mOther.index;
          expanded.push([absPos, absPos + mOther[0].length, "GENERAL", mOther[0]]);
        }
      }
    }
    expanded.sort((a, b) => a[0] - b[0]);

    const sections = [];
    const firstStart = expanded[0][0];
    if (firstStart > 0) {
      const leadingText = text.slice(0, firstStart).trim();
      sections.push({
        type: INTRO_PHRASE_RE.test(leadingText) ? "COMPANY_INTRO" : "GENERAL",
        start: 0,
        end: firstStart,
        header: "[開頭前言]",
      });
    }
    for (let i = 0; i < expanded.length; i++) {
      const [hStart, hEnd, hType, hStr] = expanded[i];
      const nextStart = i + 1 < expanded.length ? expanded[i + 1][0] : text.length;
      sections.push({ type: hType, start: hStart, end: nextStart, header: hStr, header_end: hEnd });
    }

    const splitSections = [];
    for (const sec of sections) {
      if (sec.type === "COMPANY_INTRO") {
        const bodyStart = sec.header_end !== undefined ? sec.header_end : sec.start;
        const listStart = findBareDutyListStart(text.slice(bodyStart, sec.end));
        if (listStart !== null) {
          const cut = bodyStart + listStart;
          const isWelfare = RE_WELFARE_LIST_HEAD.test(text.slice(cut, cut + 40)) ||
            text.slice(Math.max(bodyStart, cut - 15), cut).includes("福利");
          splitSections.push({ ...sec, end: cut });
          splitSections.push({
            type: isWelfare ? "WELFARE" : "JOB_DUTIES",
            header: "[公司介紹後的編號清單]",
            start: cut,
            end: sec.end,
          });
          continue;
        }
      }
      splitSections.push(sec);
    }
    return splitSections;
  }

  function getSectionForOffset(sections, offset) {
    for (const sec of sections) {
      if (sec.start <= offset && offset < sec.end) return sec;
    }
    return sections.length ? sections[sections.length - 1] : { type: "GENERAL", start: 0, end: 0, header: "" };
  }

  function extractContextSnippet(rawText, start, end, window = 50) {
    if (!rawText) return "";
    const sIdx = Math.max(0, start - window);
    const eIdx = Math.min(rawText.length, end + window + 1);
    return rawText.slice(sIdx, eIdx).replace(/[\n\r]/g, " ").trim();
  }

  function escapeRegex(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function isMarketingTargetOrDomainModifier(snippet, matchedTerm) {
    if (!snippet || !matchedTerm) return false;
    const esc = escapeRegex(matchedTerm);
    const p1 = new RegExp(`(?:為|替|針對|負責|推廣|行銷|宣傳|拍攝|剪輯|撰寫|製作|經營).{0,8}${esc}.{0,8}(?:品牌|門市|分店|粉專|社群|文案|廣告|短影片|短影音|素材|影片|企劃|官網|自媒體)`);
    if (p1.test(snippet)) return true;
    const p2 = new RegExp(`${esc}(?:相關|旗下|之)?(?:品牌|門市|分店|廠商|專案|產品|業務|產業|領域|客戶).{0,10}(?:行銷|宣傳|推廣|文案|企劃|短影音|影片|設計|拍攝|剪輯|經營)`);
    if (p2.test(snippet)) return true;
    const p3 = new RegExp(`為${esc}(?:品牌)?.{0,6}(?:製作|撰寫|企劃|拍攝|剪輯|宣傳|設計)(?:文案|影片|影音|素材|內容)?`);
    if (p3.test(snippet)) return true;
    return false;
  }

  const TITLE_DISAMBIGUATION = {
    "開發": [
      [["軟體", "韌體", "程式", "資訊", "app", "APP", "IT"], "KS120L96KMYTDJ48NRSH"],
      [["業務", "銷售"], "KS1212B6QR5SK1LSD4S4"],
      [["產品經理", "產品企劃", "研發"], "KS1270P6SLFCFT476Y3R"],
    ],
    "設計": [
      [["機構"], "KS1269J6YQG4J3V5YGGW"],
      [["電子", "電機", "硬體", "ic", "IC", "韌體", "類比"], "KS121X369RKT17LSJNZX"],
      [["室內", "裝潢"], "KS122SP76CJCX9T70P6B"],
      [["美編", "平面", "視覺", "ui", "UI", "ux", "UX", "廣告"], "KS124H46Q2PP8YC1WQ06"],
    ],
    "操作": [[["作業員", "技術員", "機台", "生產", "製造", "產線"], "TW_MFG_001"]],
    "管控": [
      [["品管", "品保", "QA", "QC", "稽核", "檢驗"], "KS1289C6QS0TSSB4PNGG"],
      [["生產", "製造", "產線", "製程"], "KS1282X64QGHTFWQ8J2Y"],
    ],
  };

  const LOCAL_CONTEXT_RULES = {
    "開發": [[/產品[之的]?開發/, "KS1270P6SLFCFT476Y3R"]],
    "教授": [[/教授.{0,6}英文/, "KS4418W709S96G1PP7DS"]],
  };

  function suppressShorterMatches(candidates) {
    if (!candidates.length) return [];
    const sorted = [...candidates].sort((a, b) => (a.start - b.start) || (b.term_len - a.term_len));
    const kept = [];
    for (const cand of sorted) {
      const cSkill = cand.skill.SKILL_ID || cand.skill.SKILL_NAME;
      let covered = false;
      for (const k of kept) {
        if (k.start <= cand.start && k.end >= cand.end) {
          if (k.term_len > cand.term_len) { covered = true; break; }
          if (k.term_len === cand.term_len && (k.skill.SKILL_ID || k.skill.SKILL_NAME) === cSkill) {
            covered = true;
            break;
          }
        }
      }
      if (!covered) kept.push(cand);
    }
    return kept;
  }

  // Aho-Corasick Trie
  class AhoCorasick {
    constructor() {
      this.nodes = [{ next: new Map(), fail: 0, outputs: null }];
    }

    addWord(word, value) {
      let state = 0;
      for (let i = 0; i < word.length; i++) {
        const ch = word[i];
        let nxt = this.nodes[state].next.get(ch);
        if (nxt === undefined) {
          nxt = this.nodes.length;
          this.nodes.push({ next: new Map(), fail: 0, outputs: null });
          this.nodes[state].next.set(ch, nxt);
        }
        state = nxt;
      }
      this.nodes[state].outputs = value;
    }

    makeAutomaton() {
      const queue = [];
      for (const [, nxt] of this.nodes[0].next) {
        this.nodes[nxt].fail = 0;
        queue.push(nxt);
      }
      let head = 0;
      while (head < queue.length) {
        const curr = queue[head++];
        const currNode = this.nodes[curr];
        for (const [ch, nxt] of currNode.next) {
          queue.push(nxt);
          let f = currNode.fail;
          while (f !== 0 && !this.nodes[f].next.has(ch)) f = this.nodes[f].fail;
          const failState = this.nodes[f].next.get(ch) || 0;
          this.nodes[nxt].fail = failState;
        }
      }
    }

    iter(text) {
      const matches = [];
      let state = 0;
      for (let i = 0; i < text.length; i++) {
        const ch = text[i];
        while (state !== 0 && !this.nodes[state].next.has(ch)) state = this.nodes[state].fail;
        state = this.nodes[state].next.get(ch) || 0;
        let temp = state;
        while (temp !== 0) {
          if (this.nodes[temp].outputs !== null) {
            matches.push([i, this.nodes[temp].outputs]);
          }
          temp = this.nodes[temp].fail;
        }
      }
      return matches;
    }
  }

  class OfflineRulesEngine {
    constructor(rulesData) {
      this.codeVersion = rulesData.CODE_VERSION;
      this.ruleVersion = rulesData.RULE_VERSION;
      this.negationRe = new RegExp(rulesData.NEGATION_PATTERN);
      this.contextExclusions = {};
      for (const [sid, pats] of Object.entries(rulesData.CONTEXT_EXCLUSION_RULES || {})) {
        this.contextExclusions[sid] = pats.map((p) => new RegExp(p, "i"));
      }
      this.acronymRules = {};
      for (const [sid, tup] of Object.entries(rulesData.ACRONYM_CONTEXT_REQUIRED || {})) {
        this.acronymRules[sid] = {
          acronym: tup[0],
          win: tup[1],
          reqPats: tup[2].map((p) => new RegExp(p, "i")),
          denyPats: (tup[3] || []).map((p) => new RegExp(p, "i")),
          nearW: tup[4] || 40,
        };
      }
    }

    isNegated(rawText, start) {
      if (start <= 0) return false;
      const prefix = rawText.slice(Math.max(0, start - 6), start);
      return this.negationRe.test(prefix);
    }

    isContextExcluded(skillId, snippet) {
      const pats = this.contextExclusions[skillId];
      if (!pats) return false;
      for (const p of pats) {
        if (p.test(snippet)) return true;
      }
      return false;
    }

    lacksRequiredContext(skillId, matchedTerm, rawText, start, end) {
      const rule = this.acronymRules[skillId];
      if (!rule) return false;
      if (matchedTerm.trim().toLowerCase() !== rule.acronym.toLowerCase()) return false;
      const near = rawText.slice(Math.max(0, start - rule.nearW), Math.min(rawText.length, end + rule.nearW + 1));
      for (const dp of rule.denyPats) {
        if (dp.test(near)) return true;
      }
      const ctx = rawText.slice(Math.max(0, start - rule.win), Math.min(rawText.length, end + rule.win + 1));
      for (const rp of rule.reqPats) {
        if (rp.test(ctx)) return false;
      }
      return true;
    }
  }

  class WebSkillEngineOffline {
    constructor(jieba, rulesData) {
      this.jieba = jieba;
      this.rules = new OfflineRulesEngine(rulesData);
      this.automaton = new AhoCorasick();
      this.skillIndex = new Map();
      this.aiSkillIds = new Set();
      this.structuredExactTags = new Map();
      this.caseSensitiveTerms = new Map();
      this.metadata = {};
      this.bundleSha256 = "";
      this.ready = false;
    }

    loadBundleObject(bundle, sha256Hex = "") {
      this.automaton = new AhoCorasick();
      this.skillIndex = new Map();
      this.aiSkillIds = new Set();
      this.structuredExactTags = new Map();
      this.caseSensitiveTerms = new Map();
      this.metadata = bundle.metadata || {};
      this.bundleSha256 = sha256Hex || "";
      const skillsList = bundle.skills || [];

      for (const w of JIEBA_2CHAR_WHITELIST) this.jieba.addWord(w, 1000);
      for (const w of COORD_TAIL_LIST) this.jieba.addWord(w, 2000);

      const termToEntries = new Map();

      for (const raw of skillsList) {
        const sid = String(raw.SKILL_ID || "").trim();
        const sname = String(raw.SKILL_NAME || "").trim();
        const snameZh = String(raw.SKILL_NAME_ZH || "").trim();
        const catCode = raw.Category_Code;
        const isSw = typeof catCode === "number" && SOFTWARE_CATEGORIES.has(catCode);

        const gCode = raw.Skill_group10_code;
        let gName = String(raw.Skill_group10 || "").trim();
        if (gCode != null && EXPECTED_GROUP10[gCode] && (!gName || gName === "待分類")) {
          gName = EXPECTED_GROUP10[gCode];
        }
        if (!gName || gCode == null) gName = gName || "待分類";

        const skill = {
          Category_Name: String(raw.Category_Name || "").trim(),
          Subcategory_Name: String(raw.Subcategory_Name || "").trim(),
          SKILL_ID: sid,
          SKILL_NAME: sname,
          SKILL_NAME_ZH: snameZh,
          SKILL_TYPE: String(raw.SKILL_TYPE || "").trim(),
          Category_Code: catCode ?? null,
          Subcategory_Code: raw.Subcategory_Code ?? null,
          Skill_group10_code: gCode ?? null,
          Skill_group10: gName,
          Grouping_rule: String(raw.Grouping_rule || "").trim(),
          Grouping_status: String(raw.Grouping_status || "").trim() || (gCode != null ? "已對應" : "待分類"),
          Allowed_group_codes: String(raw.Allowed_group_codes || "").trim(),
          Ambiguity_note: String(raw.Ambiguity_note || "").trim(),
          Is_AI_Skill: Boolean(raw.Is_AI_Skill),
          IS_SOFTWARE: isSw,
        };

        if (sid) {
          this.skillIndex.set(sid, skill);
          if (skill.Is_AI_Skill) this.aiSkillIds.add(sid);
        }

        const allowStr = String(raw.Allow_Bare_2Char_Keywords || "").trim();
        const rowBareAllow = new Set(allowStr ? allowStr.split("｜") : []);

        const exactStr = String(raw.Structured_Field_Exact_Tags || "").trim();
        if (exactStr) {
          for (const tag of exactStr.split("｜")) {
            const t = tag.trim().toLowerCase();
            if (t) {
              if (!this.structuredExactTags.has(t)) this.structuredExactTags.set(t, []);
              this.structuredExactTags.get(t).push(skill);
            }
          }
        }

        const caseStr = String(raw.Case_Sensitive_Keywords || "").trim();
        if (caseStr) {
          const owner = sid || sname;
          for (const ck of caseStr.split("｜")) {
            const ckNorm = normalizeAsciiHyphen(normalizeFullwidthAlnum(ck.trim().toLowerCase()));
            if (ckNorm && owner) {
              if (!this.caseSensitiveTerms.has(ckNorm)) this.caseSensitiveTerms.set(ckNorm, new Set());
              this.caseSensitiveTerms.get(ckNorm).add(owner);
            }
          }
        }

        const terms = [];
        const enCase = new Map();

        if (snameZh && hasChinese(snameZh) && (snameZh.length >= 3 || rowBareAllow.has(snameZh))) {
          const zhLower = snameZh.toLowerCase();
          terms.push([zhLower, true]);
          this.jieba.addWord(zhLower, 1000);
        } else if (!hasChinese(snameZh)) {
          const en = sname.toLowerCase();
          if (en.length >= 2) {
            terms.push([en, false]);
            enCase.set(en, sname);
          }
        }

        const kwStr = String(raw.Keywords || "").trim();
        if (kwStr) {
          for (const kwRaw of kwStr.split("｜")) {
            const kw = kwRaw.trim();
            if (!kw) continue;
            if (hasChinese(kw)) {
              if (kw.length < 2 || (kw.length === 2 && !rowBareAllow.has(kw))) continue;
              const kwLower = kw.toLowerCase();
              terms.push([kwLower, true]);
              this.jieba.addWord(kwLower, 1000);
            } else {
              if (kw.length < 2) continue;
              const kwLower = kw.toLowerCase();
              terms.push([kwLower, false]);
              if (!enCase.has(kwLower)) enCase.set(kwLower, kw);
            }
          }
        }

        const extraSyn = [];
        for (const [term, isZh] of terms) {
          if (!isZh) continue;
          for (const variant of expandSynonyms(term)) {
            if (variant.length >= 3 || rowBareAllow.has(variant)) {
              extraSyn.push([variant, true]);
              this.jieba.addWord(variant, 1000);
            }
          }
        }
        terms.push(...extraSyn);

        const extraStem = [];
        for (const [term, isZh] of terms) {
          if (!isZh) {
            const [stemmed] = stemEnglishTextWithMap(term, enCase.get(term));
            if (stemmed !== term && stemmed.length >= 4) extraStem.push([stemmed, false]);
          }
        }
        terms.push(...extraStem);

        const seenTerms = new Set();
        const dedupId = sid || sname;
        for (const [term, isZh] of terms) {
          const termNorm = normalizeAsciiHyphen(normalizeFullwidthAlnum(term));
          if (seenTerms.has(termNorm)) continue;
          seenTerms.add(termNorm);
          if (!termToEntries.has(termNorm)) termToEntries.set(termNorm, []);
          const bucket = termToEntries.get(termNorm);
          if (!bucket.some((e) => (e[1].SKILL_ID || e[1].SKILL_NAME) === dedupId)) {
            bucket.push([termNorm.length, skill, isZh]);
          }
        }
      }

      const nospaceVariants = new Map();
      for (const [term, entries] of termToEntries) {
        if (!term.includes(" ") || hasChinese(term)) continue;
        const variant = term.split(" ").join("");
        if (variant.length < 5 || termToEntries.has(variant)) continue;
        if (!nospaceVariants.has(variant)) nospaceVariants.set(variant, []);
        const bucket = nospaceVariants.get(variant);
        for (const e of entries) {
          if (!bucket.some((x) => x[1] === e[1])) bucket.push([variant.length, e[1], e[2]]);
        }
      }
      for (const [k, v] of nospaceVariants) termToEntries.set(k, v);

      for (const [k, v] of termToEntries) this.automaton.addWord(k, v);
      this.automaton.makeAutomaton();
      this.ready = true;
    }

    healthInfo() {
      const rawAiCnt = this.metadata.ai_skill_count;
      const hasAiCnt = rawAiCnt !== undefined && rawAiCnt !== null;
      const aiCnt = hasAiCnt ? Number(rawAiCnt) : 0;
      let aiReviewStatus = "Unknown";
      if (this.ready) {
        if (hasAiCnt && aiCnt > 0) aiReviewStatus = `Pending review (${aiCnt} AI skills flagged)`;
        else aiReviewStatus = this.metadata.ai_label_review_status || "Unknown";
      }
      return {
        ready: this.ready,
        engine_version: this.rules.codeVersion,
        rule_version: this.rules.ruleVersion,
        lexicon_version: this.metadata.base_lexicon_filename || "Unknown",
        lexicon_sha256: this.metadata.base_lexicon_sha256 || this.bundleSha256 || "Unknown",
        g11c_sha256: this.metadata.grouped_lexicon_sha256 || "Unknown",
        skill_count: this.metadata.skill_count ?? this.skillIndex.size ?? "Unknown",
        ai_skill_count: aiCnt,
        ai_label_review_status: aiReviewStatus,
      };
    }

    scanRawFieldMatches(rawText, fieldLabel, sections) {
      if (typeof rawText !== "string" || !rawText.trim()) return [];
      const rawLen = rawText.length;
      const expandedText = expandEnumeration(rawText, this.jieba);
      const textCase = normalizeFullwidthAlnum(expandedText);
      const textLower = normalizeAsciiHyphen(textCase.toLowerCase());
      const [textStemmed, stemStartMap, stemEndMap] = stemEnglishTextWithMap(textLower, textCase);

      const scanTexts = textLower === textStemmed ? [textLower] : [textLower, textStemmed];
      const zhBoundaries = getZhBoundaries(textLower.slice(0, rawLen), this.jieba);

      const candidates = [];
      for (const scanText of scanTexts) {
        const isStemPass = scanText !== textLower;
        for (const [scanEndIdx, entries] of this.automaton.iter(scanText)) {
          for (const [termLen, skill, isZh] of entries) {
            if (isZh && isStemPass) continue;
            let endIdx = scanEndIdx;
            let startIdx = endIdx - termLen + 1;
            const termKey = scanText.slice(startIdx, endIdx + 1);

            if (isZh) {
              if (startIdx < rawLen) {
                if (!zhBoundaries.has(startIdx) || !zhBoundaries.has(endIdx + 1)) continue;
                if ((termLen === 2 || termLen === 3) && (
                  ZH_CROSS_WORD_GUARD.has(scanText.slice(Math.max(0, startIdx - 1), startIdx + 1)) ||
                  ZH_CROSS_WORD_GUARD.has(scanText.slice(endIdx, endIdx + 2))
                )) {
                  continue;
                }
              }
            } else {
              if (!isWordBoundary(scanText, startIdx, endIdx + 1)) continue;
            }

            if (isStemPass) {
              startIdx = stemStartMap[startIdx];
              endIdx = stemEndMap[endIdx];
            }

            if (!isZh && fieldLabel === "職位描述" && this.caseSensitiveTerms.size > 0) {
              const owners = this.caseSensitiveTerms.get(termKey);
              if (owners && owners.has(skill.SKILL_ID || skill.SKILL_NAME) && isLowercasedWordInEnglish(textCase, startIdx, endIdx)) {
                continue;
              }
            }

            let origStart, origEnd, isMappable, matchedTerm;
            if (startIdx < rawLen) {
              origStart = startIdx;
              origEnd = Math.min(endIdx, rawLen - 1);
              isMappable = true;
              matchedTerm = rawText.slice(origStart, origEnd + 1);
            } else {
              origStart = -1;
              origEnd = -1;
              isMappable = false;
              matchedTerm = textLower.slice(startIdx, endIdx + 1);
            }

            candidates.push({
              start: startIdx,
              end: endIdx,
              orig_start: origStart,
              orig_end: origEnd,
              term_len: termLen,
              skill,
              is_zh: isZh,
              is_mappable: isMappable,
              is_stem_pass: isStemPass,
              matched_term: matchedTerm,
            });
          }
        }
      }

      const keptCandidates = suppressShorterMatches(candidates);
      const results = [];

      for (const cand of keptCandidates) {
        const origS = cand.orig_start;
        const origE = cand.orig_end;
        const matchedStr = cand.matched_term;
        let secType, snippet, isMod;

        if (fieldLabel === "職位描述" && origS >= 0) {
          const sec = getSectionForOffset(sections, origS);
          if (origS < (sec.header_end ?? -1) && !hasChinese(sec.header || "")) continue;
          snippet = extractContextSnippet(rawText, origS, origE);
          isMod = isMarketingTargetOrDomainModifier(snippet, matchedStr);
          secType = sec.type;
        } else {
          secType = (fieldLabel === "工作技能" || fieldLabel === "工具欄") ? "JOB_DUTIES" : "GENERAL";
          snippet = extractContextSnippet(rawText, Math.max(0, origS), Math.max(0, origE));
          isMod = false;
        }

        const sid = cand.skill.SKILL_ID || "";
        let isCtxExcl = this.rules.isContextExcluded(sid, snippet) ||
          this.rules.lacksRequiredContext(sid, matchedStr, rawText, Math.max(0, origS), Math.max(0, origE));
        if (fieldLabel === "職位描述" && origS > 0 && this.rules.isNegated(rawText, origS)) {
          isCtxExcl = true;
        }

        results.push({
          skill: cand.skill,
          matched_term: matchedStr,
          source_field: fieldLabel,
          start: origS,
          end: origE,
          raw_snippet: snippet,
          section_type: secType,
          is_domain_modifier: isMod,
          is_context_excluded: isCtxExcl,
          is_mappable: cand.is_mappable,
          match_type: cand.is_stem_pass ? "單複數歸一" : "原文",
          MATCHED_FROM: fieldLabel,
        });
      }

      if (STRUCTURED_FIELD_LABELS.has(fieldLabel) && this.structuredExactTags.size > 0) {
        RE_STRUCTURED_TAG.lastIndex = 0;
        let m;
        while ((m = RE_STRUCTURED_TAG.exec(rawText)) !== null) {
          const tag = m[0].trim();
          if (!tag) continue;
          const tagStart = m.index + m[0].indexOf(tag);
          const tagEnd = tagStart + tag.length - 1;
          const matchedSkills = this.structuredExactTags.get(tag.toLowerCase()) || [];
          for (const skill of matchedSkills) {
            const snippet = extractContextSnippet(rawText, tagStart, tagEnd);
            results.push({
              skill,
              matched_term: tag,
              source_field: fieldLabel,
              start: tagStart,
              end: tagEnd,
              raw_snippet: snippet,
              section_type: "JOB_DUTIES",
              is_domain_modifier: false,
              is_context_excluded: this.rules.isContextExcluded(skill.SKILL_ID || "", snippet),
              is_mappable: true,
              match_type: "結構化欄位精確對照",
              MATCHED_FROM: fieldLabel,
            });
          }
        }
      }

      return results;
    }

    resolveAmbiguousByTitle(texts, jobTitle) {
      const combined = texts.filter((t) => typeof t === "string").join("");
      const title = typeof jobTitle === "string" ? jobTitle : "";
      const resolved = [];
      const seenIds = new Set();
      const resolvedWords = new Set();

      for (const [word, rules] of Object.entries(LOCAL_CONTEXT_RULES)) {
        if (!combined.includes(word)) continue;
        for (const [pattern, skillId] of rules) {
          if (!this.skillIndex.has(skillId) || !pattern.test(combined)) continue;
          if (!seenIds.has(skillId)) {
            seenIds.add(skillId);
            const pos = combined.indexOf(word);
            resolved.push({
              skill: this.skillIndex.get(skillId),
              matched_term: word,
              source_field: "職位描述",
              start: pos,
              end: pos + word.length - 1,
              raw_snippet: extractContextSnippet(combined, pos, pos + word.length - 1),
              section_type: "JOB_DUTIES",
              is_domain_modifier: false,
              is_context_excluded: false,
              match_type: "就近文意",
              MATCHED_FROM: "就近文意",
            });
          }
          resolvedWords.add(word);
        }
      }

      for (const [word, rules] of Object.entries(TITLE_DISAMBIGUATION)) {
        if (!combined.includes(word) || resolvedWords.has(word)) continue;
        for (const [titleKeywords, skillId] of rules) {
          if (!skillId || !this.skillIndex.has(skillId)) continue;
          if (titleKeywords.some((kw) => title.includes(kw))) {
            if (seenIds.has(skillId)) continue;
            seenIds.add(skillId);
            const pos = combined.indexOf(word);
            resolved.push({
              skill: this.skillIndex.get(skillId),
              matched_term: word,
              source_field: "職位描述",
              start: pos,
              end: pos + word.length - 1,
              raw_snippet: extractContextSnippet(combined, pos, pos + word.length - 1),
              section_type: "JOB_DUTIES",
              is_domain_modifier: false,
              is_context_excluded: false,
              match_type: "職稱消歧",
              MATCHED_FROM: "職稱消歧",
            });
            break;
          }
        }
      }
      return resolved;
    }

    reviewSkillEvidence(hits) {
      for (const h of hits) {
        if ((h.source_field === "工作技能" || h.source_field === "工具欄") && !h.is_context_excluded) {
          return ["keep", `明確列於來源欄位 [${h.source_field}]`, h];
        }
      }
      const dutyHits = [];
      const excludeReasons = [];
      for (const h of hits) {
        const sec = h.section_type || "GENERAL";
        if (h.is_domain_modifier) {
          excludeReasons.push(`命中詞「${h.matched_term}」為行銷/影音/社群之對象或品牌修飾詞`);
          continue;
        }
        if (h.is_context_excluded) {
          excludeReasons.push(`命中詞「${h.matched_term}」緊鄰或領域脈絡不符（上下文規則排除）`);
          continue;
        }
        if (sec === "COMPANY_INTRO") {
          excludeReasons.push(`命中詞「${h.matched_term}」位於公司/品牌介紹段落`);
          continue;
        }
        if (sec === "WELFARE") {
          excludeReasons.push(`命中詞「${h.matched_term}」位於員工福利/活動段落`);
          continue;
        }
        dutyHits.push(h);
      }
      if (dutyHits.length > 0) {
        const rep = dutyHits[0];
        return ["keep", `工作任務/任職條件段落命中「${rep.matched_term}」`, rep];
      }
      if (excludeReasons.length > 0) {
        return ["exclude", [...new Set(excludeReasons)].join("；"), hits[0]];
      }
      return ["review", "缺乏明確工作任務證據，列為待人工查核", hits[0]];
    }

    extractSingleJob(job, defaultIndex = 1) {
      if (!this.ready) throw new Error("請先載入詞庫檔 (lexicon_bundle.json.gz)");

      const jobId = String(job.job_id || job.ID || `WEB_JOB_${String(defaultIndex).padStart(3, "0")}`).trim();
      const dataMonth = String(job.data_month || job["資料月份"] || "202611").trim();
      const jobTitle = String(job.job_title || job["104職位名稱"] || job["職稱"] || "").trim();
      const jobDesc = String(job.job_description || job["職位描述"] || "");
      const jobSkills = String(job.job_skills || job["工作技能"] || "");
      const computerTools = String(job.computer_tools || job.tools || job["電腦工具"] || job["擅長工具"] || "");

      const texts = [jobDesc, jobSkills, computerTools];
      const sections = parseTextSections(jobDesc);
      const fieldLabels = ["職位描述", "工作技能", "工具欄"];

      let allHits = [];
      for (let i = 0; i < fieldLabels.length; i++) {
        if (texts[i].trim()) {
          allHits.push(...this.scanRawFieldMatches(texts[i], fieldLabels[i], sections));
        }
      }
      if (allHits.length === 0) {
        allHits.push(...this.resolveAmbiguousByTitle(texts, jobTitle));
      }

      const groupedHits = new Map();
      for (const h of allHits) {
        const sk = h.skill.SKILL_ID || h.skill.SKILL_NAME;
        if (sk) {
          if (!groupedHits.has(sk)) groupedHits.set(sk, []);
          groupedHits.get(sk).push(h);
        }
      }

      const retainedSkills = [];
      const excludedCandidates = [];
      const auditRecords = [];

      for (const [, hits] of groupedHits) {
        const [decision, reason, rep] = this.reviewSkillEvidence(hits);
        const skMeta = rep.skill;
        const gCode = skMeta.Skill_group10_code;
        const gName = gCode == null ? "待分類" : (skMeta.Skill_group10 || "待分類");

        if (decision === "keep" || decision === "review") {
          retainedSkills.push({
            SKILL_ID: skMeta.SKILL_ID || "",
            SKILL_NAME: skMeta.SKILL_NAME || "",
            SKILL_NAME_ZH: skMeta.SKILL_NAME_ZH || "",
            SKILL_TYPE: skMeta.SKILL_TYPE || "",
            Category_Name: skMeta.Category_Name || "",
            Subcategory_Name: skMeta.Subcategory_Name || "",
            Category_Code: skMeta.Category_Code,
            Subcategory_Code: skMeta.Subcategory_Code,
            Skill_group10_code: gCode,
            Skill_group10: gName,
            Grouping_rule: skMeta.Grouping_rule || "",
            Grouping_status: gCode != null ? (skMeta.Grouping_status || "已對應") : "待分類",
            Allowed_group_codes: skMeta.Allowed_group_codes || "",
            Ambiguity_note: skMeta.Ambiguity_note || "",
            MATCHED_FROM: rep.MATCHED_FROM || rep.source_field,
            matched_term: rep.matched_term || "",
            evidence_snippet: rep.raw_snippet || "",
            match_type: rep.match_type || "原文",
            IS_SOFTWARE: Boolean(skMeta.IS_SOFTWARE),
            Is_AI_Skill: Boolean(skMeta.Is_AI_Skill),
            evidence_decision: decision,
            evidence_reason: reason,
          });
          if (skMeta.Ambiguity_note || gCode == null) {
            auditRecords.push({
              ID: jobId,
              "資料月份": dataMonth,
              "104職位名稱": jobTitle,
              SKILL_ID: skMeta.SKILL_ID || "",
              SKILL_NAME_ZH: skMeta.SKILL_NAME_ZH || "",
              matched_term: rep.matched_term || "",
              source_field: rep.source_field,
              match_type: rep.match_type || "原文",
              evidence_snippet: rep.raw_snippet || "",
              decision,
              reason: skMeta.Ambiguity_note || reason,
              "分類狀態": gCode != null ? "已對應" : "待分類",
            });
          }
        } else {
          const exclRec = {
            ID: jobId,
            "資料月份": dataMonth,
            "104職位名稱": jobTitle,
            SKILL_ID: skMeta.SKILL_ID || "",
            SKILL_NAME_ZH: skMeta.SKILL_NAME_ZH || "",
            matched_term: rep.matched_term || "",
            source_field: rep.source_field,
            match_type: rep.match_type || "原文",
            evidence_snippet: rep.raw_snippet || "",
            decision: "exclude",
            reason,
            "分類狀態": gCode != null ? "已對應" : "待分類",
          };
          excludedCandidates.push(exclRec);
          auditRecords.push(exclRec);
        }
      }

      const groupRows = this.summarizeJobGroups(retainedSkills, jobId);
      const aiCount = retainedSkills.filter((s) => s.Is_AI_Skill).length;

      return {
        job: {
          ID: jobId,
          "資料月份": dataMonth,
          "104職位名稱": jobTitle,
          "職位描述": jobDesc,
          "工作技能": jobSkills,
          "電腦工具": computerTools,
          "技能數": retainedSkills.length,
          "AI技能數": aiCount,
          "是否命中技能": retainedSkills.length > 0,
        },
        skills: retainedSkills,
        group10_summary: groupRows,
        excluded_candidates: excludedCandidates,
        audit_records: auditRecords,
        stats: {
          total_skills: retainedSkills.length,
          matched_group_count: groupRows.filter((g) => g.Skill_group10_code != null).length,
          ai_skill_count: aiCount,
          excluded_count: excludedCandidates.length,
        },
      };
    }

    summarizeJobGroups(skills, jobId) {
      const grouped = new Map();
      for (const s of skills) {
        const gCode = s.Skill_group10_code;
        const gName = s.Skill_group10 || "待分類";
        const key = `${gCode ?? ""}||${gName}`;
        if (!grouped.has(key)) grouped.set(key, { gCode, gName, items: [] });
        grouped.get(key).items.push(s);
      }
      const rows = [];
      for (const { gCode, gName, items } of grouped.values()) {
        const names = items.map((s) => s.SKILL_NAME_ZH || s.SKILL_NAME || s.SKILL_ID);
        rows.push({
          ID: jobId,
          Skill_group10_code: gCode,
          Skill_group10: gName,
          Skill_Count: items.length,
          AI_Skill_Count: items.filter((s) => s.Is_AI_Skill).length,
          Matched_Skills: names.join(GROUP10_SKILL_SEPARATOR),
        });
      }
      rows.sort((a, b) => (a.Skill_group10_code ?? 999) - (b.Skill_group10_code ?? 999));
      return rows;
    }

    extractBatchRecords(rawRecords) {
      const filtered = [];
      let excludedPartTime = 0;
      for (const r of rawRecords) {
        const role = String(r["工作角色"] || "").trim();
        if (role === "兼職") {
          excludedPartTime++;
          continue;
        }
        filtered.push(r);
      }
      const capped = filtered.slice(0, MAX_BATCH_JOBS);

      const allJobs = [];
      const allSkillsLong = [];
      const allGroupSummary = [];
      const allExcluded = [];
      const allAudit = [];

      for (let i = 0; i < capped.length; i++) {
        const res = this.extractSingleJob(capped[i], i + 1);
        allJobs.push(res.job);
        for (const s of res.skills) {
          allSkillsLong.push({
            ID: res.job.ID,
            "資料月份": res.job["資料月份"],
            "104職位名稱": res.job["104職位名稱"],
            ...s,
          });
        }
        allGroupSummary.push(...res.group10_summary);
        allExcluded.push(...res.excluded_candidates);
        allAudit.push(...res.audit_records);
      }

      const groupCounts = {};
      for (const s of allSkillsLong) {
        const code = s.Skill_group10_code;
        const label = code != null ? `G${code}` : "待分類";
        groupCounts[label] = (groupCounts[label] || 0) + 1;
      }

      return {
        summary: {
          input_rows: rawRecords.length,
          excluded_part_time: excludedPartTime,
          total_jobs: allJobs.length,
          jobs_with_skills: allJobs.filter((j) => j["技能數"] > 0).length,
          zero_skill_jobs: allJobs.filter((j) => j["技能數"] === 0).length,
          total_skill_records: allSkillsLong.length,
          ai_skill_records: allSkillsLong.filter((s) => s.Is_AI_Skill).length,
          excluded_records: allExcluded.length,
          audit_records: allAudit.length,
          group_counts: groupCounts,
        },
        jobs: allJobs,
        skills_long: allSkillsLong,
        group10_summary: allGroupSummary,
        excluded_candidates: allExcluded,
        audit_records: allAudit,
      };
    }
  }

  root.Engine1114Offline = {
    EXPECTED_GROUP10,
    WebSkillEngineOffline,
  };
})(typeof window !== "undefined" ? window : globalThis);
