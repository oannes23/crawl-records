"""Identity service — register, recover, handle availability.

Handle uniqueness is enforced by a UNIQUE index on ``handle_lower`` (case-insensitive
first-come claim). Concurrent claims are safe: the DB rejects the second insert and we
translate the IntegrityError into a clean 409. Recovery codes are issued once at
registration and stored hashed; ``/recover`` rebinds a fresh fingerprint to the identity.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import auth
from app.models import Identity, Run
from app.schemas import (
    HandleAvailableResponse,
    RecoverRequest,
    RecoverResponse,
    RegisterRequest,
    RegisterResponse,
)


def handle_available(db: Session, name: str) -> HandleAvailableResponse:
    taken = db.execute(
        select(Identity.handle_lower).where(Identity.handle_lower == name.lower())
    ).scalar_one_or_none()
    return HandleAvailableResponse(name=name, available=taken is None)


def register(db: Session, req: RegisterRequest) -> RegisterResponse:
    # reject a fingerprint that is already registered (re-register is not the flow; recover is)
    existing = db.get(Identity, req.fingerprint)
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "fingerprint already registered")

    recovery_code = auth.new_recovery_code()
    token = auth.new_token()
    identity = Identity(
        fingerprint=req.fingerprint,
        handle=req.handle,
        handle_lower=req.handle.lower(),
        recovery_code_hash=auth.hash_recovery_code(recovery_code),
        token=token,
        consent_version=req.consent_version,
    )
    db.add(identity)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # the UNIQUE(handle_lower) lost the race → handle is taken
        raise HTTPException(status.HTTP_409_CONFLICT, "handle already taken") from None

    return RegisterResponse(token=token, recovery_code=recovery_code, handle=identity.handle)


def recover(db: Session, req: RecoverRequest) -> RecoverResponse:
    # find the identity whose recovery code matches (hashed compare over candidates)
    identities = db.execute(select(Identity)).scalars().all()
    match = next(
        (i for i in identities if auth.verify_recovery_code(req.recovery_code, i.recovery_code_hash)),
        None,
    )
    if match is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invalid recovery code")

    old_fp = match.fingerprint
    new_token = auth.new_token()
    handle = match.handle

    if req.fingerprint != old_fp:
        # guard: the new fingerprint must not already belong to a different identity
        clash = db.get(Identity, req.fingerprint)
        if clash is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "new fingerprint already registered"
            )
        # rebind the identity PK AND re-point existing runs so history follows the player
        db.execute(update(Run).where(Run.fingerprint == old_fp).values(fingerprint=req.fingerprint))
        db.execute(
            update(Identity)
            .where(Identity.fingerprint == old_fp)
            .values(fingerprint=req.fingerprint, token=new_token)
        )
    else:
        db.execute(
            update(Identity).where(Identity.fingerprint == old_fp).values(token=new_token)
        )

    db.commit()
    return RecoverResponse(token=new_token, handle=handle)
