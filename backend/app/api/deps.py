from fastapi import Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Business
from ..repositories.business import get_or_create


def business(s: Session = Depends(get_session)) -> Business:
    return get_or_create(s)
