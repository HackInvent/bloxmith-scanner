"""SANE scanning and all-or-nothing PDF publication, with no framework internals."""

from collections.abc import Mapping
from contextlib import ExitStack, contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import time
import uuid
import warnings

from bloxsmith_app.block_api import BlockRuntimeOutput, BlockRuntimeResult, FILE_PATH
from .device_process import DeviceError, Cancelled, check_cancel, run_tool, require_success

DEFAULTS = {"device": "", "color": "color", "resolution": 300, "source": "flatbed", "paper": "A4", "output_directory": "", "filename_prefix": "scan", "max_pages": 10, "timeout_sec": 120, "max_scan_mb": 256}


def storage_directory(context):
    """Use only the public node-owned storage service, in all hosting modes."""
    storage = context.services.get("get_block_storage_dir")
    if not callable(storage):
        raise DeviceError("The framework did not provide instance-scoped block storage.")
    directory = Path(storage())
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@contextmanager
def request_state(context):
    """Synchronize this block's tiny pending-request file across supervised hosts.

    Node-runtime-value/lock helpers are not assumed to exist in every engine.
    The framework owns the directory; the block alone owns these files.
    """
    directory = storage_directory(context)
    with (directory / "request.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = directory / "scan-request.json"
        try:
            value = json.loads(path.read_text()) if path.exists() and path.stat().st_size < 2048 else {}
        except (OSError, ValueError):
            value = {}
        yield directory, path, value if isinstance(value, dict) else {}


def reserve_request(context):
    """Reserve one scan, coalescing duplicate clicks before acquisition has started."""
    with request_state(context) as (directory, path, value):
        if value.get("run_id") == context.run_id and value.get("token"):
            return None
        with (directory / "scanner.lock").open("a") as acquisition:
            try:
                fcntl.flock(acquisition, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return None
        token = uuid.uuid4().hex
        path.write_text(json.dumps({"run_id": context.run_id, "token": token}), encoding="utf-8")
        return token


def current_request(context, token):
    """Reject an obsolete command from another Run before touching hardware."""
    with request_state(context) as (_, __, value):
        return value.get("run_id") == context.run_id and value.get("token") == token


def release_request(context, token):
    """Only clear our reservation; never erase a newer Run's request."""
    with request_state(context) as (_, path, value):
        if value.get("run_id") == context.run_id and value.get("token") == token:
            path.unlink(missing_ok=True)


def normalize_config(raw):
    """Validate immutable preparation config without talking to a scanner."""
    if not isinstance(raw, Mapping):
        raise DeviceError("Scanner settings must be an object.")
    config = {**DEFAULTS, **{k: v for k, v in raw.items() if k in DEFAULTS}}
    for key, low, high in (("resolution", 75, 600), ("max_pages", 1, 50), ("timeout_sec", 5, 240), ("max_scan_mb", 16, 512)):
        if type(config[key]) is not int or not low <= config[key] <= high:
            raise DeviceError(f"{key} must be an integer from {low} to {high}.")
    for key, values in {"color": ("color", "gray", "lineart"), "source": ("flatbed", "adf", "adf_duplex"), "paper": ("A4", "Letter", "auto")}.items():
        if config[key] not in values:
            raise DeviceError(f"Invalid {key} setting.")
    for key in ("device", "output_directory", "filename_prefix"):
        if not isinstance(config[key], str) or len(config[key]) > 4096 or any(ord(c) < 32 for c in config[key]):
            raise DeviceError(f"Invalid {key}.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", config["filename_prefix"]):
        raise DeviceError("File prefix must use 1–64 letters, digits, dots, underscores or hyphens.")
    return config


def devices():
    """Ask installed SANE backends for their configured USB/network devices."""
    output = require_success(run_tool(["scanimage", "--formatted-device-list=%d\t%v %m\n"], timeout=15), "scanimage")
    result = []
    for line in output.splitlines():
        if "\t" in line:
            identifier, label = line.split("\t", 1)
            if identifier:
                result.append({"id": identifier, "label": label.strip() or identifier})
    return {"devices": result}


def choices(help_text, option):
    """Read discrete driver values from scanimage's own --help description."""
    match = re.search(r"^\s*--" + re.escape(option) + r"\s+([^\n\[]+)", help_text, re.M)
    return [part.strip() for part in match.group(1).strip().split("|")] if match else []


def choose(values, alternatives, label):
    """Fail unsupported requests instead of silently scanning with other settings."""
    for alternative in alternatives:
        for value in values:
            if value.casefold() == alternative.casefold():
                return value
    raise DeviceError(f"This scanner does not advertise the requested {label}. Select a supported setting.")


def scan_arguments(config, help_text):
    """Translate friendly settings to exact, advertised backend option values."""
    modes = {"color": ("Color", "Colour", "24bit Color", "24-bit Color"), "gray": ("Gray", "Grayscale", "8bit Gray", "8-bit Gray"), "lineart": ("Lineart", "LineArt", "Binary", "Black & White")}
    args = ["scanimage", "--device-name", config["device"], "--format=pnm", "--mode", choose(choices(help_text, "mode"), modes[config["color"]], "color mode"), "--resolution", str(config["resolution"])]
    sources = choices(help_text, "source")
    if sources:
        alternatives = {"flatbed": ("Flatbed", "Normal", "Platen"), "adf": ("ADF", "ADF Front", "ADF Simplex", "Automatic Document Feeder"), "adf_duplex": ("ADF Duplex", "ADF Both", "Duplex", "Automatic Document Feeder (Duplex)")}
        args += ["--source", choose(sources, alternatives[config["source"]], "paper source")]
    elif config["source"] != "flatbed":
        raise DeviceError("This scanner does not advertise an automatic document feeder.")
    if config["paper"] != "auto":
        width, height = (210, 297) if config["paper"] == "A4" else (215.9, 279.4)
        args += ["-x", str(width), "-y", str(height)]
    return args


def execute(context, *, request_token=None):
    """Acquire one device, create a unique PDF, and publish only after conversion."""
    temporary_pdf = None
    try:
        from PIL import Image
        config = normalize_config(context.config)
        if not config["device"]:
            raise DeviceError("Select an installed scanner in the block settings first.")
        check_cancel(context)
        block_dir = storage_directory(context)
        target = Path(config["output_directory"]).expanduser() if config["output_directory"] else block_dir / "scans"
        if not target.is_absolute():
            target = Path(context.root_dir) / target
        target.mkdir(parents=True, exist_ok=True)
        target = target.resolve()
        deadline = time.monotonic() + config["timeout_sec"]
        with (block_dir / "scanner.lock").open("a") as lock, tempfile.TemporaryDirectory(prefix="scan-", dir=block_dir) as temporary:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise DeviceError("A scan is already running for this block. Wait for it to finish.") from error
            if request_token is not None and not current_request(context, request_token):
                return BlockRuntimeResult(status="skipped", outputs=[], last_message="Obsolete scan request ignored.")
            help_text = require_success(run_tool(["scanimage", "--device-name", config["device"], "--help"], timeout=min(15, config["timeout_sec"]), context=context), "scanimage")
            args = scan_arguments(config, help_text)
            directory = Path(temporary)
            budget = config["max_scan_mb"] * 1024 * 1024
            count = 1 if config["source"] == "flatbed" else config["max_pages"]
            args += [f"--batch={directory / 'page-%04d.pnm'}", f"--batch-count={count}"]
            response = run_tool(args, timeout=max(.1, deadline - time.monotonic()), context=context, directory=directory, budget=budget)
            # SANE_STATUS_NO_DOCS is normal only at the end of a feeder batch.
            if response[0] != 0 and not (response[0] == 7 and config["source"] != "flatbed"):
                require_success(response, "scanimage")
            pages = sorted(directory.glob("page-*.pnm"))
            if not pages:
                raise DeviceError("No page was scanned. Check the document feeder, paper and device.")
            if len(pages) > count or sum(p.stat().st_size for p in pages) > budget:
                raise DeviceError("Scan exceeded the configured page or storage limit.")
            check_cancel(context)
            filename = f"{config['filename_prefix']}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex}.pdf"
            final_pdf = target / filename
            temporary_pdf = target / ("." + filename + ".partial")
            # Keep a global decoded-pixel cap as well as the compressed-file budget.
            with ExitStack() as stack, warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                images, pixels = [], 0
                for page in pages:
                    check_cancel(context)
                    if time.monotonic() > deadline:
                        raise DeviceError("Scan conversion timed out; no PDF was published.")
                    with Image.open(page) as original:
                        pixels += original.width * original.height
                        if pixels * 4 > min(budget, 256 * 1024 * 1024):
                            raise DeviceError("Decoded pages exceed the memory limit. Reduce the resolution or page count.")
                        image = original.convert("RGB" if config["color"] == "color" else "L")
                    stack.callback(image.close)
                    images.append(image)
                with temporary_pdf.open("xb") as output:
                    images[0].save(output, format="PDF", save_all=True, append_images=images[1:], resolution=config["resolution"], quality=95, subsampling=0)
            check_cancel(context)
            if time.monotonic() > deadline or temporary_pdf.stat().st_size > budget:
                raise DeviceError("PDF conversion exceeded the configured time or size limit.")
            # An exclusive hard link publishes the completed file atomically, and
            # unlike rename never replaces even an extraordinarily unlikely collision.
            os.link(temporary_pdf, final_pdf)
            temporary_pdf.unlink()
            temporary_pdf = None
        details = {"absolute_path": str(final_pdf), "mime_type": "application/pdf", "pages": len(pages), "bytes": final_pdf.stat().st_size, "resolution": config["resolution"]}
        logs = [f"[scanner] Saved {len(pages)} page(s) as {final_pdf.name}."]
        if config["source"] != "flatbed" and len(pages) == count:
            logs.append("[scanner] Page limit reached. More sheets may remain in the feeder; start another scan if needed.")
        return BlockRuntimeResult(status="success", outputs=[BlockRuntimeOutput(port_id=1, port_name="pdf", value=str(final_pdf), content_type=FILE_PATH, metadata=details)], metadata={"scan": details}, logs=logs, last_message=str(final_pdf), content_type=FILE_PATH)
    except Cancelled:
        return BlockRuntimeResult(status="cancelled", outputs=[], last_message="Scan cancelled; no partial PDF was published.")
    except ImportError:
        return BlockRuntimeResult(status="failed", outputs=[], error="Pillow is required on the BloxSmith host to generate PDFs.")
    except Exception as error:
        message = str(error) if isinstance(error, DeviceError) else "Cannot scan or create the PDF. Check device permissions, output folder and available storage."
        return BlockRuntimeResult(status="failed", outputs=[], error=message, last_message=message, logs=[f"[scanner-error] {message}"])
    finally:
        if temporary_pdf is not None:
            temporary_pdf.unlink(missing_ok=True)
