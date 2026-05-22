# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for StructLab -- 2D Structural Analysis Desktop App.

Standard build command (outside OneDrive):
    pyinstaller StructLab.spec --distpath C:\Builds\StructLab\dist --workpath C:\Builds\StructLab\build --noconfirm

Protected build (PyArmor obfuscated):
    powershell -ExecutionPolicy Bypass -File build_protected.ps1

Output:
    C:\Builds\StructLab\dist\StructLab\StructLab.exe  (one-folder bundle)
"""

import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

mpl_hidden = collect_submodules("matplotlib")
mpl_datas  = collect_data_files("matplotlib")
pyqt6_hidden = collect_submodules("PyQt6")

a = Analysis(
    ["ui_qt/main.py"],
    pathex=["."],
    binaries=[],
    datas=mpl_datas + [
        ("ui_qt/assets", "ui_qt/assets"),
    ],
    hiddenimports=(
        mpl_hidden
        + pyqt6_hidden
        + [
            "matplotlib.backends.backend_qtagg",
            "matplotlib.backends.backend_qt",
            "scipy",
            "scipy.linalg",
            "scipy.sparse",
            "numpy",
            "numpy.core._multiarray_umath",
            "core",
            "core.model",
            "core.node",
            "core.element",
            "core.load",
            "core.support",
            "core.material",
            "core.section",
            "elements",
            "elements.frame_element",
            "elements.bar_element",
            "elements.truss_element",
            "solver",
            "solver.assembler",
            "solver.linear_solver",
            "solver.postprocessor",
            "solver.fem_loads",
            "ui_qt",
            "ui_qt.main",
            "ui_qt.main_window",
            "ui_qt.canvas",
            "ui_qt.canvas_overlay",
            "ui_qt.panels",
            "ui_qt.model_state",
            "ui_qt.model_builder",
            "ui_qt.presets",
            "ui_qt.wizards",
            "ui_qt.combinations",
            "ui_qt.pattern_loading",
            "ui_qt.envelope",
            "ui_qt.io",
            "ui_qt.theme",
            "ui_qt.section_library",
            "ui_qt.section_picker",
        ]
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "streamlit", "IPython",
        "jupyter", "notebook", "pytest", "setuptools",
    ],
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
    name="StructLab",
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
    icon="ui_qt/assets/structlab.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="StructLab",
)
