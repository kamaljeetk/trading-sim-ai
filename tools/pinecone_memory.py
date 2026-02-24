"""
Pinecone memory for storing and retrieving daily trading records.
Enables strategy evolution through experience.
"""
import os
import json
from typing import List, Dict, Optional
from datetime import datetime
from dotenv import load_dotenv
from config.logging_config import get_logger

log = get_logger("tools.pinecone_memory")

load_dotenv()

PINECONE_INDEX = os.getenv("PINECONE_INDEX_NAME", "trading-memory")
PINECONE_NAMESPACE = "daily-records"
EMBEDDING_DIMENSION = 384  # all-MiniLM-L6-v2


def _get_embedder():
    """Return HuggingFace embedding function."""
    from langchain_huggingface import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


def _get_index():
    """Return Pinecone index, creating it if needed."""
    from pinecone import Pinecone, ServerlessSpec
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

    if PINECONE_INDEX not in pc.list_indexes().names():
        pc.create_index(
            name=PINECONE_INDEX,
            dimension=EMBEDDING_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(
                cloud=os.getenv("PINECONE_CLOUD", "aws"),
                region=os.getenv("PINECONE_REGION", "us-east-1"),
            )
        )
    return pc.Index(PINECONE_INDEX)


def _build_record_text(record: Dict) -> str:
    """Convert daily record dict to text for embedding."""
    return (
        f"Date: {record.get('date')} | "
        f"Macro: {record.get('macro_bias')} | "
        f"Mode: {record.get('mode')} | "
        f"Strategy: {record.get('strategy_type')} | "
        f"Assets: {', '.join(record.get('symbols', []))} | "
        f"Return: {record.get('portfolio_return', 0):.2f}% | "
        f"Lessons: {'; '.join(record.get('lessons', []))}"
    )


def store_daily_record(record: Dict, date: str) -> Optional[str]:
    """
    Embed and upsert a daily trading record into Pinecone.

    Args:
        record: Dict with keys: date, macro_bias, mode, strategy_type,
                symbols, portfolio_return, lessons
        date: ISO date string (e.g. "2026-02-23")

    Returns:
        Vector ID on success, None on failure.
    """
    try:
        index = _get_index()
        embedder = _get_embedder()
        text = _build_record_text(record)
        vector = embedder.embed_query(text)
        vector_id = f"daily-{date}"
        index.upsert(
            vectors=[{
                "id": vector_id,
                "values": vector,
                "metadata": {
                    "date": date,
                    "record_json": json.dumps(record),
                }
            }],
            namespace=PINECONE_NAMESPACE,
        )
        return vector_id
    except Exception as e:
        log.warning("[PineconeMemory] Store failed: %s", e)
        return None


def retrieve_recent_performance(n_days: int = 7) -> List[Dict]:
    """
    Retrieve recent trading day records from Pinecone.
    Queries with a neutral embedding to get the most recent records.

    Args:
        n_days: Number of recent records to retrieve.

    Returns:
        List of record dicts, sorted by date descending.
    """
    try:
        index = _get_index()
        embedder = _get_embedder()
        query_text = "recent trading performance strategy portfolio return"
        query_vector = embedder.embed_query(query_text)

        results = index.query(
            vector=query_vector,
            top_k=n_days,
            namespace=PINECONE_NAMESPACE,
            include_metadata=True,
        )

        records = []
        for match in results.matches:
            try:
                record_json = match.metadata.get("record_json", "{}")
                records.append(json.loads(record_json))
            except Exception:
                continue

        records.sort(key=lambda r: r.get("date", ""), reverse=True)
        return records

    except Exception as e:
        log.warning("[PineconeMemory] Retrieve failed: %s", e)
        return []


def retrieve_best_performing(top_k: int = 5, min_return_pct: float = 0.0) -> List[Dict]:
    """
    Retrieve the best-performing historical trading days from Pinecone.
    Used to reinforce winning strategies and macro conditions.

    Args:
        top_k: Number of top records to retrieve.
        min_return_pct: Minimum portfolio_return threshold to consider a day a "winner".

    Returns:
        List of record dicts sorted by portfolio_return descending.
    """
    try:
        index = _get_index()
        embedder = _get_embedder()
        # Query biased toward profitable outcomes
        query_text = "profitable trading day positive return winning strategy outperformed benchmark"
        query_vector = embedder.embed_query(query_text)

        results = index.query(
            vector=query_vector,
            top_k=max(top_k * 3, 20),  # over-fetch, then filter
            namespace=PINECONE_NAMESPACE,
            include_metadata=True,
        )

        records = []
        for match in results.matches:
            try:
                record_json = match.metadata.get("record_json", "{}")
                record = json.loads(record_json)
                if float(record.get("portfolio_return", -999)) >= min_return_pct:
                    records.append(record)
            except Exception:
                continue

        records.sort(key=lambda r: float(r.get("portfolio_return", 0)), reverse=True)
        return records[:top_k]

    except Exception as e:
        log.warning("[PineconeMemory] Best-performing retrieve failed: %s", e)
        return []
