"""上传文件类型与标准文档清单的格式约束。

文档清单中的 ``file_formats`` 是业务语言（报告、图纸、照片等），
这里把它映射为实际可接受的扩展名。前端用同一份结果生成 accept，
后端在写入存储前再次校验，避免只靠前端限制。
"""
from __future__ import annotations

import re
from pathlib import Path

REPORT_EXTENSIONS = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".txt", ".md", ".csv",
)
DRAWING_EXTENSIONS = (".pdf", ".dwg", ".dxf", ".rvt", ".ifc", ".skp")
MODEL_EXTENSIONS = (".rvt", ".ifc", ".skp", ".dwg", ".dxf", ".glb", ".gltf", ".zip")
LICENSE_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png")
PHOTO_EXTENSIONS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm")

FORMAT_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "证照": LICENSE_EXTENSIONS,
    "报告": REPORT_EXTENSIONS,
    "图纸": DRAWING_EXTENSIONS,
    "模型": MODEL_EXTENSIONS,
    "照片": PHOTO_EXTENSIONS,
    "图片": PHOTO_EXTENSIONS,
    "视频": VIDEO_EXTENSIONS,
    # 清单中的记录表按办公文档和扫描件处理。
    "施工记录表": REPORT_EXTENSIONS + PHOTO_EXTENSIONS,
    "施工验收记录表": REPORT_EXTENSIONS + PHOTO_EXTENSIONS,
}

# 兜底白名单。清单标记为“待定”时使用，仍拒绝可执行文件。
ALLOWED_EXT = frozenset(
    ext
    for extensions in FORMAT_EXTENSIONS.values()
    for ext in extensions
).union({".json", ".xml", ".mdb", ".zip", ".rar", ".7z"})
BLOCKED_EXT = frozenset({
    ".exe", ".bat", ".cmd", ".ps1", ".sh", ".dll", ".scr", ".js", ".vbs",
})


def _parts(file_formats: str | None) -> list[str]:
    if not file_formats:
        return []
    return [p for p in re.split(r"[\/、,，;；\s]+", file_formats) if p]


def allowed_extensions_for_formats(file_formats: str | None) -> list[str]:
    """返回清单项允许的扩展名，顺序稳定且去重。"""
    result: list[str] = []
    for part in _parts(file_formats):
        extensions = FORMAT_EXTENSIONS.get(part)
        if extensions is None:
            continue
        for ext in extensions:
            if ext not in result:
                result.append(ext)
    if result:
        return result
    return sorted(ALLOWED_EXT)


def validate_catalog_extension(filename: str, file_formats: str | None) -> str:
    """校验清单项的上传文件类型，返回小写扩展名。"""
    ext = Path(filename).suffix.lower()
    allowed = allowed_extensions_for_formats(file_formats)
    if not ext:
        raise ValueError("文件缺少扩展名，无法识别类型")
    if ext in BLOCKED_EXT:
        raise ValueError(f"不允许上传 {ext} 类型的文件")
    if ext not in allowed:
        shown = " / ".join(x.lstrip(".").upper() for x in allowed)
        raise ValueError(f"该清单项不支持 {ext} 类型，可上传：{shown}")
    return ext
