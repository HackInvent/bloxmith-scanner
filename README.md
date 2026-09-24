# Scanner

An autonomous BloxSmith block that scans with an **already installed SANE device**,
creates a PDF and publishes its path. Scan directly from a button on the block card.
USB and network support depend on the installed SANE backend (for example AirScan
for compatible eSCL/WSD devices).

<!-- block-metadata:start -->
[![Block version: 0.1.0](https://img.shields.io/badge/block-0.1.0-blue)](model.json)
[![BloxSmith compatibility: 1.0.9](https://img.shields.io/badge/BloxSmith-1.0.9-brightgreen)](compatibility.json)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

Verified BloxSmith versions: **1.0.9** (bundled-block tests; see [test evidence](compatibility.json)).
<!-- block-metadata:end -->

## Requirements

- Linux on the BloxSmith host, with `scanimage` (SANE utilities), the correct backend
  and permission for the application account to access the scanner.
- Pillow in the Python environment used by BloxSmith (`PIL.Image`), for PDF creation.
- A configured USB/network scanner. A USB device connected only to a remote
  browser's computer is not accessible through this server-side block.

The block never installs a driver, modifies system scanner configuration or tries
to bypass device permissions.

## Use

1. In the modal or inspector, click **Refresh** and select a scanner. Selection is
   explicit; the block never silently uses the first discovered device.
2. Choose color/grayscale/black and white, resolution (75–600 dpi), flatbed or
   feeder (simplex/duplex), and A4/Letter/device-default page size.
3. Optionally set an output folder and filename prefix. Apply the settings.
4. Load **Run**, then click **Scan** on the block card. Connect `pdf` to a File
   consumer, a document processor or the Printer block.

Run preparation starts an **idle listener**, without contacting the scanner.
The card button calls the existing public runtime `trigger_node` control with the
canonical node ID (also inside composites). Acquisition happens inside the block
runtime, not in an HTTP UI hook, and the result is published normally downstream.
The button needs a prepared/running Active Runtime and is disabled in read-only
surfaces. Closing a modal or navigating the graph does not cancel an ongoing scan.

**Executing this source also scans:** the graph's Play action and One Shot execute
source blocks, so they are not hardware-free simulations. If you only want the
button, use Run then Scan, without Play. Apply changes before Run; restart a loaded
Run to use new settings. The block does not maintain an unbounded request queue:
overlapping requests for the same instance are rejected/ignored while busy.

For API-driven event workflows, use the persistent **prepare → trigger/Play →
Stop** lifecycle, as the editor does. The legacy finite auto-start run endpoint is
not suitable for asynchronous sources: ordinary consumers can close before their
delayed result. Centralized One Shot acquires and returns its PDF synchronously.

### Output

| Port | Type | Meaning |
| --- | --- | --- |
| `pdf` · output | `file/path` | Absolute path of one completed PDF on the BloxSmith host |

Metadata contains `mime_type: application/pdf`, page count, file size and resolution.
No output is emitted for failures or cancelled/incomplete scans.

A blank output folder uses the public `get_block_storage_dir()` service and stores
files in this node's persistent `scans/` subdirectory. A custom folder is created
if needed; relative paths start at the application directory. Files survive Stop
and Run. Every filename includes the prefix, timestamp and a random ID; previous
PDFs are never overwritten. There is no automatic deletion of saved documents.

## Acquisition behavior and limits

- Flatbed: one page per click. Feeder: pages are collected until empty or the
  configured maximum is reached (default 10, maximum 50). A full batch may leave
  sheets in the feeder; the log reports that limit.
- Duplex requires a backend advertising a recognized duplex source. Flatbed pages
  are not accumulated through repeated clicks: each click creates a separate PDF.
- Color/source choices are matched to the device's advertised values. Unsupported
  modes fail explicitly. There is no silent downgrade to a different color/source.
- Defaults: 300 dpi, color, flatbed, A4, 120 seconds, 256 MiB temporary storage.
  Memory is also bounded to 256 MiB of decoded image data; reduce page count or
  resolution for longer batches. PDFs contain images, **not OCR text**.
- Stop terminates the owned CLI. Partial pages and incomplete PDFs are removed;
  only a complete PDF is atomically made visible on the output.
- Processes receive no shell/terminal, diagnostics are bounded, and a guard kills
  acquisition when its managed host disappears. Temporary files may remain after
  an uncatchable host kill; saved PDFs are never automatically removed.

## Tests and compatibility

Tests cover discovery, driver option mapping, flatbed/simplex/duplex PDFs, unique
names, page and memory limits, failures after partial acquisition, cancellation,
concurrent requests, managed/linked packages, both execution engines, passive Run,
the real canvas Scan button, repeated scans and downstream output. Browser QA
checks modal/inspector Apply/Cancel, translations and widths of 1440/390/320 pixels.
All hardware calls are substituted by fake SANE tools. **No physical scanner
model, driver or network environment is certified by these tests.**

```bash
python3 -B tests/run_tests.py --refresh-framework scanner
```

Exact successful test evidence is recorded in `compatibility.json`. Version
`0.1.0` is the initial local development version; no release is implied.

Device option names vary by backend. See the [SANE scanimage manual](https://www.sane-project.org/man/scanimage.1.html)
and [SANE AirScan documentation](https://github.com/alexpevzner/sane-airscan).
Licensed under Apache-2.0; see [LICENSE](LICENSE).
