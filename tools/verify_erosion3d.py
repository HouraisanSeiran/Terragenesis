"""Compile and run only the pure-Java erosion3d verification with the pinned JDK 25."""
from pathlib import Path
import subprocess

from build_local import JAVA, ROOT


def main() -> None:
    output = ROOT / "verification" / "erosion3d"
    classes = output / "classes"
    classes.mkdir(parents=True, exist_ok=True)

    package = Path("com/remotemountains/erosion3d")
    production = sorted((ROOT / "src/main/java" / package).glob("*.java"))
    tests = sorted((ROOT / "src/test/java" / package).glob("*.java"))
    if not production or not tests:
        raise RuntimeError("erosion3d sources or verification are missing")

    subprocess.run(
        [str(JAVA / "javac.exe"), "-encoding", "UTF-8", "--release", "25",
         "-proc:none", "-d", str(classes), *(str(path) for path in production + tests)],
        cwd=ROOT, check=True,
    )
    subprocess.run(
        [str(JAVA / "java.exe"), "-cp", str(classes),
         "com.remotemountains.erosion3d.Erosion3dVerification"],
        cwd=ROOT, check=True,
    )


if __name__ == "__main__":
    main()
