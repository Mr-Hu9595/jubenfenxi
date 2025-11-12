import os
import io
import json
import time
import mimetypes
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path

try:
    import psutil  # type: ignore
except Exception:
    psutil = None  # Optional, used for memory metrics

try:
    import fitz  # PyMuPDF
except Exception as e:
    fitz = None  # Will raise a helpful error if PDF input is used

try:
    from PIL import Image
except Exception as e:
    Image = None  # Will raise a helpful error if image input is used

try:
    import pytesseract
    from pytesseract import Output
except Exception as e:
    pytesseract = None
    Output = None


# ----------------------
# Data Structures
# ----------------------

@dataclass
class OCRResult:
    original_filename: str
    file_type: str
    status: str  # 'success' | 'low_accuracy' | 'failed'
    text_output_path: Optional[str]
    hocr_paths: List[str]
    accuracy: Optional[float]
    page_count: int
    duration_seconds: float
    errors: List[str]
    metrics: Dict[str, Any]


SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}


def detect_file_type(path: str) -> str:
    """Detect file type by extension and mimetype.

    Returns: 'pdf' | 'image' | 'unsupported'
    """
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in SUPPORTED_IMAGE_EXTS:
        return "image"

    mt, _ = mimetypes.guess_type(path)
    if mt == "application/pdf":
        return "pdf"
    if mt and mt.startswith("image/"):
        return "image"
    return "unsupported"


def _ensure_dirs(base_out: Path) -> Dict[str, Path]:
    text_dir = base_out / "text"
    hocr_dir = base_out / "hocr"
    report_dir = base_out / "reports"
    log_dir = base_out / "logs"
    for d in (text_dir, hocr_dir, report_dir, log_dir):
        d.mkdir(parents=True, exist_ok=True)
    return {"text": text_dir, "hocr": hocr_dir, "reports": report_dir, "logs": log_dir}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _get_process_metrics() -> Dict[str, Any]:
    m: Dict[str, Any] = {"timestamp_ms": _now_ms()}
    if psutil:
        p = psutil.Process(os.getpid())
        with p.oneshot():
            mem = p.memory_info().rss
            cpu = p.cpu_percent(interval=None)
        m.update({"rss_bytes": mem, "cpu_percent": cpu})
    return m


def _pdf_to_images(pdf_path: str, dpi: int = 250) -> List[Image.Image]:
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) 未安装，无法处理 PDF。请在环境中安装 PyMuPDF。")
    if Image is None:
        raise RuntimeError("Pillow 未安装，无法处理图像。请在环境中安装 Pillow。")
    doc = fitz.open(pdf_path)
    images: List[Image.Image] = []
    try:
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        for page in doc:
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
    finally:
        doc.close()
    return images


def _rescale_image(img: Image.Image, max_side: int = 2400) -> Image.Image:
    w, h = img.size
    scale = min(1.0, max_side / float(max(w, h)))
    if scale < 1.0:
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
    return img


def _ocr_image(img: Image.Image, lang: str = "chi_sim+eng", psm: int = 6, oem: int = 3) -> Tuple[str, bytes, Dict[str, Any]]:
    if pytesseract is None:
        raise RuntimeError("pytesseract 未安装或 Tesseract 未配置，请安装 tesseract 并配置 pytesseract。")
    config = f"--psm {psm} --oem {oem}"
    # data with confidences
    data = pytesseract.image_to_data(img, lang=lang, output_type=Output.DICT, config=config)
    # HOCR preserves layout
    hocr_bytes = pytesseract.image_to_pdf_or_hocr(img, extension='hocr', lang=lang, config=config)
    # Reconstruct text with paragraphs
    text_lines: List[str] = []
    prev_block = prev_par = prev_line = None
    line_buf: List[str] = []
    n = len(data.get("text", []))
    for i in range(n):
        word = data["text"][i]
        if not word or word.strip() == "":
            continue
        block = data.get("block_num", [None] * n)[i]
        par = data.get("par_num", [None] * n)[i]
        line = data.get("line_num", [None] * n)[i]

        if (prev_block, prev_par, prev_line) != (block, par, line):
            # flush previous line
            if line_buf:
                text_lines.append(" ".join(line_buf))
                line_buf = []
            # start new paragraph when paragraph id changes
            if prev_par is not None and par != prev_par:
                text_lines.append("")  # empty line -> paragraph break
            prev_block, prev_par, prev_line = block, par, line

        line_buf.append(word)

    if line_buf:
        text_lines.append(" ".join(line_buf))

    text = "\n".join(text_lines)
    return text, hocr_bytes, data


def _accuracy_from_data(data: Dict[str, Any]) -> Optional[float]:
    confs_raw = data.get("conf", [])
    confs: List[int] = []
    for c in confs_raw:
        try:
            ci = int(c)
            if ci >= 0:
                confs.append(ci)
        except Exception:
            continue
    if not confs:
        return None
    avg_conf = sum(confs) / float(len(confs))
    # Normalize to [0,1]
    return max(0.0, min(1.0, avg_conf / 100.0))


def process_file(
    input_path: str,
    output_dir: str,
    provider: str = "tesseract",
    lang: str = "chi_sim+eng",
    accuracy_threshold: float = 0.95,
    max_side: int = 2400,
    max_retries: int = 2,
) -> OCRResult:
    """Process a single file with OCR, preserving page order and layout via HOCR.

    Returns standardized OCRResult with paths to outputs and metrics.
    """
    start = time.perf_counter()
    base_out = Path(output_dir)
    dirs = _ensure_dirs(base_out)
    errors: List[str] = []
    hocr_paths: List[str] = []
    metrics: Dict[str, Any] = {"pages": []}

    input_path = str(input_path)
    ft = detect_file_type(input_path)
    page_texts: List[str] = []
    page_accuracies: List[float] = []
    page_durations: List[float] = []

    if ft == "unsupported":
        err = f"不支持的文件类型: {input_path}"
        errors.append(err)
        duration = time.perf_counter() - start
        return OCRResult(
            original_filename=Path(input_path).name,
            file_type=ft,
            status="failed",
            text_output_path=None,
            hocr_paths=[],
            accuracy=None,
            page_count=0,
            duration_seconds=duration,
            errors=errors,
            metrics={"error": err, **_get_process_metrics()},
        )

    if ft == "pdf":
        images = _pdf_to_images(input_path, dpi=250)
    else:
        if Image is None:
            raise RuntimeError("Pillow 未安装，无法处理图像。")
        images = [Image.open(input_path)]

    page_count = len(images)
    # Process each page in order
    for page_idx, img in enumerate(images, start=1):
        page_start = time.perf_counter()
        text: Optional[str] = None
        data: Optional[Dict[str, Any]] = None
        hocr_bytes: Optional[bytes] = None
        attempt = 0
        last_err: Optional[str] = None

        while attempt <= max_retries:
            try:
                attempt += 1
                img2 = _rescale_image(img, max_side=max_side if attempt == 1 else max_side * 1.25)
                text, hocr_bytes, data = _ocr_image(img2, lang=lang, psm=6 if attempt == 1 else 3, oem=3)
                break
            except Exception as e:
                last_err = f"page {page_idx} attempt {attempt}: {e}"
                time.sleep(0.2)

        if text is None or data is None or hocr_bytes is None:
            errors.append(last_err or f"page {page_idx} OCR 失败")
            # add empty page to keep order
            page_texts.append("")
            page_accuracies.append(0.0)
            page_durations.append(time.perf_counter() - page_start)
            metrics["pages"].append({
                "page": page_idx,
                "status": "failed",
                "duration_seconds": page_durations[-1],
                **_get_process_metrics(),
            })
            continue

        # Save HOCR
        hocr_path = dirs["hocr"] / f"{Path(input_path).stem}_page_{page_idx}.hocr.html"
        with open(hocr_path, "wb") as f:
            f.write(hocr_bytes)
        hocr_paths.append(str(hocr_path))

        acc = _accuracy_from_data(data) or 0.0
        page_accuracies.append(acc)
        page_texts.append(text)

        duration_page = time.perf_counter() - page_start
        page_durations.append(duration_page)
        metrics["pages"].append({
            "page": page_idx,
            "status": "success",
            "accuracy": acc,
            "duration_seconds": duration_page,
            **_get_process_metrics(),
        })

    # Combine pages text with separators and paragraph breaks
    combined_lines: List[str] = []
    for idx, t in enumerate(page_texts, start=1):
        combined_lines.append(f"=== [PAGE {idx}] ===")
        if t:
            combined_lines.append(t)
        combined_lines.append("")
    combined_text = "\n".join(combined_lines)

    # Write combined text (UTF-8)
    text_path = dirs["text"] / f"{Path(input_path).stem}.txt"
    with open(text_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(combined_text)

    avg_acc = None
    if page_accuracies:
        avg_acc = sum(page_accuracies) / float(len(page_accuracies))

    duration_total = time.perf_counter() - start

    # Build result
    status = "success"
    if avg_acc is not None and avg_acc < accuracy_threshold:
        status = "low_accuracy"
        errors.append(f"平均准确度 {avg_acc:.3f} 低于阈值 {accuracy_threshold:.3f}")

    result = OCRResult(
        original_filename=Path(input_path).name,
        file_type=ft,
        status=status,
        text_output_path=str(text_path),
        hocr_paths=hocr_paths,
        accuracy=avg_acc,
        page_count=page_count,
        duration_seconds=duration_total,
        errors=errors,
        metrics={
            "avg_page_duration_seconds": (sum(page_durations) / float(len(page_durations))) if page_durations else None,
            "accuracy_threshold": accuracy_threshold,
            "provider": provider,
            **_get_process_metrics(),
        },
    )

    # Save per-file report JSON
    report_path = dirs["reports"] / f"{Path(input_path).stem}.json"
    with open(report_path, "w", encoding="utf-8") as rf:
        json.dump(asdict(result), rf, ensure_ascii=False, indent=2)

    return result


def process_files(
    inputs: List[str],
    output_dir: str,
    provider: str = "tesseract",
    lang: str = "chi_sim+eng",
    accuracy_threshold: float = 0.95,
    max_workers: Optional[int] = None,
) -> List[OCRResult]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    base_out = Path(output_dir)
    _ensure_dirs(base_out)

    max_workers = max_workers or min(4, (os.cpu_count() or 2))
    start = time.perf_counter()

    results: List[OCRResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(process_file, p, output_dir, provider, lang, accuracy_threshold) for p in inputs]
        for fut in as_completed(futs):
            try:
                res = fut.result()
                results.append(res)
            except Exception as e:
                # Build failed record for visibility
                results.append(OCRResult(
                    original_filename=Path("unknown").name,
                    file_type="unsupported",
                    status="failed",
                    text_output_path=None,
                    hocr_paths=[],
                    accuracy=None,
                    page_count=0,
                    duration_seconds=0.0,
                    errors=[str(e)],
                    metrics=_get_process_metrics(),
                ))

    duration_total = time.perf_counter() - start
    # Save run summary
    summary = {
        "duration_seconds": duration_total,
        "files": [asdict(r) for r in results],
        "metrics": _get_process_metrics(),
    }
    out_summary = base_out / "reports" / "ocr_run_summary.json"
    with open(out_summary, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return results


def collect_input_files(input_path: str, recursive: bool = False) -> List[str]:
    p = Path(input_path)
    files: List[str] = []
    if p.is_file():
        files.append(str(p))
        return files
    if not p.is_dir():
        return files

    exts = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}
    if recursive:
        for fp in p.rglob("*"):
            if fp.is_file() and fp.suffix.lower() in exts:
                files.append(str(fp))
    else:
        for fp in p.glob("*"):
            if fp.is_file() and fp.suffix.lower() in exts:
                files.append(str(fp))
    return files


__all__ = [
    "OCRResult",
    "detect_file_type",
    "process_file",
    "process_files",
    "collect_input_files",
]