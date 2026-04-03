"""
services/memory_service.py — Memória de curto/longo prazo com TF-IDF e FTS5
"""
import json
import logging
import re
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from config import settings
from database.db import get_db
from models.schemas import MemoryCreate, MemoryItem, MemorySearchResult, MemoryType

logger = logging.getLogger(__name__)

# Padrões de extração de informação
INFO_PATTERNS = {
    MemoryType.person: [r'\b(?:meu|minha)\s+(?:chefe|amigo|amiga|esposa|marido|filho|filha|pai|mãe|irmão|irmã)\b.*',
                        r'(?:sr\.?|sra\.?|dr\.?|dra\.?)\s+[A-Z][a-z]+'],
    MemoryType.preference: [r'(?:prefiro|gosto de|adoro|não gosto|odeio|favorito)\s+.*',
                             r'sempre (?:uso|uso|faço|como|bebo)\s+.*'],
    MemoryType.fact: [r'(?:moro em|trabalho em|trabalho como|sou de|nasci em)\s+.*',
                      r'(?:meu número|meu email|meu cpf)\s+(?:é|:)\s+.*'],
    MemoryType.event: [r'(?:amanhã|hoje|próxima semana|semana que vem)\s+.*',
                       r'(?:reunião|compromisso|viagem|consulta)\s+.*'],
}

class MemoryService:
    def __init__(self):
        self._tfidf_matrix = None
        self._tfidf_docs = []
        self._vectorizer = None

    async def initialize(self):
        await self._rebuild_tfidf()
        logger.info("✅ MemoryService inicializado")

    async def add(self, memory: MemoryCreate) -> MemoryItem:
        mem_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        db = await get_db()
        await db.execute(
            "INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?,?)",
            (mem_id, memory.type.value, memory.content, memory.importance,
             memory.source, json.dumps(memory.tags), now, now,
             memory.expires_at.isoformat() if memory.expires_at else None,
             json.dumps(memory.meta))
        )
        # FTS5
        try:
            await db.execute(
                "INSERT INTO memories_fts(rowid, content, tags) SELECT rowid, content, ? FROM memories WHERE id=?",
                (json.dumps(memory.tags), mem_id)
            )
        except Exception:
            pass
        await db.commit()
        asyncio.create_task(self._rebuild_tfidf())
        return MemoryItem(id=mem_id, created_at=datetime.utcnow(),
                          updated_at=datetime.utcnow(), **memory.model_dump())

    async def search(self, query: str, limit: int = 5, memory_type: str = None) -> List[MemorySearchResult]:
        """Busca semântica com TF-IDF + FTS5."""
        results = []

        # FTS5 search primeiro
        db = await get_db()
        fts_query = ' OR '.join(query.split()[:5])
        try:
            cur = await db.execute(
                "SELECT m.*, rank FROM memories_fts f "
                "JOIN memories m ON m.rowid = f.rowid "
                "WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?",
                (fts_query, limit * 2)
            )
            fts_rows = await cur.fetchall()
            seen = set()
            for row in fts_rows:
                if row["id"] not in seen:
                    seen.add(row["id"])
                    results.append(MemorySearchResult(
                        id=row["id"], type=row["type"],
                        content=row["content"], importance=row["importance"],
                        score=0.8, tags=json.loads(row["tags"] or "[]")
                    ))
        except Exception:
            pass

        # TF-IDF se poucos resultados
        if len(results) < 3 and self._vectorizer is not None:
            try:
                from sklearn.metrics.pairwise import cosine_similarity
                import numpy as np
                q_vec = self._vectorizer.transform([query])
                scores = cosine_similarity(q_vec, self._tfidf_matrix).flatten()
                top_idx = scores.argsort()[::-1][:limit]
                seen_ids = {r.id for r in results}
                for idx in top_idx:
                    if scores[idx] > 0.1 and idx < len(self._tfidf_docs):
                        doc = self._tfidf_docs[idx]
                        if doc["id"] not in seen_ids:
                            seen_ids.add(doc["id"])
                            results.append(MemorySearchResult(
                                id=doc["id"], type=doc["type"],
                                content=doc["content"], importance=doc["importance"],
                                score=float(scores[idx]),
                                tags=doc.get("tags", [])
                            ))
            except Exception as e:
                logger.debug(f"TF-IDF search error: {e}")

        # Filtra por tipo se solicitado
        if memory_type:
            results = [r for r in results if r.type == memory_type]

        return sorted(results, key=lambda x: x.score * x.importance, reverse=True)[:limit]

    async def get_all(self, memory_type: str = None, limit: int = 50) -> List[Dict]:
        db = await get_db()
        if memory_type:
            cur = await db.execute(
                "SELECT * FROM memories WHERE type=? ORDER BY importance DESC, updated_at DESC LIMIT ?",
                (memory_type, limit)
            )
        else:
            cur = await db.execute(
                "SELECT * FROM memories ORDER BY importance DESC, updated_at DESC LIMIT ?",
                (limit,)
            )
        rows = await cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["tags"] = json.loads(d.get("tags") or "[]")
            except Exception:
                d["tags"] = []
            result.append(d)
        return result

    async def delete(self, memory_id: str) -> bool:
        db = await get_db()
        await db.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        await db.commit()
        return True

    async def auto_extract(self, user_msg: str, ai_response: str, source: str = "chat"):
        """Extrai automaticamente informações importantes da conversa."""
        text = f"{user_msg} {ai_response}"
        extracted = []

        for mtype, patterns in INFO_PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    if len(match) > 5:
                        extracted.append(MemoryCreate(
                            type=mtype,
                            content=match.strip(),
                            importance=0.6,
                            source=source,
                            tags=["auto-extracted"],
                        ))

        # Salva extrações (sem duplicar)
        for mem in extracted[:5]:
            await self._save_if_new(mem)

    async def _save_if_new(self, memory: MemoryCreate):
        """Salva memória se não existe conteúdo similar."""
        db = await get_db()
        cur = await db.execute(
            "SELECT id FROM memories WHERE content=? AND type=?",
            (memory.content, memory.type.value)
        )
        if not await cur.fetchone():
            await self.add(memory)

    async def _rebuild_tfidf(self):
        """Reconstrói o índice TF-IDF."""
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            import numpy as np
            db = await get_db()
            cur = await db.execute("SELECT id, type, content, importance, tags FROM memories")
            rows = await cur.fetchall()
            if not rows:
                return
            self._tfidf_docs = [
                {"id": r["id"], "type": r["type"], "content": r["content"],
                 "importance": r["importance"], "tags": json.loads(r["tags"] or "[]")}
                for r in rows
            ]
            texts = [d["content"] for d in self._tfidf_docs]
            self._vectorizer = TfidfVectorizer(max_features=5000, ngram_range=(1, 2))
            self._tfidf_matrix = self._vectorizer.fit_transform(texts)
        except Exception as e:
            logger.debug(f"TF-IDF rebuild error: {e}")

import asyncio

memory_service = MemoryService()
