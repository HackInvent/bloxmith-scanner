#!/usr/bin/env python3
"""FB1/FB2/FB3: SANE/PDF safety, cancellation and installed-package runtime parity."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from blocs.scanner.block import ScannerBlock
from blocs.scanner.runtime import normalize_config, reserve_request, release_request, current_request
from blocs.scanner.device_process import DeviceError
from device_fixtures import equipment, calls, context, node
from block_test_packages import install_test_package, prepare_release_run
from ui_smoke_common import (isolated_server, graph_payload, display_node, data_edge,
    create_project_api, create_run_api, wait_for_run_predicate, stop_run_api, play_run_api)


def test_pdf():
    """FB1/FB2: complete unique PDFs, feeder pages, unsupported modes and no partials."""
    block = ScannerBlock()
    assert block.model["version"] == "0.1.0"
    for invalid in ({"resolution": 9999}, {"max_pages": False}, {"source": "camera"}, {"filename_prefix": "../overwrite"}):
        try:
            normalize_config(invalid)
        except DeviceError:
            pass
        else:
            raise AssertionError(invalid)
    with equipment() as root:
        cfg = {"device": "test:scanner", "timeout_sec": 5}
        probe = context(root, "scanner", config=cfg)
        assert block.prepare_runtime(probe).listen_on_run
        assert not calls(root), "Run preparation contacted equipment"
        token = reserve_request(probe)
        assert token and current_request(probe, token)
        assert reserve_request(probe) is None, "Duplicate pending scan was enqueued"
        release_request(probe, "wrong-token")
        assert current_request(probe, token)
        release_request(probe, token)
        assert not current_request(probe, token)
        assert block.handle_ui_request(node=node("scanner"), route="devices", method="POST", values={})["devices"][0]["id"] == "test:scanner"
        created = []
        for source, pages in (("flatbed", 1), ("adf", 3), ("adf_duplex", 3)):
            result = block.execute_runtime(context(root, "scanner", config={**cfg, "source": source, "output_directory": str(root / "pdfs")}))
            assert result.status == "success", result.error
            path = Path(result.outputs[0].value)
            assert path.read_bytes().startswith(b"%PDF-") and result.outputs[0].content_type == "file/path"
            assert result.metadata["scan"]["pages"] == pages
            inspected = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True).stdout
            assert f"Pages:           {pages}" in inspected, inspected
            created.append(path)
        assert len(set(created)) == 3 and all(p.exists() for p in created)
        limited = block.execute_runtime(context(root, "scanner", config={**cfg, "source": "adf", "max_pages": 2, "output_directory": str(root / "pdfs")}))
        assert limited.status == "success" and limited.metadata["scan"]["pages"] == 2
        assert "Page limit reached" in str(limited.logs)
        for mode in ("failure", "partial-jam", "empty", "invalid-image", "huge-image", "gray-only"):
            (root / "mode").write_text(mode)
            result = block.execute_runtime(context(root, "scanner", config=cfg))
            assert result.status == "failed" and not result.outputs, (mode, result)
            assert not list((root / "scanner-storage").rglob("*.partial"))
            assert not list((root / "scanner-storage").glob("scan-*"))
        (root / "mode").write_text("slow")
        stop = threading.Event()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(block.execute_runtime, context(root, "scanner", config=cfg, services={"cancel_requested": stop.is_set}))
            deadline = time.monotonic() + 3
            while not (root / "active.pid").exists() and time.monotonic() < deadline:
                time.sleep(.03)
            assert (root / "active.pid").exists()
            duplicate = block.execute_runtime(context(root, "scanner", config=cfg))
            assert duplicate.status == "failed" and "already running" in duplicate.error
            stop.set()
            assert future.result(timeout=2).status == "cancelled"
        pid = int((root / "active.pid").read_text())
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise AssertionError("Scanner child survived Stop")
        assert not list((root / "scanner-storage").rglob("*.pdf"))
        assert not list((root / "scanner-storage").glob("scan-*"))


def test_installed():
    """FB3: PDFs reach a display through managed/linked packages and both engines."""
    for origin in ("managed", "linked"):
        with equipment() as root, isolated_server() as server:
            install_test_package(server, "scanner", origin=origin)
            for mode in ("centralized", "zeromq_active"):
                sink = display_node("sink", "PDF", 660, 140)
                sink["inputs"][0]["accepts"].append("file/path")
                document = graph_payload("Scanner test", [node("scanner"), sink], [data_edge("out", "scanner-test", 1, "sink", 1)])
                project = create_project_api(server, document=document)["project"]
                # An asynchronous source uses the persistent editor Run lifecycle.
                # The legacy finite auto-start endpoint closes ordinary consumers
                # before a listener's delayed result; it is not an event session.
                if mode == "zeromq_active":
                    created = prepare_release_run(server, project["project_id"], document)
                    play_run_api(server, created["run_id"])
                else:
                    created = create_run_api(server, document, project_id=project["project_id"], runtime_mode=mode)
                try:
                    run = wait_for_run_predicate(server, created["run_id"], lambda r: r.get("node_statuses", {}).get("sink") == "success" or r.get("status") == "failed", "Scanner PDF did not reach sink", timeout_sec=20)
                    assert run.get("node_statuses", {}).get("sink") == "success", run.get("logs")
                    output = run["output_values"]["scanner-test:1"]
                    path = Path(output["value"] if isinstance(output, dict) else output)
                    assert path.exists() and path.read_bytes().startswith(b"%PDF-")
                finally:
                    stop_run_api(server, created["run_id"])
                assert path.exists(), "Stop deleted persistent PDF"
                print(f"[ok] scanner {origin} {mode}", flush=True)


if __name__ == "__main__":
    test_pdf()
    test_installed()
