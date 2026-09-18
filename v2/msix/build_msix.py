"""Build the Microsoft Store MSIX package.

python build_msix.py --name <Package/Identity/Name> --publisher "CN=..." --display "<PublisherDisplayName>"
Values come from Partner Center > Product management > Product identity.
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import make_assets  # noqa: E402


def sdkTool(name):
    hits = sorted(glob.glob(rf"C:\Program Files (x86)\Windows Kits\10\bin\10.*\x64\{name}"))
    if not hits:
        sys.exit(f"{name} not found, install the Windows SDK")
    return hits[-1]


def run(cmd, **kw):
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--publisher", required=True)
    ap.add_argument("--display", required=True)
    ap.add_argument("--version", default="2.3.0.0")
    ap.add_argument("--skip-build", action="store_true")
    args = ap.parse_args()
    if not args.version.endswith(".0"):
        sys.exit("the Store requires the last version part to be 0")

    work = os.path.join(tempfile.gettempdir(), "cleanix_msix")
    if not args.skip_build:
        run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
             "--distpath", os.path.join(work, "dist"), "--workpath", os.path.join(work, "build"),
             os.path.join(V2, "Cleanix-store.spec")])

    layout = os.path.join(work, "layout")
    shutil.rmtree(layout, ignore_errors=True)
    shutil.copytree(os.path.join(work, "dist", "Cleanix"), os.path.join(layout, "Cleanix"))
    make_assets.build(os.path.join(layout, "Assets"))

    with open(os.path.join(HERE, "AppxManifest.template.xml"), encoding="utf-8") as f:
        manifest = f.read()
    for key, value in (("{IDENTITY_NAME}", args.name), ("{PUBLISHER}", args.publisher),
                       ("{PUBLISHER_DISPLAY_NAME}", args.display), ("{VERSION}", args.version)):
        manifest = manifest.replace(key, escape(value, {'"': "&quot;"}))
    with open(os.path.join(layout, "AppxManifest.xml"), "w", encoding="utf-8") as f:
        f.write(manifest)

    priconfig = os.path.join(work, "priconfig.xml")
    run([sdkTool("makepri.exe"), "createconfig", "/cf", priconfig, "/dq", "ar", "/o"])
    run([sdkTool("makepri.exe"), "new", "/pr", layout, "/cf", priconfig,
         "/mn", os.path.join(layout, "AppxManifest.xml"), "/of", os.path.join(layout, "resources.pri"), "/o"])

    outDir = os.path.join(HERE, "out")
    os.makedirs(outDir, exist_ok=True)
    msix = os.path.join(work, f"Cleanix_{args.version}_x64.msix")
    run([sdkTool("makeappx.exe"), "pack", "/d", layout, "/p", msix, "/o"])
    shutil.copy2(msix, outDir)
    print("package:", os.path.join(outDir, os.path.basename(msix)))
    print("layout:", layout)


if __name__ == "__main__":
    main()
