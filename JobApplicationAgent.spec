from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


root = Path(SPEC).resolve().parent
datas = [
    (str(root / "app" / "dashboard" / "static"), "app/dashboard/static"),
    (str(root / "config"), "config"),
]
for relative in (Path("data/resumes"), Path("data/fixtures")):
    source = root / relative
    if source.is_dir():
        datas.append((str(source), str(relative).replace("\\", "/")))

a = Analysis(
    [str(root / "app" / "desktop.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=collect_submodules("playwright"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JobApplicationAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    contents_directory=".",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="JobApplicationAgent",
)
