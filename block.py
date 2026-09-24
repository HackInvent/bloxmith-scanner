"""Autonomous scanner with an idle-on-Run listener and a canvas scan action."""

from bloxsmith_app.block_api import BlockDefinition, BlockRuntimePreparation, BlockRuntimeResult
from .runtime import DEFAULTS, normalize_config, execute, devices, reserve_request, release_request
from .ui import DeviceUI


# FB1: A canvas action executes a scan and publishes a completed PDF path.
# FB2: Exact driver capabilities, bounded files/processes, no partial publications.
# FB3: Run prepares an idle listener; manual execution and both runtimes work.
# FB4: Release-scoped accessible card/modal/inspector with editable scan settings.
class ScannerBlock(DeviceUI, BlockDefinition):
    """Keep acquisition out of HTTP UI hooks and publish through the normal runtime."""

    kind = "scanner"
    defaults = DEFAULTS
    normalize = staticmethod(normalize_config)
    discover = staticmethod(devices)

    def prepare_runtime(self, context):
        """Declare a passive listener: Run itself never touches the equipment."""
        normalize_config(context.config)
        return BlockRuntimePreparation(listen_on_run=True)

    def execute_runtime(self, context):
        """Reserve at most one request and hand acquisition to the persistent worker."""
        if context.runtime_mode != "zeromq_active":
            return execute(context)
        token = reserve_request(context)
        if token is None:
            return BlockRuntimeResult(status="success", outputs=[], last_message="A scan is already in progress; duplicate request ignored.")
        try:
            context.services["runtime_listener"].send({"action": "scan", "token": token})
        except Exception:
            release_request(context, token)
            raise
        return BlockRuntimeResult(status="success", outputs=[], last_message="Scan request accepted; acquisition in progress.")

    def listen_runtime(self, context):
        """Perform only explicitly requested scans; Stop cancels the owned CLI."""
        while not context.stop_requested():
            command = context.receive_command(timeout_sec=.1)
            if command is None or command.payload.get("action") != "scan":
                continue
            token = command.payload.get("token")
            if not isinstance(token, str) or len(token) != 32:
                continue
            try:
                result = execute(context, request_token=token)
                if not context.stop_requested() and result.status not in {"skipped", "cancelled"}:
                    context.emit_result(result)
            finally:
                release_request(context, token)
