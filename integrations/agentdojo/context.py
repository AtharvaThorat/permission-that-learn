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
        result['current_day'] = env.calendar.current_day.isoformat()
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


class SuiteFacts:
    def __init__(self, suite, metadata):
        self.suite, self.metadata = suite, metadata

    def resolve(self, tool, args, env):
        from .suites import INVENTORIES
        if tool not in INVENTORIES[self.suite]:
            raise ValueError('UNKNOWN_TOOL_METADATA')
        result = {'source': 'native_' + self.suite + '_identities',
                  'sidecar_source': self.metadata.provenance, 'sidecar_version': digest(self.metadata.model_dump()),
                  'resources': [], 'recipients': [], 'missing': [],
                  'environment_fingerprint': digest(env.model_dump(mode='json'))}
        if self.suite == 'slack':
            slack = env.slack
            channel = args.get('channel')
            if channel is not None:
                if channel not in slack.channels:
                    result['missing'].append('channel:' + channel)
                else:
                    members = sorted(u for u, channels in slack.user_channels.items() if channel in channels)
                    result['resources'].append({'kind': 'channel', 'id': channel, 'recipients': members,
                        'content_hash': digest([m.model_dump() for m in slack.channel_inbox.get(channel, [])])})
            for key in ('user', 'recipient'):
                if key in args:
                    result['recipients'].append(args[key])
                    if args[key] not in slack.users and tool != 'invite_user_to_slack':
                        result['missing'].append('user:' + args[key])
            if 'url' in args:
                result['destination'] = args['url']
            if 'user_email' in args:
                result['recipients'].append(args['user_email'])
        else:
            account = env.bank_account
            result['account'] = {'iban': account.iban, 'balance': account.balance}
            if args.get('recipient'):
                result['recipients'].append(args['recipient'])
            if tool == 'update_scheduled_transaction':
                transaction = next((t for t in account.scheduled_transactions if t.id == args['id']), None)
                if transaction is None:
                    result['missing'].append('transaction:' + str(args['id']))
                else:
                    result['resources'].append({'kind': 'transaction', 'id': str(transaction.id),
                        'recipients': [transaction.recipient], 'amount': transaction.amount,
                        'date': transaction.date, 'recurring': transaction.recurring,
                        'content_hash': digest(transaction.model_dump())})
            if tool == 'read_file':
                path = args['file_path']
                result['resources'].append({'kind': 'bank_file', 'id': path,
                    'exists': path in env.filesystem.files,
                    'content_hash': digest(env.filesystem.files.get(path))})
        return result


def suite_facts(suite, metadata):
    if suite == 'workspace':
        return WorkspaceFacts(metadata)
    if suite not in ('slack', 'banking'):
        raise ValueError('Unsupported suite')
    return SuiteFacts(suite, metadata)
