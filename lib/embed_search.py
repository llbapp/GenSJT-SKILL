#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
embed_search.py — 行业岗位 Embedding 向量检索模块
================================================
从独立脚本精简而来，仅保留核心 embedding 能力，
供 gensjt.py 的 search_context() 调用。

核心能力：
  - EmbeddingModel: Mean Pooling + L2 归一化（与 sentence-transformers 行为一致）
  - 向量缓存: .npz 格式 + MD5 校验自动失效
  - 语义检索: numpy 余弦相似度（faiss 可选加速）
  - 高层接口: search_context_embedding() 返回与 search_context() 兼容格式
"""

import os
import sys
import json
import time
import hashlib
import types
from pathlib import Path

# ─── 环境兼容 & scipy 修复 ───────────────────────────────────
if not os.environ.get("USERNAME") and not os.environ.get("USER"):
    os.environ["USERNAME"] = "user"


def _fix_scipy():
    """预注入占位模块，修复残缺的 scipy 安装；注入 csr_matrix 别名。"""
    _stub = types.ModuleType("scipy.sparse.linalg._propack")
    for _attr in ["_spropack", "_dpropack", "_cpropack", "_zpropack"]:
        setattr(_stub, _attr, None)
    sys.modules["scipy.sparse.linalg._propack"] = _stub

    _svdp = types.ModuleType("scipy.sparse.linalg._svdp")
    def _svdp_fn(*a, **kw): raise RuntimeError("_propack not available")
    _svdp._svdp = _svdp_fn
    sys.modules["scipy.sparse.linalg._svdp"] = _svdp

    try:
        import scipy.sparse as sp
        for _old, _new in [
            ("csr_matrix", "csr_array"), ("csc_matrix", "csc_array"),
            ("coo_matrix", "coo_array"), ("lil_matrix", "lil_array"),
            ("bsr_matrix", "bsr_array"), ("dok_matrix", "dok_array"),
            ("dia_matrix", "dia_array"),
        ]:
            if not hasattr(sp, _old) and hasattr(sp, _new):
                setattr(sp, _old, getattr(sp, _new))
    except Exception:
        pass

_fix_scipy()


# ─────────────────────────────────────────────────────────────
# 配置（相对于 SKILL_DIR）
# ─────────────────────────────────────────────────────────────
SKILL_DIR = os.path.expanduser("~/.workbuddy/skills/GenSJT.skill")
DECODED_DIR = os.path.join(SKILL_DIR, "references_decoded")
DB_PATH = os.path.join(DECODED_DIR, "industry_job_context_db.json")
CACHE_DIR = os.path.join(DECODED_DIR, "embed_cache")
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MAX_SEQ_LEN = 256

# ─── 全局懒加载状态 ──────────────────────────────────────────
_model_instance = None
_db_vectors = None
_db_cache = None
_db_path_cache = None


# ─────────────────────────────────────────────────────────────
# 文本构建
# ─────────────────────────────────────────────────────────────
def build_record_text(record: dict) -> str:
    """将数据库记录压缩成一段供 embedding 编码的自然语言文本"""
    parts = []
    ind = record.get("industry", "")
    pos_cat = record.get("position_category", "")
    pos_arch = record.get("position_archetype", "")
    parts.append(f"行业：{ind}，岗位类别：{pos_cat}，岗位原型：{pos_arch}")

    logic = record.get("logic_v3", {})
    actions = logic.get("typical_work_actions", [])
    if actions:
        parts.append("典型工作：" + "；".join(actions[:3]))

    conflict = logic.get("conflict_source", "")
    if conflict:
        parts.append(f"核心矛盾：{conflict[:60]}")

    vocab = record.get("domain_vocabulary", [])
    if vocab:
        parts.append("领域词汇：" + "、".join(vocab[:6]))

    scenarios = record.get("exclusive_scenarios", [])
    if scenarios:
        parts.append("典型场景：" + scenarios[0].get("scenario", "")[:60])

    return " ".join(parts)


def build_query_text(industry: str, position: str) -> str:
    return f"行业：{industry}，岗位：{position}"


# ─────────────────────────────────────────────────────────────
# Embedding 模型
# ─────────────────────────────────────────────────────────────
class EmbeddingModel:
    """
    轻量封装，使用 transformers AutoTokenizer + AutoModel，
    Mean Pooling + L2 归一化，与 sentence-transformers 行为一致。
    """

    def __init__(self, model_name: str):
        self.model_name = model_name
        try:
            from transformers import AutoTokenizer, AutoModel
            import torch
        except ImportError as e:
            raise RuntimeError(f"缺少依赖：{e}\n请运行：pip install transformers torch")
        self._torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
        self.model.eval()

    def _mean_pool(self, token_embeddings, attention_mask):
        import torch
        mask = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return torch.sum(token_embeddings * mask, 1) / torch.clamp(mask.sum(1), min=1e-9)

    def encode(self, texts: list, batch_size: int = 32) -> 'np.ndarray':
        """编码文本列表，返回 L2 归一化的 numpy 向量矩阵，shape=(N, D)"""
        import numpy as np
        import torch
        all_vecs = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start: start + batch_size]
            encoded = self.tokenizer(
                batch, padding=True, truncation=True,
                max_length=MAX_SEQ_LEN, return_tensors="pt"
            )
            with torch.no_grad():
                output = self.model(**encoded)
            pooled = self._mean_pool(output.last_hidden_state, encoded["attention_mask"])
            normed = torch.nn.functional.normalize(pooled, p=2, dim=1)
            all_vecs.append(normed.cpu().numpy())
        import numpy as np
        return np.vstack(all_vecs)


# ─────────────────────────────────────────────────────────────
# 向量缓存
# ─────────────────────────────────────────────────────────────
def _load_db(db_path) -> list:
    with open(db_path, encoding="utf-8") as f:
        return json.load(f)


def _db_hash(db_path) -> str:
    h = hashlib.md5()
    with open(db_path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _get_cache_path(model_name: str) -> Path:
    safe = model_name.replace("/", "_").replace("\\", "_")
    return Path(CACHE_DIR) / f"vectors_{safe}.npz"


def _build_or_load_vectors(model: EmbeddingModel, db: list,
                            db_path: str, force_rebuild: bool = False):
    """返回向量矩阵 shape=(N, D)，N = len(db)"""
    import numpy as np
    Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
    cache_path = _get_cache_path(model.model_name)
    current_hash = _db_hash(db_path)

    if not force_rebuild and cache_path.exists():
        data = np.load(cache_path, allow_pickle=True)
        cached_hash = str(data.get("db_hash", np.array("")).item())
        if cached_hash == current_hash:
            return data["vectors"]

    texts = [build_record_text(r) for r in db]
    vectors = model.encode(texts, batch_size=32)

    np.savez_compressed(cache_path, vectors=vectors, db_hash=np.array(current_hash))
    return vectors


# ─────────────────────────────────────────────────────────────
# 语义检索
# ─────────────────────────────────────────────────────────────
def _cosine_search_numpy(query_vec, db_vectors, top_n: int) -> list:
    """向量已 L2 归一化，点积 = 余弦相似度"""
    import numpy as np
    scores = db_vectors @ query_vec
    top_idx = np.argsort(scores)[::-1][:top_n]
    return [(int(i), float(scores[i])) for i in top_idx]


def _embed_search(industry: str, position: str,
                   model: EmbeddingModel, db: list,
                   db_vectors, top_n: int = 3) -> list:
    """执行 embedding 检索，返回 [(db_index, score), ...]"""
    import numpy as np
    query_text = build_query_text(industry, position)
    query_vec = model.encode([query_text])[0]

    try:
        import faiss
        dim = db_vectors.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(db_vectors.astype(np.float32))
        q = query_vec.reshape(1, -1).astype(np.float32)
        scores, indices = index.search(q, top_n)
        hits = list(zip(indices[0].tolist(), scores[0].tolist()))
    except ImportError:
        hits = _cosine_search_numpy(query_vec, db_vectors, top_n)

    return hits


# ─────────────────────────────────────────────────────────────
# 高层接口（供 gensjt.py 调用）
# ─────────────────────────────────────────────────────────────
def search_context_embedding(industry: str, position: str,
                              top_n: int = 3) -> dict:
    """
    高层接口：加载模型 → 编码查询 → 语义检索 → 返回与 search_context() 兼容格式。

    返回:
        {
            "results": [{完整记录 + _meta}, ...],
            "query": {"industry": ..., "position": ...},
            "_embedding_available": True
        }
    """
    global _model_instance, _db_vectors, _db_cache, _db_path_cache

    db_path = DB_PATH
    if not os.path.exists(db_path):
        return {
            "results": [],
            "query": {"industry": industry, "position": position},
            "_embedding_available": False,
        }

    # 懒加载：模型 + 向量只加载一次
    if _model_instance is None or _db_vectors is None or _db_path_cache != db_path:
        _model_instance = EmbeddingModel(DEFAULT_MODEL)
        _db_cache = _load_db(db_path)
        _db_vectors = _build_or_load_vectors(_model_instance, _db_cache, db_path)
        _db_path_cache = db_path

    db = _db_cache
    hits = _embed_search(industry, position, _model_instance, db, _db_vectors, top_n)

    # 收集行业/岗位匹配列表（从 top 结果中提取）
    all_industries = sorted(set(item.get("industry", "") for item in db))
    all_positions = set()
    for item in db:
        all_positions.add(item.get("position_category", ""))
        all_positions.add(item.get("position_archetype", ""))
    all_positions = sorted(all_positions)

    # 构建输出（格式兼容 search_context_char 的返回结构）
    output_results = []
    for idx, score in hits:
        rec = db[idx]
        entry = dict(rec)
        entry["_meta"] = {
            "match_score": round(float(score), 3),
            "industry_score": None,   # embedding 不区分行业/岗位分
            "position_score": None,
            "matched_position_field": "embedding",
            "backend": "embedding",
        }
        output_results.append(entry)

    # industry_match / position_match：embedding 没有单独的行业/岗位分，
    # 从 top 结果的行业/岗位名中提取供参考
    industry_match = []
    position_match = []
    seen_ind, seen_pos = set(), set()
    for entry in output_results[:top_n]:
        ind = entry.get("industry", "")
        pos_arch = entry.get("position_archetype", "")
        pos_cat = entry.get("position_category", "")
        if ind and ind not in seen_ind:
            industry_match.append({"name": ind, "score": round(entry["_meta"]["match_score"], 3)})
            seen_ind.add(ind)
        for pos in [pos_arch, pos_cat]:
            if pos and pos not in seen_pos:
                position_match.append({"name": pos, "score": round(entry["_meta"]["match_score"], 3)})
                seen_pos.add(pos)

    return {
        "industry_match": industry_match,
        "position_match": position_match,
        "results": output_results,
        "query": {"industry": industry, "position": position},
        "_embedding_available": True,
    }
