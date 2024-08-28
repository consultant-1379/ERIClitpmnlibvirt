##############################################################################
# COPYRIGHT Ericsson AB 2014
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from litpmnlibvirt.litp_libvirt_connector import get_handle
from litpmnlibvirt.litp_libvirt_connector import URI as libvirt_connector_URI

import unittest
import mock


class TestLitpLibVirtConnector(unittest.TestCase):
    def setUp(self):
        get_handle.clear()

    @mock.patch("libvirt.open")
    def test_connector_opens_with_URI(self, lvpatch):
        conn1 = get_handle("foo")
        conn2 = get_handle("foo")
        self.assertTrue(conn1 is conn2)
        lvpatch.assert_called_once_with("foo")

    @mock.patch("libvirt.open")
    def test_connector_opens_without_URI(self, lvpatch):
        conn1 = get_handle()
        conn2 = get_handle()
        self.assertTrue(conn1 is conn2)
        lvpatch.assert_called_once_with(libvirt_connector_URI)

    @mock.patch("libvirt.open")
    def test_connector_opens_without_URI_and_default_URI(self, lvpatch):
        lvpatch.side_effect = [mock.Mock(), mock.Mock()]
        conn1 = get_handle()
        conn2 = get_handle(libvirt_connector_URI)
        self.assertTrue(conn1 is conn2)
        lvpatch.assert_called_once_with(libvirt_connector_URI)

    @mock.patch("libvirt.open")
    def test_connector_returns_different_handlers_for_different_URIs(self,
                                                                     lvpatch):
        lvpatch.side_effect = [mock.Mock(), mock.Mock()]
        conn1 = get_handle("foo")
        conn2 = get_handle("bar")
        self.assertFalse(conn1 is conn2)
        lvpatch.assert_any_call("foo")
        lvpatch.assert_any_call("bar")
