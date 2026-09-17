# Bulk Auto Process Runbook

## What it does

`bulk-auto-process.py` processes every supported image in a workspace through two passes:

1. Remove the logo.
2. Remove the watermark text.

Successful originals are moved immediately, one image at a time, to `<base-folder>/input/done`. Final images are written to `<base-folder>/output` with exactly the same filename and file type as the input (`input/photo.jpg` becomes `output/photo.jpg`, `input/photo.png` becomes `output/photo.png`, and so on). This makes the output suitable for replacing the original with a file drop. If the final output already exists, the input is skipped and archived without overwriting the output. Temporary files are stored in `<base-folder>/input/tmp` and removed when each image finishes. The temporary folder is cleared when the script starts so interrupted work does not get reused.

The script creates the workspace folders automatically. It shows the batch total, completed, failed and skipped images, remaining images, progress percentage, and an ETA after two images have been processed. Existing files in `done` are never overwritten; a timestamp is added to duplicate names.

## How to use (step by step)

1. Open PowerShell.
2. Change to the repository root:

   ```powershell
   cd C:\path\to\WatermarkRemover-AI
   ```

3. Put the images to process in `images/input`.
4. Start the default batch:

   ```powershell
   .\python\python.exe bulk-auto-process.py
   ```

5. Wait for the batch summary. Successful input files will be in `images/input/done`, and processed images will be in `images/output`.

Failed images remain in `images/input` so they can be retried after the problem is fixed.

## Examples

Process the default workspace:

```powershell
.\python\python.exe bulk-auto-process.py
```

Process a separate workspace:

```powershell
.\python\python.exe bulk-auto-process.py --base-folder .\images-batch-1
```

The short option is also available:

```powershell
.\python\python.exe bulk-auto-process.py -b .\images-batch-2
```

Each base folder has its own `input`, `input/done`, `input/tmp`, and `output` folders, so independent batches can run at the same time:

```powershell
Start-Process powershell -ArgumentList '-NoExit', '-Command', '.\python\python.exe bulk-auto-process.py -b .\images-batch-1'
Start-Process powershell -ArgumentList '-NoExit', '-Command', '.\python\python.exe bulk-auto-process.py -b .\images-batch-2'
```

See all options with:

```powershell
.\python\python.exe bulk-auto-process.py --help
```
