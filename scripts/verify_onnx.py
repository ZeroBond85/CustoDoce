"""
CustoDoce - ONNX Verification
Compares embeddings produced by PyTorch vs ONNX to ensure consistency.
"""

import logging

import numpy as np

from parsers.semantic_matcher import SemanticMatcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def verify():
    matcher = SemanticMatcher()
    text = "Leite Condensado Moça 395g"

    # 1. Get embedding via PyTorch (force fallback by temporarily disabling ONNX)
    original_onnx_model = matcher._onnx_model
    matcher._onnx_model = None  # Force PyTorch

    logger.info("Generating PyTorch embedding...")
    emb_pytorch = matcher.get_embedding(text)

    # 2. Get embedding via ONNX
    matcher._onnx_model = original_onnx_model  # Restore ONNX
    logger.info("Generating ONNX embedding...")
    emb_onnx = matcher.get_embedding(text)

    # 3. Compare
    cosine_sim = np.dot(emb_pytorch, emb_onnx) / (np.linalg.norm(emb_pytorch) * np.linalg.norm(emb_onnx))
    logger.info(f"Cosine Similarity (PyTorch vs ONNX): {cosine_sim:.6f}")

    if cosine_sim > 0.99:
        logger.info("✅ SUCCESS: ONNX embeddings are consistent with PyTorch.")
    else:
        logger.error("❌ FAILURE: Significant difference between PyTorch and ONNX embeddings.")
        raise ValueError(f"Similarity too low: {cosine_sim}")


if __name__ == "__main__":
    verify()
