"""Download and install the default Vosk Chinese speech-recognition model.

The model is a third-party resource downloaded directly from the official Vosk
model host. It remains outside Git and is installed under assets/vosk-model-cn.
"""
from __future__ import annotations

import argparse
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_URL = "https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip"
DEFAULT_TARGET = ROOT / "assets" / "vosk-model-cn"
REQUIRED_ENTRIES = ("am", "conf", "graph", "ivector")


def model_is_ready(path: Path) -> bool:
    """Return whether path looks like an extracted Vosk model directory."""
    return path.is_dir() and all((path / name).exists() for name in REQUIRED_ENTRIES)


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "moonlit-werewolf/0.5"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def _find_model_root(extract_root: Path) -> Path:
    if model_is_ready(extract_root):
        return extract_root
    matches = [path for path in extract_root.iterdir() if model_is_ready(path)]
    if len(matches) != 1:
        raise RuntimeError("下载包中未找到唯一且完整的 Vosk 模型目录")
    return matches[0]


def install_model(url: str = DEFAULT_URL, target: Path = DEFAULT_TARGET, force: bool = False) -> Path:
    """Download, validate, and atomically install a Vosk model."""
    target = target.resolve()
    if model_is_ready(target) and not force:
        print(f"Vosk 中文模型已就绪：{target}")
        return target
    if target.exists() and not force:
        raise RuntimeError(f"目标路径已存在但模型不完整：{target}；确认后使用 --force 重装")

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="moonlit-vosk-") as temp_name:
        temp = Path(temp_name)
        archive = temp / "model.zip"
        extracted = temp / "extracted"
        extracted.mkdir()
        print(f"正在从 Vosk 官方模型站下载：{url}")
        _download(url, archive)
        if not zipfile.is_zipfile(archive):
            raise RuntimeError("下载内容不是有效 ZIP 文件")
        with zipfile.ZipFile(archive) as package:
            package.extractall(extracted)
        source = _find_model_root(extracted)
        staged = target.parent / f".{target.name}.installing"
        if staged.exists():
            shutil.rmtree(staged)
        shutil.copytree(source, staged)
        if not model_is_ready(staged):
            shutil.rmtree(staged, ignore_errors=True)
            raise RuntimeError("解压后的 Vosk 模型校验失败")
        if target.exists():
            shutil.rmtree(target)
        staged.replace(target)

    print(f"Vosk 中文模型安装完成：{target}")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="下载并安装月夜狼人杀所需的 Vosk 中文模型")
    parser.add_argument("--url", default=DEFAULT_URL, help="模型 ZIP 下载地址")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET, help="模型安装目录")
    parser.add_argument("--force", action="store_true", help="覆盖已有模型目录")
    args = parser.parse_args()
    install_model(args.url, args.target, args.force)


if __name__ == "__main__":
    main()
