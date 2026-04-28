# GenSJT — 情境判断测验(SJT)自动化命题系统

基于结构化胜任特征辞典与母题模板，为特定行业/岗位生成具有高心理测量学效度的 SJT 题目。每次输出纯净题目卷（Word）、完整答案卷（Word）、汇总表（Excel）。

## 核心特性

- **六步 Pipeline**：维度内化 → 原理加载 → 母题模仿 → 情境渲染 → P/D 参数估算 → 文档生成
- **程序定向检索**：`query` 命令按维度精准检索知识库，输出精简 JSON 供 AI 命题
- **P/D 参数估算**：每题自动估算 p_value（难度）、d_value（区分度）及合理取值范围
- **跨任务保护**：自动检测 industry/position 不匹配并清理旧数据
- **加密知识库**：参考资料通过 GPG 加密存储，运行时解密

## 文件结构

```
GenSJT.skill/
├── SKILL.md                          # Skill 定义与执行流规范
├── CHANGELOG.md                      # 版本更新日志
├── gensjt.py                         # 核心程序（密码验证/解密/检索/文档生成）
├── references.gpg                    # 加密的参考资料包
└── references_decoded/               # 解密后的知识库
    ├── competence_dictionary.json    # 57 维度胜任特征辞典
    ├── competence_SJT.json           # 胜任特征与 SJT 情境对应
    ├── extracted_templates.json      # 母题模板
    ├── example_questions.json        # 331 道 SJT 例题
    └── SJT_parameter_estimation.md   # P/D 参数估算指南
```

## 使用方式

### 作为 WorkBuddy Skill 安装

将本目录放入 `~/.workbuddy/skills/` 下即可。

### 命令行接口

```bash
# 密码验证 + 按维度检索知识库（输出 JSON）
python3 gensjt.py "<密码>" query --dimensions 创新思维,压力应对

# 从 temp_items.json 生成三份文档
python3 gensjt.py "<密码>" gen_docs --output-dir ./output
```

## 依赖

- Python 3.8+
- GnuPG（用于解密 references.gpg）
- python-docx、openpyxl（用于文档生成）

## 版本

当前版本：**V3.1**（详见 [CHANGELOG.md](CHANGELOG.md)）

## License

MIT
