"""Tool schema checks and one deliberately narrow exact UTC comparison."""
import re
from datetime import datetime, timezone
from pydantic import Field, ValidationError, field_validator, model_validator
from .schemas import StrictModel, Nonempty, Request

def utc(value: str) -> datetime:
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)', value):
        raise ValueError('Expected ISO 8601 UTC timestamp')
    return datetime.fromisoformat(value.replace('Z', '+00:00'))

class EmailList(StrictModel):
    unread_only: bool

class Draft(StrictModel):
    to: list[str] = Field(min_length=1)
    subject: str
    body: str

    @field_validator('to')
    @classmethod
    def emails(cls, values):
        if any(not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', x) for x in values):
            raise ValueError('Invalid email address')
        return values

class Send(Draft):
    attachment_ids: list[Nonempty] = Field(default_factory=list)

class TimeRange(StrictModel):
    start: str
    end: str

    @model_validator(mode='after')
    def valid_range(self):
        if utc(self.start) >= utc(self.end):
            raise ValueError('End must be after start')
        return self

class Create(TimeRange):
    title: str
    attendees: list[str]
    send_invites: bool

    @field_validator('attendees')
    @classmethod
    def emails(cls, values):
        return Draft.emails(values)

class Update(TimeRange):
    event_id: Nonempty
    send_updates: bool

class Delete(StrictModel):
    event_id: Nonempty

class Read(StrictModel):
    file_id: Nonempty

TOOLS = {'email.list': EmailList, 'email.create_draft': Draft, 'email.send': Send,
         'calendar.list': TimeRange, 'calendar.create': Create, 'calendar.update': Update,
         'calendar.delete': Delete, 'files.read': Read}

def validate(raw):
    try:
        req = Request.model_validate(raw)
    except ValidationError as exc:
        action_error = all(e['loc'] and e['loc'][0] == 'action' for e in exc.errors())
        return None, 'INVALID_ACTION' if action_error else 'INVALID_REQUEST'
    try:
        schema = TOOLS[req.action.tool]
        schema.model_validate(req.action.arguments)
        if req.wall and req.wall.evaluated_action_id != req.action.action_id:
            raise ValueError('Wall/action ID mismatch')
    except (KeyError, ValueError):
        return None, 'INVALID_ACTION'
    return req, None

# No keyword task policy: only a fully spelled English month-date UTC range is
# extracted from an imperative scheduling request. Other date syntax, multiple
# ranges, quotes and explicit negation are left to semantic judgment. This is
# not a general natural-language parser (e.g. indirect/conditional phrasing).
MONTHS = {name: i for i, name in enumerate(
    'January February March April May June July August September October November December'.split(), 1)}
RANGE = re.compile(r'\bon (' + '|'.join(MONTHS) +
                   r') (\d{1,2}), (\d{4}), from (\d{2}:\d{2}) to (\d{2}:\d{2}) UTC\b')

def exact_time_conflict(req: Request) -> bool:
    if req.action.tool not in ('calendar.create', 'calendar.update'):
        return False
    if (not re.match(r'^(Create|Schedule|Move)\b', req.user_request) or
        re.search(r'["\u201c\u201d]|\b(not|never|unless|if|instead)\b', req.user_request, re.I)):
        return False
    matches = list(RANGE.finditer(req.user_request))
    if len(matches) != 1:
        return False
    month, day, year, start, end = matches[0].groups()
    try:
        date = datetime(int(year), MONTHS[month], int(day), tzinfo=timezone.utc)
        wanted = [date.replace(hour=int(t[:2]), minute=int(t[3:])) for t in (start, end)]
        return wanted != [utc(req.action.arguments[k]) for k in ('start', 'end')]
    except ValueError:
        return False
