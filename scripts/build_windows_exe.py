"""
build_windows_exe.py - 打包 Weme v2 为 Windows .exe

使用 PyInstaller 构建自包含的 Windows 可执行文件。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SPEC_FILE = ROOT / "weme_windows.spec"

SPEC_CONTENT = """
# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

a = Analysis(
    ['src/weme/__main__.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('config', 'config'),
        ('profiles', 'profiles'),
    ],
    hiddenimports=[
        'weme.cli',
        'weme.daemon',
        'weme.dashboard',
        'weme.apps.wechat',
        'weme.apps.dingtalk',
        'weme.apps.feishu',
        'weme.providers.mock',
        'weme.providers.openai_compat',
        'weme.providers.anthropic',
        'weme.platform.windows',
        'typer',
        'yaml',
        'httpx',
        'tkinter',
        'tkinter.ttk',
        'tkinter.scrolledtext',
        'win32gui',
        'win32con',
        'pyperclip',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['pyobjc'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='WemeAssistant',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version_file=None,
    icon=None,
)
"""


def main() -> None:
    print("Building WemeAssistant.exe...")

    SPEC_FILE.write_text(SPEC_CONTENT.strip(), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--clean", str(SPEC_FILE)],
        cwd=ROOT,
        check=False,
    )

    if result.returncode == 0:
        exe_path = ROOT / "dist" / "WemeAssistant.exe"
        print(f"\n✅ 打包成功: {exe_path}")
    else:
        print("\n❌ 打包失败，请检查错误信息")
        sys.exit(1)


if __name__ == "__main__":
    main()
