"""
Source Independence Module for Lumen.
Detects near-duplicate or copied sources using text similarity (word n-grams, Jaccard, containment, SequenceMatcher),
groups them under one canonical original source, and updates source metadata.
"""

import re
import string
import difflib
import sqlite3
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime

try:
    from app.database import get_db_connection, row_to_dict
except ImportError:
    from database import get_db_connection, row_to_dict


def _normalize_text_for_comparison(text: str) -> List[str]:
    """Tokenize and normalize text into clean lowercase words for n-gram comparison."""
    if not text:
        return []
    # Lowercase
    cleaned = text.lower()
    # Replace punctuation with space
    cleaned = re.sub(r'[\r\n\t]+', ' ', cleaned)
    cleaned = re.sub(r'[' + re.escape(string.punctuation) + r']', ' ', cleaned)
    # Split into words
    words = [w for w in cleaned.split() if len(w) > 1]
    return words


def _get_word_ngrams(words: List[str], n: int = 3) -> Set[str]:
    """Extract set of word n-grams (shingles) from a word list."""
    if not words:
        return set()
    if len(words) < n:
        return set([" ".join(words)])
    return set(" ".join(words[i:i + n]) for i in range(len(words) - n + 1))


def calculate_text_similarity(text_a: str, text_b: str) -> Dict[str, float]:
    """
    Compute comprehensive text similarity between two source documents.
    Returns jaccard, containment, sequence_ratio, and overall_similarity.
    """
    if not text_a or not text_b:
        return {"jaccard": 0.0, "containment": 0.0, "sequence_ratio": 0.0, "overall_similarity": 0.0}

    # Exact string match shortcut
    if text_a.strip() == text_b.strip():
        return {"jaccard": 1.0, "containment": 1.0, "sequence_ratio": 1.0, "overall_similarity": 1.0}

    words_a = _normalize_text_for_comparison(text_a)
    words_b = _normalize_text_for_comparison(text_b)

    if not words_a or not words_b:
        return {"jaccard": 0.0, "containment": 0.0, "sequence_ratio": 0.0, "overall_similarity": 0.0}

    # Word 3-grams
    ngrams_a = _get_word_ngrams(words_a, n=3)
    ngrams_b = _get_word_ngrams(words_b, n=3)

    intersection = len(ngrams_a & ngrams_b)
    union = len(ngrams_a | ngrams_b)
    min_len = min(len(ngrams_a), len(ngrams_b))

    jaccard = (intersection / union) if union > 0 else 0.0
    containment = (intersection / min_len) if min_len > 0 else 0.0

    # Sequence matcher on sampled/word stream (bounded for speed)
    sample_a = words_a[:1000]
    sample_b = words_b[:1000]
    seq_ratio = difflib.SequenceMatcher(None, sample_a, sample_b).quick_ratio()

    # Overall similarity:
    # High containment means one source essentially copied large blocks of the other (e.g. blog copying circular)
    overall = max(jaccard, containment * 0.92, seq_ratio)

    return {
        "jaccard": round(jaccard, 4),
        "containment": round(containment, 4),
        "sequence_ratio": round(seq_ratio, 4),
        "overall_similarity": round(overall, 4)
    }


def _pick_canonical_original(cluster: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Given a cluster of near-duplicate sources, select the canonical original source.
    Priority:
    1. Authority: 'official' > 'secondary' > 'low'
    2. Published date: Earlier date wins
    3. Document length / structure
    4. Deterministic tie-breaker: sort by ID
    """
    auth_priority = {"official": 3, "secondary": 2, "low": 1}

    def sort_key(s: Dict[str, Any]):
        auth_score = auth_priority.get(s.get("authority", "low"), 1)
        
        # Parsed date score (earlier is better, invert timestamp)
        date_score = 0
        pub_date_str = s.get("published_date")
        if pub_date_str:
            try:
                # Try simple ISO or year format
                if len(pub_date_str) == 4 and pub_date_str.isdigit():
                    dt = datetime(int(pub_date_str), 1, 1)
                else:
                    dt = datetime.fromisoformat(pub_date_str[:10])
                date_score = -dt.timestamp()  # Earlier date -> larger negative -> earlier in sort if ascending
            except Exception:
                date_score = 0

        # Text length (original official text is often clean and foundational)
        text_len = len(s.get("text", ""))

        # We want: highest auth_score, earliest date (largest date_score), longer text, lowest id
        return (-auth_score, -date_score, -text_len, s.get("id", ""))

    sorted_cluster = sorted(cluster, key=sort_key)
    return sorted_cluster[0]


def group_sources_by_independence(
    sources: List[Dict[str, Any]],
    similarity_threshold: float = 0.60
) -> Dict[str, Any]:
    """
    Cluster sources based on text similarity and content hash.
    Designate canonical original for each cluster and map all duplicates to it.
    """
    n = len(sources)
    if n == 0:
        return {
            "total_sources": 0,
            "independent_sources": 0,
            "badge_text": "0 sources",
            "clusters": [],
            "source_group_map": {}
        }

    if n == 1:
        s0 = sources[0]
        sid = s0["id"]
        return {
            "total_sources": 1,
            "independent_sources": 1,
            "badge_text": "1 source, 1 original",
            "clusters": [{
                "original_source_id": sid,
                "original_source_title": s0.get("title") or "Source",
                "original_authority": s0.get("authority") or "official",
                "copies": []
            }],
            "source_group_map": {sid: sid}
        }

    # Build adjacency matrix for connected components (DSU)
    parent = list(range(n))

    def find(i):
        if parent[i] == i:
            return i
        parent[i] = find(parent[i])
        return parent[i]

    def union(i, j):
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    pairwise_sims = {}

    for i in range(n):
        for j in range(i + 1, n):
            si = sources[i]
            sj = sources[j]

            # Fast content hash match
            hash_i = si.get("content_hash")
            hash_j = sj.get("content_hash")
            if hash_i and hash_j and hash_i == hash_j:
                union(i, j)
                pairwise_sims[(i, j)] = 1.0
                continue

            sim_data = calculate_text_similarity(si.get("text", ""), sj.get("text", ""))
            score = sim_data["overall_similarity"]
            containment = sim_data["containment"]
            pairwise_sims[(i, j)] = score

            # Cluster if similarity exceeds threshold or containment is very high (copied notice)
            if score >= similarity_threshold or containment >= 0.70:
                union(i, j)

    # Group sources into clusters
    clusters_by_root: Dict[int, List[Dict[str, Any]]] = {}
    for idx, s in enumerate(sources):
        root = find(idx)
        if root not in clusters_by_root:
            clusters_by_root[root] = []
        clusters_by_root[root].append(s)

    clusters_output = []
    source_group_map: Dict[str, str] = {}
    source_details_map: Dict[str, Dict[str, Any]] = {}

    for root, cluster_sources in clusters_by_root.items():
        canonical_original = _pick_canonical_original(cluster_sources)
        orig_id = canonical_original["id"]
        orig_title = canonical_original.get("title") or "Original Source"
        orig_auth = canonical_original.get("authority") or "official"

        copies = []
        for s in cluster_sources:
            sid = s["id"]
            source_group_map[sid] = orig_id
            is_orig = (sid == orig_id)
            source_details_map[sid] = {
                "original_group_id": orig_id,
                "is_original": is_orig,
                "copied_from_id": orig_id if not is_orig else None,
                "copied_from_title": orig_title if not is_orig else None,
            }
            if not is_orig:
                copies.append({
                    "id": sid,
                    "title": s.get("title") or "Copied Source",
                    "authority": s.get("authority") or "low",
                    "url": s.get("url")
                })

        clusters_output.append({
            "original_source_id": orig_id,
            "original_source_title": orig_title,
            "original_authority": orig_auth,
            "copies": copies
        })

    total_sources = n
    independent_sources = len(clusters_output)

    # Format Badge Text: e.g. "3 sources, 1 original" or "3 sources, 2 originals"
    src_label = "source" if total_sources == 1 else "sources"
    orig_label = "original" if independent_sources == 1 else "originals"
    badge_text = f"{total_sources} {src_label}, {independent_sources} {orig_label}"

    return {
        "total_sources": total_sources,
        "independent_sources": independent_sources,
        "badge_text": badge_text,
        "clusters": clusters_output,
        "source_group_map": source_group_map,
        "source_details_map": source_details_map
    }


def detect_and_group_sources(
    session_id: str,
    conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Run independence detection on all sources of a session in SQLite database.
    Updates sources.original_group_id in the database and returns clustering results.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True

    try:
        rows = conn.execute("""
            SELECT id, session_id, url, title, authority, published_date,
                   published_date_origin, content_hash, original_group_id, text
            FROM sources
            WHERE session_id = ?
            ORDER BY id ASC
        """, (session_id,)).fetchall()

        sources = [row_to_dict(r) for r in rows]
        result = group_sources_by_independence(sources)

        # Update original_group_id in database for each source
        for sid, orig_id in result["source_group_map"].items():
            conn.execute(
                "UPDATE sources SET original_group_id = ? WHERE id = ?",
                (orig_id, sid)
            )

        conn.commit()
        return result
    finally:
        if should_close and conn:
            conn.close()
