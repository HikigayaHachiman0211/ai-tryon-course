"""In-memory stand-in for the official OSS SDK client, used by storage contracts."""

from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace

import alibabacloud_oss_v2 as oss


def _service_error(status, code):
    return oss.exceptions.ServiceError(status_code=status, code=code, request_id="test", message="test",
                                       ec="", timestamp="", request_target="")


def _not_found():
    return oss.exceptions.OperationError(
        name="object", error=_service_error(404, "NoSuchKey")
    )


class FakeOSSClient:
    def __init__(self):
        self.objects = {}
        self.metadata = {}
        self.read_forbidden = False
        self.list_requests = []

    def put_object(self, request):
        key = (request.bucket, request.key)
        if request.forbid_overwrite and key in self.objects:
            raise oss.exceptions.OperationError(name="put", error=_service_error(409, "FileAlreadyExists"))
        body = request.body.read() if hasattr(request.body, "read") else request.body
        self.objects[key] = (body, request.content_type, request.cache_control)
        self.metadata[key] = dict(request.metadata or {})

    def head_object(self, request):
        if self.read_forbidden:
            raise oss.exceptions.OperationError(
                name="head", error=_service_error(403, "AccessDenied")
            )
        if (request.bucket, request.key) not in self.objects:
            raise _not_found()
        return SimpleNamespace(status_code=200, metadata=self.metadata.get((request.bucket, request.key), {}))

    def get_object(self, request):
        self.head_object(request)
        return SimpleNamespace(body=BytesIO(self.objects[(request.bucket, request.key)][0]))

    def delete_object(self, request):
        self.objects.pop((request.bucket, request.key), None)
        self.metadata.pop((request.bucket, request.key), None)

    def list_objects_v2(self, request):
        self.list_requests.append(request)
        names = sorted(key for bucket, key in self.objects if bucket == request.bucket and key.startswith(request.prefix or ""))
        offset = int(request.continuation_token or 0)
        end = min(offset + min(request.max_keys or 1000, 2), len(names))
        return SimpleNamespace(
            contents=[SimpleNamespace(key=name, size=len(self.objects[(request.bucket, name)][0]),
                                      last_modified=datetime.now(timezone.utc)) for name in names[offset:end]],
            is_truncated=end < len(names),
            next_continuation_token=str(end) if end < len(names) else None,
        )
