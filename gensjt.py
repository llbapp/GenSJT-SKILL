#!/usr/bin/env python3
"""
GenSJT - 情境判断测验编制
生成三份文档：纯净题目卷、完整答案卷、Excel汇总表

主文件：CLI 入口 + 流程编排
功能实现已拆分到 lib/ 子模块：
  lib/crypto.py         — 密码验证与 GPG 解密
  lib/doc_generator.py  — Word 文档生成（题目卷+答案卷）
  lib/excel_generator.py— Excel 汇总表生成
  lib/knowledge.py      — 知识库检索与引用匹配
  lib/storage.py        — 临时文件管理
  lib/char_match.py     — 字符模糊匹配
  lib/embed_search.py   — Embedding 语义匹配
"""

import datetime
import json
import os
import sys

# ============ 配置 ============
SKILL_DIR = os.path.expanduser("~/.workbuddy/skills/GenSJT.skill")
DECODED_DIR = os.path.join(SKILL_DIR, "references_decoded")

# ============ 子模块路径 ============
LIB_DIR = os.path.join(SKILL_DIR, "lib")
if os.path.isdir(LIB_DIR):
    sys.path.insert(0, LIB_DIR)

OUTPUT_DIR = os.getcwd()


# ============ 双路检索入口 ============
def search_context(industry_query: str, position_query: str, top_n: int = 3) -> dict:
    """
    双路检索：字符匹配 + Embedding 语义匹配，自动选择最优结果。

    策略：字符匹配 top1 综合分 > 0.7 且 >= embedding → 字符（精确匹配场景），
          否则 → embedding（语义理解更强）。
          Embedding 不可用时自动回退纯字符匹配。

    返回格式与原版完全兼容，_meta 中增加 "backend" 字段标记来源。
    """
    db_path = os.path.join(DECODED_DIR, "industry_job_context_db.json")
    if not os.path.exists(db_path):
        return {
            "industry_match": [],
            "position_match": [],
            "results": [],
            "query": {"industry": industry_query, "position": position_query},
            "error": f"行业岗位知识库不存在: {db_path}"
        }

    with open(db_path, "r", encoding="utf-8") as f:
        db = json.load(f)

    # ── 路径1：字符匹配（始终可用） ──
    from char_match import search_context_char
    char_result = search_context_char(industry_query, position_query, db, top_n)

    # ── 路径2：Embedding 语义匹配（可选） ──
    emb_result = None
    try:
        from embed_search import search_context_embedding
        emb_result = search_context_embedding(industry_query, position_query, top_n)
    except Exception:
        pass

    # ── 选优策略 ──
    if emb_result and emb_result.get("_embedding_available") and char_result.get("results"):
        char_score = char_result["results"][0].get("_meta", {}).get("match_score", 0)
        emb_score = emb_result["results"][0].get("_meta", {}).get("match_score", 0)

        if char_score > 0.7 and char_score >= emb_score:
            return char_result
        else:
            return emb_result
    else:
        return char_result


# ============ 文档生成总控 ============
def generate_docs_from_temp(industry: str, position: str, output_dir: str = None):
    """
    从 temp_items.json 读取已生成的题目，生成三份文档。
    output_dir 默认为调用时的当前工作目录（os.getcwd()）。
    """
    from storage import load_partial
    from knowledge import _load_dimension_defs, _load_knowledge_references
    from doc_generator import create_test_doc, create_answer_doc, _normalize_items
    from excel_generator import create_excel_summary

    data = load_partial()
    if not data or not data.get("items"):
        print("错误：未找到已生成的题目数据（temp_items.json）")
        return

    items = data["items"]

    # 收集本批次涉及的所有维度名
    dim_names = []
    for it in items:
        dim = it.get("dimension")
        if dim and dim not in dim_names:
            dim_names.append(dim)

    dimension_defs = _load_dimension_defs(dim_names)
    knowledge_refs = _load_knowledge_references(dim_names)
    normalized = _normalize_items(items)
    out_dir = output_dir or os.getcwd()

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    test_path = os.path.join(out_dir, f"测验卷_{industry}_{position}_{ts}.docx")
    answer_path = os.path.join(out_dir, f"答案卷_{industry}_{position}_{ts}.docx")
    excel_path = os.path.join(out_dir, f"汇总表_{industry}_{position}_{ts}.xlsx")

    create_test_doc(normalized, industry, position, test_path)
    create_answer_doc(normalized, industry, position, answer_path)
    create_excel_summary(items, dimension_defs, industry, position, excel_path,
                         knowledge_refs=knowledge_refs, search_context_fn=search_context)

    print(f"文档已生成：")
    print(f"  纯净题目卷：{test_path}")
    print(f"  完整答案卷：{answer_path}")
    print(f"  Excel汇总表：{excel_path}")


# ============ 主函数 ============
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python gensjt.py <密码> [命令] [选项]")
        print("  verify                     - 仅验证密码")
        print("  query --dimensions D1,D2 [--industry 行业] [--position 岗位]")
        print("                              按维度检索知识库 + 可选行业岗位模糊搜索")
        print("  gen_docs [--output-dir <路径>] - 从 temp_items.json 生成三份文档")
        sys.exit(1)

    password = sys.argv[1]
    from crypto import verify_password, decrypt_references
    if not verify_password(password):
        print("密码错误")
        sys.exit(1)

    # verify 命令：仅验证密码，不执行任何其他操作
    if len(sys.argv) >= 3 and sys.argv[2] == "verify":
        print("密码验证通过")
        sys.exit(0)

    decrypt_references(password)
    if "query" not in (sys.argv[2:] if len(sys.argv) > 2 else []):
        print("参考资料解密成功")

    if len(sys.argv) >= 3 and sys.argv[2] == "query":
        from knowledge import query_refs

        if "--dimensions" not in sys.argv:
            print("错误：query 命令需要 --dimensions 参数，如 --dimensions 创新思维,压力应对")
            sys.exit(1)
        idx = sys.argv.index("--dimensions")
        if idx + 1 >= len(sys.argv):
            print("错误：--dimensions 后需指定维度名称，用逗号分隔")
            sys.exit(1)
        dim_str = sys.argv[idx + 1]
        dim_names = [d.strip() for d in dim_str.split(",") if d.strip()]
        if not dim_names:
            print("错误：维度列表为空")
            sys.exit(1)
        result = query_refs(dim_names)

        # 可选：行业岗位模糊搜索
        industry_query = None
        position_query = None
        if "--industry" in sys.argv:
            iidx = sys.argv.index("--industry")
            if iidx + 1 < len(sys.argv):
                industry_query = sys.argv[iidx + 1]
        if "--position" in sys.argv:
            pidx = sys.argv.index("--position")
            if pidx + 1 < len(sys.argv):
                position_query = sys.argv[pidx + 1]

        if industry_query or position_query:
            ctx = search_context(
                industry_query or "",
                position_query or "",
                top_n=3
            )
            result["job_context"] = ctx

        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif len(sys.argv) >= 3 and sys.argv[2] == "gen_docs":
        from storage import load_partial, clear_partial

        output_dir = None
        if "--output-dir" in sys.argv:
            idx = sys.argv.index("--output-dir")
            if idx + 1 < len(sys.argv):
                output_dir = sys.argv[idx + 1]

        data = load_partial()
        if data:
            items = data.get("items", [])
            industry = data.get("industry", "")
            position = data.get("position", "")

            if not industry or not position:
                print("错误：temp_items.json 缺少 industry 或 position 字段，请检查数据格式")
                sys.exit(1)

            print(f"已加载 {len(items)} 道题目（行业：{industry}，岗位：{position}）")

            expected_dims = set(it.get("dimension") for it in items if it.get("dimension"))
            print(f"涉及维度：{', '.join(expected_dims)}")

            generate_docs_from_temp(
                industry=industry,
                position=position,
                output_dir=output_dir
            )

            clear_partial()
            print("临时文件已清理")
        else:
            print("错误：temp_items.json 为空或不存在")
