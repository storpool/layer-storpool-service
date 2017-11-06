#!/usr/bin/python3

"""
A set of unit tests for the storpool-service layer.
"""

import os
import platform
import sys
import unittest

import copy
import json
import mock

from charmhelpers.core import unitdata

lib_path = os.path.realpath('lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)


class MockReactive(object):
    def r_clear_states(self):
        self.states = set()

    def __init__(self):
        self.r_clear_states()

    def set_state(self, name):
        self.states.add(name)

    def remove_state(self, name):
        if name in self.states:
            self.states.remove(name)

    def is_state(self, name):
        return name in self.states

    def r_get_states(self):
        return set(self.states)

    def r_set_states(self, states):
        self.states = set(states)


r_state = MockReactive()


def mock_reactive_states(f):
    def inner1(inst, *args, **kwargs):
        @mock.patch('charms.reactive.set_state', new=r_state.set_state)
        @mock.patch('charms.reactive.remove_state', new=r_state.remove_state)
        @mock.patch('charms.reactive.helpers.is_state', new=r_state.is_state)
        def inner2(*args, **kwargs):
            return f(inst, *args, **kwargs)

        return inner2()

    return inner1


class MockDB(object):
    """
    A simple replacement for unitdata.kv's get() and set() methods,
    along with some helper methods for testing.
    """
    def __init__(self, **data):
        """
        Initialize a dictionary-like object with the specified key/value pairs.
        """
        self.data = dict(data)

    def get(self, name, default=None):
        """
        Get the value for the specified key with a fallback default.
        """
        return self.data.get(name, default)

    def set(self, name, value):
        """
        Set the value for the specified key.
        """
        self.data[name] = value

    def r_get_all(self):
        """
        For testing purposes: return a shallow copy of the whole dictinary.
        """
        return dict(self.data)

    def r_set_all(self, data):
        """
        For testing purposes: set the stored data to a shallow copy of
        the supplied dictionary.
        """
        self.data = dict(data)

    def r_clear(self):
        """
        For testing purposes: remove all key/value pairs.
        """
        self.data = {}


r_kv = MockDB()

# Make sure all consumers of unitdata.kv() get our version.
unitdata.kv = lambda: r_kv


from spcharms import service_hook as testee

SP_NODE = platform.node()
CINDER_LXD_KEY = 'storpool-openstack-integration.lxd-name'
CINDER_LXD_NAME = 'juju-cinder'
US_TWO = set([SP_NODE, CINDER_LXD_NAME])
STATE_KEY = 'storpool-service.state'

STATE_ONLY_ME = {
    '-local': {
        SP_NODE: True,
    }
}

STATE_US_TWO = {
    '-local': {
        SP_NODE: True,
        CINDER_LXD_NAME: True
    }
}


class TestStorPoolService(unittest.TestCase):
    """
    Test various aspects of the storpool-service layer.
    """
    def setUp(self):
        """
        Clean up the reactive states information between tests.
        """
        super(TestStorPoolService, self).setUp()
        r_state.r_clear_states()
        r_kv.r_clear()

    def fail_on_err(self, msg):
        self.fail('sputils.err() invoked: {msg}'.format(msg=msg))

    def test_init(self):
        """
        Test the initial creation of a service presence structure
        only describing the local node.
        """
        # Initialize a service state object with no Cinder LXD
        state = testee.init_state(r_kv)
        self.assertEqual(state, STATE_ONLY_ME)

        # Now specify one
        r_kv.set(CINDER_LXD_KEY, CINDER_LXD_NAME)
        state = testee.init_state(r_kv)
        self.assertEqual(state, STATE_US_TWO)

    def test_get_state(self):
        """
        Test the various combinations of options for get_state() to
        fetch its data from.
        """
        r_kv.set(CINDER_LXD_KEY, 'r')
        b_kv = MockDB()
        b_kv.set(CINDER_LXD_KEY, 'b')
        e_kv = MockDB()

        (state_r, ch_t) = testee.get_state()
        self.assertEqual(set(state_r['-local'].keys()), set([SP_NODE, 'r']))
        self.assertTrue(ch_t)

        (state_b, ch_t) = testee.get_state(b_kv)
        self.assertEqual(set(state_b['-local'].keys()), set([SP_NODE, 'b']))
        self.assertTrue(ch_t)

        (state_e, ch_t) = testee.get_state(e_kv)
        self.assertEqual(list(state_e['-local'].keys()), [SP_NODE])
        self.assertTrue(ch_t)

        r_kv.set(STATE_KEY, state_b)
        (state_b_r, ch_f) = testee.get_state()
        self.assertEqual(state_b_r, state_b)
        self.assertFalse(ch_f)

        b_kv.set(STATE_KEY, state_e)
        (state_e_b, ch_f) = testee.get_state(b_kv)
        self.assertEqual(state_e_b, state_e)
        self.assertFalse(ch_f)

        e_kv.set(STATE_KEY, state_r)
        (state_r_e, ch_f) = testee.get_state(e_kv)
        self.assertEqual(state_r_e, state_r)
        self.assertFalse(ch_f)

    def test_update_state(self):
        """
        Test the update_state() method in its various variants.
        """
        st_all = {'a': {'aa': True, 'ab': True},
                  'b': {'ba': True, 'bb': True}}
        st_a = {'a': {'aa': True, 'ab': True}}
        st_false = {'a': {'aa': False, 'ab': True},
                    'b': {'ba': False, 'bb': True}}

        test = copy.deepcopy(st_false)

        ch = testee.update_state(r_kv, test, False, 'a', 'aa', False)
        self.assertEqual(test, st_false)
        self.assertEqual(r_kv.r_get_all(), {})
        self.assertFalse(ch)

        ch = testee.update_state(r_kv, test, True, 'a', 'aa', False)
        self.assertEqual(test, st_false)
        self.assertEqual(r_kv.r_get_all(), {STATE_KEY: test})
        self.assertTrue(ch)
        r_kv.r_clear()

        ch = testee.update_state(r_kv, test, False, 'a', 'aa', True)
        self.assertNotEqual(test, st_false)
        self.assertNotEqual(test, st_all)
        self.assertEqual(r_kv.r_get_all(), {STATE_KEY: test})
        self.assertTrue(ch)
        r_kv.r_clear()

        ch = testee.update_state(r_kv, test, False, 'b', 'ba', True)
        self.assertEqual(test, st_all)
        self.assertEqual(r_kv.r_get_all(), {STATE_KEY: test})
        self.assertTrue(ch)
        r_kv.r_clear()

        test = copy.deepcopy(st_a)

        ch = testee.update_state(r_kv, test, False, 'b', 'ba', False)
        self.assertNotEqual(test, st_a)
        self.assertNotEqual(test, st_false)
        self.assertEqual(r_kv.r_get_all(), {STATE_KEY: test})
        self.assertTrue(ch)
        r_kv.r_clear()

        ch = testee.update_state(r_kv, test, False, 'b', 'bb', True)
        self.assertNotEqual(test, st_a)
        self.assertNotEqual(test, st_false)
        self.assertEqual(r_kv.r_get_all(), {STATE_KEY: test})
        self.assertTrue(ch)
        r_kv.r_clear()

        same = copy.deepcopy(test)
        ch = testee.update_state(r_kv, test, False, 'a', 'aa', True)
        self.assertEqual(test, same)
        self.assertEqual(r_kv.r_get_all(), {})
        self.assertFalse(ch)

        ch = testee.update_state(r_kv, test, False, 'a', 'aa', False)
        self.assertEqual(test, st_false)
        self.assertEqual(r_kv.r_get_all(), {STATE_KEY: test})
        self.assertTrue(ch)
        r_kv.r_clear()

    @mock.patch('charmhelpers.core.hookenv.relation_set')
    @mock.patch('charmhelpers.core.hookenv.relation_ids')
    def test_add_present_node(self, rel_ids, rel_set):
        """
        Test the add_present_node() method, used for announcing to
        the world that a node (might be us, might be a container near us,
        might be another peer entirely) is up.
        """

        rel_data_received = []
        rels = ['peer-rel/1', 'peer-rel/42']
        rel_ids.return_value = rels
        rel_set.side_effect = lambda rid, storpool_service: \
            rel_data_received.append([rid, storpool_service])

        # Start with an empty database, this is supposed to fill out
        # the information about our node, too.
        node_name = 'new-node'
        testee.add_present_node(node_name, 'peer-relation')

        # Now let's see if it has filled in the database...
        self.assertEqual({
            STATE_KEY: {
                '-local': {
                    SP_NODE: True,
                    node_name: True,
                },
            },
        }, r_kv.r_get_all())

        jdata = json.dumps(r_kv.get(STATE_KEY)['-local'])
        self.assertEqual(rel_data_received,
                         list(map(lambda rid: [rid, jdata], rels)))

        # Change the relation IDs to ferret out anything that may
        # have cached them...
        rels = ['another-relation', 'and-another-one']
        rel_ids.return_value = rels

        # OK, let's see what happens if another node comes up
        rel_data_received = []
        another_name = 'newer-node'
        testee.add_present_node(another_name, 'peer-relation')
        self.assertEqual({
            STATE_KEY: {
                '-local': {
                    SP_NODE: True,
                    node_name: True,
                    another_name: True,
                },
            },
        }, r_kv.r_get_all())

        jdata = json.dumps(r_kv.get(STATE_KEY)['-local'])
        self.assertEqual(rel_data_received,
                         list(map(lambda rid: [rid, jdata], rels)))
