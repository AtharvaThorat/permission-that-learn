"""Declared metadata only. Neither evaluator objects nor arbitrary environment dumps."""
import json
from pathlib import Path
from pydantic import Field
from blackbox.actions import digest
from blackbox.config import Strict

class Metadata(Strict):
    provenance: str
    version: str
    # Project sidecar labels; not native AgentDojo ground truth.
    labels: dict[str, dict[str, str]] = Field(default_factory=dict)

class WorkspaceFacts:
    def __init__(self, metadata):
        self.metadata = metadata

    @classmethod
    def from_file(cls, path):
        return cls(Metadata.model_validate(json.loads(Path(path).read_text(encoding='utf-8'))))

    def resolve(self, tool, args, env):
        result = {'source': 'declared_workspace_metadata', 'sidecar_source': self.metadata.provenance,
                  'sidecar_version': digest(self.metadata.model_dump()), 'resources': [],
                  'recipients': [], 'missing': []}
        collections = {'file': ('cloud_drive', 'files'), 'event': ('calendar', 'events'),
                       'email': ('inbox', 'emails')}

        def collection(kind):
            parent, attr = collections[kind]
            return getattr(getattr(env, parent), attr)

        def resource(kind, ident):
            ident = str(ident)
            obj = collection(kind).get(ident)
            if obj is None:
                result['missing'].append(kind + ':' + ident)
                return None
            # Metadata plus opaque content fingerprints for freshness only. Raw
            # text is not used as policy authority and is not exposed to Laya here.
            item = {'kind': kind, 'id': ident, 'source': 'environment_identity',
                    'label': self.metadata.labels.get(kind, {}).get(ident)}
            if kind == 'file':
                item.update(owner=str(obj.owner), shared_with={str(k): str(v) for k, v in obj.shared_with.items()},
                            modified=obj.last_modified.isoformat(), content_hash=digest(obj.content))
            elif kind == 'event':
                item.update(participants=[str(p) for p in obj.participants],
                            start=obj.start_time.isoformat(), end=obj.end_time.isoformat(),
                            status=str(obj.status), content_hash=digest([obj.title, obj.description, obj.location]))
            else:
                item.update(read=obj.read, status=str(obj.status),
                            content_hash=digest([obj.subject, obj.body]))
            result['resources'].append(item)
            return obj

        for key, kind in (('file_id', 'file'), ('event_id', 'event'), ('email_id', 'email')):
            if key in args:
                resource(kind, args[key])

        # Collection tools may return any matching member. Conservatively check
        # the full collection's identities/labels; do not inspect text to predict hits.
        collection_tools = {
            'get_unread_emails': 'email', 'get_sent_emails': 'email',
            'get_received_emails': 'email', 'get_draft_emails': 'email', 'search_emails': 'email',
            'search_calendar_events': 'event', 'get_day_calendar_events': 'event',
            'search_files_by_filename': 'file', 'list_files': 'file', 'search_files': 'file'}
        if tool in collection_tools:
            kind = collection_tools[tool]
            for ident in sorted(collection(kind)):
                resource(kind, ident)

        if tool in ('search_contacts_by_name', 'search_contacts_by_email'):
            result['contact_identity_hash'] = digest([str(c.email) for c in env.inbox.contact_list])
        if tool == 'get_current_day':
            result['current_day'] = env.calendar.current_day.isoformat()
        if tool == 'send_email':
            for key in ('recipients', 'cc', 'bcc'):
                result['recipients'].extend(args.get(key) or [])
            for attachment in args.get('attachments') or []:
                if attachment.get('type') == 'file' and set(attachment) == {'type', 'file_id'}:
                    resource('file', attachment['file_id'])
                else:
                    # Native event attachments contain compound payloads; v1 has
                    # no reviewed metadata mapping for them. Do not silently pass.
                    result['missing'].append('unsupported_attachment_metadata')
        if tool in ('create_calendar_event', 'add_calendar_event_participants'):
            result['recipients'].extend(args.get('participants') or [])
            if tool == 'create_calendar_event':
                result['recipients'].append(str(env.calendar.account_email))
        if tool in ('cancel_calendar_event', 'reschedule_calendar_event'):
            event = collection('event').get(args['event_id'])
            if event is not None:
                result['recipients'].extend(str(p) for p in event.participants)
        if tool == 'share_file':
            result['recipients'].append(args['email'])
        return result
