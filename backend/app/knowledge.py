"""一个用户目录保存独立的文档索引分片，不加载外部提供的索引文件。"""
import json
import re
from functools import lru_cache
from uuid import uuid4
from zipfile import ZipFile

import faiss
import numpy as np
from rank_bm25 import BM25Okapi
from sqlalchemy import select

from .db import EMBEDDING_MODEL, STORE, Document

CHUNK_SIZE = 700
OVERLAP = 100


@lru_cache(maxsize=1)
def embedding_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBEDDING_MODEL, device="cpu")


def embed(texts):
    vectors = embedding_model().encode(texts, batch_size=32, normalize_embeddings=True,
                                       show_progress_bar=False)
    return np.ascontiguousarray(vectors, dtype=np.float32)


def chunk_text(text):
    """尽量按空白处分段，并保留一些重叠上下文。"""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            for separator in ("\n\n", "\n", " "):
                boundary = text.rfind(separator, start + CHUNK_SIZE // 2, end)
                if boundary != -1:
                    end = boundary + len(separator)
                    break
        snippet = text[start:end].strip()
        if snippet:
            chunks.append(snippet)
        if end == len(text):
            break
        start = end - OVERLAP
    return chunks


def index_path(user_id, document_id):
    return STORE / str(user_id) / f"{document_id}.zip"


def build_index(doc):
    path = index_path(doc.user_id, doc.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    chunks = chunk_text(doc.content)
    if not chunks:
        raise ValueError("文档没有可索引文本")
    vectors = embed(chunks)
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        # 索引和证据一起发布，查询不会读到一半写入的文件。
        with ZipFile(temp, "w") as bundle:
            bundle.writestr("index", faiss.serialize_index(index).tobytes())
            bundle.writestr("chunks.json", json.dumps({"model": EMBEDDING_MODEL, "texts": chunks},
                                                       ensure_ascii=False))
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    return len(chunks)


def terms(text):
    return re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]", text.lower())


def retrieve(db, user_id, query, k=5, method="vector"):
    docs = db.scalars(select(Document).where(Document.user_id == user_id,
                                              Document.status == "READY")).all()
    evidence = []
    lexical = []
    vector = embed([query]) if docs and method == "vector" else None
    for doc in docs:
        try:
            with ZipFile(index_path(user_id, doc.id)) as bundle:
                metadata = json.loads(bundle.read("chunks.json"))
                chunks = metadata["texts"]
                if method == "vector":
                    if metadata["model"] != EMBEDDING_MODEL:
                        raise ValueError("Embedding 模型已更改，请重新导入文档")
                    index = faiss.deserialize_index(np.frombuffer(bundle.read("index"), dtype="uint8"))
                    if index.d != vector.shape[1]:
                        raise ValueError("索引与 Embedding 维度不同，请重新导入文档")
                    scores, ids = index.search(vector, min(k, len(chunks)))
                else:
                    lexical.extend((doc, i, text) for i, text in enumerate(chunks))
                    continue
        except FileNotFoundError:
            # 文档可能在读取快照后被删除。
            continue
        evidence.extend(make_evidence(doc, int(i), chunks[i], float(score))
                        for score, i in zip(scores[0], ids[0]) if i >= 0)
    if lexical:
        corpus = [terms(text) or [""] for _, _, text in lexical]
        query_terms = terms(query)
        engine = BM25Okapi(corpus)
        scores = engine.get_scores(query_terms)
        wanted = set(query_terms)
        evidence.extend(make_evidence(doc, i, text, float(score))
                        for (doc, i, text), tokens, score in zip(lexical, corpus, scores)
                        if wanted.intersection(tokens))
    return sorted(evidence, key=lambda item: item["score"], reverse=True)[:k]


def make_evidence(doc, index, text, score=None):
    return {"document_id": doc.id, "source_id": doc.source_id, "title": doc.title,
            "source_url": doc.source_url, "chunk": index + 1, "excerpt": text,
            "score": round(score, 5) if score is not None else None}
