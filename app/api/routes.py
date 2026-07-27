from typing import Type

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.database.models import PaperOrder, Portfolio, Signal, SystemEvent
from app.database.session import get_db

router = APIRouter()


def serialize(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def page(db: Session, model: Type, offset: int, limit: int):
    statement = select(model).order_by(desc(model.id)).offset(offset).limit(limit)
    return [serialize(row) for row in db.scalars(statement)]


@router.get("/system/config")
def safe_config(settings: Settings = Depends(get_settings)):
    return settings.safe_dict()


@router.get("/portfolios")
def portfolios(db: Session = Depends(get_db)):
    return [serialize(row) for row in db.scalars(select(Portfolio).order_by(Portfolio.id))]


@router.get("/signals")
def signals(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return page(db, Signal, offset, limit)


@router.get("/orders")
def orders(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return page(db, PaperOrder, offset, limit)


@router.get("/events")
def events(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return page(db, SystemEvent, offset, limit)
