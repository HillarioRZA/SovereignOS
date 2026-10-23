"""
Deterministic Agent Flight Recorder & Time-Travel Debugger.
Merekam alur keputusan agen, input/output mentah, dan transisi state dalam format append-only event stream
ke folder .flight_logs/flight_stream.jsonl untuk auditabilitas dan pengulangan (replay).
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from app.core.logger import logger


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentFlightRecorder:
    """Perekam kotak hitam otonom (Black Box Flight Recorder) untuk multi-agent system."""

    def __init__(self, log_dir: Optional[Path] = None) -> None:
        self.log_dir = log_dir or Path("data/flight_logs")
        self._in_memory_logs: Dict[str, List[Dict[str, Any]]] = {}

    def set_log_dir(self, new_dir: Path) -> None:
        """Mengatur direktori penyimpanan berkas stream rekaman."""
        self.log_dir = Path(new_dir)

    def record_step(
        self,
        project_id: str,
        agent_role: str,
        event_type: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Mencatat satu peristiwa langkah agen ke dalam append-only stream."""
        if project_id not in self._in_memory_logs:
            self._in_memory_logs[project_id] = []

        step_idx = len(self._in_memory_logs[project_id]) + 1
        event_id = f"evt_{uuid.uuid4().hex[:10]}"

        record = {
            "event_id": event_id,
            "project_id": project_id,
            "timestamp": _now_iso(),
            "step_index": step_idx,
            "agent_role": agent_role,
            "event_type": event_type,
            "payload": payload,
        }
        self._in_memory_logs[project_id].append(record)

        # Simpan ke disk secara append-only
        target_dir = self.log_dir / project_id
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            log_file = target_dir / "flight_stream.jsonl"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except OSError as err:
            logger.debug(f"[FlightRecorder] Penulisan berkas stream dilewati: {err}")

        logger.debug(f"[FlightRecorder] Recorded step {step_idx} [{event_type}] for {agent_role} in {project_id}")
        return record

    def replay_step(self, project_id: str, step_index: int) -> Optional[Dict[str, Any]]:
        """Mengambil rekaman langkah tertentu untuk time-travel debugger."""
        logs = self.get_flight_log(project_id)
        for ev in logs:
            if ev.get("step_index") == step_index:
                return ev
        return None

    def get_flight_log(self, project_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Mengambil seluruh riwayat peristiwa dari file disk atau memori."""
        log_file = self.log_dir / project_id / "flight_stream.jsonl"
        if log_file.exists():
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    file_logs = [json.loads(line) for line in f if line.strip()]
                    if file_logs:
                        self._in_memory_logs[project_id] = file_logs
                        return file_logs[-limit:]
            except (json.JSONDecodeError, OSError) as err:
                logger.debug(f"[FlightRecorder] Gagal membaca persistent stream: {err}")

        return self._in_memory_logs.get(project_id, [])[-limit:]


flight_recorder = AgentFlightRecorder()
