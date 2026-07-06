"""
CustoDoce - ONNX Model Exporter
Exports the Sentence-Transformer model to ONNX format for faster cold starts.
"""

import logging
from pathlib import Path

from optimum.onnxruntime import ORTModelForFeatureExtraction
from transformers import AutoTokenizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "onnx_models" / MODEL_NAME.replace("/", "_")


def export_model():
    try:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)

        logger.info(f"Exporting model {MODEL_NAME} to ONNX...")

        # Load and export model to ONNX
        model = ORTModelForFeatureExtraction.from_pretrained(MODEL_NAME, export=True)
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

        # Save to disk
        model.save_pretrained(str(EXPORT_DIR))
        tokenizer.save_pretrained(str(EXPORT_DIR))

        logger.info(f"Successfully exported ONNX model to: {EXPORT_DIR}")

        # Verify the files exist
        onnx_files = list(EXPORT_DIR.glob("*.onnx"))
        if not onnx_files:
            raise FileNotFoundError("ONNX model file not found after export.")

        logger.info(f"Verified {len(onnx_files)} ONNX file(s) created.")

    except Exception as e:
        logger.error(f"Failed to export ONNX model: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    export_model()
