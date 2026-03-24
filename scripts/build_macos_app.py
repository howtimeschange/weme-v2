"""
build_macos_app.py - 打包 Weme v2 为 macOS .app

使用 PyInstaller 构建自包含的 macOS 应用包。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SPEC_FILE = ROOT / "weme_macos.spec"

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
        'typer',
        'yaml',
        'httpx',
        'tkinter',
        'tkinter.ttk',
        'tkinter.scrolledtext',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='weme',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='weme',
)

app = BUNDLE(
    coll,
    name='Weme Assistant.app',
    icon=None,
    bundle_identifier='com.weme.assistant',
    info_plist={
        'CFBundleName': 'Weme Assistant',
        'CFBundleDisplayName': '虾说',
        'CFBundleVersion': '2.0.0',
        'CFBundleShortVersionString': '2.0.0',
        'NSHighResolutionCapable': True,
        'NSAppleEventsUsageDescription': 'Weme 需要 AppleScript 访问权限来读取聊天内容',
        'NSAccessibilityUsageDescription': 'Weme 需要辅助功能权限来自动化聊天操作',
    },
)
"""


def main() -> None:
    print("Building Weme Assistant.app...")

    # 写 spec 文件
    SPEC_FILE.write_text(SPEC_CONTENT.strip(), encoding="utf-8")

    # 运行 PyInstaller
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--clean", str(SPEC_FILE)],
        cwd=ROOT,
        check=False,
    )

    if result.returncode == 0:
        app_path = DIST / "Weme Assistant.app"
        print(f"\n✅ 打包成功: {app_path}")
        print(f"\n使用方法:")
        print(f"  open '{app_path}'")
        print(f"\n如果 macOS 提示安全问题，运行:")
        print(f"  xattr -cr '{app_path}'")
    else:
        print("\n❌ 打包失败，请检查错误信息")
        sys.exit(1)


if __name__ == "__main__":
    main()
