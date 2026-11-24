"""Task queue adapter for Azure Storage Queue and local persistent test queue."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


QUEUE_MESSAGE_VERSION = 1


@dataclass(frozen=True)
class QueueMessage:
    message_id: str
    pop_receipt: str
    task_id: str
    version: int = QUEUE_MESSAGE_VERSION
    dequeue_count: int = 1
    raw_handle: Any = None


def encode_task_message(task_id: str) -> str:
    clean_id = str(task_id or "").strip()
    if not clean_id:
        raise ValueError("task_id is required for queue message")
    return json.dumps({"version": QUEUE_MESSAGE_VERSION, "task_id": clean_id}, separators=(",", ":"))


def parse_task_message(raw_content: str) -> Dict[str, Any]:
    data = json.loads(str(raw_content or ""))
    if not isinstance(data, dict):
        raise ValueError("Queue message must be a JSON object")
    version = int(data.get("version") or 0)
    task_id = str(data.get("task_id") or "").strip()
    if version != QUEUE_MESSAGE_VERSION or not task_id:
        raise ValueError("Invalid queue message contract")
    return {"version": version, "task_id": task_id}


class AzureStorageTaskQueue:
    def __init__(
        self,
        *,
        account_name: str = "",
        connection_string: str = "",
        queue_name: str = "tryon-tasks",
        queue_client: Any = None,
    ):
        self.account_name = account_name
        self.connection_string = connection_string
        self.queue_name = queue_name or "tryon-tasks"
        self._client = queue_client
        self._ensured = False

    def _get_client(self):
        if self._client is not None:
            return self._client
        from azure.storage.queue import QueueClient

        if self.connection_string:
            self._client = QueueClient.from_connection_string(self.connection_string, self.queue_name)
        else:
            from azure.identity import DefaultAzureCredential

            if not self.account_name:
                raise RuntimeError("AZURE_STORAGE_ACCOUNT_NAME or AZURE_STORAGE_CONNECTION_STRING is required")
            self._client = QueueClient(
                account_url=f"https://{self.account_name}.queue.core.windows.net",
                queue_name=self.queue_name,
                credential=DefaultAzureCredential(),
            )
        if not self._ensured:
            try:
                self._client.create_queue()
            except Exception as exc:
                if exc.__class__.__name__ != "ResourceExistsError":
                    pass
            self._ensured = True
        return self._client

    def enqueue(self, task_id: str, *, retries: int = 3) -> str:
        payload = encode_task_message(task_id)
        last_exc: Optional[Exception] = None
        for attempt in range(max(1, retries)):
            try:
                resp = self._get_client().send_message(payload)
                return str(getattr(resp, "id", "") or task_id)
            except Exception as exc:
                last_exc = exc
                if attempt + 1 < retries:
                    time.sleep(min(2.0, 0.25 * (2 ** attempt)))
        raise RuntimeError(f"Failed to enqueue task {task_id}: {last_exc}") from last_exc

    def receive(self, *, max_messages: int = 1, visibility_timeout: int = 90) -> List[QueueMessage]:
        client = self._get_client()
        pager = client.receive_messages(
            messages_per_page=max(1, min(32, int(max_messages))),
            visibility_timeout=max(10, int(visibility_timeout)),
        )
        results: List[QueueMessage] = []
        for msg in pager:
            parsed = parse_task_message(getattr(msg, "content", ""))
            results.append(
                QueueMessage(
                    message_id=str(msg.id),
                    pop_receipt=str(msg.pop_receipt),
                    task_id=parsed["task_id"],
                    version=parsed["version"],
                    dequeue_count=int(getattr(msg, "dequeue_count", 1) or 1),
                    raw_handle=msg,
                )
            )
            if len(results) >= max_messages:
                break
        return results

    def renew(self, message: QueueMessage, *, visibility_timeout: int = 90) -> QueueMessage:
        updated = self._get_client().update_message(
            message.message_id,
            pop_receipt=message.pop_receipt,
            visibility_timeout=max(10, int(visibility_timeout)),
        )
        new_receipt = str(getattr(updated, "pop_receipt", "") or message.pop_receipt)
        return QueueMessage(
            message_id=message.message_id,
            pop_receipt=new_receipt,
            task_id=message.task_id,
            version=message.version,
            dequeue_count=message.dequeue_count,
            raw_handle=updated,
        )

    def delete(self, message: QueueMessage) -> bool:
        try:
            self._get_client().delete_message(message.message_id, message.pop_receipt)
            return True
        except Exception as exc:
            if exc.__class__.__name__ in {"ResourceNotFoundError", "MessageNotFound"}:
                return False
            raise

    def health_check(self) -> Dict[str, Any]:
        props = self._get_client().get_queue_properties()
        return {
            "provider": "azure",
            "queue_name": self.queue_name,
            "approximate_message_count": getattr(props, "approximate_message_count", None),
        }


class LocalTaskQueue:
    """File-backed queue with visibility timeout for local development and failure-recovery tests."""

    def __init__(self, root_dir: Path):
        self.root_dir = Path(root_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _msg_path(self, message_id: str) -> Path:
        safe = os.path.basename(str(message_id))
        return self.root_dir / f"{safe}.json"

    def enqueue(self, task_id: str, *, retries: int = 3) -> str:
        del retries
        payload = encode_task_message(task_id)
        parsed = parse_task_message(payload)
        now = time.time()
        msg_id = f"{int(now * 1000):015d}_{uuid.uuid4().hex[:12]}"
        record = {
            "message_id": msg_id,
            "pop_receipt": "",
            "content": payload,
            "task_id": parsed["task_id"],
            "version": parsed["version"],
            "visible_after": 0.0,
            "dequeue_count": 0,
            "created_at": now,
        }
        with self._lock:
            self._msg_path(msg_id).write_text(json.dumps(record), encoding="utf-8")
        return msg_id

    def receive(
        self,
        *,
        max_messages: int = 1,
        visibility_timeout: int = 90,
        now_ts: Optional[float] = None,
    ) -> List[QueueMessage]:
        now = float(now_ts if now_ts is not None else time.time())
        results: List[QueueMessage] = []
        with self._lock:
            for path in sorted(self.root_dir.glob("*.json")):
                if len(results) >= max_messages:
                    break
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if float(data.get("visible_after") or 0.0) > now:
                    continue
                parsed = parse_task_message(data.get("content", ""))
                receipt = uuid.uuid4().hex
                data["pop_receipt"] = receipt
                data["visible_after"] = now + max(1, int(visibility_timeout))
                data["dequeue_count"] = int(data.get("dequeue_count") or 0) + 1
                path.write_text(json.dumps(data), encoding="utf-8")
                results.append(
                    QueueMessage(
                        message_id=str(data["message_id"]),
                        pop_receipt=receipt,
                        task_id=parsed["task_id"],
                        version=parsed["version"],
                        dequeue_count=int(data["dequeue_count"]),
                    )
                )
        return results

    def renew(
        self,
        message: QueueMessage,
        *,
        visibility_timeout: int = 90,
        now_ts: Optional[float] = None,
    ) -> QueueMessage:
        now = float(now_ts if now_ts is not None else time.time())
        with self._lock:
            path = self._msg_path(message.message_id)
            if not path.is_file():
                raise RuntimeError("Queue message no longer exists")
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("pop_receipt") != message.pop_receipt:
                raise RuntimeError("Queue pop_receipt mismatch during visibility renewal")
            new_receipt = uuid.uuid4().hex
            data["pop_receipt"] = new_receipt
            data["visible_after"] = now + max(1, int(visibility_timeout))
            path.write_text(json.dumps(data), encoding="utf-8")
        return QueueMessage(
            message_id=message.message_id,
            pop_receipt=new_receipt,
            task_id=message.task_id,
            version=message.version,
            dequeue_count=message.dequeue_count,
        )

    def delete(self, message: QueueMessage) -> bool:
        with self._lock:
            path = self._msg_path(message.message_id)
            if not path.is_file():
                return False
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return False
            if data.get("pop_receipt") != message.pop_receipt:
                return False
            path.unlink(missing_ok=True)
            return True

    def health_check(self) -> Dict[str, Any]:
        return {
            "provider": "local",
            "root_dir": str(self.root_dir),
            "ready": self.root_dir.is_dir(),
        }


def create_task_queue(environ: Optional[Dict[str, str]] = None, *, queue_client: Any = None):
    values = dict(os.environ if environ is None else environ)
    get = lambda key, default="": str(values.get(key, default) or "").strip()
    provider = get("TASK_QUEUE_PROVIDER").lower()
    if not provider:
        obj_provider = get("OBJECT_STORAGE_PROVIDER").lower()
        if obj_provider == "azure" or get("AZURE_STORAGE_ACCOUNT_NAME") or get("AZURE_STORAGE_CONNECTION_STRING"):
            provider = "azure"
        else:
            provider = "local"

    if provider == "azure":
        return AzureStorageTaskQueue(
            account_name=get("AZURE_STORAGE_ACCOUNT_NAME"),
            connection_string=get("AZURE_STORAGE_CONNECTION_STRING"),
            queue_name=get("AZURE_STORAGE_QUEUE_NAME", "tryon-tasks") or "tryon-tasks",
            queue_client=queue_client,
        )

    if get("APP_ENV").lower() in {"production", "prod"}:
        raise RuntimeError("Local task queue cannot be used in production")
    history_dir = get(
        "HISTORY_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "history"),
    )
    local_dir = Path(get("TASK_QUEUE_LOCAL_DIR") or os.path.join(history_dir, "local-queue"))
    return LocalTaskQueue(local_dir)
