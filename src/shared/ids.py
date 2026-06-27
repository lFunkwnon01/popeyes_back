import uuid


def new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:12]}"
