#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
knowledge.py — 知识库检索模块
从 gensjt.py 提取，负责知识库的按维度检索和引用匹配。
"""

import json
import os

from lib import DECODED_DIR


def _load_knowledge_references(dim_names: list) -> dict:
    """
    从知识库文件中按维度自动匹配引用信息，返回：
    {dim_name: {
        "dict_found": bool,
        "dict_summary": str,
        "template_ids": [str],
        "competence_found": bool,
        "competence_count": int,
        "competence_summary": str,
        "examples_found": bool,
        "examples_count": int,
        "examples_summary": str,
    }}
    """
    result = {}

    # --- 1. 胜任特征辞典（JSON格式） ---
    dict_json_path = os.path.join(DECODED_DIR, "competence_dictionary.json")
    dict_dimensions = {}
    if os.path.exists(dict_json_path):
        with open(dict_json_path, "r", encoding="utf-8") as f:
            dict_data = json.load(f)
        for dim in dict_data.get("dimensions", []):
            dict_dimensions[dim["name"]] = dim

    # --- 2. 母题模板 extracted_templates.json ---
    templates_path = os.path.join(DECODED_DIR, "extracted_templates.json")
    templates_data = []
    if os.path.exists(templates_path):
        with open(templates_path, "r", encoding="utf-8") as f:
            templates_data = json.load(f)

    # --- 3. competence_SJT.json ---
    competence_path = os.path.join(DECODED_DIR, "competence_SJT.json")
    competence_data = []
    if os.path.exists(competence_path):
        with open(competence_path, "r", encoding="utf-8") as f:
            competence_data = json.load(f)

    # --- 4. 例题库（JSON格式） ---
    examples_json_path = os.path.join(DECODED_DIR, "example_questions.json")
    examples_groups = {}
    if os.path.exists(examples_json_path):
        with open(examples_json_path, "r", encoding="utf-8") as f:
            ex_data = json.load(f)
        for group in ex_data.get("groups", []):
            dim = group["dimension"]
            if dim not in examples_groups:
                examples_groups[dim] = []
            examples_groups[dim].extend(group.get("questions", []))

    for dim_name in dim_names:
        info = {
            "dict_found": False, "dict_summary": "",
            "template_ids": [],
            "competence_found": False, "competence_count": 0, "competence_summary": "",
            "examples_found": False, "examples_count": 0, "examples_summary": "",
        }

        # 1) 胜任特征辞典匹配
        dim_dict = dict_dimensions.get(dim_name)
        if dim_dict:
            info["dict_found"] = True
            parts = []
            if dim_dict.get("definition"):
                parts.append("引用维度定义")
            if dim_dict.get("high_score_features"):
                parts.append("高分行为特征")
            if dim_dict.get("low_score_features"):
                parts.append("低分行为特征")
            info["dict_summary"] = (
                f"胜任特征辞典中包含'{dim_name}'维度的" + "、".join(parts)
                if parts else f"胜任特征辞典中存在'{dim_name}'维度条目"
            )

        # 2) 母题模板匹配
        dim_templates = [t for t in templates_data if t.get("dimension") == dim_name]
        if dim_templates:
            info["template_ids"] = [t.get("template_id", "") for t in dim_templates]

        # 3) competence_SJT.json 匹配
        dim_competence = [c for c in competence_data if c.get("dimension") == dim_name]
        if dim_competence:
            info["competence_found"] = True
            info["competence_count"] = len(dim_competence)
            scenarios = []
            for c in dim_competence[:3]:
                scenario = c.get("abstract_scenario", "")
                if scenario:
                    scenarios.append(scenario[:50] + ("..." if len(scenario) > 50 else ""))
            if scenarios:
                info["competence_summary"] = f"共{len(dim_competence)}条情境模式，如：" + "；".join(scenarios)
            else:
                info["competence_summary"] = f"共{len(dim_competence)}条情境模式"

        # 4) 例题库匹配
        dim_questions = examples_groups.get(dim_name, [])
        if dim_questions:
            info["examples_found"] = True
            info["examples_count"] = len(dim_questions)
            info["examples_summary"] = f"例题库中该维度共{len(dim_questions)}道参考题，用于参考情境结构和选项表达风格"

        result[dim_name] = info

    return result


def _load_dimension_defs(dim_names: list) -> dict:
    """
    从胜任特征辞典 JSON 中解析指定维度的完整定义信息。
    返回 {dim_name: {"定义":..., "高分表现":..., "低分表现":...,
                      "关键行为指标": [...5个], "优秀":..., "良好":..., ...}}
    """
    dict_json_path = os.path.join(DECODED_DIR, "competence_dictionary.json")
    if not os.path.exists(dict_json_path):
        return {}

    with open(dict_json_path, "r", encoding="utf-8") as f:
        dict_data = json.load(f)

    dim_index = {}
    for dim in dict_data.get("dimensions", []):
        dim_index[dim["name"]] = dim

    result = {}

    for dim_name in dim_names:
        dim = dim_index.get(dim_name)
        if not dim:
            result[dim_name] = {
                "定义": "", "高分表现": "", "低分表现": "",
                "关键行为指标": ["", "", "", "", ""],
                "优秀": "", "良好": "", "中等": "", "欠佳": "", "不足": ""
            }
            continue

        a_text = dim.get("behavior_levels", {}).get("优秀", "")
        kbi = []
        if a_text:
            segments = [s.strip() for s in a_text.split("；") if s.strip()]
            if len(segments) >= 5:
                kbi = segments[:5]
            else:
                kbi = segments[:]
                b_text = dim.get("behavior_levels", {}).get("良好", "")
                if b_text:
                    b_segments = [s.strip() for s in b_text.split("；") if s.strip()]
                    for seg in b_segments:
                        if len(kbi) >= 5:
                            break
                        if seg not in kbi:
                            kbi.append(seg)
        while len(kbi) < 5:
            kbi.append("")

        levels = dim.get("behavior_levels", {})
        result[dim_name] = {
            "定义": dim.get("definition", ""),
            "高分表现": dim.get("high_score_features", ""),
            "低分表现": dim.get("low_score_features", ""),
            "关键行为指标": kbi,
            "优秀": levels.get("优秀", ""),
            "良好": levels.get("良好", ""),
            "中等": levels.get("中等", ""),
            "欠佳": levels.get("欠佳", ""),
            "不足": levels.get("不足", ""),
        }

    return result


def query_refs(dim_names: list) -> dict:
    """
    按维度精准检索所有知识库，返回结构化的参考资料摘要。
    供 AI 命题前定向加载，避免全量读取。

    返回：
    {
      "dimensions": {dim_name: {"definition": ..., "high_score": ..., ...}},
      "templates": [{template_id, dimension, item_skeleton, ...}, ...],
      "competence_sjt": [{dimension, abstract_scenario, ...}, ...],
      "examples": [{id, dimension, scenario, ...}, ...],
      "parameter_guide": "...",
      "skipped_dimensions": [...]
    }
    """
    result = {
        "dimensions": {}, "templates": [], "competence_sjt": [],
        "examples": [], "parameter_guide": "", "skipped_dimensions": []
    }
    found_dims = set()

    # 1. 胜任特征辞典
    dict_json_path = os.path.join(DECODED_DIR, "competence_dictionary.json")
    if os.path.exists(dict_json_path):
        with open(dict_json_path, "r", encoding="utf-8") as f:
            dict_data = json.load(f)
        dim_index = {d["name"]: d for d in dict_data.get("dimensions", [])}
        for dim_name in dim_names:
            dim = dim_index.get(dim_name)
            if dim:
                result["dimensions"][dim_name] = {
                    "code": dim.get("code", ""),
                    "category": dim.get("category", ""),
                    "definition": dim.get("definition", ""),
                    "high_score_features": dim.get("high_score_features", ""),
                    "low_score_features": dim.get("low_score_features", ""),
                    "behavior_levels": dim.get("behavior_levels", {}),
                }
                found_dims.add(dim_name)

    for dim_name in dim_names:
        if dim_name not in found_dims:
            result["skipped_dimensions"].append(dim_name)

    # 2. 母题模板
    templates_path = os.path.join(DECODED_DIR, "extracted_templates.json")
    if os.path.exists(templates_path):
        with open(templates_path, "r", encoding="utf-8") as f:
            all_templates = json.load(f)
        for t in all_templates:
            if t.get("dimension") in dim_names:
                result["templates"].append(t)

    # 3. competence_SJT.json
    csjt_path = os.path.join(DECODED_DIR, "competence_SJT.json")
    if os.path.exists(csjt_path):
        with open(csjt_path, "r", encoding="utf-8") as f:
            all_csjt = json.load(f)
        for c in all_csjt:
            if c.get("dimension") in dim_names:
                result["competence_sjt"].append(c)

    # 4. 例题库（每维度最多返回5道）
    ex_path = os.path.join(DECODED_DIR, "example_questions.json")
    if os.path.exists(ex_path):
        with open(ex_path, "r", encoding="utf-8") as f:
            ex_data = json.load(f)
        for group in ex_data.get("groups", []):
            if group["dimension"] in dim_names:
                result["examples"].extend(group.get("questions", [])[:5])

    # 5. 参数估算指南（全文，内容不长）
    param_path = os.path.join(DECODED_DIR, "SJT_parameter_estimation.md")
    if os.path.exists(param_path):
        with open(param_path, "r", encoding="utf-8") as f:
            result["parameter_guide"] = f.read()

    return result
