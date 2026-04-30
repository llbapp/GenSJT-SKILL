#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
char_match.py — 字符级模糊匹配模块
从 gensjt.py 提取，用于行业岗位知识库的字符匹配检索。
"""

import json
import os


def fuzzy_score(query: str, target: str) -> float:
    """
    计算两个字符串的模糊相似度（0-1）。
    使用字符级 SequenceMatcher，并额外处理 '/' 分隔的别名模式和中文复合词重叠。
    """
    from difflib import SequenceMatcher

    # 基础相似度
    base = SequenceMatcher(None, query, target).ratio()

    # 如果 target 包含 '/'（如 "IT/互联网/通信"），逐段匹配取最高分
    if '/' in target:
        segments = [s.strip() for s in target.split('/') if s.strip()]
        seg_scores = []
        for seg in segments:
            seg_scores.append(SequenceMatcher(None, query, seg).ratio())
            # 也检查 query 的子串是否包含在 segment 中
            if query in seg or seg in query:
                seg_scores.append(0.95)
        if seg_scores:
            base = max(base, max(seg_scores))

    # 同样处理 query 中的 '/' 或常见分隔符
    for sep in ['/', '、', '，', ',']:
        if sep in query:
            parts = [p.strip() for p in query.split(sep) if p.strip()]
            part_scores = []
            for part in parts:
                part_scores.append(SequenceMatcher(None, part, target).ratio())
                if '/' in target:
                    for seg in [s.strip() for s in target.split('/') if s.strip()]:
                        if part in seg or seg in part:
                            part_scores.append(0.95)
            if part_scores:
                base = max(base, max(part_scores) * 0.9)

    # 中文复合词重叠度补充评分
    if '/' in target:
        segments = [s.strip() for s in target.split('/') if s.strip()]
        q_chars = list(query)
        for length in range(2, min(len(query) + 1, 5)):
            for i in range(len(q_chars) - length + 1):
                ngram = "".join(q_chars[i:i + length])
                for seg in segments:
                    if ngram in seg or seg in ngram:
                        overlap_score = 0.3 + 0.15 * (length - 2)
                        base = max(base, overlap_score)
    elif len(query) >= 2 and len(target) >= 2:
        for length in range(2, min(len(query), len(target)) + 1):
            found = False
            for i in range(len(query) - length + 1):
                ngram = query[i:i + length]
                if ngram in target:
                    overlap_score = 0.3 + 0.15 * (length - 2)
                    base = max(base, overlap_score)
                    found = True
                    break
            if found:
                break

    return base


def search_context_char(industry_query: str, position_query: str,
                        db: list, top_n: int = 3) -> dict:
    """
    纯字符匹配检索行业岗位。

    参数:
        industry_query: 用户输入的行业描述
        position_query: 用户输入的岗位描述
        db: 行业岗位数据库列表
        top_n: 返回前 N 条匹配结果

    返回:
        {
            "industry_match": [{"name": ..., "score": ...}, ...],
            "position_match": [{"name": ..., "score": ...}, ...],
            "results": [{完整记录 + _meta}, ...],
            "query": {"industry": ..., "position": ...}
        }
    """
    # 1. 收集所有唯一行业名
    all_industries = sorted(set(item.get("industry", "") for item in db))
    # 2. 收集所有唯一岗位（category + archetype 合并）
    all_positions = set()
    for item in db:
        all_positions.add(item.get("position_category", ""))
        all_positions.add(item.get("position_archetype", ""))
    all_positions = sorted(all_positions)

    # 3. 行业模糊匹配
    ind_scores = [(name, fuzzy_score(industry_query, name)) for name in all_industries]
    ind_scores.sort(key=lambda x: x[1], reverse=True)
    industry_match = [{"name": n, "score": round(s, 3)} for n, s in ind_scores[:top_n] if s > 0.25]

    # 4. 岗位模糊匹配
    pos_scores = [(name, fuzzy_score(position_query, name)) for name in all_positions]
    pos_scores.sort(key=lambda x: x[1], reverse=True)
    position_match = [{"name": n, "score": round(s, 3)} for n, s in pos_scores[:top_n] if s > 0.25]

    # 5. 综合匹配
    scored_records = []
    for item in db:
        ind_name = item.get("industry", "")
        cat_name = item.get("position_category", "")
        arch_name = item.get("position_archetype", "")

        ind_score = fuzzy_score(industry_query, ind_name)

        cat_score = fuzzy_score(position_query, cat_name)
        arch_score = fuzzy_score(position_query, arch_name)
        pos_score = max(cat_score, arch_score)

        combined = ind_score * 0.4 + pos_score * 0.6

        if combined > 0.25:
            scored_records.append({
                "record": item,
                "match_score": round(combined, 3),
                "industry_score": round(ind_score, 3),
                "position_score": round(pos_score, 3),
                "matched_position_field": "archetype" if arch_score >= cat_score else "category"
            })

    scored_records.sort(key=lambda x: x["match_score"], reverse=True)
    results = scored_records[:top_n]

    output_results = []
    for r in results:
        entry = dict(r["record"])
        entry["_meta"] = {
            "match_score": r["match_score"],
            "industry_score": r["industry_score"],
            "position_score": r["position_score"],
            "matched_position_field": r["matched_position_field"],
            "backend": "char",
        }
        output_results.append(entry)

    return {
        "industry_match": industry_match,
        "position_match": position_match,
        "results": output_results,
        "query": {"industry": industry_query, "position": position_query}
    }
