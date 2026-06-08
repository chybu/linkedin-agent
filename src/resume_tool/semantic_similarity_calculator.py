import re, ollama
import numpy as np
from config import ResumeConfig
from resume_tool.schema import MatchResult

def parse_bullet_text(text: str) -> list[str]:
    items: list[str] = []

    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue

        line = re.sub(r"^\s*[-*•●]\s+", "", line).strip()
        line = " ".join(line.split())

        if line:
            items.append(line)

    return items

def embed_texts(
    texts: list[str],
) -> np.ndarray:
    if not texts:
        return np.array([])

    response = ollama.embed(
        model=ResumeConfig.EMBED_MODEL.value,
        input=texts,
    )

    vectors = np.array(response["embeddings"], dtype=np.float32)
    return normalize_vectors(vectors)

def normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    return vectors / norms

def cosine_similarity_matrix(
    left_vectors: np.ndarray,
    right_vectors: np.ndarray,
) -> np.ndarray:
    return left_vectors @ right_vectors.T

def match_jd_sentences_to_resume(
    jd_sentences: list[str],
    resume_sentences: list[str],
) -> list[MatchResult]:
    if not jd_sentences:
        return []

    if not resume_sentences:
        return [
            MatchResult(
                jd_sentence=jd_sentence,
                resume_sentence=None,
                score=0.0,
            )
            for jd_sentence in jd_sentences
        ]

    jd_vectors = embed_texts(jd_sentences)
    resume_vectors = embed_texts(resume_sentences)

    scores = cosine_similarity_matrix(jd_vectors, resume_vectors)

    results: list[MatchResult] = []

    for jd_i, jd_sentence in enumerate(jd_sentences):
        best_resume_i = int(np.argmax(scores[jd_i]))
        best_score = float(scores[jd_i][best_resume_i])

        results.append(
            MatchResult(
                jd_sentence=jd_sentence,
                resume_sentence=(
                    resume_sentences[best_resume_i]
                    if best_score >= ResumeConfig.MIN_MATCH_SCORE.value
                    else None
                ),
                score=best_score,
            )
        )

    return results
