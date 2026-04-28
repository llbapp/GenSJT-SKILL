#!/usr/bin/env python3
"""
GenSJT - 情境判断测验编制
生成三份文档：纯净题目卷、完整答案卷、Excel汇总表
"""

import docx
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
import random, sys, os, zipfile, subprocess, hashlib, json

# ============ 配置 ============
SKILL_DIR = os.path.expanduser("~/.workbuddy/skills/GenSJT.skill")
DECODED_DIR = os.path.join(SKILL_DIR, "references_decoded")
# 输出到当前工作目录（调用脚本时的 cwd），调用方也可通过 output_dir 参数覆盖
OUTPUT_DIR = os.getcwd()
# 密码哈希（SHA-256），不存储明文
_PWD_HASH = "21a3f27b0e966371cd2d7c46955fabf29fa6c7fd3f53b0a81a0de00b54e7f735"

# ============ 密码验证 ============
def verify_password(password: str) -> bool:
    return hashlib.sha256(password.encode()).hexdigest() == _PWD_HASH

def _fix_zip_filename(name: str) -> str:
    """修复 zip 中中文文件名编码错误（CP437 → GBK）"""
    try:
        # zipfile 默认用 CP437 解码非 UTF-8 文件名，实际应为 GBK
        raw = name.encode("cp437")
        return raw.decode("gbk")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name

def _clean_garbled_files(directory: str):
    """清理目录中乱码文件名的残留文件"""
    import glob
    for f in os.listdir(directory):
        # 检测乱码特征：包含 σ/Σ/τ/╛/Θ 等典型 CP437→GBK 乱码字符
        if any(c in f for c in "σΣτ╛Θóÿσ║σÅΣ╗╗σ╛üΦ╛₧σà╕"):
            try:
                os.remove(os.path.join(directory, f))
                print(f"已清理乱码文件：{f}", file=sys.stderr)
            except OSError:
                pass

def decrypt_references(password: str):
    """解密并解压参考资料"""
    env = os.environ.copy()
    env["GPG_TTY"] = "/dev/null"

    zip_path = os.path.join(DECODED_DIR, "references_decoded.zip")
    gpg_path = os.path.join(SKILL_DIR, "references.gpg")

    result = subprocess.run(
        ["gpg", "--batch", "--yes", "--passphrase", password,
         "-o", zip_path, "-d", gpg_path],
        capture_output=True, text=True, env=env
    )
    if result.returncode != 0:
        raise Exception(f"GPG解密失败：{result.stderr}")

    # 解压时修复中文文件名编码
    with zipfile.ZipFile(zip_path, "r") as z:
        for member in z.infolist():
            # 跳过目录条目
            if member.is_dir():
                continue
            fixed_name = _fix_zip_filename(member.filename)
            # 去掉可能的顶层目录前缀（zip 内可能有 references_decoded/ 前缀）
            basename = os.path.basename(fixed_name)
            if not basename:
                continue
            target = os.path.join(DECODED_DIR, basename)
            # 跳过已存在的正确文件
            if os.path.exists(target):
                continue
            with z.open(member) as src, open(target, "wb") as dst:
                dst.write(src.read())
    os.remove(zip_path)

    # 清理历史遗留的乱码文件
    _clean_garbled_files(DECODED_DIR)

# ============ Word文档工具 ============
def _normalize_items(items):
    """
    将分批JSON格式或分组格式统一转换为 [(dim_name, [items...]), ...] 格式。
    分批JSON格式: [{"dimension": "...", "stem": "...", "options": {...}}, ...]
    分组格式:     [(dim_name, [item, ...]), ...]
    """
    if not items:
        return []
    first = items[0]
    # 分组格式
    if isinstance(first, tuple):
        return items
    # 分批JSON格式：需要按dimension分组
    from collections import defaultdict
    groups = defaultdict(list)
    for item in items:
        dim = item.get("dimension", "未知维度")
        groups[dim].append(item)
    return [(dim, list(items_list)) for dim, items_list in groups.items()]

def create_test_doc(items: list, industry: str, position: str, output_path: str):
    """
    生成纯净题目卷（选项打乱）。
    打乱后按位置重新标记 A/B/C/D，映射存入 item['test_labels']。
    """
    doc = docx.Document()

    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.left_margin = section.right_margin = section.top_margin = section.bottom_margin = Cm(2.54)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("情境判断测验")
    run.font.name = "SimSun"
    run.font.size = Pt(18)
    run.font.bold = True
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run(f"【{industry}】【{position}】")
    run.font.name = "SimSun"
    run.font.size = Pt(12)
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    doc.add_paragraph()

    for dim_idx, (dim_name, dim_items) in enumerate(items, 1):
        dim_title = doc.add_paragraph()
        run = dim_title.add_run(f"维度{dim_idx}：{dim_name}")
        run.font.name = "SimSun"
        run.font.size = Pt(12)
        run.font.bold = True
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

        for q_idx, item in enumerate(dim_items, 1):
            q_para = doc.add_paragraph()
            run = q_para.add_run(f"{q_idx}. {item['stem']}")
            run.font.name = "SimSun"
            run.font.size = Pt(12)
            run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

            # 打乱原始选项内容
            raw_options = [
                ("A", item['options']['A']),
                ("B", item['options']['B']),
                ("C", item['options']['C']),
                ("D", item['options']['D']),
            ]
            random.seed(q_idx * 100 + dim_idx * 17)
            random.shuffle(raw_options)

            # 按打乱后的位置从上到下用 A B C D 标记，记录映射
            pos_labels = ["A", "B", "C", "D"]
            test_labels = {}          # pos_label -> orig_key
            for pos_idx, (orig_key, _) in enumerate(raw_options):
                test_labels[pos_labels[pos_idx]] = orig_key

            item["test_labels"] = test_labels  # 供答案卷使用

            for pos_idx, (orig_key, opt_data) in enumerate(raw_options):
                opt_para = doc.add_paragraph()
                opt_para.paragraph_format.left_indent = Cm(0.5)
                run = opt_para.add_run(f"{pos_labels[pos_idx]} {opt_data['text']}")
                run.font.name = "SimSun"
                run.font.size = Pt(11)
                run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

            doc.add_paragraph()

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    doc.save(output_path)

def create_answer_doc(items: list, industry: str, position: str, output_path: str):
    """
    生成完整答案卷。
    选项标签与测试卷保持一致（使用 item['test_labels'] 映射），
    按分值 0→1→2→3 升序排列。
    若 test_labels 不存在（如单独调用），则回退到以原始键 A-D 标记。
    """
    doc = docx.Document()

    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.left_margin = section.right_margin = section.top_margin = section.bottom_margin = Cm(2.54)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("情境判断测验（答案卷）")
    run.font.name = "SimSun"
    run.font.size = Pt(18)
    run.font.bold = True
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run(f"【{industry}】【{position}】")
    run.font.name = "SimSun"
    run.font.size = Pt(12)
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    doc.add_paragraph()

    for dim_idx, (dim_name, dim_items) in enumerate(items, 1):
        dim_title = doc.add_paragraph()
        run = dim_title.add_run(f"维度{dim_idx}：{dim_name}")
        run.font.name = "SimSun"
        run.font.size = Pt(12)
        run.font.bold = True
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

        for q_idx, item in enumerate(dim_items, 1):
            q_para = doc.add_paragraph()
            run = q_para.add_run(f"{q_idx}. {item['stem']}")
            run.font.name = "SimSun"
            run.font.size = Pt(12)
            run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

            # 构建 "测试卷位置标签 → 选项数据" 的映射
            test_labels = item.get("test_labels")
            if test_labels:
                # test_labels: {pos_label: orig_key}，反转为 orig_key → pos_label
                orig_to_pos = {v: k for k, v in test_labels.items()}
            else:
                # 回退：原始键即为位置标签
                orig_to_pos = {"A": "A", "B": "B", "C": "C", "D": "D"}

            # 按分值 0→3 排序
            sorted_opts = sorted(
                item['options'].items(),
                key=lambda kv: kv[1]['score']
            )

            for orig_key, opt_data in sorted_opts:
                pos_label = orig_to_pos[orig_key]
                score = opt_data['score']
                opt_para = doc.add_paragraph()
                opt_para.paragraph_format.left_indent = Cm(0.5)
                run = opt_para.add_run(f"{pos_label}（{score}分）{opt_data['text']}")
                run.font.name = "SimSun"
                run.font.size = Pt(11)
                run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

            doc.add_paragraph()

            # 赋分说明（同样按分值排序，保持与选项顺序一致）
            explain_title = doc.add_paragraph()
            run = explain_title.add_run("【赋分说明】")
            run.font.name = "SimSun"
            run.font.size = Pt(10.5)
            run.font.bold = True
            run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

            for orig_key, opt_data in sorted_opts:
                pos_label = orig_to_pos[orig_key]
                score = opt_data['score']
                p = doc.add_paragraph()
                run = p.add_run(f"{pos_label}={score}分：{opt_data['reason']}")
                run.font.name = "SimSun"
                run.font.size = Pt(10.5)
                run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

            doc.add_paragraph()

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    doc.save(output_path)

def create_excel_summary(items: list, dimension_defs: dict, industry: str, position: str, output_path: str, knowledge_refs: dict = None):
    """生成Excel汇总表"""
    wb = openpyxl.Workbook()

    # ===== Sheet1: 题目明细 =====
    ws1 = wb.active
    ws1.title = "题目明细"

    headers1 = ["序号", "行业", "岗位", "维度", "题干",
                "选项A", "选项B", "选项C", "选项D",
                "A分值", "B分值", "C分值", "D分值",
                "A说明", "B说明", "C说明", "D说明",
                "P值(难度)", "P难度等级", "D值(区分度)", "D区分度等级", "P/D估算理由"]

    thin = Side(style="thin")
    thin_border = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    hdr_font = Font(name="微软雅黑", bold=True, size=10)

    ws1.append(headers1)
    for col in range(1, len(headers1) + 1):
        c = ws1.cell(row=1, column=col)
        c.font = hdr_font
        c.fill = hdr_fill
        c.border = thin_border
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    row_num = 2
    # 兼容两种数据格式：分组格式或单条格式
    if items and isinstance(items[0], tuple):
        # 分组格式: [(dim_name, [items...]), ...]
        for dim_idx, (dim_name, dim_items) in enumerate(items, 1):
            for q_idx, item in enumerate(dim_items, 1):
                row_data = [
                    f"{dim_idx}.{q_idx}", industry, position, dim_name,
                    item['stem'],
                    item['options']['A']['text'], item['options']['B']['text'],
                    item['options']['C']['text'], item['options']['D']['text'],
                    0, 1, 2, 3,
                    item['options']['A']['reason'], item['options']['B']['reason'],
                    item['options']['C']['reason'], item['options']['D']['reason'],
                    item.get('p_value', ''), item.get('p_level', ''),
                    item.get('d_value', ''), item.get('d_level', ''),
                    item.get('p_d_reason', '')
                ]
                ws1.append(row_data)
                for col in range(1, len(headers1) + 1):
                    c = ws1.cell(row=row_num, column=col)
                    c.border = thin_border
                    c.alignment = Alignment(vertical="top", wrap_text=True)
                    c.font = Font(name="微软雅黑" if col <= 4 or col == 5 or col >= 12 else "Times New Roman", size=10)
                row_num += 1
    else:
        # 单条格式: [{item...}, ...]
        from collections import defaultdict
        dim_groups = defaultdict(list)
        for item in items:
            dim = item.get("dimension", "未知维度")
            dim_groups[dim].append(item)
        for dim_idx, (dim_name, dim_items) in enumerate(dim_groups.items(), 1):
            for q_idx, item in enumerate(dim_items, 1):
                row_data = [
                    f"{dim_idx}.{q_idx}", industry, position, dim_name,
                    item['stem'],
                    item['options']['A']['text'], item['options']['B']['text'],
                    item['options']['C']['text'], item['options']['D']['text'],
                    0, 1, 2, 3,
                    item['options']['A']['reason'], item['options']['B']['reason'],
                    item['options']['C']['reason'], item['options']['D']['reason'],
                    item.get('p_value', ''), item.get('p_level', ''),
                    item.get('d_value', ''), item.get('d_level', ''),
                    item.get('p_d_reason', '')
                ]
                ws1.append(row_data)
                for col in range(1, len(headers1) + 1):
                    c = ws1.cell(row=row_num, column=col)
                    c.border = thin_border
                    c.alignment = Alignment(vertical="top", wrap_text=True)
                    c.font = Font(name="微软雅黑" if col <= 4 or col == 5 or col >= 12 else "Times New Roman", size=10)
                row_num += 1

    # 列宽：序号8、行业10、岗位12、维度14、题干55、选项各38、分值各7、说明各45、P值8、P等级10、D值8、D等级10、P/D理由45
    col_widths1 = [8, 10, 12, 14, 55, 38, 38, 38, 38, 7, 7, 7, 7, 45, 45, 45, 45, 8, 10, 8, 10, 45]
    for i, w in enumerate(col_widths1, 1):
        ws1.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    # ===== Sheet2: 维度描述 =====
    ws2 = wb.create_sheet("维度描述")

    headers2 = ["维度", "定义", "高分表现", "低分表现",
                "关键行为指标1", "关键行为指标2", "关键行为指标3",
                "关键行为指标4", "关键行为指标5",
                "优秀(5)", "良好(4)", "中等(3)", "欠佳(2)", "不足(1)"]

    ws2.append(headers2)
    for col in range(1, len(headers2) + 1):
        c = ws2.cell(row=1, column=col)
        c.font = hdr_font
        c.fill = hdr_fill
        c.border = thin_border
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # 获取维度列表
    if items and isinstance(items[0], tuple):
        dim_list = items
    else:
        from collections import defaultdict
        dim_groups = defaultdict(list)
        for item in items:
            dim = item.get("dimension", "未知维度")
            dim_groups[dim].append(item)
        dim_list = list(dim_groups.items())

    for dim_idx, (dim_name, _) in enumerate(dim_list, 1):
        dim_info = dimension_defs.get(dim_name, {})
        kbi = dim_info.get("关键行为指标", [])
        if isinstance(kbi, str):
            kbi = [kbi] + [""] * 4
        kbi = (kbi + [""] * 5)[:5]

        row_data = [
            dim_name,
            dim_info.get("定义", ""),
            dim_info.get("高分表现", ""),
            dim_info.get("低分表现", ""),
        ] + kbi + [
            dim_info.get("优秀", ""),
            dim_info.get("良好", ""),
            dim_info.get("中等", ""),
            dim_info.get("欠佳", ""),
            dim_info.get("不足", "")
        ]
        ws2.append(row_data)
        for col in range(1, len(headers2) + 1):
            c = ws2.cell(row=dim_idx + 1, column=col)
            c.border = thin_border
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.font = Font(name="微软雅黑", size=10)

    ws2.column_dimensions["A"].width = 16
    ws2.column_dimensions["B"].width = 45
    ws2.column_dimensions["C"].width = 35
    ws2.column_dimensions["D"].width = 35
    for col_letter in ["E", "F", "G", "H", "I"]:
        ws2.column_dimensions[col_letter].width = 32
    for col_letter in ["J", "K", "L", "M", "N"]:
        ws2.column_dimensions[col_letter].width = 38

    # ===== Sheet3: 知识库引用记录 =====
    ws3 = wb.create_sheet("知识库引用记录")

    headers3 = ["序号", "维度",
                "胜任特征辞典", "辞典引用说明",
                "母题模板ID",
                "胜任-情境对应", "情境对应说明",
                "例题库参考", "例题参考说明",
                "行业岗位参考", "岗位匹配说明"]

    ws3.append(headers3)
    for col in range(1, len(headers3) + 1):
        c = ws3.cell(row=1, column=col)
        c.font = hdr_font
        c.fill = hdr_fill
        c.border = thin_border
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    row_num3 = 2
    # 复用 Sheet2 的维度分组逻辑
    if items and isinstance(items[0], tuple):
        dim_list = items
    else:
        from collections import defaultdict
        dim_groups = defaultdict(list)
        for item in items:
            dim = item.get("dimension", "未知维度")
            dim_groups[dim].append(item)
        dim_list = list(dim_groups.items())

    # 行业岗位匹配信息（仅计算一次）
    job_ctx_info = ""
    if industry and position:
        ctx = search_context(industry, position, top_n=3)
        if ctx.get("results"):
            top_match = ctx["results"][0]
            meta = top_match.get("_meta", {})
            matched_ind = top_match.get("industry", "")
            matched_pos = top_match.get("position_archetype", "")
            matched_cat = top_match.get("position_category", "")
            combined_score = meta.get("match_score", 0)
            ind_score = meta.get("industry_score", 0)
            pos_score = meta.get("position_score", 0)
            job_ctx_info = f"✓ 已匹配"
            job_ctx_detail = (
                f"用户输入：{industry} / {position}\n"
                f"最佳匹配：{matched_ind} / {matched_cat} - {matched_pos}\n"
                f"匹配分：综合 {combined_score}（行业 {ind_score} + 岗位 {pos_score}）"
            )
            if len(ctx["results"]) > 1:
                runners = []
                for r in ctx["results"][1:]:
                    rmeta = r.get("_meta", {})
                    runners.append(
                        f"{r.get('industry', '')} / {r.get('position_archetype', '')}（{rmeta.get('match_score', 0)}）"
                    )
                job_ctx_detail += f"\n备选：{'；'.join(runners)}"
        else:
            job_ctx_info = "✗ 未匹配"
            job_ctx_detail = f"用户输入：{industry} / {position}，未在行业岗位知识库中找到匹配记录"

    for dim_idx, (dim_name, dim_items) in enumerate(dim_list, 1):
        # 从知识库自动匹配结果中获取引用信息
        ref_info = (knowledge_refs or {}).get(dim_name, {})
        dict_found = ref_info.get("dict_found", False)
        dict_summary = ref_info.get("dict_summary", "")
        template_ids = ref_info.get("template_ids", [])
        competence_found = ref_info.get("competence_found", False)
        competence_summary = ref_info.get("competence_summary", "")
        examples_found = ref_info.get("examples_found", False)
        examples_summary = ref_info.get("examples_summary", "")

        for q_idx, item in enumerate(dim_items, 1):
            row_data = [
                f"{dim_idx}.{q_idx}",
                dim_name,
                "✓ 已匹配" if dict_found else "✗ 未匹配",
                dict_summary,
                ", ".join(template_ids) if template_ids else "无",
                "✓ 已匹配" if competence_found else "✗ 未匹配",
                competence_summary,
                "✓ 已匹配" if examples_found else "✗ 未匹配",
                examples_summary,
                job_ctx_info if job_ctx_info else "未提供行业岗位",
                job_ctx_detail if job_ctx_info else "",
            ]
            ws3.append(row_data)
            for col in range(1, len(headers3) + 1):
                c = ws3.cell(row=row_num3, column=col)
                c.border = thin_border
                c.alignment = Alignment(vertical="top", wrap_text=True)
                c.font = Font(name="微软雅黑", size=10)
            row_num3 += 1

    # Sheet3 列宽
    col_widths3 = [8, 14, 12, 45, 20, 14, 45, 12, 45, 14, 55]
    for i, w in enumerate(col_widths3, 1):
        ws3.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    wb.save(output_path)

# ============ 分批生成支持 ============
TEMP_FILE = os.path.join(SKILL_DIR, "temp_items.json")

def save_partial(data: dict):
    """保存中间结果到JSON文件（追加模式）。
    
    如果已有 temp_items.json 中的 industry/position 与本次不同，
    视为跨任务操作，清空旧数据后写入，防止题目混入。
    """
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
    import re
    result = {}

    # --- 1. 胜任特征辞典（JSON格式） ---
    dict_json_path = os.path.join(DECODED_DIR, "competence_dictionary.json")
    dict_dimensions = {}  # {dim_name: dim_data}
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
    examples_groups = {}  # {dim_name: [questions]}
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
            info["dict_summary"] = f"胜任特征辞典中包含'{dim_name}'维度的" + "、".join(parts) if parts else f"胜任特征辞典中存在'{dim_name}'维度条目"

        # 2) 母题模板匹配
        dim_templates = [t for t in templates_data if t.get("dimension") == dim_name]
        if dim_templates:
            info["template_ids"] = [t.get("template_id", "") for t in dim_templates]

        # 3) competence_SJT.json 匹配
        dim_competence = [c for c in competence_data if c.get("dimension") == dim_name]
        if dim_competence:
            info["competence_found"] = True
            info["competence_count"] = len(dim_competence)
            # 生成摘要：取每个条目的 abstract_scenario 前半段
            scenarios = []
            for c in dim_competence[:3]:  # 最多取3条
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

    # 构建 {dim_name: dim_data} 索引
    dim_index = {}
    for dim in dict_data.get("dimensions", []):
        dim_index[dim["name"]] = dim

    result = {}

    for dim_name in dim_names:
        dim = dim_index.get(dim_name)
        if not dim:
            result[dim_name] = {"定义": "", "高分表现": "", "低分表现": "",
                                 "关键行为指标": ["", "", "", "", ""],
                                 "优秀": "", "良好": "", "中等": "", "欠佳": "", "不足": ""}
            continue

        # 从 A 等级（优秀）描述中提取关键行为指标
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


def _fuzzy_score(query: str, target: str) -> float:
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
    # 解决 "互联网电商" vs "供应链/物流/采购" 中 SequenceMatcher 给 0 分的问题
    # 原理：将 query 按常见中文分词粒度（2-4字）拆分为候选词元，
    #       检查每个词元是否出现在 target 的 '/' 分段中
    if '/' in target:
        segments = [s.strip() for s in target.split('/') if s.strip()]
        # 将 query 按所有可能的 2-4 字子串枚举
        q_chars = list(query)
        for length in range(2, min(len(query) + 1, 5)):
            for i in range(len(q_chars) - length + 1):
                ngram = "".join(q_chars[i:i + length])
                for seg in segments:
                    if ngram in seg or seg in ngram:
                        # 匹配到的词元越长，权重越高
                        overlap_score = 0.3 + 0.15 * (length - 2)
                        base = max(base, overlap_score)
    elif len(query) >= 2 and len(target) >= 2:
        # target 无 '/' 但也可以做 ngram 重叠检测
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


def search_context(industry_query: str, position_query: str, top_n: int = 3) -> dict:
    """
    根据用户输入的行业和岗位，在 industry_job_context_db.json 中模糊搜索最匹配的记录。

    参数:
        industry_query: 用户输入的行业描述（如 "互联网电商"、"金融"）
        position_query: 用户输入的岗位描述（如 "销售"、"产品经理"）
        top_n: 返回前 N 条匹配结果

    返回:
        {
            "industry_match": [{"name": ..., "score": ...}, ...],
            "position_match": [{"name": ..., "score": ...}, ...],
            "results": [{完整记录 + match_score}, ...],
            "query": {"industry": ..., "position": ...}
        }
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

    # 1. 收集所有唯一行业名
    all_industries = sorted(set(item.get("industry", "") for item in db))
    # 2. 收集所有唯一岗位（category + archetype 合并）
    all_positions = set()
    for item in db:
        all_positions.add(item.get("position_category", ""))
        all_positions.add(item.get("position_archetype", ""))
    all_positions = sorted(all_positions)

    # 3. 行业模糊匹配 —— 返回 top_n 行业名及分数
    ind_scores = [(name, _fuzzy_score(industry_query, name)) for name in all_industries]
    ind_scores.sort(key=lambda x: x[1], reverse=True)
    industry_match = [{"name": n, "score": round(s, 3)} for n, s in ind_scores[:top_n] if s > 0.25]

    # 4. 岗位模糊匹配 —— 返回 top_n 岗位名及分数
    pos_scores = [(name, _fuzzy_score(position_query, name)) for name in all_positions]
    pos_scores.sort(key=lambda x: x[1], reverse=True)
    position_match = [{"name": n, "score": round(s, 3)} for n, s in pos_scores[:top_n] if s > 0.25]

    # 5. 综合匹配：每条记录计算行业分 + 岗位分（取 category 和 archetype 中较高者）
    scored_records = []
    for item in db:
        ind_name = item.get("industry", "")
        cat_name = item.get("position_category", "")
        arch_name = item.get("position_archetype", "")

        # 行业分：直接对每条记录的行业名计算分数
        ind_score = _fuzzy_score(industry_query, ind_name)

        # 岗位分：取 category 和 archetype 中的较高分
        cat_score = _fuzzy_score(position_query, cat_name)
        arch_score = _fuzzy_score(position_query, arch_name)
        pos_score = max(cat_score, arch_score)

        # 综合分 = 行业分 * 0.4 + 岗位分 * 0.6（岗位更关键）
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

    # 输出结果中保留完整记录，去掉 "record" 包装
    output_results = []
    for r in results:
        entry = dict(r["record"])
        entry["_meta"] = {
            "match_score": r["match_score"],
            "industry_score": r["industry_score"],
            "position_score": r["position_score"],
            "matched_position_field": r["matched_position_field"]
        }
        output_results.append(entry)

    return {
        "industry_match": industry_match,
        "position_match": position_match,
        "results": output_results,
        "query": {"industry": industry_query, "position": position_query}
    }


def query_refs(dim_names: list) -> dict:
    """
    按维度精准检索所有知识库，返回结构化的参考资料摘要。
    供 AI 命题前定向加载，避免全量读取。

    返回：
    {
      "dimensions": {dim_name: {"definition": ..., "high_score": ..., "low_score": ..., "behavior_levels": {...}, "code": ..., "category": ...}},
      "templates": [{template_id, dimension, item_skeleton, options_skeleton, logic_analysis}, ...],
      "competence_sjt": [{dimension, abstract_scenario, management_task, behavioral_anchors}, ...],
      "examples": [{id, dimension, scenario, options, option_scores}, ...],
      "parameter_guide": "..."
    }
    """
    result = {"dimensions": {}, "templates": [], "competence_sjt": [], "examples": [], "parameter_guide": "", "skipped_dimensions": []}
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

    # 记录未找到的维度
    for dim_name in dim_names:
        if dim_name not in found_dims:
            result["skipped_dimensions"].append(dim_name)

    # 2. 母题模板（extracted_templates.json）
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

    # 4. 例题库（example_questions.json）— 每维度最多返回5道
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


def generate_docs_from_temp(industry: str, position: str, output_dir: str = None):
    """
    从 temp_items.json 读取已生成的题目，生成三份文档。
    output_dir 默认为调用时的当前工作目录（os.getcwd()）。
    """
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

    # 从胜任特征辞典.md 读取维度完整信息（如无法找到则给空占位）
    dimension_defs = _load_dimension_defs(dim_names)

    # 从知识库自动匹配引用信息（胜任职典、母题模板、胜任-情境对应、例题库）
    knowledge_refs = _load_knowledge_references(dim_names)

    normalized = _normalize_items(items)
    out_dir = output_dir or os.getcwd()

    import datetime
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    test_path = os.path.join(out_dir, f"测验卷_{industry}_{position}_{ts}.docx")
    answer_path = os.path.join(out_dir, f"答案卷_{industry}_{position}_{ts}.docx")
    excel_path = os.path.join(out_dir, f"汇总表_{industry}_{position}_{ts}.xlsx")

    create_test_doc(normalized, industry, position, test_path)
    create_answer_doc(normalized, industry, position, answer_path)
    create_excel_summary(items, dimension_defs, industry, position, excel_path, knowledge_refs=knowledge_refs)

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
        # query 命令：按维度检索知识库 + 可选行业岗位模糊搜索
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
        # 解析 --output-dir 参数
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

            # 校验：如果没有 industry/position 字段，说明是旧格式数据，拒绝生成
            if not industry or not position:
                print("错误：temp_items.json 缺少 industry 或 position 字段，请检查数据格式")
                sys.exit(1)

            print(f"已加载 {len(items)} 道题目（行业：{industry}，岗位：{position}）")

            # 二次校验：检查每个 item 是否都属于本次任务的维度（防止混入旧数据）
            expected_dims = set(it.get("dimension") for it in items if it.get("dimension"))
            print(f"涉及维度：{', '.join(expected_dims)}")

            generate_docs_from_temp(
                industry=industry,
                position=position,
                output_dir=output_dir
            )

            # 生成完毕后自动清理 temp 文件，防止下次任务读到旧数据
            clear_partial()
            print("临时文件已清理")
        else:
            print("错误：temp_items.json 为空或不存在")
