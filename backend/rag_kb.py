"""
rag_kb.py
=========
Production-oriented RAG pipeline for AquaBot, the Jaldrishti wheat irrigation
assistant.

The module prefers LangChain + Ollama embeddings + FAISS, and automatically
falls back to a local TF-IDF retriever when optional services or models are not
available. This keeps the chatbot useful during Docker startup, local
development, and partial outages.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import threading
import time
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Generator, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

_THIS_DIR = Path(__file__).parent
KB_DIR = _THIS_DIR / "data"
DEFAULT_INDEX_DIR = KB_DIR / ".rag_index"


def _env_int(name: str, default: int, min_value: int = 1, max_value: int = 100000) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        return max(min_value, min(value, max_value))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float, min_value: float = 0.0, max_value: float = 5.0) -> float:
    try:
        value = float(os.getenv(name, str(default)))
        return max(min_value, min(value, max_value))
    except (TypeError, ValueError):
        return default


def _model_chain_from_env() -> List[str]:
    raw = os.getenv(
        "AQUABOT_MODEL_CHAIN",
        os.getenv("OLLAMA_MODEL_CHAIN", "llama3.2:3b,qwen2.5:3b"),
    )
    models = [m.strip() for m in raw.split(",") if m.strip()]
    return models or ["llama3.2:3b", "qwen2.5:3b"]


MODEL_CHAIN: List[str] = _model_chain_from_env()


@dataclass(frozen=True)
class RAGSettings:
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://ollama:11434")
    embedding_model: str = os.getenv("AQUABOT_EMBEDDING_MODEL", "nomic-embed-text")
    vector_backend: str = os.getenv("AQUABOT_VECTOR_BACKEND", "faiss").lower()
    index_dir: Path = Path(os.getenv("AQUABOT_VECTOR_DIR", str(DEFAULT_INDEX_DIR)))
    chunk_size: int = _env_int("AQUABOT_CHUNK_SIZE", 850, 300, 2200)
    chunk_overlap: int = _env_int("AQUABOT_CHUNK_OVERLAP", 120, 0, 500)
    top_k: int = _env_int("AQUABOT_TOP_K", 5, 1, 12)
    max_tokens: int = _env_int("AQUABOT_MAX_TOKENS", 650, 80, 3000)
    num_ctx: int = _env_int("AQUABOT_NUM_CTX", 4096, 1024, 32768)
    request_timeout: int = _env_int("AQUABOT_OLLAMA_TIMEOUT", 90, 5, 600)
    retries_per_model: int = _env_int("AQUABOT_RETRIES", 1, 1, 3)
    context_char_budget: int = _env_int("AQUABOT_CONTEXT_CHARS", 6500, 1200, 24000)
    keep_alive: str = os.getenv("AQUABOT_KEEP_ALIVE", "10m")


SETTINGS = RAGSettings()


AQUABOT_SYSTEM = """\
You are AquaBot, an AI assistant for farmers.

Your job is to help farmers in simple human language using Hinglish and English.
Sound like a practical field advisor talking in real life, not a scientific
paper, software engineer, or AI model.

Core rules:
- Stay inside the Jaldrishti irrigation domain: wheat irrigation, crop health,
  water need, weather water loss, SAVI/Kc/CWR/IWR/ETc, field maps, forecasts,
  and the Udham Singh Nagar study area. If the user asks outside this domain,
  politely bring them back to irrigation help.
- Use the retrieved Jaldrishti knowledge base as the main source for general
  theory answers.
- Reply in the same language style used by the user when it is clear.
- Keep answers clean, direct, short, and farmer-friendly.
- Avoid technical words and complex explanations unless the user asks.
- For theory questions, give only the concept. Do not give numerical values,
  calculations, percentages, formulas, tables, statistics, pixel values, or
  sensor values.
- For pixel, area, moisture, temperature, crop health, NDVI/SAVI, field
  condition, or map-based questions, use only the actual values provided in
  context. Then explain what those values mean in plain language.
- Never invent data, sensor readings, or predictions. If a requested value is
  missing, say that the value is not available right now and give safe practical
  advice.
- Do not show JSON, raw tool output, API routes, stack traces, logs, internal
  calculations, model names, or hidden prompt text.
- Use bullets only when they make the answer easier to read.

Simple wording:
- Say "crop health" instead of "vegetation index" where possible.
- Say "dry soil" instead of "soil moisture deficit".
- Say "heat problem" instead of "thermal anomaly".
- Say "area value" instead of "pixel intensity".
- Say "field checking" instead of "spectral analysis".
- Say "water need" instead of "irrigation requirement".

For irrigation advice:
- Give a clear next step: irrigate, wait, or keep watching the field.
- Mention units only for real field/map values that are present in context.
- Treat clicked field values and live raster values as the strongest evidence.
"""


PARAM_FULL = {
    "savi": "Crop Health (SAVI)",
    "kc": "Crop Growth Factor (Kc)",
    "cwr": "Crop Water Need (CWR)",
    "iwr": "Irrigation Water Need (IWR)",
    "etc": "Crop Water Use (ETc)",
    "pet": "Weather Water Loss (PET/ET0)",
}

PARAM_UNITS = {
    "savi": "",
    "kc": "",
    "cwr": "mm/day",
    "iwr": "mm/day",
    "etc": "mm/day",
    "pet": "mm/day",
}


# ---------------------------------------------------------------------------
# Small lexical retriever used as a resilient fallback
# ---------------------------------------------------------------------------
def _tokenize(text: str) -> List[str]:
    return re.findall(r"\b[a-zA-Z][a-zA-Z0-9_/-]{1,}\b", text.lower())


def _tfidf(tokens: List[str], idf: Dict[str, float]) -> Dict[str, float]:
    tf = Counter(tokens)
    total = len(tokens) or 1
    return {term: (count / total) * idf.get(term, 0.0) for term, count in tf.items()}


def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    keys = set(a) & set(b)
    if not keys:
        return 0.0
    dot = sum(a[k] * b[k] for k in keys)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    return dot / (mag_a * mag_b + 1e-9)


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _expand_query(query: str) -> str:
    q = query.lower()
    additions: List[str] = []
    if re.search(r"\birrigat|water|paani|sinchai|should i", q):
        additions.extend(["IWR", "CWR", "effective rainfall", "irrigation decision", "water depth"])
    if re.search(r"\bsavi|vegetation|health|green|canopy", q):
        additions.extend(["SAVI", "crop health", "Kc", "growth stage"])
    if re.search(r"\bforecast|predict|next|5|10|15", q):
        additions.extend(["SARIMAX", "forecast window", "cumulative IWR", "CWR outlook"])
    if re.search(r"\bstage|das|heading|tillering|grain", q):
        additions.extend(["Rabi wheat growth stage", "DAS", "critical irrigation"])
    if re.search(r"\budham|nagar|uttarakhand|region|area", q):
        additions.extend(["Udham Singh Nagar", "Terai", "study area"])
    return " ".join([query] + additions)


@dataclass
class RetrievedChunk:
    score: float
    content: str
    title: str
    source: str
    section: str = ""
    tags: List[str] = field(default_factory=list)

    def source_id(self) -> str:
        return Path(self.source).name if self.source else self.title

    def public_title(self) -> str:
        return self.section or self.title or self.source_id()

    def to_public(self) -> Dict[str, Any]:
        return {
            "title": self.public_title(),
            "source": self.source_id(),
            "score": round(float(self.score), 4),
        }


class LexicalIndex:
    def __init__(self, chunks: List[Dict[str, Any]]):
        self.chunks = chunks
        corpus = [
            _tokenize(
                " ".join(
                    [
                        c.get("content", ""),
                        c.get("title", ""),
                        c.get("section", ""),
                        " ".join(c.get("tags", [])),
                    ]
                )
            )
            for c in chunks
        ]
        doc_count = len(corpus) or 1
        df: Counter = Counter()
        for toks in corpus:
            df.update(set(toks))
        self.idf = {term: math.log((doc_count + 1) / (df[term] + 1)) + 1 for term in df}
        self.vectors = [_tfidf(tokens, self.idf) for tokens in corpus]

    def search(self, query: str, top_k: int) -> List[RetrievedChunk]:
        q_vec = _tfidf(_tokenize(_expand_query(query)), self.idf)
        scored = [(_cosine(q_vec, vector), chunk) for vector, chunk in zip(self.vectors, self.chunks)]
        scored.sort(key=lambda item: item[0], reverse=True)

        results: List[RetrievedChunk] = []
        for score, chunk in scored[:top_k]:
            if score <= 0.005:
                continue
            results.append(
                RetrievedChunk(
                    score=float(score),
                    content=chunk.get("content", ""),
                    title=chunk.get("title", ""),
                    source=chunk.get("source", ""),
                    section=chunk.get("section", ""),
                    tags=list(chunk.get("tags", [])),
                )
            )
        return results


# ---------------------------------------------------------------------------
# Knowledge base loading and chunking
# ---------------------------------------------------------------------------
def _kb_paths(kb_dir: Path = KB_DIR) -> List[Path]:
    configured = os.getenv("AQUABOT_KB_FILES", "").strip()
    if configured:
        paths = []
        for part in configured.split(","):
            p = Path(part.strip())
            if not p.is_absolute():
                p = kb_dir / p
            if p.exists() and p.suffix.lower() == ".txt":
                paths.append(p)
        if paths:
            return sorted(paths)

    primary = kb_dir / "jaldrishti_knowledge_base.txt"
    if primary.exists():
        return [primary]
    return sorted(kb_dir.glob("*.txt")) if kb_dir.exists() else []


def _file_signature(paths: List[Path], settings: RAGSettings) -> Dict[str, Any]:
    digest = hashlib.sha256()
    file_meta = []
    for path in paths:
        stat = path.stat()
        raw = path.read_bytes()
        digest.update(path.name.encode("utf-8"))
        digest.update(raw)
        file_meta.append({"name": path.name, "size": stat.st_size, "mtime": int(stat.st_mtime)})
    return {
        "digest": digest.hexdigest(),
        "files": file_meta,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "embedding_model": settings.embedding_model,
        "vector_backend": settings.vector_backend,
    }


def _extract_title_tags(raw: str, path: Path) -> Tuple[str, List[str], str]:
    title = path.stem.replace("_", " ").title()
    tags: List[str] = []
    body_lines: List[str] = []
    for line in raw.splitlines():
        if line.startswith("TITLE:"):
            title = line[6:].strip() or title
        elif line.startswith("TAGS:"):
            tags = [tag.strip() for tag in line[5:].split(",") if tag.strip()]
        else:
            body_lines.append(line)
    return title, tags, "\n".join(body_lines)


def _clean_section_title(line: str) -> str:
    line = line.strip().strip("#").strip()
    line = re.sub(r"^SECTION\s+\d+\s*:\s*", "", line, flags=re.IGNORECASE)
    return line or "Knowledge"


def _split_semantic_sections(raw: str, path: Path) -> List[Dict[str, Any]]:
    title, tags, body = _extract_title_tags(raw, path)
    sections: List[Dict[str, Any]] = []
    current_title = title
    current_lines: List[str] = []

    def flush() -> None:
        content = _normalize_whitespace("\n".join(current_lines))
        if not content:
            return
        sections.append(
            {
                "title": title,
                "section": current_title,
                "content": content,
                "source": str(path),
                "tags": tags,
            }
        )

    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if re.match(r"^\s*=+\s*$", line):
            continue
        is_heading = bool(re.match(r"^\s*(#{1,4}\s+|SECTION\s+\d+\s*:)", line, flags=re.IGNORECASE))
        if is_heading:
            flush()
            current_title = _clean_section_title(line)
            current_lines = [current_title]
            continue
        current_lines.append(line)

    flush()
    if not sections and body.strip():
        sections.append(
            {
                "title": title,
                "section": title,
                "content": _normalize_whitespace(body),
                "source": str(path),
                "tags": tags,
            }
        )
    return sections


def _manual_chunks(section: Dict[str, Any], chunk_size: int, overlap: int) -> List[Dict[str, Any]]:
    text = section["content"]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: List[Dict[str, Any]] = []
    buf: List[str] = []
    size = 0

    def emit() -> None:
        nonlocal buf, size
        if not buf:
            return
        content = "\n\n".join(buf).strip()
        if content:
            chunks.append({**section, "content": content})
        if overlap > 0 and content:
            tail = content[-overlap:]
            buf = [tail]
            size = len(tail)
        else:
            buf = []
            size = 0

    for para in paragraphs:
        if len(para) > chunk_size:
            emit()
            start = 0
            step = max(1, chunk_size - overlap)
            while start < len(para):
                piece = para[start : start + chunk_size].strip()
                if piece:
                    chunks.append({**section, "content": piece})
                start += step
            continue
        if size + len(para) + 2 > chunk_size:
            emit()
        buf.append(para)
        size += len(para) + 2
    emit()
    return chunks


def _build_chunks(paths: List[Path], settings: RAGSettings) -> Tuple[List[Dict[str, Any]], List[Any]]:
    sections: List[Dict[str, Any]] = []
    for path in paths:
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("[rag_kb] Cannot read %s: %s", path, exc)
            continue
        sections.extend(_split_semantic_sections(raw, path))

    chunks: List[Dict[str, Any]] = []
    documents: List[Any] = []

    try:
        from langchain_core.documents import Document
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        docs = [
            Document(
                page_content=section["content"],
                metadata={
                    "title": section["title"],
                    "section": section["section"],
                    "source": section["source"],
                    "tags": section["tags"],
                },
            )
            for section in sections
        ]
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            separators=["\n## ", "\n### ", "\nQ:", "\n- ", "\n\n", "\n", ". ", " "],
        )
        split_docs = splitter.split_documents(docs)
        for index, doc in enumerate(split_docs):
            metadata = dict(doc.metadata or {})
            metadata["chunk_id"] = f"{Path(metadata.get('source', 'kb')).name}:{index}"
            documents.append(Document(page_content=doc.page_content, metadata=metadata))
            chunks.append(
                {
                    "content": doc.page_content,
                    "title": metadata.get("title", ""),
                    "section": metadata.get("section", ""),
                    "source": metadata.get("source", ""),
                    "tags": list(metadata.get("tags", [])),
                    "chunk_id": metadata["chunk_id"],
                }
            )
    except Exception as exc:
        logger.info("[rag_kb] LangChain splitter unavailable, using manual chunker: %s", exc)
        for section in sections:
            chunks.extend(_manual_chunks(section, settings.chunk_size, settings.chunk_overlap))

    return chunks, documents


class AdvancedKnowledgeStore:
    """Hybrid vector store: FAISS/Ollama embeddings first, lexical fallback always."""

    def __init__(self, paths: List[Path], settings: RAGSettings = SETTINGS):
        self.settings = settings
        self.paths = paths
        self.signature = _file_signature(paths, settings) if paths else {}
        self.chunks, self.documents = _build_chunks(paths, settings)
        self.lexical = LexicalIndex(self.chunks)
        self.vectorstore: Optional[Any] = None
        self.backend = "lexical_fallback"
        self.error: Optional[str] = None

        if self.chunks and settings.vector_backend == "faiss":
            self._init_faiss()

        logger.info(
            "[rag_kb] Knowledge store ready: %s files, %s chunks, backend=%s",
            len(paths),
            len(self.chunks),
            self.backend,
        )

    def _make_embeddings(self) -> Any:
        try:
            from langchain_ollama import OllamaEmbeddings

            return OllamaEmbeddings(model=self.settings.embedding_model, base_url=self.settings.ollama_host)
        except Exception:
            from langchain_community.embeddings import OllamaEmbeddings

            return OllamaEmbeddings(model=self.settings.embedding_model, base_url=self.settings.ollama_host)

    def _signature_path(self) -> Path:
        return self.settings.index_dir / "signature.json"

    def _signature_matches(self) -> bool:
        try:
            if not self._signature_path().exists():
                return False
            stored = json.loads(self._signature_path().read_text(encoding="utf-8"))
            return stored == self.signature
        except Exception:
            return False

    def _save_signature(self) -> None:
        try:
            self.settings.index_dir.mkdir(parents=True, exist_ok=True)
            self._signature_path().write_text(json.dumps(self.signature, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.debug("[rag_kb] Could not save FAISS signature: %s", exc)

    def _init_faiss(self) -> None:
        try:
            from langchain_community.vectorstores import FAISS

            embeddings = self._make_embeddings()
            index_exists = (self.settings.index_dir / "index.faiss").exists()

            if index_exists and self._signature_matches():
                self.vectorstore = FAISS.load_local(
                    str(self.settings.index_dir),
                    embeddings,
                    allow_dangerous_deserialization=True,
                )
                self.backend = "faiss_ollama_cached"
                return

            if not self.documents:
                raise RuntimeError("No LangChain documents were produced for FAISS")

            self.vectorstore = FAISS.from_documents(self.documents, embeddings)
            self.settings.index_dir.mkdir(parents=True, exist_ok=True)
            self.vectorstore.save_local(str(self.settings.index_dir))
            self._save_signature()
            self.backend = "faiss_ollama"
        except Exception as exc:
            self.vectorstore = None
            self.backend = "lexical_fallback"
            self.error = str(exc)[:240]
            logger.warning("[rag_kb] FAISS/Ollama embeddings unavailable; using lexical fallback: %s", self.error)

    def _search_faiss(self, query: str, top_k: int) -> List[RetrievedChunk]:
        if self.vectorstore is None:
            return []
        raw = self.vectorstore.similarity_search_with_score(_expand_query(query), k=top_k)
        results: List[RetrievedChunk] = []
        for doc, distance in raw:
            metadata = dict(doc.metadata or {})
            try:
                score = 1.0 / (1.0 + float(distance))
            except (TypeError, ValueError):
                score = 0.0
            results.append(
                RetrievedChunk(
                    score=score,
                    content=doc.page_content,
                    title=metadata.get("title", ""),
                    source=metadata.get("source", ""),
                    section=metadata.get("section", ""),
                    tags=list(metadata.get("tags", [])),
                )
            )
        return results

    def search(self, query: str, top_k: int = 5) -> List[RetrievedChunk]:
        top_k = max(1, min(top_k, 12))
        if self.vectorstore is not None:
            try:
                hits = self._search_faiss(query, top_k)
                if hits:
                    return hits
            except Exception as exc:
                self.error = str(exc)[:240]
                logger.warning("[rag_kb] FAISS search failed, falling back to lexical: %s", self.error)
        return self.lexical.search(query, top_k=top_k)


# ---------------------------------------------------------------------------
# Prompting and message assembly
# ---------------------------------------------------------------------------
def _format_live_data(live_data: Optional[Dict[str, Any]]) -> str:
    if not live_data:
        return ""
    lines: List[str] = []
    for param in ("savi", "kc", "cwr", "iwr", "etc", "pet"):
        value = live_data.get(param)
        if value is None:
            continue
        name = PARAM_FULL.get(param, param.upper())
        unit = PARAM_UNITS.get(param, "")
        lines.append(f"- {name}: {value} {unit}".strip())

    if live_data.get("query_location"):
        lines.append(f"- Clicked field area: {live_data['query_location']}")
    for param in ("savi", "kc", "cwr", "iwr", "etc"):
        value = live_data.get(f"point_{param}")
        if value is None:
            continue
        unit = PARAM_UNITS.get(param, "")
        lines.append(f"- Point {PARAM_FULL.get(param, param.upper())}: {value} {unit}".strip())

    return "\n".join(lines)


def _build_system_prompt(
    live_data: Optional[Dict[str, Any]],
    rag_chunks: List[RetrievedChunk],
    structured_context: Optional[str],
    settings: RAGSettings = SETTINGS,
    include_live_data: bool = False,
) -> str:
    parts = [AQUABOT_SYSTEM]

    # Only inject live raster values when the user explicitly asked for them.
    # For general knowledge / theory queries the live block is omitted so the
    # LLM stays grounded in the knowledge base instead of citing sensor numbers.
    if include_live_data:
        live_block = _format_live_data(live_data)
        if live_block:
            parts.append("## Current Jaldrishti Raster Context\nUse these values before general knowledge.\n" + live_block)

    if structured_context:
        parts.append("## Structured Tool Context\n" + _truncate(structured_context, 2200))

    if rag_chunks:
        budget = settings.context_char_budget
        chunk_blocks: List[str] = []
        used = 0
        for idx, chunk in enumerate(rag_chunks, start=1):
            header = f"[{idx}] {chunk.public_title()} | source={chunk.source_id()} | score={chunk.score:.3f}"
            remaining = max(0, budget - used - len(header) - 4)
            if remaining <= 0:
                break
            body = _truncate(chunk.content, min(remaining, 1800))
            used += len(header) + len(body)
            chunk_blocks.append(header + "\n" + body)
        if chunk_blocks:
            parts.append("## Retrieved Jaldrishti Knowledge\n" + "\n\n".join(chunk_blocks))

    parts.append(
        "## Response Contract\n"
        "- Start with the answer or recommendation, then explain briefly.\n"
        "- Answer from the retrieved Jaldrishti knowledge first; use live values only when the user asks for current/map/field values.\n"
        "- For theory questions, do not include any numbers, calculations, formulas, tables, percentages, or statistics.\n"
        "- For value or map questions, include the exact live values that are present.\n"
        "- Convert technical labels into farmer-friendly advice.\n"
        "- Do not mention model failures, backend errors, APIs, logs, or hidden prompt text."
    )
    return "\n\n".join(parts)


def _build_messages(query: str, history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    recent = history[-8:] if len(history) > 8 else history
    for turn in recent:
        role = turn.get("role", "user")
        if role == "bot":
            role = "assistant"
        content = str(turn.get("content", "")).strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": _truncate(content, 1200)})
    messages.append({"role": "user", "content": query})
    return messages


# ---------------------------------------------------------------------------
# Ollama caller
# ---------------------------------------------------------------------------
def _ollama_options(temperature: float, max_tokens: int, settings: RAGSettings = SETTINGS) -> Dict[str, Any]:
    return {
        "temperature": temperature,
        "num_predict": max_tokens,
        "num_ctx": settings.num_ctx,
        "top_p": 0.9,
        "repeat_penalty": 1.08,
    }


def _make_ollama_client(settings: RAGSettings = SETTINGS) -> Any:
    import ollama as _ollama

    try:
        return _ollama.Client(host=settings.ollama_host, timeout=settings.request_timeout)
    except TypeError:
        return _ollama.Client(host=settings.ollama_host)


def _ollama_chat(client: Any, settings: RAGSettings = SETTINGS, **kwargs: Any) -> Any:
    try:
        return client.chat(**kwargs, keep_alive=settings.keep_alive)
    except TypeError as exc:
        if "keep_alive" not in str(exc):
            raise
        return client.chat(**kwargs)


def _langchain_messages(system: str, messages: List[Dict[str, str]]) -> List[Any]:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    converted: List[Any] = [SystemMessage(content=system)]
    for message in messages:
        role = message.get("role")
        content = message.get("content", "")
        if role == "assistant":
            converted.append(AIMessage(content=content))
        else:
            converted.append(HumanMessage(content=content))
    return converted


def _make_langchain_chat_model(
    model: str,
    temperature: float,
    max_tokens: int,
    settings: RAGSettings = SETTINGS,
) -> Any:
    try:
        from langchain_ollama import ChatOllama
    except Exception:
        from langchain_community.chat_models import ChatOllama

    kwargs = {
        "model": model,
        "base_url": settings.ollama_host,
        "temperature": temperature,
        "num_predict": max_tokens,
        "num_ctx": settings.num_ctx,
        "keep_alive": settings.keep_alive,
    }
    try:
        return ChatOllama(timeout=settings.request_timeout, **kwargs)
    except TypeError:
        return ChatOllama(**kwargs)


def _message_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content or "")


def _call_ollama(
    system: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 650,
    settings: RAGSettings = SETTINGS,
) -> Tuple[Optional[str], str, List[Dict[str, Any]]]:
    attempts: List[Dict[str, Any]] = []

    for model in MODEL_CHAIN:
        for attempt_no in range(settings.retries_per_model):
            start = time.time()
            try:
                chat_model = _make_langchain_chat_model(model, temperature, max_tokens, settings)
                resp = chat_model.invoke(_langchain_messages(system, messages))
                elapsed = int((time.time() - start) * 1000)
                text = _message_text(resp).strip()
                if text:
                    attempts.append(
                        {"model": model, "status": "success", "attempt": attempt_no + 1, "ms": elapsed}
                    )
                    return text, model, attempts
                attempts.append(
                    {"model": model, "status": "empty", "attempt": attempt_no + 1, "ms": elapsed}
                )
            except Exception as exc:
                elapsed = int((time.time() - start) * 1000)
                err = str(exc)[:180]
                attempts.append(
                    {"model": model, "status": "failed", "attempt": attempt_no + 1, "error": err, "ms": elapsed}
                )
                logger.warning("[rag_kb] %s attempt %s failed in %sms: %s", model, attempt_no + 1, elapsed, err)

    return None, "none", attempts


def _stream_ollama(
    system: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 650,
    settings: RAGSettings = SETTINGS,
) -> Generator[Dict[str, Any], None, None]:
    attempts: List[Dict[str, Any]] = []

    for model in MODEL_CHAIN:
        start = time.time()
        token_count = 0
        try:
            yield {"type": "status", "model": model, "status": "running"}
            chat_model = _make_langchain_chat_model(model, temperature, max_tokens, settings)
            stream = chat_model.stream(_langchain_messages(system, messages))
            for chunk in stream:
                token = _message_text(chunk)
                if not token:
                    continue
                token_count += 1
                yield {"type": "token", "model": model, "content": token}

            elapsed = int((time.time() - start) * 1000)
            if token_count > 0:
                attempts.append({"model": model, "status": "success", "ms": elapsed, "chunks": token_count})
                yield {"type": "model_done", "model": model, "attempts": attempts}
                return
            attempts.append({"model": model, "status": "empty", "ms": elapsed})
        except Exception as exc:
            elapsed = int((time.time() - start) * 1000)
            err = str(exc)[:180]
            attempts.append({"model": model, "status": "failed", "error": err, "ms": elapsed})
            logger.warning("[rag_kb] stream %s failed in %sms: %s", model, elapsed, err)

    yield {"type": "error", "model": "none", "error": "All Ollama models failed", "attempts": attempts}


# ---------------------------------------------------------------------------
# Live metric intent and unavailable responses
# ---------------------------------------------------------------------------
_FALLBACK_RULES: List[Tuple[str, str]] = [
    (
        r"\bcwr\b|crop water",
        "CWR means crop water need. It tells how much water the crop may use in a day. If this value is high, the crop needs more water.",
    ),
    (
        r"\biwr\b|irrigation water",
        "IWR means irrigation water need. It tells how much extra water may be needed after rainfall. If this value is high, plan irrigation soon.",
    ),
    (
        r"\bsavi\b|\bndvi\b|vegetation|canopy|crop health",
        "SAVI helps check crop health from satellite images. A higher value usually means the crop is greener and healthier. A low value can mean young crop, thin crop cover, or stress.",
    ),
    (
        r"\bkc\b|crop coefficient",
        "Kc shows how much water the crop needs at its current growth stage. It is lower in early growth, higher during strong growth, and lower again near harvest.",
    ),
    (
        r"\bforecast|predict|next",
        "The forecast gives an idea of crop water need for the coming days. Use the nearest forecast first, and keep checking the field if weather changes.",
    ),
    (
        r"\budham|uttarakhand|region|study area",
        "The study area is Udham Singh Nagar in Uttarakhand. It is a Terai wheat-growing area where Rabi irrigation is usually important from November to April.",
    ),
]

_FRIENDLY_PARAM_LABELS = {
    "savi": "Crop health value",
    "kc": "Crop growth factor",
    "cwr": "Crop water need",
    "iwr": "Irrigation water need",
    "etc": "Crop water use",
    "pet": "Weather water loss",
}


def _query_asks_for_values(query: str) -> bool:
    q = query.lower()
    if re.search(r"\b(why|how|what happens|what does|what is|explain|meaning|mean)\b", q) and not re.search(
        r"\b(value|level|current|today|now|live|pixel|area|condition|reading)\b", q
    ):
        return False
    return bool(
        re.search(
            r"\b(value|pixel|area data|moisture level|temperature|ndvi|savi|kc|cwr|iwr|etc|reading|current|today|now|live)\b",
            q,
        )
        or re.search(r"\b(field condition|condition of (this|my|the) field|this area|clicked field)\b", q)
    )


def query_requests_live_metrics(query: str) -> bool:
    """True only when the user asks for live/current field values or readings."""
    q = (query or "").lower()
    if not q.strip():
        return False

    live_terms = (
        r"\b(today|now|current|live|latest|real[- ]?time|right now|"
        r"pixel|clicked|map|field value|reading|value|values|"
        r"condition|this field|my field|this area|selected area)\b"
    )
    metric_terms = (
        r"\b(savi|ndvi|kc|cwr|iwr|etc|pet|et0|crop health|growth|"
        r"crop water|water need|irrigation water|moisture|temperature|"
        r"field|area|map|pixel|reading|metric|metrics)\b"
    )
    action_terms = (
        r"\b(irrigate|irrigation|sinchai|paani|water now|water today|"
        r"need water|should i water|should i irrigate)\b"
    )

    return bool(
        (re.search(live_terms, q) and re.search(metric_terms, q))
        or re.search(action_terms, q)
    )


def _is_theory_question(query: str) -> bool:
    q = query.lower()
    if re.search(r"\b(value|level|current|today|now|live|pixel|area|condition|reading|forecast|predict)\b", q):
        return False
    return bool(
        re.search(r"\b(what is|what does|meaning|mean|explain|why|how does|ka matlab|kya hota|kyu|kyon)\b", q)
    )


def _sanitize_theory_answer(answer: str) -> str:
    safe_lines: List[str] = []
    for line in (answer or "").splitlines():
        text = line.strip()
        if not text:
            continue
        if re.search(r"\d|%|\bpercent\b|=|≈|~|\|", text, re.IGNORECASE):
            continue
        safe_lines.append(text)

    cleaned = "\n".join(safe_lines).strip()
    return cleaned or (
        "Iska simple matlab hai ki crop ya mitti ki condition ko samajhkar "
        "sahi samay par paani dena. Field ko zyada sukha ya zyada geela mat hone do."
    )


def _requested_value_params(query: str) -> List[str]:
    q = query.lower()
    selected: List[str] = []
    checks = [
        ("savi", r"\bsavi\b|\bndvi\b|crop health|vegetation|green"),
        ("kc", r"\bkc\b|growth factor|crop coefficient|growth stage"),
        ("cwr", r"\bcwr\b|crop water|water need"),
        ("iwr", r"\biwr\b|irrigation water|irrigation need|moisture|dry"),
        ("etc", r"\betc\b|crop water use|water use"),
        ("pet", r"\bpet\b|\bet0\b|weather water|evaporation"),
    ]
    for param, pattern in checks:
        if re.search(pattern, q):
            selected.append(param)

    if not selected and re.search(r"\b(value|pixel|area|condition|current|today|now|live|reading)\b", q):
        selected = ["savi", "iwr", "cwr", "kc"]

    return list(dict.fromkeys(selected))


def _live_value(live_data: Dict[str, Any], param: str) -> Any:
    point_value = live_data.get(f"point_{param}")
    if point_value is not None:
        return point_value
    return live_data.get(param)


def _format_live_value(param: str, value: Any) -> str:
    number = _safe_float(value)
    if number is None:
        return str(value)
    precision = 3 if param in {"savi", "kc"} else 2
    formatted = f"{number:.{precision}f}"
    unit = PARAM_UNITS.get(param, "")
    return f"{formatted} {unit}".strip()


def _simple_metric_meaning(param: str, value: Any) -> str:
    number = _safe_float(value)
    if number is None:
        return "Use this as a field reading and compare it with nearby areas."

    if param == "savi":
        if number < 0.15:
            return "Crop cover looks low, so check for early growth, bare soil, or stress."
        if number < 0.35:
            return "Crop health looks moderate."
        return "Crop looks fairly green and healthy."
    if param == "iwr":
        if number > 4.0:
            return "Water need is high, so irrigation should be done soon."
        if number > 2.0:
            return "Water may be needed in the next few days."
        if number > 0.1:
            return "Water need is light right now."
        return "Irrigation is not needed right now unless the field looks stressed."
    if param == "cwr":
        if number > 4.0:
            return "The crop is using more water, so watch the field closely."
        if number > 2.0:
            return "The crop has a moderate water need."
        return "The crop water need is low right now."
    if param == "kc":
        if number > 0.9:
            return "The crop is in a high water-demand stage."
        if number > 0.5:
            return "The crop has a medium water demand."
        return "The crop is in a lower water-demand stage."
    if param == "etc":
        return "This shows how much water the crop is using from soil and air."
    if param == "pet":
        return "This shows how strongly the weather can pull water from the field."
    return "This is the current field value."


def _fallback_live_values(query: str, live_data: Optional[Dict[str, Any]]) -> Optional[str]:
    if not live_data or not _query_asks_for_values(query):
        return None

    q = query.lower()
    if "temperature" in q and not any(k in live_data for k in ("temperature", "temp", "point_temperature", "point_temp")):
        return "I do not have the field temperature value right now. I can still help with crop health and water need from the available field data."

    if "moisture" in q and not any(k in live_data for k in ("moisture", "soil_moisture", "point_moisture")):
        iwr = _live_value(live_data, "iwr")
        if iwr is not None:
            return (
                "I do not have a direct soil moisture number for this field. "
                f"The irrigation water need is {_format_live_value('iwr', iwr)}. "
                f"{_simple_metric_meaning('iwr', iwr)}"
            )

    params = _requested_value_params(query)
    lines = ["For the clicked area:" if live_data.get("query_location") else "For the current field area:"]

    for param in params:
        value = _live_value(live_data, param)
        if value is None:
            continue
        label = _FRIENDLY_PARAM_LABELS.get(param, param.upper())
        lines.append(f"- {label}: {_format_live_value(param, value)}. {_simple_metric_meaning(param, value)}")

    return "\n".join(lines) if len(lines) > 1 else None


def _fallback_irrigation_decision(live_data: Optional[Dict[str, Any]]) -> Optional[str]:
    if not live_data:
        return None
    iwr = _safe_float(live_data.get("point_iwr", live_data.get("iwr")))
    cwr = _safe_float(live_data.get("point_cwr", live_data.get("cwr")))
    kc = _safe_float(live_data.get("point_kc", live_data.get("kc")))
    if iwr is None:
        return None

    if iwr > 4.0:
        decision = "Irrigate soon. The water need is high."
    elif iwr > 2.0:
        decision = "Plan irrigation in the next few days and keep checking the field."
    elif iwr > 0.1:
        decision = "Keep watching the field. The water need is light right now."
    else:
        decision = "Do not irrigate now unless the crop looks stressed."

    details = [f"Irrigation water need: {iwr:.2f} mm/day"]
    if cwr is not None:
        details.append(f"Crop water need: {cwr:.2f} mm/day")
    if kc is not None:
        details.append(f"Growth factor: {kc:.2f}")
    return decision + "\n\n" + " | ".join(details) + "\n\nFor 1 hectare, 1 mm of water is about 10,000 litres."


def fallback_answer(
    query: str,
    live_data: Optional[Dict[str, Any]] = None,
    rag_chunks: Optional[List[RetrievedChunk]] = None,
    structured_context: Optional[str] = None,
) -> str:
    q = query.lower()
    if re.search(r"\b(irrigat|sinchai|should i|do i need|need water|water now|water today|paani)\b", q):
        decision = _fallback_irrigation_decision(live_data)
        if decision:
            return decision

    value_answer = _fallback_live_values(query, live_data)
    if value_answer:
        return value_answer

    if re.search(r"\birrigat|water|paani|sinchai|should i", q):
        decision = _fallback_irrigation_decision(live_data)
        if decision:
            return decision

    for pattern, answer in _FALLBACK_RULES:
        if re.search(pattern, q):
            return answer

    if rag_chunks:
        best = rag_chunks[0]
        snippet = _truncate(best.content, 650)
        return (
            f"Here is the closest useful Jaldrishti guidance: {best.public_title()}.\n\n"
            f"{snippet}"
        )

    if structured_context:
        return (
            "I can use the current Jaldrishti field values. Here is what is available right now:\n\n"
            + _truncate(structured_context, 700)
        )

    return "I am having trouble checking the data right now. Please try again in a moment."


def llm_unavailable_answer() -> str:
    return (
        "I could not generate a knowledge-base answer right now because the LLM is unavailable. "
        "Please check that the configured Ollama model is installed and running, then try again."
    )


# ---------------------------------------------------------------------------
# Session history
# ---------------------------------------------------------------------------
class SessionStore:
    MAX_SESSIONS = 500
    MAX_TURNS_EACH = 24

    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: "OrderedDict[str, List[Dict[str, str]]]" = OrderedDict()

    def get(self, session_id: str) -> List[Dict[str, str]]:
        with self._lock:
            turns = list(self._sessions.get(session_id, []))
            if session_id in self._sessions:
                self._sessions.move_to_end(session_id)
            return turns

    def append(self, session_id: str, role: str, content: str) -> None:
        content = (content or "").strip()
        if not content:
            return
        with self._lock:
            if session_id not in self._sessions and len(self._sessions) >= self.MAX_SESSIONS:
                self._sessions.popitem(last=False)
            turns = self._sessions.setdefault(session_id, [])
            turns.append({"role": role, "content": _truncate(content, 3000)})
            self._sessions[session_id] = turns[-self.MAX_TURNS_EACH :]
            self._sessions.move_to_end(session_id)


_session_store = SessionStore()
_kb_store: Optional[AdvancedKnowledgeStore] = None
_kb_lock = threading.Lock()


def _get_kb() -> AdvancedKnowledgeStore:
    global _kb_store
    if _kb_store is None:
        with _kb_lock:
            if _kb_store is None:
                paths = _kb_paths()
                if not paths:
                    logger.warning("[rag_kb] No knowledge base .txt files found in %s", KB_DIR)
                _kb_store = AdvancedKnowledgeStore(paths, SETTINGS)
    return _kb_store


def reload_kb() -> int:
    """Hot-reload the knowledge base and rebuild the retriever."""
    global _kb_store
    with _kb_lock:
        paths = _kb_paths()
        _kb_store = AdvancedKnowledgeStore(paths, SETTINGS)
    logger.info("[rag_kb] Knowledge base reloaded: %s chunks", len(_kb_store.chunks))
    return len(_kb_store.chunks)


def rag_health() -> Dict[str, Any]:
    kb = _get_kb()
    return {
        "status": "ok",
        "backend": kb.backend,
        "kb_files": [path.name for path in kb.paths],
        "chunks": len(kb.chunks),
        "embedding_model": SETTINGS.embedding_model,
        "ollama_host": SETTINGS.ollama_host,
        "model_chain": MODEL_CHAIN,
        "fallback_reason": kb.error,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_chat_answer(
    query: str,
    live_data: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, str]]] = None,
    session_id: str = "default",
    structured_context: Optional[str] = None,
    top_k: Optional[int] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    start = time.time()
    kb = _get_kb()
    retrieve_start = time.time()
    rag_hits = kb.search(query, top_k=top_k or SETTINGS.top_k)
    retrieval_ms = int((time.time() - retrieve_start) * 1000)
    logger.info("[rag_kb] RAG hits for %r: %s", query[:70], [h.public_title() for h in rag_hits])

    include_live_metrics = query_requests_live_metrics(query)
    combined_history = (history or [])[-12:]
    system = _build_system_prompt(
        live_data, rag_hits, structured_context, include_live_data=include_live_metrics
    )
    messages = _build_messages(query, combined_history)

    answer, model_used, attempts = _call_ollama(
        system=system,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens or SETTINGS.max_tokens,
    )

    if not answer:
        answer = llm_unavailable_answer()
        model_used = "llm_unavailable"

    if _is_theory_question(query):
        answer = _sanitize_theory_answer(answer)

    elapsed = int((time.time() - start) * 1000)
    sources = list(
        dict.fromkeys(
            [hit.source_id() for hit in rag_hits]
            + (["live_raster"] if live_data and include_live_metrics else [])
            + (["structured_data"] if structured_context else [])
        )
    )

    return {
        "answer": answer,
        "sources": sources,
        "model_used": model_used,
        "rag_chunks": [hit.public_title() for hit in rag_hits],
        "retrieved_context": [hit.to_public() for hit in rag_hits],
        "attempts": attempts,
        "latency_ms": elapsed,
        "retrieval_ms": retrieval_ms,
        "rag_backend": kb.backend,
        "include_live_metrics": include_live_metrics,
    }


def _stream_text(text: str, chunk_size: int = 24) -> Iterable[str]:
    for index in range(0, len(text), chunk_size):
        yield text[index : index + chunk_size]


def stream_chat_answer(
    query: str,
    live_data: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, str]]] = None,
    session_id: str = "default",
    structured_context: Optional[str] = None,
    top_k: Optional[int] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
) -> Generator[Dict[str, Any], None, None]:
    start = time.time()
    kb = _get_kb()
    retrieve_start = time.time()
    rag_hits = kb.search(query, top_k=top_k or SETTINGS.top_k)
    retrieval_ms = int((time.time() - retrieve_start) * 1000)

    include_live_metrics = query_requests_live_metrics(query)
    sources = list(
        dict.fromkeys(
            [hit.source_id() for hit in rag_hits]
            + (["live_raster"] if live_data and include_live_metrics else [])
            + (["structured_data"] if structured_context else [])
        )
    )

    yield {
        "type": "meta",
        "sources": sources,
        "rag_chunks": [hit.public_title() for hit in rag_hits],
        "retrieved_context": [hit.to_public() for hit in rag_hits],
        "retrieval_ms": retrieval_ms,
        "rag_backend": kb.backend,
        "include_live_metrics": include_live_metrics,
    }

    combined_history = (history or [])[-12:]
    system = _build_system_prompt(
        live_data, rag_hits, structured_context, include_live_data=include_live_metrics
    )
    messages = _build_messages(query, combined_history)

    answer_parts: List[str] = []
    model_used = "none"
    attempts: List[Dict[str, Any]] = []
    theory_question = _is_theory_question(query)

    for event in _stream_ollama(
        system=system,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens or SETTINGS.max_tokens,
    ):
        if event.get("type") == "token":
            token = event.get("content", "")
            answer_parts.append(token)
            model_used = event.get("model", model_used)
            if not theory_question:
                yield event
        elif event.get("type") == "model_done":
            model_used = event.get("model", model_used)
            attempts = list(event.get("attempts", []))
        elif event.get("type") == "status":
            yield event
        elif event.get("type") == "error":
            attempts = list(event.get("attempts", []))

    answer = "".join(answer_parts).strip()
    if not answer:
        answer = llm_unavailable_answer()
        model_used = "llm_unavailable"

    if theory_question:
        answer = _sanitize_theory_answer(answer)
        for token in _stream_text(answer):
            yield {"type": "token", "model": model_used, "content": token}
    elif model_used == "llm_unavailable":
        for token in _stream_text(answer):
            yield {"type": "token", "model": model_used, "content": token}

    elapsed = int((time.time() - start) * 1000)
    yield {
        "type": "done",
        "answer": answer,
        "sources": sources,
        "model_used": model_used,
        "rag_chunks": [hit.public_title() for hit in rag_hits],
        "retrieved_context": [hit.to_public() for hit in rag_hits],
        "attempts": attempts,
        "latency_ms": elapsed,
        "retrieval_ms": retrieval_ms,
        "rag_backend": kb.backend,
        "include_live_metrics": include_live_metrics,
    }