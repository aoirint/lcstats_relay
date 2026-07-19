"""Map relay state to immutable monitor presentation state."""

from __future__ import annotations

from datetime import datetime

from lcstats_relay.application.state import ConnectionState, OutputState, OutputStatus, RelayStatus
from lcstats_relay.presentation.models import (
    HealthViewState,
    OutputViewState,
    RelayViewState,
    StatusGlyph,
    Tone,
)

_STATUS_LABELS = {
    RelayStatus.STOPPED: "停止中",
    RelayStatus.WAITING: "統計データ待機中",
    RelayStatus.RECEIVED: "ペイロード受信",
    RelayStatus.DISPATCHING: "出力処理中",
    RelayStatus.ERROR: "エラー",
}

_OUTPUT_STATUS_LABELS = {
    OutputStatus.IDLE: "待機中",
    OutputStatus.RUNNING: "処理中",
    OutputStatus.SUCCESS: "成功",
    OutputStatus.ERROR: "エラー",
    OutputStatus.RETRY_QUEUED: "再送待ち",
}

_OUTPUT_STATUS_TONES = {
    OutputStatus.IDLE: Tone.NEUTRAL,
    OutputStatus.RUNNING: Tone.INFO,
    OutputStatus.SUCCESS: Tone.SUCCESS,
    OutputStatus.ERROR: Tone.ERROR,
    OutputStatus.RETRY_QUEUED: Tone.WARNING,
}

_UNHEALTHY_OUTPUT_STATUSES = frozenset({OutputStatus.ERROR, OutputStatus.RETRY_QUEUED})
_DEFAULT_OUTPUT_ORDER = ("archive", "gas")


def present_relay(state: ConnectionState, *, gas_enabled: bool) -> RelayViewState:
    """Map one application snapshot without reading or mutating Flet controls."""
    outputs = _display_outputs(state, gas_enabled=gas_enabled)
    unhealthy = any(_is_unhealthy(output) for output in outputs)
    return RelayViewState(
        status_label=_STATUS_LABELS[state.status],
        receive_count=str(state.receive_count),
        last_received=_format_time(state.last_received_at),
        error=state.last_error or "",
        health=_present_health(state, has_unhealthy_output=unhealthy),
        outputs=tuple(_present_output(output, connected=state.running) for output in outputs),
    )


def settings_summaries(
    *,
    tracker_url: str,
    data_dir: str,
    gas_url: str,
    has_gas_token: bool,
) -> tuple[str, str]:
    """Format persisted and ephemeral settings without exposing token contents."""
    settings = f"LCStatsTracker: {tracker_url} / 保存先: {data_dir}"
    gas_state = gas_url if gas_url else "未設定"
    token_state = "設定済み" if has_gas_token else "未設定"
    return settings, f"GAS: {gas_state} / Token: {token_state}"


def _display_outputs(state: ConnectionState, *, gas_enabled: bool) -> list[OutputState]:
    if state.outputs and not any(key in state.outputs for key in _DEFAULT_OUTPUT_ORDER):
        return list(state.outputs.values())
    defaults = {"archive": OutputState(key="archive", label="ローカル保存")}
    if gas_enabled:
        defaults["gas"] = OutputState(key="gas", label="Google Sheets")
    outputs = defaults | state.outputs
    return [outputs[key] for key in _DEFAULT_OUTPUT_ORDER if key in outputs]


def _present_health(
    state: ConnectionState,
    *,
    has_unhealthy_output: bool,
) -> HealthViewState:
    if state.running and state.receive_count == 0 and not has_unhealthy_output:
        return HealthViewState(
            label="接続失敗" if state.last_error else "接続試行中",
            detail=_connection_attempt_detail(state),
            tone=Tone.WARNING,
            glyph=StatusGlyph.WARNING if state.last_error else StatusGlyph.SYNC,
            glyph_tone=Tone.WARNING,
        )
    if state.last_error:
        return HealthViewState(
            label="要確認",
            detail=state.last_error,
            tone=Tone.ERROR,
            glyph=StatusGlyph.ERROR,
            glyph_tone=Tone.ERROR,
        )
    if has_unhealthy_output:
        return HealthViewState(
            label="要確認",
            detail="出力先を確認",
            tone=Tone.ERROR,
            glyph=StatusGlyph.WARNING,
            glyph_tone=Tone.ERROR,
        )
    if state.running:
        return HealthViewState(
            label="異常なし",
            detail="監視中",
            tone=Tone.SUCCESS,
            glyph=StatusGlyph.CHECK,
            glyph_tone=Tone.SUCCESS,
        )
    return HealthViewState(
        label="停止中",
        detail="未接続",
        tone=Tone.NEUTRAL,
        glyph=StatusGlyph.ERROR,
        glyph_tone=Tone.ERROR,
    )


def _present_output(output: OutputState, *, connected: bool) -> OutputViewState:
    status_label = _OUTPUT_STATUS_LABELS[output.status]
    tone = _OUTPUT_STATUS_TONES[output.status]
    if output.status is OutputStatus.IDLE and not connected:
        status_label = "未接続"
        tone = Tone.NEUTRAL
    return OutputViewState(
        label=output.label,
        status_label=status_label,
        tone=tone,
        glyph=_output_glyph(output, connected=connected),
        glyph_tone=_output_glyph_tone(output),
        detail=output.message if _is_unhealthy(output) else None,
    )


def _output_glyph(output: OutputState, *, connected: bool) -> StatusGlyph:
    if output.status is OutputStatus.ERROR:
        return StatusGlyph.ERROR
    if output.status is OutputStatus.RETRY_QUEUED or output.pending_count > 0:
        return StatusGlyph.WARNING
    if output.status is OutputStatus.SUCCESS:
        return StatusGlyph.CHECK
    if output.status is OutputStatus.RUNNING:
        return StatusGlyph.SYNC
    if not connected:
        return StatusGlyph.LINK_OFF
    return StatusGlyph.IDLE


def _output_glyph_tone(output: OutputState) -> Tone:
    if output.status is OutputStatus.ERROR:
        return Tone.ERROR
    if output.status is OutputStatus.RETRY_QUEUED or output.pending_count > 0:
        return Tone.WARNING
    if output.status is OutputStatus.SUCCESS:
        return Tone.SUCCESS
    if output.status is OutputStatus.RUNNING:
        return Tone.INFO
    return Tone.NEUTRAL


def _is_unhealthy(output: OutputState) -> bool:
    return output.status in _UNHEALTHY_OUTPUT_STATUSES or output.pending_count > 0


def _connection_attempt_detail(state: ConnectionState) -> str:
    if state.retry_after_seconds is not None:
        retry_after = f"{state.retry_after_seconds:g}"
        return f"{retry_after}秒後に再試行"
    return "再試行中" if state.last_error else "待機中"


def _format_time(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value is not None else "-"
