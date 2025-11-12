import argparse
import sys
from pathlib import Path
from typing import List

from ocr_pipeline import collect_input_files, process_files


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description="OCR 文件处理 CLI：检测类型并进行 OCR 转换为 UTF-8 文本，保留 HOCR 布局")
    parser.add_argument("--input", required=True, help="输入文件或目录（支持 PDF/JPG/PNG/TIFF/BMP）")
    parser.add_argument("--output", required=True, help="输出目录（将生成 text/hocr/reports/logs 子目录）")
    parser.add_argument("--lang", default="chi_sim+eng", help="OCR 语言（默认中文简体+英文）")
    parser.add_argument("--threshold", type=float, default=0.95, help="准确率阈值，低于此值标记为 low_accuracy")
    parser.add_argument("--workers", type=int, default=0, help="并发工作线程数（默认 min(4, CPU)）")
    parser.add_argument("--recursive", action="store_true", help="目录递归扫描")

    args = parser.parse_args(argv)

    input_path = args.input
    output_dir = args.output
    lang = args.lang
    threshold = args.threshold
    workers = args.workers or None
    recursive = args.recursive

    files = collect_input_files(input_path, recursive=recursive)
    if not files:
        print(f"[错误] 未找到可处理的文件：{input_path}")
        return 2

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    results = process_files(files, output_dir, provider="tesseract", lang=lang, accuracy_threshold=threshold, max_workers=workers)
    # 简要汇总输出
    success = sum(1 for r in results if r.status == "success")
    low = sum(1 for r in results if r.status == "low_accuracy")
    failed = sum(1 for r in results if r.status == "failed")
    print(f"[完成] 共处理 {len(results)} 个文件：成功 {success}，低准确 {low}，失败 {failed}")
    print(f"输出目录：{output_dir}（text/hocr/reports/logs）")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())