"""
2026/11/14 AC + Rules 共享規則模組 (src/ac_rules_1114.py)

直接抽取自 104_single_city_merged_20261114.py，供 Web Adapter 與回歸測試共用，
確保否定句排除、福利/公司介紹語境排除與縮寫/一詞多義佐證與 11/14 CLI 保持一致。
"""

from __future__ import annotations

import re

CODE_VERSION = "20261114_web_ac_v1"
RULE_VERSION = "ac_rules_20261114"

_BENEFIT_WORDS = [
    r"福利", r"禮[金品券盒]", r"獎金", r"團(體)?保", r"勞健保", r"津貼", r"補助", r"聚餐", r"尾牙", r"旅遊",
    r"制服", r"優惠", r"折扣", r"特約", r"年終", r"休假", r"週休", r"員工(意外|保險|健檢|旅遊)",
]

# 食品/供膳業錄取條件「體檢項目包括：肺結核、皮膚病、A型肝炎、傷寒」不是醫療技能
_HEALTH_CHECK_REQ = [r"體檢", r"健康檢查", r"供膳", r"檢查報告", r"檢查須", r"健檢", r"檢驗報告", r"證明"]

_CONTEXT_EXCLUSION_RULES = {
    "KS1287R64YNBZGR50Y1N": [  # 採購 (Purchasing)
        r"採購單.{0,15}(對帳|核對|查核|稽核|沖帳)",
        r"(對帳|核對|查核|稽核|沖帳).{0,15}採購單",
    ],
    "KS120BV6SR75RBKQH0G3": [  # 人工智慧 (Artificial Intelligence)
        r"被\s*AI.{0,10}取代",
        r"AI\s*(不會|不是|無法)\s*取代",
    ],
    "ESA5839C44D0970CF79F": [  # Go (Programming Language)：go-to-market、Go Big Together、go live 不是 Go 語言
        r"\bgo[\s-]+to[\s-]+market",
        r"\bgo[\s-]+(?:big|live|beyond|further|green|global|digital)\b",
        r"\b(?:recharge|ready|on[\s-]+the)[\s-]+(?:and[\s-]+)?go\b",
    ],
    "KSSHV35JS8ALRTU4TALI": [  # Physical Design：藥廠品保的 APR 是 Annual Product Review（常和 CAPA、deviation 一起出現），不是 IC 自動佈局繞線
        r"\bcapas?\b",
        r"annual\s+product",
        r"\bdeviations?\b",
    ],
    "KS120FS6BLSM312DKD5B": [  # AMBA：SMT的「SPI/AOI/AXI」是自動X光檢測，不是AXI匯流排
        r"\baoi\b", r"x[\s-]?ray", r"x光", r"\bsmt\b", r"automated\s+x",
    ],
    "KS1202960X30JT97TXHC": [  # Analog-To-Digital Converters：網管的F5 ADC是應用交付控制器（負載平衡）
        r"\bf5\b", r"load\s*balanc", r"負載平衡", r"application\s+delivery", r"netscaler", r"防火牆", r"firewall",
    ],
    "BGSF10F7DA728582E391": [  # Board Bring-Up：自動化設備/產線的「試車（Bring-up）」是設備試運轉
        r"試車", r"試運轉", r"commissioning", r"turn-?key", r"交機",
    ],
    "KS1203V5WXB7NG26XSR8": [  # Accounts Payable：網管的「無線AP」是 access point（只認緊貼的寫法，避免誤殺「應付帳款」）
        r"無線\s*ap(?![a-z])", r"(?<![a-z])ap\s*(?:設定|建置|佈建|架設|控制器)", r"wi-?fi", r"access\s*points?",
        r"(?<![a-z])ap\s*/\s*(?:switch|router)", r"(?:switch|router|交換器|路由器)\s*/\s*ap(?![a-z])",
        r"(?<![a-z])ap\s*(?:開發|程式|工程師|端|server|伺服器)",  # 軟體職缺的AP=應用程式
        r"(?<![a-z])ap\s*[:：]\s*(?:apache|tomcat|weblogic|websphere|jboss|iis|nginx)",  # 「AP:apache tomcat」=應用程式伺服器
        r"(?<![a-z])(?:db|web)\s*[:：]",  # 「AP: … DB: … Web:」技術堆疊條列
    ],
    "KS1267F6MSPN366LX7ST": [  # Project Management：「機台PM」「設備PM」是預防保養（只認緊貼的寫法）
        r"(?:機台|設備|tool|equipment)\s*pm(?![a-z])", r"(?<![a-z])pm\s*(?:保養|作業|週期|排程)", r"preventive\s+maintenance",
    ],
    "KS7G7ZR641Z34Q7M2CZT": [  # In-Plane Switching：資安的 IPS 是入侵防禦系統
        r"資安", r"防火牆", r"firewall", r"\bids\b", r"入侵", r"\bwaf\b", r"\bsiem\b",
        # IC 設計的「memory IPs」「CPU and other relevant IPs」是矽智財
        r"(?<![a-z])(memory|cpu|gpu|phy|sram|rom|soc|silicon|controller|serdes|ddr|pcie|usb|analog|mixed)(?![a-z])", r"矽智財",
    ],
    "KS124S378XP3PC6J2N1J": [  # Intrusion Prevention Systems：面板的 IPS 是 In-Plane Switching
        r"面板", r"\bpanel", r"display", r"\blcd\b", r"螢幕", r"顯示器", r"\btft\b",
    ],
    "TW_LINE_001": [  # LINE官方帳號經營：「加LINE」「LINE ID」「LINE洽詢」是求職聯絡方式，不是在經營LINE
        # 只認聯絡格式：「LINE@」單獨出現是官方帳號產品名，「電話行銷/FB、LINE線上銷售」是真的在用LINE做業務，都不排除
        r"加\s*(?:入\s*)?(?:官方\s*)?line", r"line\s*(?:id|洽詢|詢問|聯繫|聯絡|預約|報名|截圖)",
        r"line[^\s，。,、]{0,6}\s*[:：]?\s*@\s*[0-9a-z]{4,}", r"line\s*[:：]?\s*0\d{8,9}",
    ],
    "KS1203W6419RJG2KW4QS": [  # Accounts Receivable：軟體/硬體職缺的AR是擴增實境
        r"(?<![a-z])ar\s*/\s*vr", r"vr\s*/\s*ar(?![a-z])", r"擴增實境", r"augmented", r"(?<![a-z])xr(?![a-z])",
        r"(?<![a-z])ar\s*(?:眼鏡|glasses|技術|應用|互動|導覽|頭戴|headset)",
    ],
    "KS120RX61Z1Z2DHXR4H6": [  # Augmented Reality：會計的AR是應收帳款
        r"應收", r"帳款", r"會計", r"(?<![a-z])ap\s*/\s*ar", r"invoice", r"收款", r"receivable", r"對帳",
    ],
    "KS121HK6FQS5GM0VTQ2Z": [  # Clock Domain Crossing：資料工程的CDC是 Change Data Capture
        r"資料庫", r"database", r"kafka", r"(?<![a-z])etl(?![a-z])", r"debezium", r"data\s*pipeline", r"資料同步",
        r"疫苗", r"vaccine", r"疾管", r"disease", r"clinical", r"臨床", r"bidding",  # 美國CDC疾病管制中心
    ],
    "BGSED41BF182E7A55A17": [  # Change Data Capture：IC設計的CDC是 Clock Domain Crossing
        r"(?<![a-z])rtl(?![a-z])", r"(?<![a-z])lint(?![a-z])", r"verilog", r"clock", r"(?<![a-z])sta(?![a-z])",
        r"(?<![a-z])dft(?![a-z])", r"synthesis", r"時脈", r"(?<![a-z])lec(?![a-z])",
    ],
    "KS1239Z71LLXDMTGRJ5S": [  # Economic Development：飯店/企業的ESG永續聲明「氣候變遷、生態保育、經濟發展」
        r"氣候", r"生態", r"永續", r"(?<![a-z])esg(?![a-z])",
    ],
    "ES92A402F893456D877B": [  # Health Screenings：員工福利的健檢、寵物健康檢查
        # 只看福利用語；「辦理員工健康檢查」「年度健檢規劃」是勞工健康護理/職安的真工作，不能排除
        *_BENEFIT_WORDS, r"保險", r"寵物",
    ],
    "BGS423420828D2785973": [  # Group Insurance：福利清單裡的「勞健保/團體保險」不是團險業務技能
        *_BENEFIT_WORDS, r"員工", r"健康檢查",
    ],
    "ES8E13F7072E92C43C42": [  # Employers Liability：福利清單「勞保、健保、雇主責任險」不是雇主責任法務技能
        *_BENEFIT_WORDS, r"勞保", r"健保", r"勞退", r"保險類", r"團體意外", r"雇主責任(險|額)",
    ],
    "KS121C76HJ5W4VDVBPNJ": [  # Cancer：福利「醫療險、癌症險、壽險」不是癌症醫學
        r"癌症險", r"(醫療|壽|意外|防癌)險", *_BENEFIT_WORDS,
    ],
    "KS1254G739VBXHP430DV": [  # Information Management：「房地產資訊管理」是整理物件資料，不是資訊管理（IT）
        r"(房地產|房屋|物件|不動產|客戶|商品|產品|會員)資訊管理",
    ],
    "KS1218H6JY4J8RS4VJ78": [  # Management Consulting：公司名「XX管理顧問有限公司」不是管理顧問技能
        r"管理顧問(股份)?有限公司", r"管理顧問(公司|集團|事業)",
    ],
    "ES716C5796BF61AC43D3": [  # USP Compliance：Google 雲端連結「?usp=sharing」
        r"usp=", r"https?://", r"drive\.google", r"docs\.google",
    ],
    "KS1214G602SVSCGL80S5": [  # Bones：「懶骨頭沙發」、動畫「骨骼綁定/骨骼動畫」
        r"懶骨頭", r"動畫", r"綁定", r"模型", r"spine", r"dragon\s*bones?", r"(?<![a-z])rig", r"3d", r"建模", r"遊戲",
    ],
    "KS441J961KBW0V36CZMS": [  # Travel Insurance：福利「Medical insurance and travel insurance •Holiday bonuses」
        *[w for w in _BENEFIT_WORDS if w != r"旅遊"], r"medical\s+insurance", r"life\s+insurance", r"bonus", r"benefit", r"勞健保",
    ],
    "ES335691142D65A7FCD8": [  # Administrative Agencies：休假說明「依照政府行政機關辦公日曆表」
        r"辦公日曆", r"行事曆", r"休假", r"放假", r"國定假日",
    ],
    "KS122ZQ6X99D6GDFH046": [  # Direct Marketing：不動產招募賣點「物件有700位夥伴直效行銷」
        r"\d+\s*位夥伴", r"夥伴直效行銷",
    ],
    "ES521F8BA3E475CFEB34": [  # File Naming：投遞說明「履歷檔案命名方式為…」
        r"履歷", r"應徵", r"投遞", r"resume", r"\bcv\b",
    ],
    "KS126DG60LZR91S4DNYJ": [  # Merchant Services：福利「特約商店員工優惠」不是收單業務
        *_BENEFIT_WORDS, r"員工",
    ],
    "KS121FJ73Y72V62WS2SG": [  # Casualty Insurance：福利清單的「員工意外險/團保（含意外險）」
        *_BENEFIT_WORDS, r"員工", r"健康檢查", r"職災",
    ],
    "ESBE2E8DE338C307E78F": [  # Companionship：「團隊全程陪伴」「學長姐陪伴新人」是帶新人，不是陪伴照護
        r"(團隊|學長|學姊|學姐|主管|前輩|老鳥|師傅|導師|夥伴).{0,6}陪伴", r"陪伴(你|您|妳|新人|新進|夥伴|成長)",
        # 寵物、員工訓練、公司使命/品牌標語裡的「陪伴」
        r"毛孩", r"寵物", r"陪伴學習", r"肩併肩", r"陪伴(每一位|每位|所有|顧客|客人|客戶|消費者)",
        r"(我們|使命|致力|相信|願景|理念|品牌).{0,15}陪伴",
    ],
    "KS122CN6BRVZ0SHTVYF9": [  # Control Engineering：「以控制工程的執行進度」是「控制／工程」，斷詞斷錯
        r"控制工程(的|之)?(執行|進度|品質|施工|預算|成本|品管)", r"以控制工程",
    ],
    "KS1230C5X5T37GZ1NJ2B": [  # Disabilities：公平就業聲明「不歧視殘障人士或退伍軍人」、身障者優先錄用說明
        r"歧視", r"discriminat", r"equal\s+(employment\s+)?opportunit", r"accommodat", r"veteran", r"退伍",
        r"平等", r"certificate", r"(證明|手冊)", r"(優先|保障)(錄|進用|名額)",
    ],
    "BGSD21CF2746CB8B2ECD": [  # Environmental Quality：門市「維持整潔與環境品質」是打掃，不是環境工程
        r"門市", r"整潔", r"清潔", r"店面", r"用餐", r"客人", r"顧客",
    ],
    "KS122YY5WBP7GQPNRFG3": [  # Digital Signal Processing：廣告技術的 DSP 是需求方平台
        r"廣告", r"(?<![a-z])(adx|dmp|ssp|rtb)(?![a-z])", r"programmatic", r"程式化", r"ad\s*tech", r"投放", r"media\s*buy",
    ],
    "ES78D706A6A18746395D": [  # Social Influences：「社會影響力」是社會影響（CSR），不是社會心理學的社會影響
        r"社會影響力",
    ],
    "KS12403769SV21756FDY": [  # Employee Benefits：「※員工福利※」「《員工福利》三節獎金」是福利段標題，不是福利管理技能
        r"[※#☆★《【\[◆■●◎▶►]\s*員工福利", r"員工福利\s*[※》】\]:：亮點]", r"員工福利\s*(制度)?\s*[-–—]",
        r"員工福利\s*(三節|年終|勞健保|獎金|旅遊|聚餐|生日|伙食|制服|享有|包含|完善)",
    ],
    "KS121DS6GB09TFN7RLX0": [  # Career Development：「清晰的職涯發展路徑」「長期職涯發展機會」是招募賣點，不是生涯輔導技能
        r"職涯發展.{0,4}(路徑|機會|舞台|空間|前景|藍圖|管道|制度)", r"(擁有|完善|清晰|良好|長期|廣闊|多元).{0,6}職涯發展",
        r"職涯發展\s*[:：】》]", r"[【《★☆※#]\s*(未來)?\s*職涯發展", r"職涯發展.{0,4}(選擇|潛力|安排)", r"視.{0,8}職涯發展",
    ],
    "KS123XW6P97RPNNMNSVR": [  # Sterilization：餐飲/房務/動物房的「清潔、消毒」是環境清潔，器械消毒滅菌才是
        r"環境消毒", r"清潔.{0,4}消毒", r"消毒.{0,4}(維護|垃圾|整理|打掃)", r"打掃", r"(地面|桌面|水溝|廁所|客房|房務)",
    ],
    "KS1286Z676M8QT4VF18Q": [  # Public Offering：公司介紹「公司並預計公開發行」不是辦理公開發行的財務技能
        r"(預計|即將|準備|計畫|規劃中|已|已經).{0,4}公開發行", r"公開發行(公司|之公司)", r"股票分紅", r"(公司|本公司).{0,4}公開發行",
    ],
    "ES34A9B47D6EC1BC42D1": [  # Environment Management：「門市環境管理」是店面整潔，不是 ISO 14001 環境管理
        r"門市", r"店面", r"賣場", r"整潔", r"清潔", r"教室", r"營業場所",
    ],
    "KS123KG60GGMNWN891FJ": _HEALTH_CHECK_REQ,  # Typhoid Fever
    "BGS11C52A75C1BEE1B8E": _HEALTH_CHECK_REQ,  # Skin Disorders
    "KS124PC74G19MCTPFTX2": _HEALTH_CHECK_REQ,  # Hepatitis
    "KS7G5MH748VW3PWW01ZV": _HEALTH_CHECK_REQ,  # Tuberculosis
    "KS1253W6N7B22L0ZD773": _HEALTH_CHECK_REQ,  # Infectious Diseases
    "KS4407H64CVBMTRQZRCF": [  # Sales Management：門市「進貨入庫、銷售管理及庫存管理」是店務，不是業務團隊管理（使用者11/12決定）
        r"門市", r"店面", r"店內", r"賣場", r"專櫃", r"進貨", r"入庫", r"庫存", r"陳列", r"收銀", r"(?<![a-z])pos(?![a-z])", r"上架", r"補貨",
    ],
    "KS441GF61XWGQYBJRY2J": [  # Trachea：「排氣管」「機台氣管裝配」是機械/汽車的氣管
        r"排氣管", r"氣管(裝配|接頭|配管|管路|組立)", r"機台", r"空壓", r"氣壓", r"改裝", r"煞車", r"避震", r"馬達",
    ],
    "KS125BG6KF4M0K7X6QJ8": [  # Rate Of Return：公司介紹「股東權益報酬率」、業務招募「獎金回報率」
        r"股東權益", r"(?<![a-z])roe(?![a-z])", r"獎金", r"連續.{0,6}(年|季)", r"上市櫃", r"薪資", r"收入",
    ],
    "KS125S56Y4CXSJHQHCZJ": [  # Learning Platforms：福利「透過公司學習平台，多元化學習」
        r"(透過|提供|享有|完善|使用).{0,6}學習平台", r"(公司|內部|員工|線上)學習平台", *_BENEFIT_WORDS,
    ],
    "KS1225N6R4M64Z082XLZ": [  # Public Health：「食品、藥學、公共衛生等相關科系」是學歷條件
        r"科系", r"學系", r"系所", r"相關科系", r"畢業",
    ],
    "KS1280P6542CXXZN0FHY": [  # Caregiving：動物、寵物的照顧不是照護
        r"動物", r"寵物", r"飼育", r"飼養", r"(?<![一-鿿])(犬|貓)", r"鸚鵡", r"豬隻", r"魚隻",
    ],
    "ES93F8B89DCFEB3D8E20": [  # Demand Planning：「客戶人力/保險需求規劃」不是供應鏈需求規劃
        r"客戶", r"保險", r"人力",
    ],
    "KS43I7T7CU4Q66EGVQLU": [  # Coaching：「作業指導書」、「供應商輔導」不是教練指導
        r"指導書", r"供應商", r"協力廠", r"廠商",
    ],
    "KS127MC6FMH3R4C3N5PZ": [  # PCI 匯流排：PCI-DSS 是支付卡資安標準
        r"pci[\s\-]?dss", r"支付", r"payment", r"信用卡", r"資安", r"資訊安全", r"資料安全", r"security", r"27001",
    ],
}


def is_context_excluded(skill_id: str, snippet: str) -> bool:
    """只看命中位置附近的文字片段(snippet)判斷要不要排除，不要掃整篇——否則
    同一份職缺裡真的有「負責採購」又剛好另外提到「採購單對帳」時，前者會被
    後者一起誤殺。"""
    rules = _CONTEXT_EXCLUSION_RULES.get(skill_id)
    if not rules:
        return False
    return any(re.search(p, snippet, re.IGNORECASE) for p in rules)


# 一詞多義的裸縮寫：命中的是裸縮寫本身（不是全名）時，要在命中位置前後 window 字內
# 找到該領域的佐證詞才算，範圍比排除規則的 50 字大，因為縮寫常出現在條列裡，
# 領域線索在前後幾行。例：GCP 在雲端職缺是 Google Cloud，在藥廠是臨床試驗規範；
# GDP 在藥品物流是優良運銷規範，在一般文字是國內生產毛額。
_W = r"(?<![a-z])"
_CLINICAL = [r"臨床", r"clinical", r"trial", r"試驗", _W + r"ich(?![a-z])", _W + r"glp(?![a-z])",
             _W + r"gmp(?![a-z])", _W + r"irb(?![a-z])", _W + r"cr[aco](?![a-z])",
             r"藥", r"pharma", r"受試", r"sponsor", r"醫"]
_CLOUD = [r"雲", r"cloud", _W + r"aws(?![a-z])", r"azure", r"docker", r"kubernetes", _W + r"k8s",
          r"bigquery", r"devops", r"ci/cd", r"linux", r"deploy", r"部署", _W + r"gke(?![a-z])",
          r"vertex", r"terraform", r"容器", r"container", r"微服務", r"阿里", r"server", r"伺服器",
          _W + r"api(?![a-z])", _W + r"sql(?![a-z])", r"python", r"java", r"平台"]
# 另可給「緊鄰排除」：命中位置前後 60 字內出現另一個意思的線索就不算
# （醫療業的雲端職缺也會出現「醫」「protocol」，但 GCP 緊鄰 AWS/Azure 就是雲端）
_NEAR = 60
_CLINICAL_NEAR = [r"臨床", r"clinical", r"trial", r"試驗", _W + r"ich(?![a-z])", _W + r"glp(?![a-z])",
                  _W + r"gmp(?![a-z])", r"受試", r"sponsor"]
_CLOUD_NEAR = [r"雲", r"cloud", _W + r"aws(?![a-z])", r"azure", r"docker", r"kubernetes", _W + r"k8s",
               r"bigquery", r"devops", r"部署", r"deploy", r"阿里",
               r"network", r"網路", r"data center", r"資料中心"]
_SW_NEAR = [r"程式", r"軟體", r"演算法", r"系統", r"平台", r"嵌入式", r"(?<![a-z])code", r"firmware", r"韌體",
                 r"android", r"linux", r"驅動", r"資料", r"專案", r"(?<![a-z])(ios|app|bsp)(?![a-z])"]
_ACRONYM_CONTEXT_REQUIRED = {
    "KS124ZQ6RS1V188JSCTX": ("GCP", 300, _CLINICAL, _CLOUD_NEAR),   # Good Clinical Practices
    "ESC7869CF7378283E0AA": ("GCP", 300, _CLOUD, _CLINICAL_NEAR),   # Google Cloud Platform
    "KS1220H6CP1BQGH9STNK": ("GCP", 300, _CLOUD, _CLINICAL_NEAR),   # Cloud Computing
    "ES63C92B9AE0C7FC326A": ("GDP", 300, [             # Good Distribution Practices
        r"藥", r"pharma", r"醫", r"運銷", r"distribution", _W + r"gmp(?![a-z])", _W + r"gsp(?![a-z])",
        r"冷鏈", r"cold chain", r"溫[溼濕]度", r"倉", r"物流", r"logistic", r"品質", r"quality",
        _W + r"iso(?![a-z])", r"healthcare", _W + r"cmo(?![a-z])", r"compliance", r"法規", r"稽核", r"疫苗",
        r"庫存", r"進貨", r"出貨", r"調撥"], []),
    "ESA5839C44D0970CF79F": ("GO", 150, [              # Go 程式語言：GO GREEN、go the extra mile 不算
        r"python", r"java", r"c\+\+", r"(?<![a-z])c#", r"rust", r"golang", r"node", r"php", r"ruby",
        r"kotlin", r"swift", r"scala", r"typescript", r"程式", r"後端", r"backend", r"語言", r"language",
        r"programming", r"docker", r"kubernetes", r"microservice", r"微服務", r"grpc", r"(?<![a-z])api(?![a-z])",
        r"開發", r"develop", r"software", r"軟體"],
        [r"go[\s\-]*green", r"go[\s\-]*getter", r"extra mile", r"go[\s\-]*live", r"go[\s\-]*to[\s\-]*market",
         r"let'?s go", r"go[\s\-]*go"]),
    # 中文詞也可用：key 是命中的詞本身。「移植」在軟體職缺是程式移植（porting）
    "KS1219M6MNGKS2RQ88KR": ("移植", 150, [r"醫", r"手術", r"器官", r"皮膚", r"骨", r"植牙", r"毛髮", r"幹細胞", r"臨床",
        r"病", r"護理", r"接枝", r"嫁接", r"果樹", r"植物", r"園藝"], _SW_NEAR),       # Graft
    "KS4400J6VPDDLT3B7ND1": ("移植", 150, [r"植物", r"苗", r"園藝", r"種植", r"花", r"樹", r"農", r"盆栽"], _SW_NEAR),  # Transplanting
    "KS1239T79CX8F0MNH5CS": ("生態系統", 150, [r"生物", r"保育", r"物種", r"棲地", r"生態學", r"水域", r"森林", r"野生",
        r"[濕溼]地", r"海洋", r"河川", r"環境影響", r"動物", r"植物"],
        [r"python", r"程式", r"技術", r"(?<![a-z])api", r"amazon", r"平台", r"產業", r"軟體", r"開發", r"商業",
         r"(?<![a-z])ai(?![a-z])", r"雲", r"數位", r"產品", r"品牌", r"夥伴", r"合作"]),     # Ecological Systems
    "BGSD8087190524796EEE": ("基礎設計", 150, [r"地基", r"基樁", r"樁", r"結構", r"土木", r"大地", r"建築", r"開挖",
        r"基礎工程", r"地質", r"筏式", r"擋土"],
        [r"電路", r"電子", r"韌體", r"程式", r"軟體", r"網頁", r"(?<![a-z])ui(?![a-z])", r"視覺", r"平面", r"美術",
         r"品牌", r"色彩", r"金融"]),                                                   # Foundation Design
    "ES91BEBA3032A3B99273": ("OCP", 150, [r"oracle", r"資料庫", r"database", r"(?<![a-z])dba", r"sql"],
        [r"openshift", r"red\s*hat", r"open\s*compute", r"資料中心", r"data\s*center", r"伺服器", r"虛擬化"]),  # Oracle OCP
    # 「系統管理」：「ISO9001系統管理」「安全衛生系統管理」「出勤及徵才系統管理」不是資訊系統管理
    "KS122VV71XNN7Y03XJNN": ("系統管理", 150, [r"伺服器", r"server", r"linux", r"windows", r"unix", r"網路", r"資訊",
        r"資安", r"(?<![a-z])(mis|it|ad|dns|dhcp|vm|aix)(?![a-z])", r"主機", r"帳號", r"資料庫", r"虛擬化", r"作業系統",
        r"機房", r"備份", r"防火牆", r"vmware", r"雲", r"電腦", r"維運", r"部署", r"開發", r"軟體", r"程式"],
        # 只看緊貼的前後 10 字：ISO27001 是資安標準不排除，只排除管理系統類 ISO
        [r"iso\s*(9001|14001|45001|50001|22000)", r"安全衛生", r"安衛", r"職安", r"品質", r"環境管理", r"環保", r"能源",
         r"出勤", r"徵才", r"條碼", r"倉儲"], 10),
    "KS121ZQ6V2BPNM2CQQC5": ("CNS", 150, [r"護理", r"臨床", r"nurs", r"病人", r"病患", r"醫院"],   # Clinical Nurse Specialist
        [r"(?<![a-z])(iso|jis|asme|astm|din|ul|iec|en)(?![a-z])", r"標準", r"規範", r"法規", r"國家標準", r"驗證", r"檢驗"]),
    "KS121MM6JC9ZH1N8P9LG": ("CHT", 150, [r"透析", r"洗腎", r"hemodialysis", r"dialysis", r"醫院", r"護理", r"腎"],  # 血液透析技術師
        [r"cht\.com", r"中華電信", r"https?://", r"www\."]),
    # 「員工福利」多半是福利描述（「等等員工福利」「員工福利卡」「支付員工福利金」）；
    # 人資職缺會寫「規劃/辦理/管理員工福利」，所以前後 12 字內要有人資動作才算
    "KS12403769SV21756FDY": ("員工福利", 12, [r"規劃", r"辦理", r"執行", r"管理", r"推動", r"負責", r"承辦", r"處理",
        r"作業", r"設計", r"事務", r"事項", r"方案", r"福委", r"福利委員", r"建立", r"維持", r"活動"], [], 0),
    "ES874661E61612F924CC": ("MAP", 150, [r"給藥", r"藥物", r"medication", r"護理", r"照護", r"醫"],   # MAP 給藥認證；「Map API」是地圖
        [r"(?<![a-z])api(?![a-z])", r"gis", r"圖台", r"google", r"arcgis", r"tgos", r"地圖"]),
    "ES21F3D33FACABBA01C2": ("CCC", 150, [r"信用", r"債務", r"credit", r"counsel", r"理財", r"財務諮詢"],   # 信用諮詢師；安規 CCC 是中國強制認證
        [r"(?<![a-z])(ul|cb|tuv|bsmi|pse|bis|kc|ce|fcc|nemko)(?![a-z])", r"安規", r"認證"]),
    "ESC5D4222D51E1693D50": ("AMS", 150, [r"協會", r"association", r"會員", r"社團", r"公會"],   # 協會管理專員；Android AMS 是系統元件
        [r"android", r"(?<![a-z])(wms|pms)(?![a-z])", r"framework", r"surfaceflinger"]),
    "BGSF5045F8EFDBF0641E": ("AMS", 150, [r"提單", r"報關", r"艙", r"海關", r"船", r"(?<![a-z])(afr|isf|bl|b/l)(?![a-z])", r"進出口", r"shipping", r"customs", r"manifest"],  # 美國海關艙單系統
        [r"android", r"(?<![a-z])(wms|pms)(?![a-z])", r"framework"]),
    "ESD17DD1296EFCCCF0AF": ("CTO", 150, [r"塔台", r"航管", r"飛航", r"tower", r"aviation", r"機場", r"air\s*traffic"],  # 塔台管制員證照；CTO多半是技術長
        [r"技術長", r"主管", r"chief", r"(?<![a-z])(vp|ceo|cfo|coo|cio)s?(?![a-z])", r"負責人", r"executive"]),
    "KS126966H39MX8JKF9TX": ("MECHANICS", 150, [r"engineer", r"physics", r"structural", r"fluid", r"solid", r"machin", r"mechanical",  # 力學
        r"力學", r"機械", r"結構", r"材料", r"thermo", r"dynamics", r"cae", r"finite\s+element"],
        [r"game", r"campaign", r"product\s+mechanics", r"royalt", r"recoup", r"gameplay", r"promo", r"loyalty", r"reward"]),
    "KS127MD73WL7RSVDW53X": ("PCI", 300, [             # PCI Data Security Standards
        _W + r"dss(?![a-z])", r"支付", r"payment", r"信用卡", r"credit card", r"刷卡", r"金流", r"收單",
        r"資安", r"資訊安全", r"security", r"27001", r"compliance", r"法遵"], []),
}


# 否定句（2026-11-12 使用者同意上線）：「無需陌生開發」「不需輪大夜班」「不需要業務銷售」「免外撥電話」
# 裡的技能不是職缺要求。否定詞到關鍵字之間最多 6 字、且中間沒有斷句標點才算；
# 「免」排除 免費/免疫/免稅/免責/免於/免除 與 避免/以免/難免/未免。
# 臺北202601 評估：約 500 組（0.08%），抽樣幾乎都是該拿掉的（陌生開發 159、銷售 71、輪大夜班 40…）
_NEGATION_RE = re.compile(
    r"(無需|無須|不需要|不需|不用|不必|毋須|毋需|(?<![避以難未])免(?!費|疫|稅|責|於|除))"
    r"(具備|擁有|有|負擔|會|相關|任何|專業)?([^，。,、；;！!？?\n]{0,6})$"
)


def is_negated(raw_text: str, start: int) -> bool:
    if start <= 0:
        return False
    return _NEGATION_RE.search(raw_text[max(0, start - 14):start]) is not None


def lacks_required_context(skill_id: str, matched_term: str, raw_text: str, start: int, end: int) -> bool:
    rule = _ACRONYM_CONTEXT_REQUIRED.get(skill_id)
    if not rule:
        return False
    acronym, window, patterns, near_deny = rule[:4]
    near_w = rule[4] if len(rule) > 4 else _NEAR
    if matched_term.strip().upper() != acronym:
        return False
    near = raw_text[max(0, start - near_w): end + near_w + 1]
    if any(re.search(p, near, re.IGNORECASE) for p in near_deny):
        return True
    ctx = raw_text[max(0, start - window): end + window + 1]
    return not any(re.search(p, ctx, re.IGNORECASE) for p in patterns)
