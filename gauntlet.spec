# PyInstaller spec: `pyinstaller gauntlet.spec` -> dist/gauntlet (one-folder build).
# Bundled game configs are copied into the per-user data dir on first run (see paths.seed_data_dir).
a = Analysis(
    ["gauntlet.py"],
    pathex=[],
    datas=[("gauntlet/presets", "gauntlet/presets"), ("gauntlet_data", "gauntlet_data"),
           ("start_states", "start_states")],
    hiddenimports=[],
    excludes=["tkinter", "numpy", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="gauntlet",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="gauntlet", upx=False)
