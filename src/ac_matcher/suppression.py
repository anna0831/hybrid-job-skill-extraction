"""最長匹配優先抑制模組：解決子字串被長字串包含時的冗餘匹配衝突。"""

from typing import List, Set, Tuple, Dict, Any


def suppress_shorter_matches(
    candidates: List[Dict[str, Any]], scan_text: str
) -> Tuple[List[Dict[str, Any]], Set[str]]:
    """最長匹配優先抑制。
    
    若某段文字同時被短詞與完全涵蓋它的長詞命中，且兩者對應不同技能 ID，
    則捨棄短詞、保留長詞。
    
    回傳：
        kept: 保留下來的候選技能列表
        suppressed_texts: 被抑制掉的字面文字集合 (供後續跨掃描共用)
    """
    kept: List[Dict[str, Any]] = []
    suppressed_texts: Set[str] = set()

    for i, a in enumerate(candidates):
        covered = False
        for j, b in enumerate(candidates):
            if i == j or a["skill"]["SKILL_ID"] == b["skill"]["SKILL_ID"]:
                continue
            if b["term_len"] <= a["term_len"]:
                continue
            if b["start"] <= a["start"] and b["end"] >= a["end"]:
                covered = True
                break
        if covered:
            suppressed_texts.add(scan_text[a["start"] : a["end"] + 1])
        else:
            kept.append(a)

    return kept, suppressed_texts
