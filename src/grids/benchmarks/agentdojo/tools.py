"""Reviewed workspace effects at the pinned source revision; not name heuristics."""
from grids.core.actions import canonical, digest, json_value, parse_json

# Includes compound effects and actual implementation quirks, not just docstrings.
EFFECTS = {
    'send_email': ('outbound',),
    'delete_email': ('destructive',),
    'get_unread_emails': ('read', 'mark_read'),
    'get_sent_emails': ('read',), 'get_received_emails': ('read',),
    'get_draft_emails': ('read',), 'search_emails': ('read',),
    'search_contacts_by_name': ('read',), 'search_contacts_by_email': ('read',),
    'get_current_day': ('read',), 'search_calendar_events': ('read',),
    'get_day_calendar_events': ('read',),
    'create_calendar_event': ('calendar_write', 'outbound'),
    'cancel_calendar_event': ('destructive', 'outbound'),
    'reschedule_calendar_event': ('calendar_write', 'outbound'),
    'add_calendar_event_participants': ('calendar_write', 'authority_write'),
    'append_to_file': ('file_write',), 'search_files_by_filename': ('read',),
    'create_file': ('file_write',), 'delete_file': ('destructive',),
    'get_file_by_id': ('read',), 'list_files': ('read',),
    'share_file': ('authority_write',), 'search_files': ('read',),
}

class NativeTools:
    def __init__(self, runtime, guarded=True):
        self.runtime = runtime
        self.guarded = guarded

    def schemas(self):
        return [{'type': 'function', 'function': {'name': f.name,
                 'description': f.description, 'parameters': f.parameters.model_json_schema()}}
                for f in self.runtime.functions.values()]

    def effects(self, name):
        if name not in EFFECTS:
            from .suites import INVENTORIES
            for inventory in INVENTORIES.values():
                if name in inventory:
                    return inventory[name][1]
            if self.guarded:
                raise ValueError('UNKNOWN_TOOL_EFFECTS')
            return ('unreviewed',)
        return EFFECTS[name]

    def schema_digest(self, name):
        return digest(self.runtime.functions[name].parameters.model_json_schema())

    def validate(self, name, arguments):
        json_value(arguments)
        if type(arguments) is not dict or name not in self.runtime.functions:
            raise ValueError('UNKNOWN_TOOL_OR_ARGUMENTS')
        self.effects(name)
        schema = self.runtime.functions[name].parameters
        if set(arguments) - set(schema.model_fields):
            raise ValueError('EXTRA_ARGUMENTS')
        # Native Pydantic coercion/defaults are made explicit before authorization.
        # mode=json removes enums while preserving the native validated value.
        normalized = schema.model_validate(arguments).model_dump(mode='json')
        json_value(normalized)
        for key, value in arguments.items():
            if value != normalized[key] or isinstance(value, bool) != isinstance(normalized[key], bool):
                raise ValueError('MODEL_ARGUMENT_COERCION_REQUIRED')
        if canonical(schema.model_validate(normalized).model_dump(mode='json')) != canonical(normalized):
            raise ValueError('UNSTABLE_ARGUMENT_COERCION')
        return parse_json(canonical(normalized))
