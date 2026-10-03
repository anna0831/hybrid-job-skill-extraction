# -*- coding: utf-8 -*-
"""
建置 104技能擷取程式_修改邏輯與會議審查_0930詞庫更新版.docx
嚴格遵守學術審查中性語氣、無 evaluative wording、字體全域微軟正黑體、
移除撰寫者資訊、決策表精簡為4欄（移除負責人與期限）。
"""

import os
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

def set_cell_shading(cell, color_hex):
    """設定儲存格背景底色"""
    tcPr = cell._tc.get_or_add_tcPr()
    for child in list(tcPr):
        if child.tag.endswith('shd'):
            tcPr.remove(child)
    tcPr.append(parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>'))

def set_cell_margins(cell, top=100, bottom=100, left=140, right=140):
    """設定儲存格內邊距 (dxa)"""
    tcPr = cell._tc.get_or_add_tcPr()
    for child in list(tcPr):
        if child.tag.endswith('tcMar'):
            tcPr.remove(child)
    tcMar_xml = f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>'
    tcPr.append(parse_xml(tcMar_xml))

def set_table_borders(table, color="D3D3D3", sz="4", val="single"):
    """設定表格精緻灰色格線"""
    tblPr = table._tbl.tblPr
    borders_xml = f'''
    <w:tblBorders {nsdecls("w")}>
        <w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>
        <w:left w:val="none"/>
        <w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>
        <w:right w:val="none"/>
        <w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>
        <w:insideV w:val="none"/>
    </w:tblBorders>
    '''
    tblPr.append(parse_xml(borders_xml))

def apply_row_protection(row, is_header=False):
    """防止跨頁斷裂與設置表頭跨頁重複"""
    trPr = row._tr.get_or_add_trPr()
    trPr.append(parse_xml(f'<w:cantSplit {nsdecls("w")}/>'))
    if is_header:
        trPr.append(parse_xml(f'<w:tblHeader {nsdecls("w")}/>'))

def format_cell_text(cell, text, bold=False, color="000000", size=9.5, align=WD_ALIGN_PARAGRAPH.LEFT):
    """填入儲存格文字並強制鎖定微軟正黑體"""
    p = cell.paragraphs[0]
    p.alignment = align
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.15
    run = p.add_run(text)
    run.bold = bold
    run.font.name = 'Microsoft JhengHei'
    run.font.size = Pt(size)
    rPr = run._r.get_or_add_rPr()
    rPr.append(parse_xml(f'<w:rFonts {nsdecls("w")} w:eastAsia="Microsoft JhengHei" w:ascii="Microsoft JhengHei" w:hAnsi="Microsoft JhengHei"/>'))
    if color != "000000":
        r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
        run.font.color.rgb = RGBColor(r, g, b)

def build_review_docx(output_path="104技能擷取程式_修改邏輯與會議審查_0930詞庫更新版.docx"):
    doc = docx.Document()

    # 頁面邊界設定 (Top/Bottom/Left/Right 各 0.8 英吋，可列印寬度 6.9 英吋)
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)
        
        # 頁首 (9 pt 微軟正黑體)
        header = section.header
        hp = header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        hrun = hp.add_run("研究會議審查技術文件（草案）｜104 職缺技能擷取系統")
        hrun.font.name = "Microsoft JhengHei"
        hrun.font.size = Pt(9)
        hrun.font.color.rgb = RGBColor(140, 140, 140)
        rPr_h = hrun._r.get_or_add_rPr()
        rPr_h.append(parse_xml(f'<w:rFonts {nsdecls("w")} w:eastAsia="Microsoft JhengHei" w:ascii="Microsoft JhengHei" w:hAnsi="Microsoft JhengHei"/>'))

        # 頁尾 (9 pt 微軟正黑體)
        footer = section.footer
        fp = footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        frun = fp.add_run("— 僅供研究團隊內部審查與決策討論使用 —")
        frun.font.name = "Microsoft JhengHei"
        frun.font.size = Pt(9)
        frun.font.color.rgb = RGBColor(140, 140, 140)
        rPr_f = frun._r.get_or_add_rPr()
        rPr_f.append(parse_xml(f'<w:rFonts {nsdecls("w")} w:eastAsia="Microsoft JhengHei" w:ascii="Microsoft JhengHei" w:hAnsi="Microsoft JhengHei"/>'))

    # 全域 Normal 樣式強制微軟正黑體 (11 pt)
    normal_style = doc.styles['Normal']
    normal_style.font.name = 'Microsoft JhengHei'
    normal_style.font.size = Pt(11)
    normal_style.font.color.rgb = RGBColor(40, 40, 40)
    normal_style.paragraph_format.line_spacing = 1.25
    normal_style.paragraph_format.space_after = Pt(4)
    rPr_norm = normal_style.element.get_or_add_rPr()
    rPr_norm.append(parse_xml(f'<w:rFonts {nsdecls("w")} w:eastAsia="Microsoft JhengHei" w:ascii="Microsoft JhengHei" w:hAnsi="Microsoft JhengHei"/>'))

    def add_p(text):
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.font.name = 'Microsoft JhengHei'
        run.font.size = Pt(11)
        rPr = run._r.get_or_add_rPr()
        rPr.append(parse_xml(f'<w:rFonts {nsdecls("w")} w:eastAsia="Microsoft JhengHei" w:ascii="Microsoft JhengHei" w:hAnsi="Microsoft JhengHei"/>'))
        return p

    def add_h1(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text)
        run.bold = True
        run.font.name = 'Microsoft JhengHei'
        run.font.size = Pt(16)
        run.font.color.rgb = RGBColor(26, 54, 93) # #1A365D Deep Navy
        rPr = run._r.get_or_add_rPr()
        rPr.append(parse_xml(f'<w:rFonts {nsdecls("w")} w:eastAsia="Microsoft JhengHei" w:ascii="Microsoft JhengHei" w:hAnsi="Microsoft JhengHei"/>'))
        return p

    def add_h2(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text)
        run.bold = True
        run.font.name = 'Microsoft JhengHei'
        run.font.size = Pt(13.5)
        run.font.color.rgb = RGBColor(43, 108, 176) # #2B6CB0 Slate Blue
        rPr = run._r.get_or_add_rPr()
        rPr.append(parse_xml(f'<w:rFonts {nsdecls("w")} w:eastAsia="Microsoft JhengHei" w:ascii="Microsoft JhengHei" w:hAnsi="Microsoft JhengHei"/>'))
        return p

    def add_callout(text, title="說明事項", bg_color="EDF2F7", border_color="2B6CB0"):
        table = doc.add_table(rows=1, cols=1)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        cell = table.rows[0].cells[0]
        cell.width = Inches(6.9)
        set_cell_shading(cell, bg_color)
        set_cell_margins(cell, top=100, bottom=100, left=160, right=160)
        
        tcPr = cell._tc.get_or_add_tcPr()
        borders_xml = f'''
        <w:tcBorders {nsdecls("w")}>
            <w:top w:val="none"/>
            <w:left w:val="single" w:sz="24" w:space="0" w:color="{border_color}"/>
            <w:bottom w:val="none"/>
            <w:right w:val="none"/>
        </w:tcBorders>
        '''
        tcPr.append(parse_xml(borders_xml))
        
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.2
        r_title = p.add_run(f"【{title}】")
        r_title.bold = True
        r_title.font.name = 'Microsoft JhengHei'
        r_title.font.size = Pt(9.5)
        r_title.font.color.rgb = RGBColor(43, 108, 176)
        rPr_t = r_title._r.get_or_add_rPr()
        rPr_t.append(parse_xml(f'<w:rFonts {nsdecls("w")} w:eastAsia="Microsoft JhengHei" w:ascii="Microsoft JhengHei" w:hAnsi="Microsoft JhengHei"/>'))
        
        r_txt = p.add_run(text)
        r_txt.font.name = 'Microsoft JhengHei'
        r_txt.font.size = Pt(9.5)
        r_txt.font.color.rgb = RGBColor(45, 55, 72)
        rPr_txt = r_txt._r.get_or_add_rPr()
        rPr_txt.append(parse_xml(f'<w:rFonts {nsdecls("w")} w:eastAsia="Microsoft JhengHei" w:ascii="Microsoft JhengHei" w:hAnsi="Microsoft JhengHei"/>'))
        doc.add_paragraph().paragraph_format.space_after = Pt(4)

    # ----------------------------------------------------
    # 文件封面 / 抬頭資訊
    # ----------------------------------------------------
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(6)
    title_p.paragraph_format.space_after = Pt(2)
    run_t = title_p.add_run("104 技能擷取系統：修改邏輯與會議審查技術文件")
    run_t.bold = True
    run_t.font.size = Pt(18)
    run_t.font.name = 'Microsoft JhengHei'
    run_t.font.color.rgb = RGBColor(26, 54, 93)
    rPr_tp = run_t._r.get_or_add_rPr()
    rPr_tp.append(parse_xml(f'<w:rFonts {nsdecls("w")} w:eastAsia="Microsoft JhengHei" w:ascii="Microsoft JhengHei" w:hAnsi="Microsoft JhengHei"/>'))

    sub_p = doc.add_paragraph()
    sub_p.paragraph_format.space_before = Pt(0)
    sub_p.paragraph_format.space_after = Pt(10)
    run_sub = sub_p.add_run("Long Format 輸出規格、9 大原始欄位保留、最新 0930 詞庫與新版十大分類整合方案")
    run_sub.font.size = Pt(11.5)
    run_sub.font.name = 'Microsoft JhengHei'
    run_sub.font.color.rgb = RGBColor(74, 85, 104)
    rPr_sp = run_sub._r.get_or_add_rPr()
    rPr_sp.append(parse_xml(f'<w:rFonts {nsdecls("w")} w:eastAsia="Microsoft JhengHei" w:ascii="Microsoft JhengHei" w:hAnsi="Microsoft JhengHei"/>'))

    # 詮釋資料盒 (無撰寫者欄位)
    meta_tbl = doc.add_table(rows=2, cols=2)
    meta_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    for r in meta_tbl.rows:
        for c in r.cells:
            set_cell_shading(c, "F7FAFC")
            set_cell_margins(c, top=60, bottom=60, left=100, right=100)
    set_table_borders(meta_tbl, color="CBD5E0", sz="4")
    format_cell_text(meta_tbl.rows[0].cells[0], "文件定位：待研究會議審查之技術討論草案", bold=True, color="2B6CB0", size=9)
    format_cell_text(meta_tbl.rows[0].cells[1], "主要執行程式：104_single_file_20260930.py", bold=False, color="4A5568", size=9)
    format_cell_text(meta_tbl.rows[1].cells[0], "對應詞庫：0930 基底詞庫 + Chen_grouped_09 十大分類對照庫", bold=False, color="4A5568", size=9)
    format_cell_text(meta_tbl.rows[1].cells[1], "輸出規格：Long Format 25 個固定欄位 (Excel / Parquet)", bold=False, color="4A5568", size=9)
    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    add_callout(
        "本文件為研究會議技術討論草案，旨在整理目前程式之修改邏輯、輸出資料規格以及最新 0930 詞庫與十大分類 metadata 之整合情形，供研究團隊評估與審查。文中區分目前已實作行為、測試資料觀察結果與待會議討論事項。",
        title="審查說明", bg_color="EBF8FF", border_color="3182CE"
    )

    # ----------------------------------------------------
    # 第一章：本次修改目的與審查重點
    # ----------------------------------------------------
    add_h1("一、本次修改目的與審查重點")
    add_p(
        "本次修改主要針對 104 職缺技能擷取單檔作業腳本進行調整，以符合後續研究分析與人工抽檢之需求。主要調整方向包括：將輸出由寬表（Wide format）改為長表（Long format）、完整保留 9 個原始職缺欄位、將詞庫原始 Category_Name 與 Subcategory_Name 放置於前兩欄，並導入新版十大技能分類供統計使用。"
    )

    # 差異總表
    t1 = doc.add_table(rows=5, cols=4)
    t1.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t1)
    apply_row_protection(t1.rows[0], is_header=True)
    for r in t1.rows[1:]:
        apply_row_protection(r)

    headers1 = ["構面", "修改前 (原始 0909 版)", "本次修改狀態 (0930 程式)", "修改目的說明"]
    col_widths1 = [Inches(1.2), Inches(1.8), Inches(2.2), Inches(1.7)]
    for i, h in enumerate(headers1):
        cell = t1.rows[0].cells[i]
        cell.width = col_widths1[i]
        set_cell_shading(cell, "1A365D")
        format_cell_text(cell, h, bold=True, color="FFFFFF", size=9.5, align=WD_ALIGN_PARAGRAPH.CENTER)

    t1_data = [
        ("主要輸出格式", "預設僅輸出 Wide Excel 寬表，技能以「｜」合併於單一儲存格。", "主要輸出 Long format（Excel 與 Parquet 鏡像一致）；每列為一筆職缺與一項技能。", "便於計量模型展開分析；【目前已實作】"),
        ("原始職缺欄位", "輸出僅保留 ID、縣市、月份；職位描述等欄位未輸出。", "保留 9 個原始職缺欄位（職位描述、工作技能、工具等）未做截斷，於命中列中重複呈現。", "方便直接核對原文語境與擷取結果；【目前已實作】"),
        ("詞庫分類欄位", "未輸出 Category_Name，僅輸出寬表中之中文大類表頭。", "前兩欄放置詞庫原始 Category_Name 與 Subcategory_Name。", "保留 Lightcast 原始分類階層；【目前已實作】"),
        ("技能主分類", "採用舊版九大分類（含舊 AI 技能）。", "導入新版十大技能分類（代碼 1~10 及中文名稱），擴充 Grouping 稽核欄位。", "銜接 Word 建議版分類架構；【目前已實作靜態對應】")
    ]
    for row_idx, data in enumerate(t1_data, start=1):
        row = t1.rows[row_idx]
        bg = "F7FAFC" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx, text in enumerate(data):
            c = row.cells[col_idx]
            c.width = col_widths1[col_idx]
            set_cell_shading(c, bg)
            set_cell_margins(c, top=80, bottom=80, left=100, right=100)
            align = WD_ALIGN_PARAGRAPH.CENTER if col_idx in [0, 3] else WD_ALIGN_PARAGRAPH.LEFT
            format_cell_text(c, text, bold=(col_idx == 0), size=8.5, align=align)

    doc.add_paragraph().paragraph_format.space_after = Pt(4)

    # ----------------------------------------------------
    # 第二章：修改前後的處理流程
    # ----------------------------------------------------
    add_h1("二、修改前後的處理流程")
    add_p(
        "目前端到端處理流程如下：\n"
        "① 讀取職缺資料與詞庫（0930 基底詞庫 + Chen_grouped_09 分類詞庫）→ ② 整理詞庫欄位並建立十大分類對照索引 → ③ 建構 Aho-Corasick 自動機 → ④ 執行字串比對與既有消歧補救邏輯 → ⑤ 組合原始職缺資料與命中的技能記錄 → ⑥ 輸出 25 欄位之 Long format 檔案。"
    )

    add_callout(
        "架構說明：經查核，原始 104_single_file_20260909.py 腳本中，process_county() 內部即已使用 records 串列暫存一對多的技能資料結構（稱為 long_df）。但原版僅包含 7 個內部欄位，且在 main() 中直接被轉為寬表輸出，未將 long_df 儲存。本次修改為擴充該內部資料結構之欄位，並將其作為主要產出格式進行匯出。",
        title="資料結構說明", bg_color="FEFCBF", border_color="B7791F"
    )

    t2 = doc.add_table(rows=6, cols=3)
    t2.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t2)
    apply_row_protection(t2.rows[0], is_header=True)
    for r in t2.rows[1:]:
        apply_row_protection(r)

    headers2 = ["處理階段", "修改前狀態", "本次修改情形"]
    col_widths2 = [Inches(1.5), Inches(2.7), Inches(2.7)]
    for i, h in enumerate(headers2):
        cell = t2.rows[0].cells[i]
        cell.width = col_widths2[i]
        set_cell_shading(cell, "1A365D")
        format_cell_text(cell, h, bold=True, color="FFFFFF", size=9.5, align=WD_ALIGN_PARAGRAPH.CENTER)

    t2_data = [
        ("詞庫載入與解析", "讀取 0918 基底詞庫，建立關鍵字索引。", "讀取 0930 基底詞庫作為比對依據，並讀取 Chen_grouped_09 建立 Skill_ID 十大分類 metadata 查找索引。"),
        ("AC 自動機建構", "依關鍵字建構 Trie 樹與 Failure 鏈接。", "維持既有 Aho-Corasick 自動機建構方式。"),
        ("技能比對邏輯", "match_skills() 配合 jieba 邊界檢查；resolve_ambiguous_by_title() 補救零命中。", "維持既有比對演算法、長詞優先抑制及消歧補救規則，未更動比對核心。"),
        ("資料組合 (process_county)", "僅提取 job_id、縣市、月份與技能欄位組合成 7 欄內部表。", "改由逐列直接抓取原始 9 個職缺欄位，與命中的技能逐一組裝成 25 欄記錄。"),
        ("資料輸出 (main)", "輸出 Wide 寬表 Excel；未輸出 long_df。", "主要輸出具備 25 欄位的 Long Excel 與 Parquet；寬表改由 --wide 參數選用輸出。")
    ]
    for row_idx, data in enumerate(t2_data, start=1):
        row = t2.rows[row_idx]
        bg = "F7FAFC" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx, text in enumerate(data):
            c = row.cells[col_idx]
            c.width = col_widths2[col_idx]
            set_cell_shading(c, bg)
            set_cell_margins(c, top=80, bottom=80, left=100, right=100)
            align = WD_ALIGN_PARAGRAPH.CENTER if col_idx == 0 else WD_ALIGN_PARAGRAPH.LEFT
            format_cell_text(c, text, bold=(col_idx == 0), size=8.5, align=align)

    doc.add_paragraph().paragraph_format.space_after = Pt(4)

    # ----------------------------------------------------
    # 第三章：long format 與原始欄位保留方式
    # ----------------------------------------------------
    add_h1("三、Long Format 與原始欄位保留方式")
    add_p(
        "目前程式輸出的 Long format 中，每列代表「一筆原始職缺 × 一個擷取到的技能」。若一筆職缺命中 3 個相異技能，則輸出 3 列；該職缺的 9 個原始欄位在 3 列中完整呈現，未進行摘要、截斷或欄位覆蓋。"
    )

    add_h2("1. 小型資料展開範例（格式示意，非實際研究結果）")
    add_p(
        "假設一筆職缺編號 ID 為「4029539」的職缺，在描述中命中詞庫中 3 個技能：\n"
        "①「員工福利」（Skill_ID: KS1237L65TCH8606B89L）\n"
        "②「心理諮詢」（Skill_ID: KS1269S6X2RMD45V5N8R）\n"
        "③「椅子按摩」（Skill_ID: KS121CS69C4QLL85G4CS）\n"
        "其輸出樣貌示例如下表所示（僅列出代表性欄位）："
    )

    t3 = doc.add_table(rows=4, cols=6)
    t3.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t3)
    apply_row_protection(t3.rows[0], is_header=True)
    for r in t3.rows[1:]:
        apply_row_protection(r)

    headers3 = ["Category_Name", "ID", "104職位名稱", "職位描述 (原始文字保留)", "SKILL_NAME_ZH", "Skill_group10"]
    col_widths3 = [Inches(1.2), Inches(0.8), Inches(1.1), Inches(1.8), Inches(1.0), Inches(1.0)]
    for i, h in enumerate(headers3):
        cell = t3.rows[0].cells[i]
        cell.width = col_widths3[i]
        set_cell_shading(cell, "1A365D")
        format_cell_text(cell, h, bold=True, color="FFFFFF", size=8.5, align=WD_ALIGN_PARAGRAPH.CENTER)

    t3_data = [
        ("Human Resources", "4029539", "人資專員", "負責規劃員工福利、提供同仁心理諮詢及預約椅子按摩紓壓...", "員工福利", "管理、商業、法遵與治理技能"),
        ("Health Care", "4029539", "人資專員", "負責規劃員工福利、提供同仁心理諮詢及預約椅子按摩紓壓...", "心理諮詢", "醫療、健康與照護技能"),
        ("Personal Care", "4029539", "人資專員", "負責規劃員工福利、提供同仁心理諮詢及預約椅子按摩紓壓...", "椅子按摩", "營運、技職與第一線服務技能")
    ]
    for row_idx, data in enumerate(t3_data, start=1):
        row = t3.rows[row_idx]
        bg = "F7FAFC" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx, text in enumerate(data):
            c = row.cells[col_idx]
            c.width = col_widths3[col_idx]
            set_cell_shading(c, bg)
            set_cell_margins(c, top=80, bottom=80, left=80, right=80)
            align = WD_ALIGN_PARAGRAPH.CENTER if col_idx in [1, 4] else WD_ALIGN_PARAGRAPH.LEFT
            format_cell_text(c, text, bold=False, size=8.0, align=align)

    doc.add_paragraph().paragraph_format.space_after = Pt(4)

    add_h2("2. 原始 9 大欄位保留與來源別名處理")
    add_p(
        "目前程式保留以下 9 個原始職缺欄位：ID、資料月份、刊登日期、工作角色、104職位名稱、104職位名稱碼、職位描述、工作技能、電腦工具。其處理規則如下：\n"
        "• 來源欄位別名優先級：\n"
        "  - ID：優先使用「ID」，無則使用「工作編號」；兩者皆不存在時拋出 ValueError。\n"
        "  - 104職位名稱：優先使用「104職位名稱」，無則使用「職位名稱」。\n"
        "  - 104職位名稱碼：優先使用「104職位名稱碼」，無則使用「職位名稱碼」。\n"
        "  - 電腦工具：優先使用「電腦工具」，無則使用「擅長工具」。\n"
        "  - 衝突警示：同名與替代欄位同時存在且內容不同時，記錄 Warning 日誌。\n"
        "• 型態處理：ID 與職位代碼以字串型態讀取，保留前導零，避免轉換為浮點數。\n"
        "• 資料月份與月份：第 4 欄「資料月份」保留輸入檔原值；第 13 欄「月份」維持由檔名解析之月份，兩者各自獨立。"
    )

    add_h2("3. 資料組合與去重範圍說明")
    add_p(
        "為避免使用 DataFrame merge 可能引發之交叉配對風險，目前程式在 process_county() 中採逐列迭代處理：取得每筆職缺的原始資料後，直接與該筆命中的技能記錄組合成字典。未經由外部 ID merge，以確保每筆職缺資料與其技能獨立對應。\n"
        "去重範圍說明：程式內部的去重集合是在「單筆來源職缺列」層級生效。若原始資料中原本即包含 2 筆相同 ID 的獨立職缺紀錄，兩筆職缺將各自獨立產出技能列。此母體定義列入會議討論。"
    )

    # ----------------------------------------------------
    # 第四章：輸出欄位規格
    # ----------------------------------------------------
    add_h1("四、輸出欄位規格（25 欄固定字典表）")
    add_p(
        "目前程式產出的 Long format 檔案固定包含以下 25 個欄位，其順序與來源定義如下："
    )

    t4 = doc.add_table(rows=26, cols=5)
    t4.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t4)
    apply_row_protection(t4.rows[0], is_header=True)
    for r in t4.rows[1:]:
        apply_row_protection(r)

    headers4 = ["序", "欄位名稱", "來源", "資料型態", "欄位說明與定義"]
    col_widths4 = [Inches(0.4), Inches(1.8), Inches(1.0), Inches(0.9), Inches(2.8)]
    for i, h in enumerate(headers4):
        cell = t4.rows[0].cells[i]
        cell.width = col_widths4[i]
        set_cell_shading(cell, "1A365D")
        format_cell_text(cell, h, bold=True, color="FFFFFF", size=8.5, align=WD_ALIGN_PARAGRAPH.CENTER)

    t4_data = [
        ("1", "Category_Name", "詞庫原始", "string", "詞庫 Lightcast 原始英文大分類名稱。"),
        ("2", "Subcategory_Name", "詞庫原始", "string", "詞庫 Lightcast 原始英文次分類名稱。"),
        ("3", "ID", "原始職缺", "string", "職缺識別碼（字串格式，保留前導零）。"),
        ("4", "資料月份", "原始職缺", "string", "輸入檔案內原始登載之資料月份。"),
        ("5", "刊登日期", "原始職缺", "string", "原始刊登發布日期。"),
        ("6", "工作角色", "原始職缺", "string", "原始所屬工作角色或職務類別。"),
        ("7", "104職位名稱", "原始職缺", "string", "正規化後之 104 職位名稱。"),
        ("8", "104職位名稱碼", "原始職缺", "string", "104 職位官方代碼（字串格式，保留前導零）。"),
        ("9", "職位描述", "原始職缺", "string", "原始職位描述全文（無截斷保留）。"),
        ("10", "工作技能", "原始職缺", "string", "原始工作技能欄位全文（無截斷保留）。"),
        ("11", "電腦工具", "原始職缺", "string", "原始電腦工具/擅長工具全文（無截斷保留）。"),
        ("12", "縣市", "檔名解析", "string", "由職缺檔案名稱解析出的所屬縣市別。"),
        ("13", "月份", "檔名解析", "string", "由職缺檔案名稱解析出的標準化年月。"),
        ("14", "SKILL_ID", "技能比對", "string", "詞庫技能唯一代碼。"),
        ("15", "SKILL_NAME", "技能比對", "string", "詞庫官方英文標準技能名稱。"),
        ("16", "SKILL_NAME_ZH", "技能比對", "string", "詞庫官方繁體中文標準技能名稱。"),
        ("17", "SKILL_TYPE", "技能比對", "string", "技能類型（如 Hard Skill、Specialized Skill）。"),
        ("18", "Category_Code", "詞庫原始", "Int64 (可空)", "詞庫原始大分類數字代碼。"),
        ("19", "Subcategory_Code", "詞庫原始", "Int64 (可空)", "詞庫原始次分類數字代碼。"),
        ("20", "Skill_group10_code", "Word 十大類", "Int64 (可空)", "新版十大技能主分類數字代碼 (1 ~ 10)。"),
        ("21", "Skill_group10", "Word 十大類", "string", "新版十大技能主分類標準中文名稱。"),
        ("22", "Grouping_rule", "分類對照", "string", "十大分類判斷規則依據。"),
        ("23", "Grouping_status", "分類對照", "string", "分類映射狀態（已對應、未對應）。"),
        ("24", "MATCHED_FROM", "比對程序", "string", "觸發命中的職缺來源欄位（職位描述、工作技能、工具欄等）。"),
        ("25", "IS_SOFTWARE", "詞庫屬性", "boolean", "是否屬於軟體/資訊科技工具（True / False）。")
    ]
    for row_idx, data in enumerate(t4_data, start=1):
        row = t4.rows[row_idx]
        bg = "F7FAFC" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx, text in enumerate(data):
            c = row.cells[col_idx]
            c.width = col_widths4[col_idx]
            set_cell_shading(c, bg)
            set_cell_margins(c, top=50, bottom=50, left=60, right=60)
            align = WD_ALIGN_PARAGRAPH.CENTER if col_idx in [0, 2, 3] else WD_ALIGN_PARAGRAPH.LEFT
            format_cell_text(c, text, bold=(col_idx == 1), size=7.8, align=align)

    doc.add_paragraph().paragraph_format.space_after = Pt(4)

    add_callout(
        "欄位注意事項：第 1、2 欄之 Category_Name / Subcategory_Name 屬詞庫 Lightcast 原始分類；第 20、21 欄之 Skill_group10 屬本計畫修訂之新版十大主分類，兩者並存不互相覆蓋。第 24 欄 MATCHED_FROM 僅記錄觸發來源欄位，非精確字符起訖位移之證據。",
        title="欄位說明", bg_color="FFF5F5", border_color="E53E3E"
    )

    # ----------------------------------------------------
    # 第五章：最新 0930 詞庫與 Chen 十大分類之雙軌整合機制
    # ----------------------------------------------------
    add_h1("五、最新 0930 詞庫與 Chen 十大分類之雙軌整合機制")
    add_p(
        "經實證核查，儲存庫最新之 `詞庫skill_lexicon_v13_20260930.xlsx` 包含 26,578 列（26,315 個不重複 Skill_ID），內部包含標準技能名稱與觸發關鍵字，但未包含新版十大分類欄位；而 `詞庫skill_lexicon_v13_Chen_grouped_09_2026.xlsx` 收錄了新版十大分類代碼與名稱。因此目前程式維持雙軌整合架構：以 0930 版作為比對引擎基底，並以 Chen 版作為十大分類 metadata 對照來源。"
    )

    add_h2("1. 0930 Skill_ID 在 Chen 分類詞庫中的 mapping coverage")
    add_p(
        "在 0930 詞庫的 26,315 個不重複 Skill_ID 中，共有 26,310 個可在 Chen_grouped_09 詞庫中找到對應記錄。\n"
        "**0930 Skill_ID 在 Chen 分類詞庫中的 mapping coverage 為 99.98%（26,310 / 26,315）**。\n"
        "0930 中存在、但 Chen 版缺少十大分類 metadata 的 Skill_ID 共 5 筆（0.02%）。"
    )

    add_h2("2. 5 筆未在 Chen 取得十大分類 metadata 之技能")
    add_p(
        "此 5 筆技能清單如下表所示："
    )

    t5 = doc.add_table(rows=6, cols=4)
    t5.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t5)
    apply_row_protection(t5.rows[0], is_header=True)
    for r in t5.rows[1:]:
        apply_row_protection(r)

    headers5 = ["Skill_ID", "0930 中文名稱 (Skill_Name_ZH)", "Lightcast Category / Subcategory", "目前程式處理方式"]
    col_widths5 = [Inches(1.3), Inches(1.8), Inches(2.2), Inches(1.6)]
    for i, h in enumerate(headers5):
        cell = t5.rows[0].cells[i]
        cell.width = col_widths5[i]
        set_cell_shading(cell, "1A365D")
        format_cell_text(cell, h, bold=True, color="FFFFFF", size=8.5, align=WD_ALIGN_PARAGRAPH.CENTER)

    t5_data = [
        ("TW_PERS_001", "中式整復推拿", "Personal Care / Beauty & Body Treatments", "技能仍保留；分類碼與名稱為空；狀態為未對應"),
        ("TW_TCM_002", "中醫特殊療法與科別", "Health Care / Alternative Therapy", "技能仍保留；分類碼與名稱為空；狀態為未對應"),
        ("TW_NUR_010", "病患移位與基礎照護技術", "Health Care / Nursing & Patient Care", "技能仍保留；分類碼與名稱為空；狀態為未對應"),
        ("TW_MED_002", "健保申報與門診行政", "Health Care / Health Care Administration", "技能仍保留；分類碼與名稱為空；狀態為未對應"),
        ("TW_SOC_002", "身心障礙職業重建服務", "Social Services / Government Assistance", "技能仍保留；分類碼與名稱為空；狀態為未對應")
    ]
    for row_idx, data in enumerate(t5_data, start=1):
        row = t5.rows[row_idx]
        bg = "F7FAFC" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx, text in enumerate(data):
            c = row.cells[col_idx]
            c.width = col_widths5[col_idx]
            set_cell_shading(c, bg)
            set_cell_margins(c, top=60, bottom=60, left=80, right=80)
            align = WD_ALIGN_PARAGRAPH.CENTER if col_idx in [0, 3] else WD_ALIGN_PARAGRAPH.LEFT
            format_cell_text(c, text, bold=(col_idx == 0), size=8.0, align=align)

    doc.add_paragraph().paragraph_format.space_after = Pt(4)

    add_p(
        "目前處理方式：0930 詞庫仍包含這 5 個 Skill_ID，但在目前 Chen_grouped_09 中未找到對應的十大分類 metadata。因此目前程式中該技能仍保留，Skill_group10_code 為空，Skill_group10 為空，Grouping_status 為未對應，列入會議討論。"
    )

    add_h2("3. 0918 存在但 0930 移除之 11 筆 Skill_ID 查核")
    add_p(
        "經比對 0918 與 0930，共有 11 筆 Skill_ID 僅存在於 0918，變更情形查核如下表："
    )

    t11 = doc.add_table(rows=12, cols=4)
    t11.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t11)
    apply_row_protection(t11.rows[0], is_header=True)
    for r in t11.rows[1:]:
        apply_row_protection(r)

    headers11 = ["0918 Skill_ID", "0918 技能中文名稱", "0930 同名技能 Skill_ID", "變更情形說明"]
    col_widths11 = [Inches(1.4), Inches(1.5), Inches(1.6), Inches(2.4)]
    for i, h in enumerate(headers11):
        cell = t11.rows[0].cells[i]
        cell.width = col_widths11[i]
        set_cell_shading(cell, "1A365D")
        format_cell_text(cell, h, bold=True, color="FFFFFF", size=8.5, align=WD_ALIGN_PARAGRAPH.CENTER)

    t11_data = [
        ("TW_ACCT_001", "會計作業", "ES5A48B64B63BC943CF3", "0918 原已存在該 ES 代碼；0930 移除自編碼並併入該 ES 代碼"),
        ("TW_BOM_001", "物料清單", "BGS10F94E4049444B523", "0918 原已存在該 BGS 代碼；0930 移除自編碼並併入該 BGS 代碼"),
        ("TW_ECN_001", "工程變更通知", "KS123JZ6QB97DN4WD42W", "0918 原已存在該 KS 代碼；0930 移除自編碼並併入該 KS 代碼"),
        ("TW_FB_001", "食材備料", "KS1241J6ZY2S66SZG3QS", "0918 原已存在該 KS 代碼（食物準備）；0930 將備料關鍵字併入"),
        ("TW_NUR_001", "護理評估", "KS1274W63QXZT52GW1RF", "0918 原已存在該 KS 代碼；0930 移除自編碼並併入該 KS 代碼"),
        ("TW_NUR_002", "傷口護理", "KS442546YGKQC49SH18W", "0918 原已存在該 KS 代碼；0930 移除自編碼並併入該 KS 代碼"),
        ("TW_PROC_CTRL_001", "製程控制", "KS1281Y6QHJ8PQLHTZ6R", "0918 原已存在該 KS 代碼；0930 移除自編碼並併入該 KS 代碼"),
        ("TW_RETAIL_002", "補貨上架", "KSD9RL4YOWYBKJ1EOKNB", "0918 原已存在該 KS 代碼；0930 移除自編碼並併入該 KS 代碼"),
        ("TW_RETAIL_004", "商品管理", "ESB35D9808E206D5D59A", "0918 原已存在該 ES 代碼；0930 移除自編碼並併入該 ES 代碼"),
        ("TW_SEC_002", "巡邏勤務", "（無同名；併入巡邏）", "0930 移除自編碼，巡邏勤務關鍵字併入既有之 KS127LW62SG0TTVKDYQJ"),
        ("TW_SUPPLY_001", "供應鏈管理", "KS440C365HRHPM9VQDFF", "0918 原已存在該 KS 代碼；0930 移除自編碼並併入該 KS 代碼")
    ]
    for row_idx, data in enumerate(t11_data, start=1):
        row = t11.rows[row_idx]
        bg = "F7FAFC" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx, text in enumerate(data):
            c = row.cells[col_idx]
            c.width = col_widths11[col_idx]
            set_cell_shading(c, bg)
            set_cell_margins(c, top=50, bottom=50, left=70, right=70)
            align = WD_ALIGN_PARAGRAPH.CENTER if col_idx in [0, 2] else WD_ALIGN_PARAGRAPH.LEFT
            format_cell_text(c, text, bold=(col_idx == 0), size=7.8, align=align)

    doc.add_paragraph().paragraph_format.space_after = Pt(4)

    add_p(
        "說明：0930 中部分原自編 Skill_ID 已改為其他 Skill_ID；其中目前抽查的兩個案例（如物料清單、製程控制）可在 Chen 詞庫取得十大分類 metadata。此變更對整體未對應技能數量的影響仍應以完整比對結果描述。"
    )

    add_h2("4. Category / Subcategory 一致性與 Keywords 增修說明")
    add_p(
        "• 分類階層一致性：在此次 26,315 筆共同 Skill_ID 比對中，未觀察到 Category_Name 或 Subcategory_Name 差異（不一致筆數為 0 筆）。\n"
        "• Keywords 增修情形：在 26,315 筆共同 Skill_ID 中，共有 30 筆技能進行了關鍵字增修（其餘 26,285 筆一致），不重複技能關鍵字 token 淨增 13 個（由 94,731 增至 94,744 個）。"
    )

    # ----------------------------------------------------
    # 第六章：新十大分類與 Word 規則的採用範圍
    # ----------------------------------------------------
    add_h1("六、新十大分類與 Word 規則的採用範圍")
    add_p(
        "Word 建議文件《10大技能分類與選擇規則_建議版_完成.docx》定義之 10 個標準主分類代碼與名稱如下表所示："
    )

    t6 = doc.add_table(rows=11, cols=3)
    t6.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t6)
    apply_row_protection(t6.rows[0], is_header=True)
    for r in t6.rows[1:]:
        apply_row_protection(r)

    headers6 = ["代碼", "十大技能主分類標準中文名稱", "核心範疇說明 (Scope & Boundary)"]
    col_widths6 = [Inches(0.6), Inches(2.5), Inches(3.8)]
    for i, h in enumerate(headers6):
        cell = t6.rows[0].cells[i]
        cell.width = col_widths6[i]
        set_cell_shading(cell, "1A365D")
        format_cell_text(cell, h, bold=True, color="FFFFFF", size=8.5, align=WD_ALIGN_PARAGRAPH.CENTER)

    t6_data = [
        ("1", "認知、分析與創新技能", "一般推理、問題解決、決策、研究、概念分析與非特定領域創新。"),
        ("2", "溝通、語言與人際技能", "溝通、外語、翻譯實務、協商、團隊合作、教學、諮商。"),
        ("3", "個人特質、自我管理與身體能力", "工作態度、適應力、主動性、細心度、耐力與肢體搬運。"),
        ("4", "財務、會計與經濟技能", "會計、審計、稅務、預算、銀行投資、財務風控。"),
        ("5", "管理、商業、法遵與治理技能", "組織領導、專案管理、人資、商業策略、合約管理與法規遵循。"),
        ("6", "行政與一般數位技能", "文書行政、排程、微軟 Office、電子郵件、行事曆與基礎數位素養。"),
        ("7", "營運、技職與第一線服務技能", "機台操作、設備維修、營造技工、物流倉儲、餐旅零售、第一線服務作業。"),
        ("8", "資訊科技、軟體、資料與AI技能", "程式開發、演算法、資料庫、雲端、資安、資料科學、AI/ML。"),
        ("9", "醫療、健康與照護技能", "醫學、護理、藥學、臨床診斷、復健治療、病患照護。"),
        ("10", "工程、自然科學、設計、環境與能源技能", "非資通訊之工程學、自然科學實驗、建築技術、材料、環保能源與技術設計。")
    ]
    for row_idx, data in enumerate(t6_data, start=1):
        row = t6.rows[row_idx]
        bg = "F7FAFC" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx, text in enumerate(data):
            c = row.cells[col_idx]
            c.width = col_widths6[col_idx]
            set_cell_shading(c, bg)
            set_cell_margins(c, top=50, bottom=50, left=70, right=70)
            align = WD_ALIGN_PARAGRAPH.CENTER if col_idx == 0 else WD_ALIGN_PARAGRAPH.LEFT
            format_cell_text(c, text, bold=(col_idx == 0), size=8.0, align=align)

    doc.add_paragraph().paragraph_format.space_after = Pt(4)

    add_h2("規則採用範圍與目前限制")
    add_p(
        "• 目前實作範圍：單檔腳本係採用 Chen_grouped_09 詞庫之既有標註作為元資料來源，於比對命中後以 Skill_ID 填入對應之 Skill_group10；同時保留既有針對特定籠統字之就近文意與職稱輔助消歧。\n"
        "• 尚未實作部分：Word 文件第 10 節規範之動態消歧體系（JM1~JM6），要求依據職務大中類與局部句型動態判定技能群組。目前單檔程式尚未實作此套動態消歧系統，列入後續階段評估。\n"
        "• 已知限制：在 match_skills() 內部，既有之 seen_zh_terms 集合會在字串掃描過程中略過重複出現之同名中文詞彙，可能提前截斷同名候選技能。"
    )

    # ----------------------------------------------------
    # 第七章：驗證結果與研究影響
    # ----------------------------------------------------
    add_h1("七、驗證結果與研究影響")
    add_p(
        "為確認更換 0930 詞庫後的程式輸出差異，本次以 demo_彰化縣_202608_500.xlsx 進行比較。\n"
        "0918 與 0930 分別產生 3,953 與 3,954 筆技能列，兩者皆有 496 筆職缺至少命中一項技能。\n"
        "0930 相較 0918 新增 1 筆技能命中；該新增結果是否屬於正確擷取，仍需人工核對。\n"
        "共同命中對（ID, SKILL_ID）共 3,925 組，差異主要源於前述自編代碼轉換為既有代碼（例如原本命中 TW_BOM_001 改為命中 BGS10F94E4049444B523）。"
    )

    # 驗證表格
    t7 = doc.add_table(rows=9, cols=5)
    t7.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t7)
    apply_row_protection(t7.rows[0], is_header=True)
    for r in t7.rows[1:]:
        apply_row_protection(r)

    headers7 = ["測試項目", "預期結果", "實際測試結果", "測試記錄", "狀態"]
    col_widths7 = [Inches(1.4), Inches(1.5), Inches(1.5), Inches(1.8), Inches(0.7)]
    for i, h in enumerate(headers7):
        cell = t7.rows[0].cells[i]
        cell.width = col_widths7[i]
        set_cell_shading(cell, "1A365D")
        format_cell_text(cell, h, bold=True, color="FFFFFF", size=8.5, align=WD_ALIGN_PARAGRAPH.CENTER)

    t7_data = [
        ("1. 多技能拆列粒度", "1 職缺命中 3 技能輸出 3 列。", "實際產出 3 列，無合併儲存格。", "測試職缺命中福利/諮詢/按摩，輸出列數=3。", "PASS"),
        ("2. 原始 9 欄一致性", "展開後 3 列原始 9 欄與來源一致。", "比對未發現文字截斷或欄位變更。", "測試職缺不一致=0；Demo 抽樣 50 筆不一致=0。", "PASS"),
        ("3. 重複 ID 隔離測試", "來源重複 ID 不造成列數膨脹。", "輸入 2 筆相同 ID，輸出 3 列。", "各職缺技能各自對應，交叉配對數=0。", "PASS"),
        ("4. 雙格式一致性", "Excel 與 Parquet 欄位與數值一致。", "25 欄名稱順序相同，數值對齊。", "3,956 列對齊，差異儲存格數=0。", "PASS"),
        ("5. 欄位衝突檢測", "主要與替代欄位不一致時發出 Warning。", "偵測並記錄 4 處預設衝突。", "日誌打印衝突筆數與欄位名稱。", "PASS"),
        ("6. 缺失 ID 報錯防護", "缺失 ID 報錯；缺失非識別欄位補空。", "拋出 ValueError；補空正常。", "驗證無編造 ID；補空欄位符合 25 欄。", "PASS"),
        ("7. 全檔零命中保護", "若整檔職缺均無技能，產出 25 欄空表。", "產出 0 列、25 欄位空 DataFrame。", "維持下游 schema 結構一致性。", "PASS"),
        ("8. 修改前後比對等價", "字串擷取集合與原單檔邏輯一致。", "在相同 0930 詞庫下命中結果一致。", "Demo 測試集差異集合為 0。", "PASS")
    ]
    for row_idx, data in enumerate(t7_data, start=1):
        row = t7.rows[row_idx]
        bg = "F7FAFC" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx, text in enumerate(data):
            c = row.cells[col_idx]
            c.width = col_widths7[col_idx]
            set_cell_shading(c, bg)
            set_cell_margins(c, top=50, bottom=50, left=60, right=60)
            align = WD_ALIGN_PARAGRAPH.CENTER if col_idx in [0, 4] else WD_ALIGN_PARAGRAPH.LEFT
            format_cell_text(c, text, bold=(col_idx in [0, 4]), size=7.8, align=align)

    doc.add_paragraph().paragraph_format.space_after = Pt(4)

    add_h2("研究統計注意事項")
    add_p(
        "1. 列數不等於職缺數：Long 表每一列代表一個技能命中記錄，非一筆職缺，不可直接以列數推估職缺總數。\n"
        "2. 技能占比加總：單一職缺可能同時命中多個分類之技能，各十大分類的職缺占比加總可能超過 100%。\n"
        "3. 覆蓋率計算母體：主要 Long 表僅收錄有命中技能之職缺（本次 500 筆中命中 496 筆，未命中 4 筆）。計算整體市場技能覆蓋率時需回溯完整職缺母體。\n"
        "4. 未命中職缺 vs 未對應技能：整篇 JD 無技能之職缺未列於主要 Long 表；有命中技能但缺少十大分類 metadata 之技能則仍產出該列，分類欄位留空並標註「未對應」。"
    )

    # ----------------------------------------------------
    # 第八章：會議待決事項 (4 欄決策表)
    # ----------------------------------------------------
    add_h1("八、會議待決事項（決策表）")
    add_p(
        "以下整理 8 項待討論議題，決議欄均保持空白待填："
    )

    t8 = doc.add_table(rows=9, cols=4)
    t8.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t8)
    apply_row_protection(t8.rows[0], is_header=True)
    for r in t8.rows[1:]:
        apply_row_protection(r)

    headers8 = ["議題編號與名稱", "目前技術提案 / 實作現況", "研究與統計影響", "會議決議 (留空待填)"]
    col_widths8 = [Inches(1.5), Inches(2.2), Inches(2.1), Inches(1.1)]
    for i, h in enumerate(headers8):
        cell = t8.rows[0].cells[i]
        cell.width = col_widths8[i]
        set_cell_shading(cell, "1A365D")
        format_cell_text(cell, h, bold=True, color="FFFFFF", size=8.5, align=WD_ALIGN_PARAGRAPH.CENTER)

    t8_data = [
        ("D1. Long 格式與欄位順序", "固定 25 欄位，Category 居首，保留 9 大原始職缺欄位。", "統一分析資料規格，提升人工檢查便利度。", "【待討論】"),
        ("D2. 詞庫整合來源方案", "以 0930 為基底進行比對，結合 Chen 版進行十大分類映射。", "採用最新關鍵字，同時獲取十大分類 metadata。", "【待討論】"),
        ("D3. 零命中職缺處置", "主要 Long 表僅存有命中列；零命中職缺不產出無效假列。", "若計量需分析無技能職缺，需另行產出未命中清單。", "【待討論】"),
        ("D4. 缺少分類技能之補齊", "未收錄於 Chen 版的 5 筆本土化技能（推拿、中醫等）目前標註「未對應」。", "避免機器揣測分類失真；待人工專家審查歸類。", "【待討論】"),
        ("D5. 詞庫整合單檔方針", "目前採雙軌讀取，未來可評估由團隊產出單一整合詞庫。", "簡化讀取流程，降低檔案維護成本。", "【待討論】"),
        ("D6. Wide 寬表保留需求", "預設不輸出 Wide，提供 --wide 參數供研究員自由啟用。", "節省伺服器 I/O 與儲存空間，保留向下相容性。", "【待討論】"),
        ("D7. Word 第10節消歧實作", "目前單檔程式暫不實作動態上下文消歧，列入第二階段評估。", "若提前引入複雜規則可能降低單檔執行吞吐量。", "【待討論】"),
        ("D8. 重複 ID 之母體計算定義", "目前以「單列職缺」去重；重複 ID 職缺各自獨立產出技能列。", "影響研究推估全國職缺總數時的母體去重口徑。", "【待討論】")
    ]
    for row_idx, data in enumerate(t8_data, start=1):
        row = t8.rows[row_idx]
        bg = "F7FAFC" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx, text in enumerate(data):
            c = row.cells[col_idx]
            c.width = col_widths8[col_idx]
            set_cell_shading(c, bg)
            set_cell_margins(c, top=60, bottom=60, left=70, right=70)
            align = WD_ALIGN_PARAGRAPH.CENTER if col_idx in [0, 3] else WD_ALIGN_PARAGRAPH.LEFT
            format_cell_text(c, text, bold=(col_idx in [0, 3]), size=7.8, align=align)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # 尾頁結語
    p_end = doc.add_paragraph()
    p_end.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r_end = p_end.add_run("文件更新日期：2026 年 10 月 03 日 ｜ 104 技能擷取研究團隊")
    r_end.font.size = Pt(9)
    r_end.font.color.rgb = RGBColor(120, 120, 120)
    rPr_e = r_end._r.get_or_add_rPr()
    rPr_e.append(parse_xml(f'<w:rFonts {nsdecls("w")} w:eastAsia="Microsoft JhengHei" w:ascii="Microsoft JhengHei" w:hAnsi="Microsoft JhengHei"/>'))

    # 儲存檔案
    doc.save(output_path)
    print(f"成功產出全新 Word 審查文件：{output_path}")

if __name__ == "__main__":
    build_review_docx()
