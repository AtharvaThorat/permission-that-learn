"""Reviewed native suite effects and identity-only trust snapshots."""
from pydantic import Field
from grids.core.actions import digest
from grids.wall.context import WallContext
from grids.wall.models import TargetClass


SLACK = {
    'get_channels': ('read', ('read',), {}),
    'get_users_in_channel': ('read', ('read',), {}),
    'read_channel_messages': ('read', ('read',), {}),
    'read_inbox': ('read', ('read',), {}),
    'send_direct_message': ('send', ('outbound',), {'target_args': ('recipient',), 'requires_target': True}),
    'send_channel_message': ('send', ('outbound',), {'resource_kind': 'channel', 'resource_arg': 'channel'}),
    'add_user_to_channel': ('share', ('authority_write',), {'target_args': ('user',), 'requires_target': True}),
    'invite_user_to_slack': ('share', ('authority_write', 'outbound'), {'target_args': ('user_email',), 'requires_target': True}),
    'remove_user_from_slack': ('delete', ('destructive',), {'target_args': ('user',), 'requires_target': True}),
    'get_webpage': ('read', ('read', 'outbound'), {'target_args': ('url',), 'requires_target': True}),
    'post_webpage': ('send', ('outbound', 'file_write'), {'target_args': ('url',), 'requires_target': True}),
}
BANKING = {
    **{name: ('read', ('read',), {}) for name in (
        'get_iban', 'get_balance', 'get_most_recent_transactions', 'get_scheduled_transactions', 'read_file', 'get_user_info')},
    'send_money': ('pay', ('financial', 'outbound'), {'target_args': ('recipient',), 'requires_target': True}),
    'schedule_transaction': ('pay', ('financial', 'outbound'), {'target_args': ('recipient',), 'requires_target': True}),
    'update_scheduled_transaction': ('pay', ('financial', 'outbound'), {
        'target_args': ('recipient',), 'resource_arg': 'id', 'resource_kind': 'transaction'}),
    'update_password': ('modify', ('authority_write',), {}),
    'update_user_info': ('modify', ('account_write',), {}),
}
INVENTORIES = {'slack': SLACK, 'banking': BANKING}


def inventory(suite):
    from grids.wall.inventory import ToolInventory, ToolSpec
    return ToolInventory(suite=suite, tools={name: ToolSpec(name=name, capability=cap, **options)
        for name, (cap, _, options) in INVENTORIES[suite].items()})


class NativeIdentityContext(WallContext):
    suite: str
    native_identities: dict[str, TargetClass] = Field(default_factory=dict)
    native_resources: dict[str, dict[str, frozenset[str]]] = Field(default_factory=dict)

    def classify(self, raw):
        if not isinstance(raw, str):
            return TargetClass.UNKNOWN
        return self.native_identities.get(raw, TargetClass.UNKNOWN)

    def resource_people(self, kind, resource_id):
        return self.native_resources.get(kind, {}).get(str(resource_id))

    def fingerprint(self):
        return digest({'suite': self.suite, 'identities': {k: v.value for k, v in self.native_identities.items()},
                       'resources': {kind: {key: sorted(values) for key, values in sorted(items.items())}
                                     for kind, items in sorted(self.native_resources.items())}})


def clean_context(suite, env):
    known, resources = {}, {}
    if suite == 'slack':
        known = {user: TargetClass.CONTACT for user in env.slack.users}
        for url in env.web.web_content:
            for spelling in (url, 'http://' + url, 'https://' + url):
                known[spelling] = TargetClass.CONTACT
        resources['channel'] = {channel: frozenset(user for user, channels in env.slack.user_channels.items()
                                                  if channel in channels) for channel in env.slack.channels}
    elif suite == 'banking':
        known = {t.recipient: TargetClass.CONTACT for t in
                 [*env.bank_account.transactions, *env.bank_account.scheduled_transactions]}
        known[env.bank_account.iban] = TargetClass.SELF
        resources['transaction'] = {str(t.id): frozenset([t.recipient]) for t in env.bank_account.scheduled_transactions}
    else:
        raise ValueError('Unsupported native identity suite')
    return NativeIdentityContext(account_email='unused@simulation.invalid', suite=suite,
                                 native_identities=known, native_resources=resources)
