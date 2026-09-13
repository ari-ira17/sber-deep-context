"""
Text Embedder module for Meridian Knowledge Base.
Generates 768-dimensional vectors using multilingual-e5-base model.
Used by HybridSearchEngine to convert query_text → query_vector automatically.
"""

from typing import List, Optional

EMBEDDING_MODEL = "intfloat/multilingual-e5-base"
VECTOR_DIM = 768


class TextEmbedder:
    """
    Lazily-loaded text embedder using SentenceTransformers.
    Falls back to zero vector if model is unavailable.
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL, device: Optional[str] = None):
        self.model_name = model_name
        self.device = device
        self._model = None

    def _load(self):
        """Load SentenceTransformer model on first use (lazy init)."""
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            kwargs = {}
            if self.device:
                kwargs["device"] = self.device
            self._model = SentenceTransformer(self.model_name, **kwargs)
        except ImportError:
            print("[TextEmbedder Warning] sentence-transformers not installed. Falling back to zero vector.")
        except Exception as e:
            print(f"[TextEmbedder Warning] Could not load model '{self.model_name}': {e}")

    def embed(self, text: str) -> List[float]:
        """
        Embed a single text string into a 768-dim vector.
        Prefixes with 'query: ' as required by E5 model convention.
        """
        self._load()
        if self._model is None:
            return [0.0] * VECTOR_DIM
        try:
            
            prefixed = f"query: {text}" if not text.startswith("query:") else text
            vec = self._model.encode(prefixed, normalize_embeddings=True)
            return vec.tolist()
        except Exception as e:
            print(f"[TextEmbedder Error] Encoding failed: {e}")
            return [0.0] * VECTOR_DIM

    def embed_passage(self, text: str) -> List[float]:
        """
        Embed a passage (document) — uses 'passage: ' prefix for E5 convention.
        Use this during ingestion, not for queries.
        """
        self._load()
        if self._model is None:
            return [0.0] * VECTOR_DIM
        try:
            prefixed = f"passage: {text}" if not text.startswith("passage:") else text
            vec = self._model.encode(prefixed, normalize_embeddings=True)
            return vec.tolist()
        except Exception as e:
            print(f"[TextEmbedder Error] Passage encoding failed: {e}")
            return [0.0] * VECTOR_DIM

    def embed_batch(self, texts: List[str], is_query: bool = False) -> List[List[float]]:
        """
        Embed a batch of texts. is_query=True uses 'query: ' prefix.
        """
        self._load()
        if self._model is None:
            return [[0.0] * VECTOR_DIM for _ in texts]
        try:
            prefix = "query: " if is_query else "passage: "
            prefixed = [f"{prefix}{t}" if not t.startswith(prefix) else t for t in texts]
            vecs = self._model.encode(prefixed, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
            return [v.tolist() for v in vecs]
        except Exception as e:
            print(f"[TextEmbedder Error] Batch encoding failed: {e}")
            return [[0.0] * VECTOR_DIM for _ in texts]



_default_embedder: Optional[TextEmbedder] = None


def get_embedder() -> TextEmbedder:
    """Get or create the default singleton embedder."""
    global _default_embedder
    if _default_embedder is None:
        _default_embedder = TextEmbedder()
    return _default_embedder
