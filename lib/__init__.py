"""
GenSJT.skill lib — 子模块包
存放从 gensjt.py 拆分出的功能模块。
"""

import os

# ── 共享常量 ──
SKILL_DIR = os.path.expanduser("~/.workbuddy/skills/GenSJT.skill")
DECODED_DIR = os.path.join(SKILL_DIR, "references_decoded")
