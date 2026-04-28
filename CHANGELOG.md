# GenSJT Skill 更新日志

---

## V3.0（2026-04-27）

### SKILL.md 重构

#### 变更概述
将 SKILL.md 全面重构为六大板块结构，新增 P/D 参数估算步骤和 JSON 嵌套选项格式，提升命题质量和心理测量学严谨性。

#### 六大板块结构
1. **维度标准深度内化**：AI 必须先内化胜任特征辞典中目标维度的定义、行为等级、高低分特征
2. **SJT 开发原理与命题规范**：加载 SJT 开发原理，遵守情境判断测验设计规范
3. **参考母题与语言风格模仿**：参考母题模板、胜任-情境对应、例题库，确保风格一致性
4. **情境渲染与选项映射**：情境编写规范、JSON 嵌套选项格式 `{text, score, reason}`
5. **P/D 参数估算**：新增心理测量学参数估算步骤（p_value、d_value、p_level、d_level、p_d_reason）
6. **质检清单**：题目质量自查（反标准答案模式、情境真实感、选项独立性等）

#### 新增引用文件
- `SJT_parameter_estimation.md`：P/D 参数估算指南（区分中/高/高难度层级，定义合理取值范围）

#### JSON 数据格式变更
- **选项格式**：从纯字符串 `"选项文本"` 改为嵌套对象 `{text, score, reason}`
- **新增字段**：每题增加 `p_value`、`d_value`、`p_level`、`d_level`、`p_d_reason`

---

## V3.1（2026-04-27）

### 程序定向检索——query 命令

#### 变更概述
将"AI 先全量加载知识库"改为"程序先按维度精准检索，再给 AI 精简结果"，减少 token 浪费并提高检索精准度。

#### gensjt.py 变更

1. **新增 `query_refs(dim_names)` 函数**
   - 接收维度名称列表，从 5 个知识库中按维度精准检索
   - 输出精简 JSON，包含：
     - `dimensions`：维度定义、高低分特征、行为等级
     - `templates`：匹配的母题模板（含占位符骨架和逻辑分析）
     - `competence_sjt`：匹配的情境-任务-行为锚点
     - `examples`：匹配的例题（每维度最多 5 道）
     - `parameter_guide`：P/D 参数估算指南全文

2. **新增 `query` 命令**
   - 用法：`python3 gensjt.py "$PASSWORD" query --dimensions 维度1,维度2,...`
   - 同时完成密码验证 + 解密 + 定向检索
   - stdout 输出纯 JSON，无污染（解密日志重定向至 stderr）

3. **解密日志输出调整**
   - `decrypt_references()` 中的乱码清理日志改为 `sys.stderr` 输出
   - `print("参考资料解密成功")` 仅在非 query 模式下输出

#### SKILL.md 执行流更新

- **旧流程**：密码解密 → AI 全量读取所有知识库文件 → 命题 → gen_docs
- **新流程**：密码 + query 一步到位 → AI 仅基于精简 JSON 命题 → gen_docs
- AI 不再需要自行读取原始知识库文件，程序负责检索，AI 负责命题

---

## V0.3.1（2026-04-27）

### 知识库结构化

#### 变更概述
将胜任特征辞典和例题库从 Markdown 格式转换为结构化 JSON 格式，提升 AI 检索和程序解析的效率与可靠性。

#### 新增文件
- `competence_dictionary.json`：57个维度的胜任特征辞典（从 `胜任特征辞典.md` 转换）
- `example_questions.json`：331道SJT例题（从 `例题库.md` 转换）

#### JSON 结构说明

**competence_dictionary.json**：
```json
{
  "_meta": {"total_dimensions": 57, "categories": {...}},
  "categories": {"思维类": [...], "管理类": [...], ...},
  "dimensions": [
    {
      "code": "M1",
      "name": "创新思维",
      "category": "思维类",
      "definition": "...",
      "high_score_features": "...",
      "low_score_features": "...",
      "behavior_levels": {"优秀": "...", "良好": "...", "中等": "...", "欠佳": "...", "不足": "..."}
    }
  ]
}
```

**example_questions.json**：
```json
{
  "_meta": {"total_questions": 331, "dimension_stats": {...}},
  "groups": [
    {
      "dimension": "指导",
      "category": "管理类",
      "question_count": 6,
      "questions": [
        {
          "id": 7,
          "dimension": "指导",
          "scenario": "...",
          "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
          "option_scores": {"A": 1, "B": 0, "C": 2, "D": 1}
        }
      ]
    }
  ]
}
```

#### gensjt.py 变更

1. **`_load_dimension_defs()` 重写**
   - 从 `competence_dictionary.json` 读取（替代 md 正则解析）
   - 输出格式不变，完全兼容

2. **`_load_knowledge_references()` 重写**
   - 胜任特征辞典：从 `competence_dictionary.json` 按维度名精确查找（替代 md 正则）
   - 例题库：从 `example_questions.json` 按维度名查找，直接统计题目数量（替代 md 正则 section 截断）
   - 母题模板和 competence_SJT 读取方式不变
   - 输出格式不变，完全兼容

3. **测试验证**
   - 创新思维：✓辞典 ✓5个模板 ✓5条情境 ✓8道例题（与 md 版本一致）
   - 指导：✓辞典 ✓5个模板 ✓5条情境 ✓6道例题（与 md 版本一致）
   - 团队协作：✗（辞典中无此维度名，正确行为）

#### 保留文件
- `胜任特征辞典.md` 和 `例题库.md` 仍保留在 references_decoded 目录中作为原始备份，不再被程序读取

---

## V0.3.0（2026-04-27）

### gensjt.py 变更

#### 新功能

1. **Excel 汇总表新增 Sheet3（知识库引用记录）**
   - 每道题一行，记录 AI 在生成该题时实际调取了哪些知识库信息
   - 9 列：序号 / 维度 / 胜任特征辞典（是否引用+说明） / 母题模板ID / 胜任-情境对应（是否引用+说明） / 例题库参考（是否引用+说明）
   - 引用状态以 ✓/✗ 标记，引用说明为自然语言描述具体引用了哪些内容
   - 兼容分组格式和单条格式两种数据结构

#### Bug 修复

4. **修复 Excel 汇总表 Sheet2（维度描述）内容为空**
   - **问题**：`generate_docs_from_temp()` 构建 `dimension_defs` 时仅创建空字段占位，未从 `胜任特征辞典.md` 读取实际内容，导致 Sheet2 有表头但数据全空
   - **修复**：新增 `_load_dimension_defs()` 函数，正则解析 `胜任特征辞典.md`，提取目标维度的定义、高分特征、低分特征及 A/B/C/D/E 五个行为等级描述（映射为优秀/良好/中等/欠佳/不足），填充进 `dimension_defs` 后传给 Sheet2
   - **验证**：使用 3 题测试数据（创新思维、团队凝聚、压力应对）运行 `generate_docs_from_temp`，确认 Sheet2 三个维度的定义、高分/低分表现及五级行为等级均正确填充

5. **修复 Excel 汇总表 Sheet2 关键行为指标1-5 列为空**
   - **问题**：`_load_dimension_defs()` 未提取"关键行为指标"字段，而 `胜任特征辞典.md` 中没有该独立字段，导致这5列全部为空
   - **修复**：从行为等级 A（优秀）的描述文本中按中文分号拆分提取关键行为短语；不足5个时自动从 B（良好）等级描述补充，去重后补齐至5列
   - **验证**：三个测试维度中，创新思维和压力应对均提取到5个指标，团队凝聚提取到4个（数据源本身限制），功能正常

---

## V0.1.0（2026-04-24）

### SKILL.md 变更

| 变更项 | 说明 |
|--------|------|
| 新增版本号标记 | frontmatter 增加 `更新：V0.0.2 增加了结构化胜任特征和母题模板` |
| 新增参考资料 | Step 2 增加 `extracted_templates.json`（题目模板）和 `competence_SJT.json`（胜任特征与SJT对应关系） |

### gensjt.py 变更

#### Bug 修复

1. **修复 zip 解压中文文件名乱码**
   - **问题**：`decrypt_references()` 使用 `z.extractall()` 解压，Python `zipfile` 默认用 CP437 编码解码非 UTF-8 文件名，导致中文文件名变成乱码（如 `SJTσ╝ÇσÅæσÄƒτÉå.md`）
   - **修复**：新增 `_fix_zip_filename()` 函数，将 CP437 编码的文件名重新转换为 GBK；改为逐条目解压，跳过已存在的正确文件；新增 `_clean_garbled_files()` 自动清理历史遗留的乱码文件

2. **修复跨任务数据污染**
   - **问题**：`save_partial()` 使用追加模式，如果两次任务的行业/岗位不同，旧任务的题目会被混入新任务
   - **修复**：`save_partial()` 增加 industry/position 校验，检测到不匹配时清空旧数据

3. **修复 gen_docs 使用残留数据生成错误文件**
   - **问题**：`gen_docs` 命令不校验 `temp_items.json` 的数据是否属于本次任务，可能用旧数据生成文件
   - **修复**：增加 industry/position 字段存在性校验；生成前打印行业/岗位和维度信息供确认；生成完毕后自动调用 `clear_partial()` 清理临时文件

---

## V0.0.2（V0.1.0 之前）

- 增加结构化胜任特征（`competence_SJT.json`）和母题模板（`extracted_templates.json`）作为参考资料
- 修正 `SJT开发原理.md` 内容

---

## V0.0.1（初始版本）

- SKILL.md：Skill 定义、执行流程、题目编写规范、质量检查清单
- gensjt.py：密码验证、GPG 解密、文档生成（Word + Excel）
- references.gpg：加密的参考资料（胜任特征辞典、例题库、SJT 开发原理）
