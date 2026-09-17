"""Process images in two automatic watermark-removal passes on Windows."""

from __future__ import annotations

import argparse
from datetime import datetime
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
FIRST_PASS_PROMPT = "watermark logo"
SECOND_PASS_PROMPT = "watermark"


class Workspace:
    """Paths used by one bulk-processing process."""

    def __init__(self, base_folder: Path) -> None:
        self.base_folder = base_folder
        self.input_dir = base_folder / "input"
        self.done_dir = self.input_dir / "done"
        self.tmp_dir = self.input_dir / "tmp"
        self.output_dir = base_folder / "output"


def format_duration(seconds: float | None) -> str:
    """Return a compact human-readable duration."""
    if seconds is None or seconds < 0 or seconds == float("inf"):
        return "calculating"
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def processing_format(source: Path) -> str:
    """Return the remwm.py format flag matching the input image type."""
    formats = {
        ".jpg": "JPG",
        ".jpeg": "JPG",
        ".png": "PNG",
        ".webp": "WEBP",
    }
    return formats[source.suffix.lower()]


def remwm_output_extension(force_format: str) -> str:
    """Return the extension emitted by remwm.py for a forced format."""
    return ".jpeg" if force_format == "JPG" else f".{force_format.lower()}"


def clear_directory(directory: Path) -> None:
    """Remove every child from a working directory without removing the directory itself."""
    for child in directory.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def ensure_directories(workspace: Workspace) -> list[Path]:
    """Create the required workspace directories and return those newly created."""
    created: list[Path] = []
    for directory in (
        workspace.base_folder,
        workspace.input_dir,
        workspace.done_dir,
        workspace.tmp_dir,
        workspace.output_dir,
    ):
        if not directory.exists():
            directory.mkdir(parents=True)
            created.append(directory)
    return created


def print_welcome(workspace: Workspace, created: list[Path]) -> None:
    """Explain the workspace when starting the bulk processor."""
    print("=" * 72)
    print("Bulk Auto Process")
    print("=" * 72)
    if created:
        print("Created the following workspace directories:")
        for directory in created:
            print(f"  - {directory}")
        print()
        print("How it works:")
        print(f"  1. Place images to clean in {workspace.input_dir}.")
        print(f"  2. Clean originals are moved to {workspace.done_dir} after success.")
        print(f"  3. Final images are written to {workspace.output_dir}.")
        print("  4. Files already in done are preserved with a timestamped name.")
        print()
    print(f"Base:    {workspace.base_folder}")
    print(f"Input:   {workspace.input_dir}")
    print(f"Output:  {workspace.output_dir}")
    print(f"Done:    {workspace.done_dir}")
    print()


def collision_safe_done_path(workspace: Workspace, source: Path) -> Path:
    """Return a done path that never overwrites an existing original."""
    candidate = workspace.done_dir / source.name
    if not candidate.exists():
        return candidate

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = workspace.done_dir / f"{source.stem}_{timestamp}{source.suffix}"
    counter = 1
    while candidate.exists():
        candidate = workspace.done_dir / f"{source.stem}_{timestamp}_{counter}{source.suffix}"
        counter += 1
    return candidate


def final_output_path(workspace: Workspace, source: Path) -> Path:
    """Return the final output path, preserving the input name and extension."""
    return workspace.output_dir / source.name


def archive_original(workspace: Workspace, source: Path) -> Path:
    """Move an input image to done without overwriting an older original."""
    done_path = collision_safe_done_path(workspace, source)
    shutil.move(str(source), str(done_path))
    return done_path


def list_input_images(workspace: Workspace) -> list[Path]:
    """Return supported image files directly inside the input directory."""
    return sorted(
        (
            path
            for path in workspace.input_dir.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ),
        key=lambda path: path.name.lower(),
    )


def python_executable() -> Path:
    """Prefer the portable application runtime when it exists."""
    portable = ROOT / "python" / "python.exe"
    return portable if portable.exists() else Path(sys.executable)


def run_pass(
    source: Path,
    destination_base: Path,
    prompt: str,
    label: str,
    force_format: str,
) -> Path:
    """Run one remwm.py pass and return its expected output path."""
    extension = remwm_output_extension(force_format)
    destination = destination_base.with_suffix(extension)
    command = [
        str(python_executable()),
        str(ROOT / "remwm.py"),
        str(source),
        str(destination_base),
        "--detection-prompt",
        prompt,
        "--force-format",
        force_format,
    ]

    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        output = "\n".join(
            part for part in (result.stdout, result.stderr) if part
        ).strip()
        detail = next((line.strip() for line in reversed(output.splitlines()) if line.strip()), "")
        suffix = f" {detail}" if detail else ""
        raise RuntimeError(f"{label} failed with exit code {result.returncode}.{suffix}")
    if not destination.exists():
        raise RuntimeError(f"{label} finished without creating {destination}.")
    return destination


def print_dashboard(
    total: int,
    completed: int,
    failed: int,
    skipped: int,
    started_at: float,
) -> None:
    """Print batch counters and ETA based on images actually processed."""
    elapsed = time.monotonic() - started_at
    finished = completed + failed + skipped
    processed = completed + failed
    average = elapsed / processed if processed else None
    remaining = total - finished
    eta = average * remaining if average is not None and processed >= 2 else None
    percentage = (finished / total * 100) if total else 100
    eta_text = format_duration(eta) if processed >= 2 else "available after 2 processed images"
    print(
        f"\nBatch: {finished}/{total} finished | "
        f"Completed: {completed} | Failed: {failed} | Skipped: {skipped} | "
        f"Progress: {percentage:.1f}% | Remaining: {remaining} | ETA: {eta_text}"
    )
    if average is not None:
        print(f"Average per image: {format_duration(average)}")


def process_image(workspace: Workspace, source: Path) -> None:
    """Run logo removal, watermark removal, cleanup and archival for one image."""
    force_format = processing_format(source)
    processing_extension = remwm_output_extension(force_format)
    temporary_base = workspace.tmp_dir / f"{source.stem}_with_no_logo"
    temporary_output = temporary_base.with_suffix(processing_extension)
    final_output = final_output_path(workspace, source)
    final_base = final_output.with_suffix("")
    processing_final_output = final_base.with_suffix(processing_extension)

    try:
        run_pass(
            source,
            temporary_base,
            FIRST_PASS_PROMPT,
            "Pass 1/2 - logo removal",
            force_format,
        )
        if not temporary_output.exists():
            raise RuntimeError(f"Expected intermediate file was not created: {temporary_output}")

        run_pass(
            temporary_output,
            final_base,
            SECOND_PASS_PROMPT,
            "Pass 2/2 - watermark removal",
            force_format,
        )
        if processing_final_output != final_output:
            if final_output.exists():
                raise RuntimeError(f"Refusing to overwrite existing output: {final_output}")
            processing_final_output.replace(final_output)
        archive_original(workspace, source)
    finally:
        if temporary_output.exists():
            temporary_output.unlink()


def parse_args() -> argparse.Namespace:
    """Parse the optional workspace location."""
    parser = argparse.ArgumentParser(
        description="Process all supported images in a two-pass watermark-removal workflow."
    )
    parser.add_argument(
        "-b",
        "--base-folder",
        default="./images",
        help="Workspace folder containing input, output and input/done (default: ./images).",
    )
    return parser.parse_args()


def main() -> int:
    """Run the bulk processor."""
    args = parse_args()
    workspace = Workspace(Path(args.base_folder).expanduser().resolve())

    created = ensure_directories(workspace)
    clear_directory(workspace.tmp_dir)
    print_welcome(workspace, created)

    images = list_input_images(workspace)
    if not images:
        print(f"No supported images found in {workspace.input_dir}. Nothing to process.")
        return 0

    print(f"Found {len(images)} image(s) to process.")
    started_at = time.monotonic()
    completed = 0
    failed = 0
    skipped = 0

    for index, image in enumerate(images, start=1):
        output_path = final_output_path(workspace, image)
        if output_path.exists():
            try:
                done_path = archive_original(workspace, image)
            except Exception as exc:
                failed += 1
                print(f"ERROR: {image.name}: could not archive skipped input: {exc}")
            else:
                skipped += 1
                print(
                    f"Skipping: {image.name} because output already exists: {output_path}. "
                    f"Archived original as: {done_path}"
                )
            print_dashboard(len(images), completed, failed, skipped, started_at)
            continue

        print(
            f"\n[{index}/{len(images)}] Processing {image.name} "
            "(logo removal, then watermark removal)..."
        )
        try:
            process_image(workspace, image)
        except KeyboardInterrupt:
            print(f"\nStopped by user. The current original remains in {workspace.input_dir}.")
            return 130
        except Exception as exc:
            failed += 1
            print(f"ERROR: {image.name}: {exc}")
        else:
            completed += 1
        print_dashboard(len(images), completed, failed, skipped, started_at)

    print("\nBulk processing finished.")
    if failed:
        print(f"{failed} image(s) failed and remain in {workspace.input_dir} for retry.")
        return 1
    print(
        f"All images were processed or skipped successfully. "
        f"Originals are archived in {workspace.done_dir}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
