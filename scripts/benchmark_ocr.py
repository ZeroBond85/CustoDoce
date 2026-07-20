#!/usr/bin/env python3
"""Benchmark OCR/vision engines on synthetic flyer images.

Generates a synthetic flyer with 10 known products, runs the specified engine,
measures accuracy and speed.

Usage:
    python scripts/benchmark_ocr.py --engine tesseract
    python scripts/benchmark_ocr.py --engine easyocr
    python scripts/benchmark_ocr.py --engine all
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

GROUND_TRUTH = [
    ("Leite Condensado", 8.99),
    ("Creme de Leite", 5.49),
    ("Chocolate em Po", 12.90),
    ("Acucar Mascavo", 7.50),
    ("Farinha de Trigo 1kg", 4.99),
    ("Oleo de Soja 900ml", 6.79),
    ("Arroz Branco 5kg", 22.90),
    ("Feijao Carioca 1kg", 7.49),
    ("Cafe Torrado Moido", 14.90),
    ("Granulado Ao Leite", 6.99),
]
NUM_PRODUCTS = len(GROUND_TRUTH)

PRICE_RE = re.compile(r"(?:R\s*[$])\s*(\d+[.,]\d{2})", re.I)


def _find_font(size: int = 18) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for p in paths:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_flyer(font_size: int = 20) -> bytes:
    W, H = 800, 1200
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    font_title = _find_font(font_size + 8)
    font_body = _find_font(font_size)
    font_sub = _find_font(font_size - 4)

    draw.rectangle([(0, 0), (W, 70)], fill="#c0392b")
    tw, _ = draw.textbbox((0, 0), "ENCARTE PROMOCIONAL", font=font_title)[2:4]
    draw.text(((W - tw) // 2, 12), "ENCARTE PROMOCIONAL", fill="white", font=font_title)
    draw.text(((W - tw) // 2, 44), "Confira as ofertas imperdiveis!", fill="#f8d7da", font=font_sub)

    y_start = 100
    row_height = 85
    for i, (name, price) in enumerate(GROUND_TRUTH):
        y = y_start + i * row_height
        if i % 2 == 0:
            draw.rectangle([(10, y - 5), (W - 10, y + row_height - 10)], fill="#f8f9fa")
        draw.text((30, y), name, fill="black", font=font_body)
        price_text = f"R$ {price:.2f}"
        pw, _ = draw.textbbox((0, 0), price_text, font=font_body)[2:4]
        draw.text((W - 30 - pw, y), price_text, fill="#c0392b", font=font_body)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _parse_ocr_text(text: str) -> list[tuple[str, float]]:
    products: list[tuple[str, float]] = []
    lines = text.splitlines()
    current_name: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            current_name = []
            continue
        m = PRICE_RE.search(line)
        if m:
            before = line[: m.start()].strip()
            name_part = f"{' '.join(current_name)} {before}".strip() if current_name else before
            price_str = m.group(1).replace(",", ".")
            try:
                price = float(price_str)
                if price > 0 and name_part:
                    products.append((name_part, price))
                    current_name = []
                    continue
            except ValueError:
                pass
        current_name.append(line)
    return products


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower().strip())


def _score_products(found: list[tuple[str, float]]) -> tuple[int, int]:
    correct_products = 0
    correct_prices = 0
    matched = [False] * NUM_PRODUCTS

    for found_name, found_price in found:
        fn = _normalize(found_name)
        best_idx = -1
        best_score = 0.0
        for i, (gt_name, _) in enumerate(GROUND_TRUTH):
            if matched[i]:
                continue
            gn = _normalize(gt_name)
            gn_words = set(gn.split())
            if not gn_words:
                continue
            fn_words = set(fn.split())
            overlap = len(fn_words & gn_words)
            score = overlap / len(gn_words)
            if score > best_score:
                best_score = score
                best_idx = i

        if best_idx >= 0 and best_score >= 0.5:
            if not matched[best_idx]:
                matched[best_idx] = True
                correct_products += 1
                gt_price = GROUND_TRUTH[best_idx][1]
                if abs(found_price - gt_price) < 0.01:
                    correct_prices += 1

    return correct_products, correct_prices


def _run_tesseract(image_bytes: bytes) -> dict:
    import pytesseract
    from PIL import Image as PILImage

    t1 = time.perf_counter()
    img = PILImage.open(io.BytesIO(image_bytes))
    _load_time = time.perf_counter() - t1

    t2 = time.perf_counter()
    raw_text = pytesseract.image_to_string(img, lang="por", config="--psm 6 --oem 3")
    infer_time = time.perf_counter() - t2

    products = _parse_ocr_text(raw_text)
    cp, cpr = _score_products(products)

    return {
        "products_found": len(products),
        "products_correct": cp,
        "prices_correct": cpr,
        "infer_time": round(infer_time, 3),
        "raw_text": raw_text[:500],
    }


def _run_easyocr(image_bytes: bytes) -> dict:
    import easyocr

    t1 = time.perf_counter()
    reader = easyocr.Reader(["pt"], gpu=False)
    init_time = time.perf_counter() - t1

    t2 = time.perf_counter()
    detections = reader.readtext(image_bytes)
    infer_time = time.perf_counter() - t2

    text_lines = [d[1] for d in detections if len(d) >= 2]
    raw_text = "\n".join(text_lines)
    products = _parse_ocr_text(raw_text)
    cp, cpr = _score_products(products)

    return {
        "products_found": len(products),
        "products_correct": cp,
        "prices_correct": cpr,
        "init_time": round(init_time, 3),
        "infer_time": round(infer_time, 3),
        "raw_text": raw_text[:500],
        "detections": len(detections),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark OCR engines on synthetic flyer")
    parser.add_argument("--engine", choices=["tesseract", "easyocr", "all"], default="all")
    parser.add_argument("--output", "-o", type=str, default="", help="Output JSON file")
    args = parser.parse_args()

    engines = []
    if args.engine in ("tesseract", "all"):
        engines.append("tesseract")
    if args.engine in ("easyocr", "all"):
        engines.append("easyocr")

    print(f"=== OCR Benchmark ===")
    print(f"Ground truth: {NUM_PRODUCTS} products\n")

    image = generate_flyer()
    print(f"Flyer image: {len(image)} bytes\n")

    results = []
    for engine in engines:
        print(f"--- {engine.upper()} ---", flush=True)
        t_start = time.perf_counter()
        try:
            fn = _run_tesseract if engine == "tesseract" else _run_easyocr
            r = fn(image)
            elapsed = time.perf_counter() - t_start
            r["engine"] = engine
            r["total_time"] = round(elapsed, 3)
            r["error"] = None
            results.append(r)
            _print_result(r, elapsed)
        except ImportError as e:
            elapsed = time.perf_counter() - t_start
            results.append({"engine": engine, "error": f"ImportError: {e}", "total_time": round(elapsed, 3)})
            print(f"  SKIP: {e}")
        except Exception as e:
            elapsed = time.perf_counter() - t_start
            results.append({"engine": engine, "error": str(e), "total_time": round(elapsed, 3)})
            print(f"  ERROR: {e}")
        print()

    output = {"num_products": NUM_PRODUCTS, "results": results}
    output_json = json.dumps(output, indent=2)

    print("=== SUMMARY ===")
    for r in results:
        _print_summary(r)

    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(f"\nResults saved to: {args.output}")
    else:
        print(f"\nFull JSON ({len(output_json)} bytes):")
        print(output_json)

    return 0


def _print_result(r: dict, elapsed: float):
    if r.get("error"):
        return
    print(f"  Init time:   {r.get('init_time', 0):>6.2f}s" if "init_time" in r else "")
    print(f"  Infer time:  {r.get('infer_time', 0):>6.2f}s")
    print(f"  Total time:  {elapsed:>6.2f}s")
    print(f"  Products:    found={r['products_found']}, correct={r['products_correct']}/{NUM_PRODUCTS}")
    print(f"  Prices:      correct={r['prices_correct']}/{NUM_PRODUCTS}")
    if "detections" in r:
        print(f"  Detections:  {r['detections']} text regions")
    print(f"  Raw text preview: {r.get('raw_text', '')[:200]}...")


def _print_summary(r: dict):
    if r.get("error"):
        print(f"  {r['engine']:12s} | ERROR | {r['error'][:50]}")
    else:
        acc = f"{r['products_correct']}/{NUM_PRODUCTS}"
        prices = f"{r['prices_correct']}/{NUM_PRODUCTS}"
        print(f"  {r['engine']:12s} | OK | products={acc:8s} | prices={prices:8s} | time={r['total_time']:6.2f}s")


if __name__ == "__main__":
    sys.exit(main())
