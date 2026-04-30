#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
storage.py — 临时文件管理模块
从 gensjt.py 提取，负责中间结果的保存、加载和清理。
"""

import json
import os

from lib import SKILL_DIR, DECODED_DIR

TEMP_FILE = os.path.join(SKILL_DIR, "temp_items.json")


def _warn_invalid_dimensions(items: list):
    """检查题目中的维度是否都在胜任特征辞典中，无效维度发出警告。"""
    if not items:
        return

    dict_json_path = os.path.join(DECODED_DIR, "competence_dictionary.json")
    if not os.path.exists(dict_json_path):
        return

    try:
        with open(dict_json_path, "r", encoding="utf-8") as f:
            dict_data = json.load(f)
        valid_dims = {d["name"] for d in dict_data.get("dimensions", [])}
    except Exception:
        return

    item_dims = {it.get("dimension") for it in items if it.get("dimension")}
    invalid = item_dims - valid_dims
    if invalid:
        print(f"⚠️ 警告：以下维度不在胜任特征辞典中，不应生成题目：{', '.join(invalid)}")


def save_partial(data: dict):
    """保存中间结果到JSON文件（追加模式）。

    如果已有 temp_items.json 中的 industry/position 与本次不同，
    视为跨任务操作，清空旧数据后写入，防止题目混入。

    同时检查是否有维度不在胜任特征辞典中，若有则发出警告。
    """
    # ── 维度有效性校验 ──
    _warn_invalid_dimensions(data.get("items", []))

    existing = []
    existing_industry = None
    existing_position = None

    if os.path.exists(TEMP_FILE):
        with open(TEMP_FILE, "r", encoding="utf-8") as f:
            old_data = json.load(f)
        existing = old_data.get("items", [])
        existing_industry = old_data.get("industry")
        existing_position = old_data.get("position")

    new_industry = data.get("industry")
    new_position = data.get("position")

    # 跨任务保护：如果行业或岗位不同，清空旧数据
    if existing and (existing_industry != new_industry or existing_position != new_position):
        print(f"警告：检测到跨任务数据（已有 {existing_industry}/{existing_position}，"
              f"本次 {new_industry}/{new_position}），已清空旧数据")
        existing = []

    existing.extend(data.get("items", []))
    data["items"] = existing
    with open(TEMP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_partial() -> dict:
    """读取已生成的中间结果"""
    if os.path.exists(TEMP_FILE):
        with open(TEMP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def clear_partial():
    """清理临时文件"""
    if os.path.exists(TEMP_FILE):
        os.remove(TEMP_FILE)
    temp_zip = os.path.join(DECODED_DIR, "references_decoded.zip")
    if os.path.exists(temp_zip):
        os.remove(temp_zip)
