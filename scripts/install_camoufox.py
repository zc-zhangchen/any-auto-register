import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from platformdirs import user_cache_dir


def main() -> None:
    version = os.environ["CAMOUFOX_VERSION"]
    release = os.environ["CAMOUFOX_RELEASE"]
    arch_map = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "aarch64": "arm64",
        "arm64": "arm64",
        "i386": "i686",
        "i686": "i686",
        "x86": "i686",
    }
    machine = os.uname().machine.lower()
    arch = arch_map.get(machine)
    if not arch:
        raise SystemExit(f"Unsupported Camoufox arch: {machine}")

    tag = f"v{version}-{release}"
    asset_name = f"camoufox-{version}-{release}-lin.{arch}.zip"
    asset_url = f"https://github.com/daijro/camoufox/releases/download/{tag}/{asset_name}"
    addon_url = "https://addons.mozilla.org/firefox/downloads/latest/ublock-origin/latest.xpi"
    install_dir = Path(user_cache_dir("camoufox"))
    temp_dir = Path(tempfile.mkdtemp(prefix="camoufox-install-"))

    try:
        if install_dir.exists():
            shutil.rmtree(install_dir)
        install_dir.mkdir(parents=True, exist_ok=True)

        archive_path = temp_dir / asset_name
        print(f"Downloading Camoufox package: {asset_url}")
        urllib.request.urlretrieve(asset_url, archive_path)
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(install_dir)

        version_path = install_dir / "version.json"
        version_path.write_text(
            json.dumps({"version": version, "release": release}),
            encoding="utf-8",
        )

        addon_dir = install_dir / "addons" / "UBO"
        addon_dir.mkdir(parents=True, exist_ok=True)
        addon_path = temp_dir / "ublock-origin.xpi"
        print(f"Downloading default addon UBO: {addon_url}")
        urllib.request.urlretrieve(addon_url, addon_path)
        with zipfile.ZipFile(addon_path) as zf:
            zf.extractall(addon_dir)

        for path in install_dir.rglob("*"):
            if path.is_dir():
                path.chmod(0o755)
            else:
                path.chmod(0o644)

        binary = install_dir / "camoufox-bin"
        if binary.exists():
            binary.chmod(0o755)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
