#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crypto.py — 密码验证与 GPG 解密模块
从 gensjt.py 提取，负责密码校验、参考资料解密和 zip 解压。
"""

import hashlib
import os
import subprocess
import sys
import zipfile

from lib import SKILL_DIR, DECODED_DIR

# 密码哈希（SHA-256），不存储明文
_PWD_HASH = "21a3f27b0e966371cd2d7c46955fabf29fa6c7fd3f53b0a81a0de00b54e7f735"


def verify_password(password: str) -> bool:
    cleaned = password.strip()
    return hashlib.sha256(cleaned.encode()).hexdigest() == _PWD_HASH


def _fix_zip_filename(name: str) -> str:
    """修复 zip 中中文文件名编码错误（CP437 → GBK）"""
    try:
        raw = name.encode("cp437")
        return raw.decode("gbk")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def _clean_garbled_files(directory: str):
    """清理目录中乱码文件名的残留文件"""
    for f in os.listdir(directory):
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

    with zipfile.ZipFile(zip_path, "r") as z:
        for member in z.infolist():
            if member.is_dir():
                continue
            fixed_name = _fix_zip_filename(member.filename)
            basename = os.path.basename(fixed_name)
            if not basename:
                continue
            target = os.path.join(DECODED_DIR, basename)
            if os.path.exists(target):
                continue
            with z.open(member) as src, open(target, "wb") as dst:
                dst.write(src.read())
    os.remove(zip_path)

    _clean_garbled_files(DECODED_DIR)
