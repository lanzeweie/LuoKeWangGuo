#!/usr/bin/env python3
"""
在游戏窗口截图上标注 ROI 区域
"""

import cv2
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.core.capture_mode_detector import ROI_X, ROI_Y, ROI_W, ROI_H

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def annotate_roi_on_image(image_path: str, output_path: str) -> None:
    """在游戏窗口截图上标注 ROI 区域。"""
    img = cv2.imread(image_path)
    if img is None:
        print(f"ERROR: 无法读取图片: {image_path}")
        return

    h, w = img.shape[:2]

    # ROI 实际边界（不超过图片尺寸）
    x1 = max(0, ROI_X)
    y1 = max(0, ROI_Y)
    x2 = min(w, ROI_X + ROI_W)
    y2 = min(h, ROI_Y + ROI_H)

    # 画出 ROI 矩形框（红色，粗线）
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 3)

    # 标注文字
    label = f"ROI: ({x1},{y1}) {x2-x1}x{y2-y1}"
    cv2.putText(
        img, label, (x1, y1 - 10),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2
    )

    # 标注模板大小
    tpl_label = f"Template: 94x203"
    cv2.putText(
        img, tpl_label, (x1, y2 + 20),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2
    )

    # 保存标注后的图片
    cv2.imwrite(output_path, img)

    print(f"标注后的图片已保存到: {output_path}")
    print(f"图片尺寸: {w}x{h}")
    print(f"ROI 区域: ({x1}, {y1}) 到 ({x2}, {y2}) = {x2-x1}x{y2-y1}")
    print(f"模板大小: {ROI_W}x{ROI_H}")
    print(f"\n注意: ROI 高度只有 {y2-y1}，但模板高度是 {ROI_H}")
    print(f"模板超出窗口底部 {ROI_H - (y2-y1)} 像素！")


def main() -> None:
    image_path = PROJECT_ROOT / "data" / "templates" / "full_window.png"
    output_path = PROJECT_ROOT / "data" / "templates" / "full_window_annotated.png"

    annotate_roi_on_image(str(image_path), str(output_path))


if __name__ == "__main__":
    main()
