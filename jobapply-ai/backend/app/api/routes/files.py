from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.services.storage import get_storage, verify_download_token

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{token}")
def download(token: str):
    """Signed, short-lived, user-bound download. The token is the credential, so it is never logged."""
    body = verify_download_token(token)
    if not body:
        raise HTTPException(403, "This download link is invalid or has expired.")
    try:
        data = get_storage().get(body["k"])
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "File not found.")
    safe = "".join(c for c in body["f"] if c.isalnum() or c in "._- ")[:120] or "download"
    return Response(content=data, media_type=body["t"], headers={"Content-Disposition": f'attachment; filename="{safe}"', "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
