"""
A StorPool Juju charms helper module that keeps track of peer units of
the same charm so that the state may be reported to other charms.
"""
import json
import platform

from charms import reactive
from charms.reactive import helpers

from charmhelpers.core import hookenv, unitdata


def init_state(db):
    """
    Initialize the local state: the current node itself is present, and
    if the OpenStack integration has found a Cinder installation in an LXD,
    that one is present, too.
    """
    local_state = {
                   platform.node(): True,
                  }
    lxd_cinder = db.get('storpool-openstack-integration.lxd-name',
                        default=None)
    if lxd_cinder is not None:
        local_state[lxd_cinder] = True
    return {
            '-local': local_state,
           }


def get_state(db=None):
    """
    Fetch the cached state or, if none, initialize it anew.
    """
    if db is None:
        db = unitdata.kv()
    state = db.get('storpool-service.state', default=None)
    if state is None:
        state = init_state(db)
        changed = True
    else:
        changed = False
    return (state, changed)


def set_state(db, state):
    """
    Cache the current presence state in the unit's persistent storage.
    """
    db.set('storpool-service.state', state)


def update_state(db, state, changed, key, name, value):
    """
    Update the state of a single node in the database and, if it has indeed
    been changed, store it into the persistent storage.
    """
    if key not in state:
        state[key] = {}
        changed = True
    # FIXME: compare with value, not with False
    if not state[key].get(name, not value):
        state[key][name] = value
        changed = True

    if changed:
        set_state(db, state)
    return changed


def add_present_node(name, rel_name, rdebug=lambda s: s):
    """
    Update a peer's state and send the full structure right back if needed.
    """
    db = unitdata.kv()
    (state, changed) = get_state(db)
    changed = update_state(db, state, changed, '-local', name, True)
    if changed:
        rdebug('hm, let us then try to fetch the relation ids for {rel_name}'
               .format(rel_name=rel_name))
        rel_ids = hookenv.relation_ids(rel_name)
        rdebug('rel_ids: {rel_ids}'.format(rel_ids=rel_ids))
        for rel_id in rel_ids:
            rdebug('- trying for {rel_id}'.format(rel_id=rel_id))
            hookenv.relation_set(rel_id,
                                 storpool_service=json.dumps(state['-local']))
            rdebug('  - looks like we managed it for {rel_id}'
                   .format(rel_id=rel_id))
        rdebug('that is it for the rel_ids')


def get_present_nodes():
    """
    Fetch the current state of the charm's units.
    """
    (state, _) = get_state()
    res = {}
    for arr in state.values():
        for (key, value) in arr.items():
            res[key] = value or res.get(key, False)
    return res


def handle(hk, attaching, data, rdebug=lambda s: s):
    """
    Handle a state change of the internal hook; update our state if needed.
    """
    rdebug('service_hook.handle for a {t} hook {name}, attaching {attaching}, '
           'data keys {ks}'
           .format(t=type(hk).__name__,
                   name=hk.relation_name,
                   attaching=attaching,
                   ks=sorted(data.keys()) if data is not None else None))
    db = unitdata.kv()
    (state, changed) = get_state(db)
    rdebug('- current state: {state}'.format(state=state))
    rdebug('- changed even at the start: {changed}'.format(changed=changed))

    key = hk.conversation().key
    rdebug('- conversation key: {key}'.format(key=key))
    if attaching:
        rdebug('- attaching: adding new hosts as reported')
        for (name, value) in data.items():
            rdebug('  - processing name "{name}" value "{value}"'
                   .format(name=name, value=value))
            if update_state(db, state, changed, key, name, value):
                changed = True
            rdebug('    - changed: {changed}'.format(changed=changed))
    else:
        if key in state:
            rdebug('- detaching: the conversation has been recorded, '
                   'removing it')
            del state[key]
            changed = True
            set_state(db, state)
        else:
            rdebug('- detaching, but we had no idea we were having '
                   'this conversation, so nah')

    if changed:
        rdebug('- updated state: {state}'.format(state=state))

    if changed or helpers.data_changed('storpool-service.state', state) or \
       not helpers.is_state('storpool-service.changed'):
        rdebug('- something changed, notifying whomever should care')
        reactive.set_state('storpool-service.change')
    return changed
