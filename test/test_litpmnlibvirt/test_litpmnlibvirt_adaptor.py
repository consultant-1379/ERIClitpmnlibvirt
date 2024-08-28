##############################################################################
# COPYRIGHT Ericsson AB 2014
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

import argparse
import os
import sys
os.environ["TESTING_FLAG"] = "1"
from litpmnlibvirt.litp_libvirt_adaptor import (LitpLibVirtAdaptor,
                                                ActionValidator,
                                                _main,
                                                Timeout,
                                                INTERNAL_STATUS_OK,
                                                INTERNAL_STATUS_NOK,
                                                INTERNAL_STATUS_FAIL)

from litpmnlibvirt.litp_libvirt_utils import LitpLibvirtException

import unittest
import mock
from libvirt import libvirtError

ADAPTOR_MODULE = 'litpmnlibvirt.litp_libvirt_adaptor'
ADAPTOR_CLASS = ADAPTOR_MODULE + '.LitpLibVirtAdaptor'
SYSTEMD_CLASS = 'litpmnlibvirt.litp_libvirt_utils.Libvirt_systemd'
CONFIG = {"vm_data": {"image": "path/image_name",
                      "ram": "1024",
                      "cpu": "2",
                      "interfaces": {"eth0": {'host_device': 'br0'},
                               "eth1": {'host_device': 'br1'}}},
          "adaptor_data": {}
          }


class TestLitpLibVirtAdaptor(unittest.TestCase):

    def setUp(self):
        self.adaptor = LitpLibVirtAdaptor("unittest", base_os='7')

    @mock.patch("sys.exit")
    @mock.patch("sys.stderr")
    def test_init_sets_instance_name(self, _stderr, _exit):
        self.assertEquals("unittest", self.adaptor.instance_name)

    @mock.patch("sys.exit")
    @mock.patch("sys.stderr")
    def test_main_exits_on_bad_cmd(self, _stderr, _exit):
        sys.argv = ['main', 'bad_cmd']
        _exit.side_effect = SystemExit
        self.assertRaises(SystemExit, _main)

    @mock.patch(ADAPTOR_CLASS + ".can_read_conf")
    @mock.patch("sys.exit")
    @mock.patch(ADAPTOR_CLASS + ".start")
    def test_main_exits_on_lower_case_cmd(self, start, _exit, can_read_conf):
        sys.argv = ['main', 'vm-name', 'start']
        can_read_conf.return_value = True
        start.return_value = 0
        start.assert_called_once()
        _main()
        _exit.assert_called_once_with(0)

    @mock.patch(ADAPTOR_CLASS + ".can_read_conf")
    @mock.patch("sys.exit")
    @mock.patch(ADAPTOR_CLASS + ".start")
    def test_main_exits_on_mixed_case_cmd(self, start, _exit, can_read_conf):
        sys.argv = ['main', 'vm-name', 'stArt']
        can_read_conf.return_value = True
        start.return_value = 0
        start.assert_called_once()
        _main()
        _exit.assert_called_once_with(0)

    @mock.patch(ADAPTOR_CLASS + ".can_read_conf")
    @mock.patch("sys.exit")
    @mock.patch(ADAPTOR_CLASS + ".start")
    def test_main_exits_on_upper_case_cmd(self, start, _exit, can_read_conf):
        sys.argv = ['main', 'vm-name', 'START']
        can_read_conf.return_value = True
        start.return_value = 0
        start.assert_called_once()
        _main()
        _exit.assert_called_once_with(0)

    @mock.patch(ADAPTOR_CLASS)
    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch("sys.exit")
    def test_main_reports_error_when_cant_read_conf(self, _exit, _log, _adaptor):
        sys.argv = ['main', 'vm-name', 'start']
        adaptor_mock = mock.Mock()
        adaptor_mock.start = mock.Mock()
        adaptor_mock.can_read_conf = mock.Mock()
        adaptor_mock.can_read_conf.return_value = False
        adaptor_mock.start = mock.Mock()
        adaptor_mock.start.return_value = 2
        adaptor_mock.conf = mock.Mock()
        adaptor_mock.conf.conf_file = "conf_file"
        _adaptor.return_value = adaptor_mock

        _exit.side_effect = SystemExit
        self.assertRaises(SystemExit, _main)
        _exit.assert_called_once_with(2)
        _log.assert_any_call("Error: cannot read config file: conf_file",
                level="ERROR", echo=True)

    @mock.patch(SYSTEMD_CLASS + ".start_service")
    @mock.patch(ADAPTOR_CLASS + ".force_stop")
    def test_force_restart_returns_value_from_start(self, fstop, sysd_start):
        fstop.return_value = 1
        sysd_start.return_value = 2
        self.assertEquals(2, self.adaptor.force_restart())
        fstop.assert_called_once()
        sysd_start.assert_called_once()

    @mock.patch(SYSTEMD_CLASS + ".restart_service")
    @mock.patch(ADAPTOR_CLASS + ".stop")
    def test_restart_returns_value_from_start(self, stop, sysd_restart):
        stop.return_value = 1
        sysd_restart.return_value = 2
        self.assertEquals(2, self.adaptor.restart())
        stop.assert_called_once()
        sysd_restart.assert_called_once()

    @mock.patch(ADAPTOR_MODULE + ".echo_failure")
    @mock.patch(ADAPTOR_MODULE + ".echo_success")
    @mock.patch(ADAPTOR_CLASS + "._stop")
    def test_stop_calls_lsb_decorations_pos(self, _stop, e_succ, e_fail):
        _stop.return_value = 0
        self.assertEquals(0, self.adaptor.stop())
        e_succ.assert_called_once_with('Service stop for "unittest"')
        self.assertEquals(0, e_fail.call_count)

    @mock.patch(ADAPTOR_MODULE + ".echo_failure")
    @mock.patch(ADAPTOR_MODULE + ".echo_success")
    @mock.patch(ADAPTOR_CLASS + "._stop")
    def test_stop_calls_lsb_decorations_neg(self, _stop, e_succ, e_fail):
        _stop.return_value = 5
        self.assertEquals(5, self.adaptor.stop())
        e_fail.assert_called_once_with('Service stop for "unittest"')
        self.assertEquals(0, e_succ.call_count)

    @mock.patch(SYSTEMD_CLASS + ".stop_service")
    @mock.patch(ADAPTOR_MODULE + ".echo_failure")
    @mock.patch(ADAPTOR_MODULE + ".echo_success")
    @mock.patch(ADAPTOR_CLASS + "._force_stop")
    def test_force_stop_calls_lsb_decorations_pos(self, _force_stop, e_succ,
            e_fail, _sysd_stop):
        _sysd_stop.return_value = 0
        _force_stop.return_value = 0
        self.assertEquals(0, self.adaptor.force_stop())
        e_succ.assert_called_once_with('Service force-stop for "unittest"')
        self.assertEquals(0, e_fail.call_count)

    @mock.patch(SYSTEMD_CLASS + ".stop_service")
    @mock.patch(ADAPTOR_MODULE + ".echo_failure")
    @mock.patch(ADAPTOR_MODULE + ".echo_success")
    @mock.patch(ADAPTOR_CLASS + "._force_stop")
    def test_force_stop_calls_lsb_decorations_neg(self, _force_stop, e_succ,
            e_fail, _sysd_stop):
        _sysd_stop.return_value = 0
        _force_stop.return_value = 5

        self.assertEquals(5, self.adaptor.force_stop())
        e_fail.assert_called_once_with('Service force-stop for "unittest"')
        self.assertEquals(0, e_succ.call_count)

    @mock.patch(ADAPTOR_MODULE + ".echo_failure")
    @mock.patch(ADAPTOR_MODULE + ".echo_success")
    @mock.patch(ADAPTOR_CLASS + ".check_startup_requirements")
    @mock.patch(ADAPTOR_CLASS + "._start")
    @mock.patch(ADAPTOR_CLASS + "._check_config_changed")
    def test_start_calls_lsb_decorations_pos(self, _ccc, _start, check_reqs, e_succ,
            e_fail):
        _ccc.return_value = True
        check_reqs.return_value = True
        _start.return_value = 0
        self.assertEquals(0, self.adaptor.start())
        e_succ.assert_called_once_with('Service start for "unittest"')
        self.assertEquals(0, e_fail.call_count)

    @mock.patch(ADAPTOR_MODULE + ".echo_failure")
    @mock.patch(ADAPTOR_MODULE + ".echo_success")
    @mock.patch(ADAPTOR_CLASS + ".check_startup_requirements")
    @mock.patch(ADAPTOR_CLASS + "._start")
    @mock.patch(ADAPTOR_CLASS + "._check_config_changed")
    def test_start_calls_lsb_decorations_neg(self, _ccc, _start, check_reqs, e_succ,
            e_fail):
        _ccc.return_value = True
        check_reqs.return_value = True
        _start.return_value = 5
        self.assertEquals(5, self.adaptor.start())
        e_fail.assert_called_once_with('Service start for "unittest"')
        self.assertEquals(0, e_succ.call_count)

    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_BAD_CONFIG")
    @mock.patch(ADAPTOR_MODULE + ".echo_failure")
    @mock.patch(ADAPTOR_MODULE + ".echo_success")
    @mock.patch(ADAPTOR_CLASS + ".check_startup_requirements")
    @mock.patch(ADAPTOR_CLASS + "._start")
    @mock.patch(ADAPTOR_CLASS + "._check_config_changed")
    def test_start_does_not_call_lsb_decorations_bad_reqs(self, _ccc, _start,
            check_reqs, e_succ, e_fail, bad_conf):
        check_reqs.return_value = False
        _ccc.return_value = False
        _start.side_effect = self.fail
        self.assertEquals(bad_conf, self.adaptor.start())
        self.assertEquals(0, e_succ.call_count)
        self.assertEquals(0, e_fail.call_count)

    @mock.patch(ADAPTOR_MODULE +'.urlopen')
    def test_internal_status_ok(self, urlopen):
        self.adaptor.conf = mock.Mock()
        self.adaptor.conf.get_adaptor_data.return_value = {
            'internal_status_check': {
                'active': 'on',
                'ip_address': '10.10.10.1',
                },
            }
        conn = mock.Mock()
        conn.close = mock.Mock()
        conn.getcode = mock.Mock(return_value=200)
        urlopen.return_value = conn
        with mock.patch(ADAPTOR_MODULE + '.log') as log_patch:
            status = self.adaptor._internal_status()
        self.assertEqual(log_patch.call_args_list, [
            mock.call('Checking Domain "unittest" status from URL: "http://10.10.10.1:12987"', level='DEBUG'),
            mock.call('Domain "unittest" internal status check OK'),
            ])

        self.assertEquals(status, INTERNAL_STATUS_OK)
        conn.close.assert_called_once()
        conn.getcode.assert_called_once()
        conn.getcode.return_value = 500
        status = self.adaptor._internal_status()
        self.assertEquals(status, INTERNAL_STATUS_NOK)


    @mock.patch("sys.stdout")
    @mock.patch(ADAPTOR_CLASS + "._status")
    def test_status_calls_lsb_decorations_pos(self, _status, sysstdout):
        _status.return_value = 0
        self.assertEquals(0, self.adaptor.status())
        sysstdout.write.assert_any_call("unittest is running...")

    @mock.patch("sys.stdout")
    @mock.patch(ADAPTOR_CLASS + "._status")
    def test_status_calls_lsb_decorations_neg(self, _status, sysstdout):
        _status.return_value = 5
        self.assertEquals(5, self.adaptor.status())
        sysstdout.write.assert_any_call("unittest is stopped")

    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_FAILURE")
    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_SUCCESS")
    @mock.patch(ADAPTOR_CLASS + "._is_running")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    @mock.patch(ADAPTOR_MODULE + ".log")
    def test_status_logs_not_defined(self, _log, _is_def, _is_run, lv_succ, lv_fail):
        _is_def.return_value = False
        self.assertEquals(lv_fail, self.adaptor._status())
        self.assertEquals(0, _is_run.call_count)

    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_FAILURE")
    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_SUCCESS")
    @mock.patch(ADAPTOR_CLASS + "._is_running")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    @mock.patch(ADAPTOR_MODULE + ".log")
    def test_status_logs_not_running(self, _log, _is_def, _is_run, lv_succ, lv_fail):
        _is_def.return_value = True
        _is_run.return_value = False
        self.assertEquals(lv_fail, self.adaptor._status())

    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_FAILURE")
    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_SUCCESS")
    @mock.patch(ADAPTOR_CLASS + "._is_running")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    @mock.patch(ADAPTOR_CLASS + "._internal_status")
    @mock.patch(ADAPTOR_MODULE + ".log")
    def test_status_ok_when_defined_and_running(self, _log, _int_chk, _is_def,
                                                _is_run, lv_succ, lv_fail):
        _int_chk.return_value = INTERNAL_STATUS_OK
        _is_def.return_value = True
        _is_run.return_value = True
        self.assertEquals(lv_succ, self.adaptor._status())

    @mock.patch(SYSTEMD_CLASS + ".stop_service")
    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_SUCCESS")
    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch(ADAPTOR_CLASS + "._get_domain")
    @mock.patch(ADAPTOR_CLASS + "._is_running")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    def test_force_stop_calls_destroy_if_domain_defined_and_running(self,
            _is_def, _is_run, _get_dom, _log, lv_succ, _sysd_stop):
        destroy = mock.Mock()
        _get_dom.return_value.destroy = destroy
        _is_def.return_value = True
        _is_run.return_value = True
        _sysd_stop.return_value = False
        self.assertEquals(lv_succ, self.adaptor._force_stop())
        destroy.assert_called_once_with()
        _log.assert_any_call('Attempting to destroy Service "unittest"')
        _log.assert_any_call('Calling destroy on Domain "unittest"')

    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_SUCCESS")
    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch(ADAPTOR_CLASS + "._get_domain")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    def test_force_stop_does_not_calls_destroy_if_domain_not_defined(self,
            _is_def, _get_dom, _log, lv_succ):
        destroy = mock.Mock()
        _is_def.return_value = False
        _get_dom.return_value.destroy = destroy
        self.assertEquals(lv_succ, self.adaptor._force_stop())
        self.assertEquals(0, destroy.call_count)
        self.assertEquals(0, _get_dom.call_count)
        _log.assert_any_call('Domain "unittest" is not defined - nothing to '
                'destroy')

    @mock.patch(SYSTEMD_CLASS + ".is_service_inactive")
    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_SUCCESS")
    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch(ADAPTOR_CLASS + "._get_domain")
    @mock.patch(ADAPTOR_CLASS + "._is_running")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    def test_force_stop_calls_destroy_if_domain_not_running(self, _is_def,
            _is_run, _get_dom, _log, lv_succ, _is_serv_inactive):
        destroy = mock.Mock()
        _get_dom.return_value.destroy = destroy
        _is_def.return_value = True
        _is_run.return_value = False
        _is_serv_inactive.return_value = False
        self.assertEquals(lv_succ, self.adaptor._force_stop())
        self.assertEquals(0, destroy.call_count)
        self.assertEquals(0, _get_dom.call_count)
        _log.assert_any_call('Domain "unittest" is not running - nothing to '
                'destroy')

    @mock.patch(SYSTEMD_CLASS + ".stop_service")
    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_SUCCESS")
    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch(ADAPTOR_CLASS + "._get_domain")
    @mock.patch(ADAPTOR_CLASS + "._is_running")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    def test_force_stop_retry_raises_exception_if_domain_not_running(self, _is_def,
            _is_run, _get_dom, _log, lv_succ, _sysd_stop):
        destroy = mock.Mock()
        _get_dom.return_value.destroy = destroy
        _is_def.return_value = True
        _is_run.side_effect = [True, False, False, False, False]
        _sysd_stop.return_value = 1
        self.assertEquals(lv_succ, self.adaptor._force_stop())
        _log.assert_any_call('Calling destroy on Domain "unittest"')
        _log.assert_any_call('Retrying if domain unittest is not running.  Attempt 0 of 3.')
        _log.assert_any_call('All retries attempts used, VM unittest is still down')
        self.assertEquals(0, destroy.call_count)
        _log.assert_any_call('Force Shutdown failed on "unittest" due to "instance is not running"')

    @mock.patch(SYSTEMD_CLASS + ".stop_service")
    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_SUCCESS")
    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch(ADAPTOR_CLASS + "._get_domain")
    @mock.patch(ADAPTOR_CLASS + "._is_running")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    def test_force_stop_after_domain_back_running(self, _is_def,
            _is_run, _get_dom, _log, lv_succ, _sysd_stop):
        destroy = mock.Mock()
        _get_dom.return_value.destroy = destroy
        _is_def.return_value = True
        _is_run.side_effect = [True, False, False, True, True]
        _sysd_stop.return_value = 1
        self.assertEquals(lv_succ, self.adaptor._force_stop())
        _log.assert_any_call('Calling destroy on Domain "unittest"')
        _log.assert_any_call('Retrying if domain unittest is not running.  Attempt 0 of 3.')
        _log.assert_any_call('Retrying if domain unittest is not running.  Attempt 1 of 3.')
        self.assertEquals(1, destroy.call_count)

    @mock.patch(SYSTEMD_CLASS + ".stop_service")
    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch(ADAPTOR_CLASS + "._get_domain")
    @mock.patch(ADAPTOR_CLASS + "._is_running")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    def test_force_stop_calls_destroy_fails(self, _is_def, _is_run,
                                            _get_dom, _log, _sysd_stop):
        _is_def.return_value = True
        _is_run.return_value = True
        _sysd_stop.return_value = False

        domain = mock.Mock()
        _get_dom.return_value = domain

        def raise_exception():
            raise libvirtError("operation failed: failed to kill qemu process with SIGTERM")
        domain.destroy.side_effect = raise_exception
        self.assertEquals(0, self.adaptor._force_stop())

        self.assertEqual(_log.call_args_list, [
            mock.call('Attempting to destroy Service "unittest"'),
            mock.call('Calling destroy on Domain "unittest"'),
            mock.call('Force Shutdown failed on "unittest" due to "operation failed: failed to kill qemu process with SIGTERM"')
        ])

    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch(ADAPTOR_MODULE + ".Libvirt_cloud_init")
    @mock.patch(ADAPTOR_MODULE + ".Libvirt_vm_image")
    @mock.patch(ADAPTOR_MODULE + ".Libvirt_vm_xml")
    @mock.patch(ADAPTOR_MODULE + ".get_handle")
    @mock.patch(ADAPTOR_CLASS + "._get_image_name")
    def test_define_creates_xml(self, _get_img, connector,
            LVxml, LVimg, LVcloudinit, _log):
        conn = mock.Mock()
        connector.return_value = conn
        xml = mock.Mock()
        LVcloudinit.item_id = 1
        LVcloudinit.get_disk_mounts = mock.MagicMock()
        LVcloudinit.get_disk_mounts.return_value=[]
        LVxml.return_value.build_machine_xml.return_value = xml
        self.adaptor.conf = mock.Mock()
        self.adaptor._define()

        c_args, c_kwargs = LVxml.call_args
        self.assertEqual(c_args, ("unittest",))
        conn.defineXML.assert_called_once_with(xml)
        _log.assert_any_call('Defining Domain "unittest"')
        _log.assert_any_call('Adding XML definition for Domain "unittest"')

    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch(ADAPTOR_MODULE + ".Libvirt_cloud_init")
    @mock.patch(ADAPTOR_MODULE + ".Libvirt_vm_image")
    @mock.patch(ADAPTOR_MODULE + ".Libvirt_vm_xml")
    @mock.patch(ADAPTOR_MODULE + ".get_handle")
    @mock.patch(ADAPTOR_CLASS + "._get_image_name")
    def test_define_generates_cloud_init(self, _get_img, connector, LVxml,
            LVimage, LVcloudinit, _log):
        c_init_instance = mock.Mock()
        LVcloudinit.return_value = c_init_instance
        self.adaptor.conf = mock.Mock()
        self.adaptor._define()

        c_args, c_kwargs = LVcloudinit.call_args
        self.assertEqual(c_args[0], "unittest")

        c_init_instance.create_cloud_init_iso.assert_called_once_with()
        _log.assert_any_call('Creating cloud init ISO for Domain "unittest"')

    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch(ADAPTOR_MODULE + ".Libvirt_cloud_init")
    @mock.patch(ADAPTOR_MODULE + ".Libvirt_vm_image")
    @mock.patch(ADAPTOR_MODULE + ".Libvirt_vm_xml")
    @mock.patch(ADAPTOR_MODULE + ".get_handle")
    @mock.patch(ADAPTOR_CLASS + "._get_image_name")
    def test_define_copies_image(self, _get_img, connector, LVxml, LVimg,
            LVcloudinit, _log):
        _get_img.return_value = "unittest.qcow2"
        img_inst = mock.Mock()
        LVimg.return_value = img_inst
        self.adaptor.conf = mock.Mock()
        self.adaptor._define()

        LVimg.assert_called_once_with("unittest", "unittest.qcow2")
        img_inst.copy_image.assert_called_once_with()
        _log.assert_any_call('Copying base image "unittest.qcow2" to instance directory '
                'for Domain "unittest"')

    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_SUCCESS")
    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch(ADAPTOR_CLASS + "._is_running")
    def test_start_returns_success_if_running(self, _is_run, _log, LV_succ):
        _is_run.return_value = True
        self.assertEquals(LV_succ, self.adaptor._start())
        _log.assert_any_call('Domain "unittest" is already running, nothing to do')

    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_SUCCESS")
    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch(ADAPTOR_CLASS + "._get_domain")
    @mock.patch(ADAPTOR_CLASS + "._internal_status")
    @mock.patch(ADAPTOR_CLASS + ".wait_on_state")
    @mock.patch(ADAPTOR_CLASS + "._sleep")
    @mock.patch(ADAPTOR_CLASS + "._define")
    @mock.patch(ADAPTOR_CLASS + "._is_started")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    @mock.patch(ADAPTOR_CLASS + "._is_running")
    def test_start_calls_define_if_not_defined(self, _is_run, _is_def,
            _is_start, _define, _sleep, _wait, _internal_chk, _get_dom,
            _log, LV_succ):
        self.adaptor.conf = mock.Mock()
        self.adaptor.conf.get_adaptor_data.return_value = {'start-timeout': 5}
        _is_run.return_value = False
        _is_def.return_value = False
        _wait.return_value = True
        _is_start.return_value = True
        dom = mock.Mock()
        _get_dom.return_value = dom
        _internal_chk.return_value = INTERNAL_STATUS_OK

        self.assertEquals(LV_succ, self.adaptor._start())
        _define.assert_called_once_with()
        dom.create.assert_called_once_with()

    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_SUCCESS")
    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch(ADAPTOR_CLASS + "._get_domain")
    @mock.patch(ADAPTOR_CLASS + "._internal_status")
    @mock.patch(ADAPTOR_CLASS + ".wait_on_state")
    @mock.patch(ADAPTOR_CLASS + "._sleep")
    @mock.patch(ADAPTOR_CLASS + "._define")
    @mock.patch(ADAPTOR_CLASS + "._is_started")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    @mock.patch(ADAPTOR_CLASS + "._is_running")
    def test_start_does_not_call_define_if_defined(self, _is_run, _is_def,
            _is_start, _define, _sleep, _wait, _internal_chk, _get_dom,
            _log, LV_succ):
        self.adaptor.conf = mock.Mock()
        self.adaptor.conf.get_adaptor_data.return_value = {'start-timeout': 5}
        _is_run.return_value = False
        _is_def.return_value = True
        _is_start.return_value = True
        _wait.return_value = True
        dom = mock.Mock()
        _get_dom.return_value = dom
        _internal_chk.return_value = INTERNAL_STATUS_OK

        self.assertEquals(LV_succ, self.adaptor._start())
        self.assertTrue(mock._Call('Domain "unittest" is not defined') not in _log.mock_calls)
        self.assertEquals(0, _define.call_count)
        dom.create.assert_called_once_with()

    @mock.patch(ADAPTOR_MODULE + ".VIR_DOMAIN_RUNNING")
    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_SUCCESS")
    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch(ADAPTOR_CLASS + "._internal_status")
    @mock.patch(ADAPTOR_CLASS + ".wait_on_state")
    @mock.patch(ADAPTOR_CLASS + "._sleep")
    @mock.patch(ADAPTOR_CLASS + "._get_domain")
    @mock.patch(ADAPTOR_CLASS + "._is_started")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    @mock.patch(ADAPTOR_CLASS + "._is_running")
    def test_start_waits_until_started(self, _is_run, _is_def,
            _is_start, _get_dom, _sleep, _wait, _internal_chk,
            _log, LV_succ, VIR_RUNNING):
        self.adaptor.conf = mock.Mock()
        self.adaptor.conf.get_adaptor_data.return_value = {'start-timeout': 5}
        _is_run.return_value = False
        _is_def.return_value = True
        _wait.return_value = True
        dom = mock.Mock()
        _get_dom.return_value = dom
        _internal_chk.side_effect = [INTERNAL_STATUS_FAIL,
                                     INTERNAL_STATUS_FAIL,
                                     INTERNAL_STATUS_FAIL,
                                     INTERNAL_STATUS_OK]

        self.assertEquals(LV_succ, self.adaptor._start())
        _sleep.assert_has_calls([mock.call(5), mock.call(5), mock.call(5)])
        dom.create.assert_called_once_with()

    @mock.patch(ADAPTOR_MODULE + ".VIR_DOMAIN_RUNNING")
    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_SUCCESS")
    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch(ADAPTOR_CLASS + "._internal_status")
    @mock.patch(ADAPTOR_CLASS + ".wait_on_state")
    @mock.patch(ADAPTOR_CLASS + "._sleep")
    @mock.patch("sys.exit")
    @mock.patch(ADAPTOR_CLASS + "._get_domain")
    @mock.patch(ADAPTOR_CLASS + "._is_started")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    @mock.patch(ADAPTOR_CLASS + "._is_running")
    def test_start_waits_45_secs_if_no_conf(self, _is_run, _is_def,
            _is_start, _get_dom, _exit, _sleep, _wait, _internal_chk,
            _log, LV_succ, VIR_RUNNING):
        sys.argv = ['main', 'blah', 'start']
        self.adaptor.conf = mock.Mock()
        self.adaptor.conf.get_adaptor_data.return_value = {}
        _is_run.return_value = False
        _is_def.return_value = True
        _wait.return_value = True
        _is_start.side_effect = [False, False, False, True]
        dom = mock.Mock()
        _get_dom.return_value = dom
        _internal_chk.return_value = INTERNAL_STATUS_OK

        self.assertEquals(LV_succ, self.adaptor._start())
        _wait.assert_called_once_with(_is_start, 45)

    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_SUCCESS")
    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch(ADAPTOR_CLASS + "._get_domain")
    @mock.patch(ADAPTOR_CLASS + "._is_running")
    def test_stop_returns_success_if_not_running(self, _is_run, _get_dom,
            _log, LV_succ):
        _is_run.return_value = False
        self.assertEquals(LV_succ, self.adaptor._stop())
        self.assertEquals(0, _get_dom.call_count)
        _log.assert_any_call('Attempting to stop service "unittest"')
        _log.assert_any_call('Domain "unittest" is not running - nothing to do')

    @mock.patch(ADAPTOR_MODULE + ".VIR_DOMAIN_SHUTOFF")
    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_SUCCESS")
    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch(ADAPTOR_CLASS + ".wait_for_shutdown")
    @mock.patch(ADAPTOR_CLASS + "._get_domain")
    @mock.patch(ADAPTOR_CLASS + "._is_running")
    def test_stop_waits_for_time_in_conf(self, _is_run, _get_dom,
        _wait, _log, LV_succ, VIR_SHUTOFF):
        _is_run.return_value = True
        _wait.return_value = True
        dom = mock.Mock()
        _get_dom.return_value = dom

        self.assertEquals(LV_succ, self.adaptor._stop(stop_timeout=5))
        _wait.assert_called_once_with(5)
        dom.shutdown.assert_called_once_with()
        _log.assert_any_call('Waiting 5 seconds for Domain "unittest" to shut down')

    @mock.patch(ADAPTOR_MODULE + ".VIR_DOMAIN_SHUTOFF")
    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_SUCCESS")
    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch(ADAPTOR_CLASS + ".wait_for_shutdown")
    @mock.patch(ADAPTOR_CLASS + "._force_stop_undefine")
    @mock.patch(ADAPTOR_CLASS + "._get_domain")
    @mock.patch(ADAPTOR_CLASS + "._is_running")
    def test_stop_waits_for_inf_secs_if_no_conf(self, _is_run,
             _get_dom, _fstopundef, _wait, _log, LV_succ, VIR_SHUTOFF):
        self.adaptor.conf = mock.Mock()
        self.adaptor.conf.get_adaptor_data.return_value = {}
        _is_run.return_value = True
        _wait.return_value = True
        dom = mock.Mock()
        _get_dom.return_value = dom
        _fstopundef.return_value = LV_succ

        self.assertEquals(LV_succ, self.adaptor._stop(stop_timeout=1))
        _wait.assert_called_once_with(1)
        dom.shutdown.assert_called_once_with()
        self.assertEqual(_log.call_args_list, [
            mock.call('Attempting to stop service "unittest"'),
            mock.call('Calling ACPI shutdown on Domain "unittest"'),
            mock.call('Waiting 1 seconds for Domain "unittest" to shut down')
            ])

    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch(ADAPTOR_CLASS + "._force_stop_undefine")
    @mock.patch(ADAPTOR_CLASS + "._force_stop")
    @mock.patch(ADAPTOR_CLASS + ".wait_for_shutdown")
    @mock.patch(ADAPTOR_CLASS + "._get_domain")
    @mock.patch(ADAPTOR_CLASS + "._is_running")
    def test_stop_calls_force_stop_if_state_not_reached(self, _is_run,
            _get_dom, _wait, _force_stop, _fstopundef, _log):
        self.adaptor.conf = mock.Mock()
        self.adaptor.conf.get_adaptor_data.return_value = {}
        _is_run.return_value = True
        _wait.return_value = False
        dom = mock.Mock()
        _get_dom.return_value = dom
        _force_stop.return_value = 255

        self.assertEquals(255, self.adaptor._stop(stop_timeout=1))
        _force_stop.assert_called_once_with()
        _log.assert_any_call('ACPI shutdown of Domain "unittest" unsuccessful'
                ' - calling force-stop')
        dom.shutdown.assert_called_once_with()

    @mock.patch("litpmnlibvirt.litp_libvirt_adaptor.Timeout.__enter__")
    @mock.patch(ADAPTOR_CLASS + "._sleep")
    @mock.patch(ADAPTOR_CLASS + "._shutdown_domain")
    @mock.patch(ADAPTOR_CLASS + "._is_stopped")
    def test_wait_for_shutdown_normal(self, stopped, shut, sleep, enter):
        stopped.side_effect = [False, False, True]
        self.assertTrue(self.adaptor.wait_for_shutdown(5))
        self.assertEquals(3, stopped.call_count)
        self.assertEquals(2, sleep.call_count)
        self.assertEquals(0, shut.call_count)

    @mock.patch("litpmnlibvirt.litp_libvirt_adaptor.Timeout.__enter__")
    @mock.patch(ADAPTOR_CLASS + "._sleep")
    @mock.patch(ADAPTOR_CLASS + "._shutdown_domain")
    @mock.patch(ADAPTOR_CLASS + "._is_stopped")
    def test_wait_for_shutdown_repeat(self, stopped, shut, sleep, enter):
        stopped_side_effect = [False] * 32
        stopped_side_effect.append(True)
        stopped.side_effect = stopped_side_effect
        self.assertTrue(self.adaptor.wait_for_shutdown(50))
        self.assertEquals(33, stopped.call_count)
        self.assertEquals(32, sleep.call_count)
        self.assertEquals(1, shut.call_count)

    @mock.patch("litpmnlibvirt.litp_libvirt_adaptor.Timeout.__enter__")
    @mock.patch(ADAPTOR_CLASS + "._sleep")
    @mock.patch(ADAPTOR_CLASS + "._shutdown_domain")
    @mock.patch(ADAPTOR_CLASS + "._is_stopped")
    def test_wait_for_shutdown_timeout(self, stopped, shut, sleep, enter):
        stopped_side_effect = [False] * 50
        stopped_side_effect.append(Timeout.Timeout())
        stopped.side_effect = stopped_side_effect
        self.assertFalse(self.adaptor.wait_for_shutdown(50))
        self.assertEquals(51, stopped.call_count)
        self.assertEquals(50, sleep.call_count)
        self.assertEquals(1, shut.call_count)

    @mock.patch(ADAPTOR_CLASS + "._get_domain")
    def test__shutdown_domain_calls_shutdown(self, _get_domain):
        self.adaptor._shutdown_domain()
        _get_domain.return_value.shutdown.assert_called_once_with()

    @mock.patch(ADAPTOR_CLASS + "._get_domain")
    def test__shutdown_domain_swallows_all_libvirt_error(self, _get_domain):
        lvError = type("libvirtError", (Exception,), {
                            "get_error_message": (lambda slf: "some message"),
                        })
        raised_error = lvError()
        _get_domain.return_value.shutdown.side_effect = raised_error
        with mock.patch(ADAPTOR_MODULE + ".libvirtError", lvError):
            self.adaptor._shutdown_domain()
        _get_domain.return_value.shutdown.assert_called_once_with()

    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch(ADAPTOR_CLASS + "._check_disk_images")
    def test_check_startup_requirements_logs_error(self, chk_dsk, _log):
        error = mock.Mock()
        chk_dsk.return_value = [error]
        self.assertFalse(self.adaptor.check_startup_requirements())
        _log.assert_any_call(error, level="ERROR", echo=True)

    @mock.patch(ADAPTOR_MODULE + ".log")
    @mock.patch(ADAPTOR_CLASS + "._check_disk_images")
    def test_check_startup_requirements_does_not_log_if_clean(self, chk_dsk,
            _log):
        chk_dsk.return_value = []
        self.assertTrue(self.adaptor.check_startup_requirements())
        self.assertEquals(0, _log.call_count)

    @mock.patch(ADAPTOR_MODULE + ".log")
    def testcan_read_conf_pos(self, _log):
        self.adaptor.conf = mock.Mock()
        self.assertTrue(self.adaptor.can_read_conf())
        self.assertEquals(0, _log.call_count)

    @mock.patch(ADAPTOR_MODULE + ".log")
    def testcan_read_conf_neg(self, _log):
        def LitpLibvirtExceptionRaiser():
            raise LitpLibvirtException("unittest")
        self.adaptor.conf = mock.Mock()
        self.adaptor.conf.read_conf_data.side_effect = \
                LitpLibvirtExceptionRaiser
        self.assertFalse(self.adaptor.can_read_conf())
        _log.assert_any_call("unittest", level="ERROR", echo=True)

    @mock.patch(ADAPTOR_MODULE + ".Libvirt_vm_image")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    @mock.patch(ADAPTOR_CLASS + "._get_image_name")
    def test_check_disk_images_check_instance_if_defined(self, _get_img,
            _is_def, _img):
        _is_def.return_value = True
        live_image = mock.Mock()
        base_image = mock.Mock()
        _img.return_value.machine_image_exists = live_image
        _img.return_value.base_image_exists = base_image
        live_image.return_value = True
        base_image.return_value = True

        self.assertEquals([], self.adaptor._check_disk_images())
        live_image.assert_called_once()
        self.assertEquals(0, base_image.call_count)

    @mock.patch(ADAPTOR_MODULE + ".Libvirt_vm_image")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    @mock.patch(ADAPTOR_CLASS + "._get_image_name")
    def test_check_disk_images_check_base_if_not_defined(self, _get_img,
            _is_def, _img):
        _is_def.return_value = False
        mach_image = mock.Mock()
        base_image = mock.Mock()
        _img.return_value.live_image_exists = mach_image
        _img.return_value.base_image_exists = base_image
        mach_image.return_value = True
        base_image.return_value = True

        self.assertEquals([], self.adaptor._check_disk_images())
        base_image.assert_called_once()
        self.assertEquals(0, mach_image.call_count)

    @mock.patch(ADAPTOR_MODULE + ".Libvirt_vm_image")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    @mock.patch(ADAPTOR_CLASS + "._get_image_name")
    def test_check_disk_images_return_empty_if_not_issue_def(self,
            _get_img, _is_def, _img):
        _is_def.return_value = True
        live_image = mock.Mock()
        _img.return_value.live_image_exists = live_image
        live_image.return_value = True
        self.assertEquals([], self.adaptor._check_disk_images())

    @mock.patch(ADAPTOR_MODULE + ".Libvirt_vm_image")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    @mock.patch(ADAPTOR_CLASS + "._get_image_name")
    def test_check_disk_images_return_empty_if_not_issue_undef(self,
            _get_img, _is_def, _img):
        _is_def.return_value = False
        base_image = mock.Mock()
        _img.return_value.base_image_exists = base_image
        base_image.return_value = True
        self.assertEquals([], self.adaptor._check_disk_images())

    @mock.patch(ADAPTOR_MODULE + ".Libvirt_vm_image")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    @mock.patch(ADAPTOR_CLASS + "._get_image_name")
    def test_check_disk_images_return_message_list_if_issue_def(self,
            _get_img, _is_def, _img):
        _is_def.return_value = True
        mach_image = mock.Mock()
        _img.return_value.live_image_exists = mach_image
        mach_image.return_value = False

        self.assertEquals(['Instance image for Domain "unittest" does not '
            'exist'], self.adaptor._check_disk_images())

    @mock.patch(ADAPTOR_MODULE + ".Libvirt_vm_image")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    @mock.patch(ADAPTOR_CLASS + "._get_image_name")
    def test_check_disk_images_return_message_list_if_issue_undef(self,
            _get_img, _is_def, _img):
        _is_def.return_value = False
        base_image = mock.Mock()
        _img.return_value.base_image_exists = base_image
        base_image.return_value = False

        self.assertEquals(['Base image for Domain "unittest" does not '
            'exist'], self.adaptor._check_disk_images())

    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    @mock.patch(ADAPTOR_MODULE + ".Libvirt_cloud_init")
    def test_check_config_changed_no_conf_live(self, LVcloudinit, _is_def):
        _is_def.return_value = False
        self.adaptor.conf.conf_live_exists = mock.Mock(return_value=False)
        self.assertEquals(True, self.adaptor._check_config_changed())

    @mock.patch('os.path.exists')
    @mock.patch(ADAPTOR_CLASS + "._undefine")
    @mock.patch(ADAPTOR_CLASS + "._force_stop")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    @mock.patch(ADAPTOR_MODULE + ".Libvirt_cloud_init")
    def test_check_config_changed_no_conf_live_but_defined(self, LVcloudinit, 
            _is_def, _fstop, _undef, mockexists):
        _is_def.return_value = True
        mockexists.return_value = False
        self.adaptor.conf.get_vm_data = mock.Mock()
        self.adaptor.conf.get_vm_data.return_value = {'image': 'image.qcow2'}
        self.adaptor.conf.conf_live_exists = mock.Mock(return_value=False)
        self.assertEquals(True, self.adaptor._check_config_changed())
        # Need to check it calls _force_stop and _undefine
        _fstop.assert_called()
        _undef.assert_called()

    @mock.patch(ADAPTOR_MODULE + ".Libvirt_cloud_init")
    @mock.patch(ADAPTOR_MODULE + ".Libvirt_vm_image")
    @mock.patch(ADAPTOR_CLASS + "._stop")
    @mock.patch(ADAPTOR_CLASS + "._undefine")
    def test_check_config_changed_no_error(
        self, undefine, stop,  LVvmimage, LVcloudinit):
        self.adaptor.conf.conf_live_exists = mock.Mock(return_value=True)
        self.adaptor.conf.conf_same = mock.Mock(return_value=False)
        self.adaptor.conf.get_live_conf = mock.Mock(return_value=CONFIG)
        self.adaptor.conf.cleanup_instance_dir = mock.Mock()
        LVcloudinit.return_value.delete_cloud_init_iso = mock.Mock()
        LVvmimage.return_value.delete_live_image = mock.Mock()
        self.assertEquals(True, self.adaptor._check_config_changed())

    @mock.patch(ADAPTOR_CLASS + "._undefine")
    @mock.patch(ADAPTOR_CLASS + "._stop")
    def test_check_config_changed_cleanup_instance_dir_raise_error(
        self, undefine, stop):
        self.adaptor.conf.conf_live_exists = mock.Mock(return_value=True)
        self.adaptor.conf.conf_same = mock.Mock(return_value=False)
        self.adaptor.conf.cleanup_instance_dir = mock.Mock(side_effect=OSError)

        self.assertEquals(False, self.adaptor._check_config_changed())

    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    @mock.patch(ADAPTOR_CLASS + "._get_domain")
    def test_undefine(self, _is_defined, _get_domain):
        self.adaptor._get_domain = mock.Mock()
        self.adaptor._undefine()
        _get_domain.assert_called_once_with()

    @mock.patch('os.rename')
    @mock.patch('shutil.rmtree')
    @mock.patch('os.path.exists')
    @mock.patch(ADAPTOR_MODULE + ".echo_success")
    @mock.patch(ADAPTOR_MODULE + ".echo_failure")
    @mock.patch(ADAPTOR_CLASS + "._is_running")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    @mock.patch(ADAPTOR_CLASS + "._get_domain")
    @mock.patch(ADAPTOR_CLASS + "._undefine")
    @mock.patch(ADAPTOR_CLASS + ".wait_on_state")
    def test_stop_undefine_when_instance_not_running(self, _wait, _undefine,
        _get_domain, _is_def, _is_run, e_fail, e_succ, mockexists,
        mockremove, mockrename):
        _is_def.return_value = True
        _is_run.return_value = False
        _wait.return_value = True
        self.adaptor._get_domain = mock.Mock()
        mockexists.return_value = False
        self.adaptor.conf.get_vm_data = mock.Mock()
        self.adaptor.conf.get_vm_data.return_value = {'image': 'image.qcow2'}
        self.adaptor.stop_undefine(stop_timeout=1)
        _undefine.assert_called_once_with()

        self.assertEqual(mockremove.call_args_list, [])
        self.assertEqual(mockrename.call_args_list, [])

    @mock.patch(ADAPTOR_MODULE + ".echo_success")
    @mock.patch(ADAPTOR_MODULE + ".echo_failure")
    def test_force_stop_undefine(self, e_succ, e_fail):
        self.adaptor.conf = mock.Mock()
        self.adaptor.conf.move_files_to_last_undefined_vm_dir = mock.Mock()
        self.adaptor.conf.cleanup_instance_dir = mock.Mock()
        self.adaptor._force_stop = mock.Mock()
        self.adaptor._undefine = mock.Mock()
        self.adaptor.force_stop_undefine()
        e_succ.assert_called_once_with('Service force-stop-undefine for "unittest"')
        self.assertEquals(0, e_fail.call_count)
        self.adaptor.conf.move_files_to_last_undefined_vm_dir.assert_called_once_with()
        self.adaptor.conf.cleanup_instance_dir.assert_called_once_with()
        self.adaptor._force_stop.assert_called_once_with()
        self.adaptor._undefine.assert_called_once_with()

    @mock.patch(ADAPTOR_CLASS + "._undefine")
    @mock.patch(ADAPTOR_CLASS + "._force_stop")
    def test__force_stop_undefine_raises(self, _fstop, _undef):
        self.adaptor.conf = mock.Mock()
        self.adaptor.conf.move_files_to_last_undefined_vm_dir.side_effect = OSError
        self.adaptor.conf.cleanup_instance_dir.side_effect = OSError
        self.adaptor._force_stop_undefine()
        _fstop.assert_called()
        _undef.assert_called()
        self.adaptor.conf.move_files_to_last_undefined_vm_dir.assert_called()
        self.adaptor.conf.cleanup_instance_dir.assert_called()

    @mock.patch(ADAPTOR_MODULE + ".LITP_LIBVIRT_SUCCESS")
    @mock.patch(ADAPTOR_MODULE + ".echo_success")
    @mock.patch(ADAPTOR_MODULE + ".echo_failure")
    @mock.patch(ADAPTOR_CLASS + "._get_domain")
    @mock.patch(ADAPTOR_CLASS + "._is_running")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    @mock.patch(ADAPTOR_CLASS + "._stop")
    @mock.patch(ADAPTOR_CLASS + "._undefine")
    @mock.patch(ADAPTOR_CLASS + ".wait_on_state")
    @mock.patch(ADAPTOR_MODULE + ".log")
    def test_stop_undefine(self, _log, _wait, _undefine, _stop, _is_def,
        _is_run, _get_domain, e_fail, e_succ, lv_succ):
        _is_def.return_value = True
        _is_run.return_value = True
        _wait.return_value = True
        _stop.return_value = lv_succ
        self.adaptor.conf = mock.Mock()
        self.adaptor.conf.move_files_to_last_undefined_vm_dir = mock.Mock()
        self.adaptor.conf.cleanup_instance_dir = mock.Mock()
        self.adaptor.stop_undefine(stop_timeout=7)
        self.adaptor.conf.move_files_to_last_undefined_vm_dir.assert_called_once_with()
        self.adaptor.conf.cleanup_instance_dir.assert_called_once_with()
        _undefine.assert_called_once_with()

        e_succ.assert_called_once_with('Service stop-undefine for "unittest"')
        self.assertEquals(0, e_fail.call_count)


class TestLitpLibVirtAdaptorHelpers(unittest.TestCase):

    def setUp(self):
        self.adaptor = LitpLibVirtAdaptor("helper_test")

    # Note to the unwary - because we do "from ... import get_handle",
    # get_handle now lives in litp_libvirt_adaptor's namespace not
    # in the namespace of the connector. Consider yourself warned
    @mock.patch(ADAPTOR_MODULE + ".VIR_CONNECT_LIST_DOMAINS_INACTIVE")
    @mock.patch(ADAPTOR_MODULE + ".VIR_CONNECT_LIST_DOMAINS_ACTIVE")
    @mock.patch(ADAPTOR_MODULE + ".get_handle")
    def test_is_defined_neg(self, connector, _active, _inactive):
        conn = mock.Mock()
        connector.return_value = conn
        conn.listAllDomains.return_value = [mock.Mock(),
                                            mock.Mock(),
                                            mock.Mock()
                                            ]
        for mock_obj, sys_name in zip(
                conn.listAllDomains.return_value,
                ['ms-1', 'sc-1', 'sc-2']):
            mock_obj.name.return_value = sys_name
        self.assertFalse(self.adaptor._is_defined())
        connector.assert_called_once_with()
        self.assertEquals(1, conn.listAllDomains.call_count)

    @mock.patch(ADAPTOR_MODULE + ".VIR_CONNECT_LIST_DOMAINS_INACTIVE")
    @mock.patch(ADAPTOR_MODULE + ".VIR_CONNECT_LIST_DOMAINS_ACTIVE")
    @mock.patch(ADAPTOR_MODULE + ".get_handle")
    def test_is_defined_pos(self, connector, _active, _inactive):
        conn = mock.Mock()
        connector.return_value = conn
        conn.listAllDomains.return_value = [mock.Mock(),
                                            mock.Mock(),
                                            mock.Mock(),
                                            mock.Mock()
                                            ]
        for mock_obj, sys_name in zip(
                conn.listAllDomains.return_value,
                ['ms-1', 'sc-1', 'helper_test', 'sc-2']):
            mock_obj.name.return_value = sys_name

        self.assertTrue(self.adaptor._is_defined())
        connector.assert_called_once_with()
        self.assertEquals(1, conn.listAllDomains.call_count)

    @mock.patch(ADAPTOR_MODULE + ".VIR_CONNECT_LIST_DOMAINS_INACTIVE")
    @mock.patch(ADAPTOR_MODULE + ".VIR_CONNECT_LIST_DOMAINS_ACTIVE")
    @mock.patch(ADAPTOR_MODULE + ".get_handle")
    def test_is_defined_uses_active_and_inactive_flag(self, connector, _active,
            _inactive):
        conn = mock.Mock()
        connector.return_value = conn
        active_or_inactive = mock.Mock()
        def or_side_effect(operand):
            "Represents result of __or__ operation"
            if operand in (_active, _inactive):
                return active_or_inactive

        _active.__or__.side_effect = or_side_effect
        _inactive.__or__.side_effect = or_side_effect
        conn.listAllDomains.return_value = [mock.Mock(),
                                            mock.Mock(),
                                            mock.Mock(),
                                            mock.Mock()
                                            ]
        for mock_obj, sys_name in zip(
                conn.listAllDomains.return_value,
                ['ms-1', 'sc-1', 'helper_test', 'sc-2']):
            mock_obj.name.return_value = sys_name
        self.adaptor._is_defined()
        conn.listAllDomains.assert_called_with(active_or_inactive)


    @mock.patch(ADAPTOR_MODULE + ".VIR_CONNECT_LIST_DOMAINS_ACTIVE")
    @mock.patch(ADAPTOR_MODULE + ".get_handle")
    def test_is_running_pos(self, connector, dom_run):
        conn = mock.Mock()
        connector.return_value = conn
        conn.listAllDomains.return_value = [mock.Mock(),
                                            mock.Mock(),
                                            mock.Mock(),
                                            mock.Mock()
                                            ]
        for mock_obj, sys_name in zip(
                conn.listAllDomains.return_value,
                ['ms-1', 'sc-1', 'helper_test', 'sc-2']):
            mock_obj.name.return_value = sys_name
        self.assertTrue(self.adaptor._is_running())
        conn.listAllDomains.assert_called_once_with(dom_run)

    @mock.patch(ADAPTOR_MODULE + ".VIR_CONNECT_LIST_DOMAINS_ACTIVE")
    @mock.patch(ADAPTOR_MODULE + ".get_handle")
    def test_is_running_neg(self, connector, dom_run):
        conn = mock.Mock()
        connector.return_value = conn
        conn.listAllDomains.return_value = [mock.Mock(),
                                            mock.Mock(),
                                            mock.Mock()
                                            ]
        for mock_obj, sys_name in zip(
                conn.listAllDomains.return_value,
                ['ms-1', 'sc-1', 'sc-2']):
            mock_obj.name.return_value = sys_name
        self.assertFalse(self.adaptor._is_running())
        conn.listAllDomains.assert_called_once_with(dom_run)

    @mock.patch("litpmnlibvirt.litp_libvirt_adaptor.LitpLibVirtAdaptor._get_domain")
    def test_get_domain_state(self, _get_domain):
        info = mock.Mock()
        info.return_value = (255, 314)
        _get_domain.return_value.info = info
        self.assertEquals(255, self.adaptor._get_domain_state())

    @mock.patch("litpmnlibvirt.litp_libvirt_adaptor.get_handle")
    def test_get_domain(self, connector):
        conn = mock.Mock()
        connector.return_value = conn
        dom = mock.Mock()
        conn.lookupByName.return_value = dom
        self.assertEquals(dom, self.adaptor._get_domain())
        conn.lookupByName.assert_called_once_with('helper_test')

    @mock.patch("time.sleep")
    def test_sleep(self, tsleep):
        self.adaptor._sleep(5)
        tsleep.assert_called_once_with(5)

    @mock.patch("litpmnlibvirt.litp_libvirt_adaptor.Timeout.__enter__")
    @mock.patch("litpmnlibvirt.litp_libvirt_adaptor.LitpLibVirtAdaptor._sleep")
    def test_wait_on_state_run_to_timeout(self, _sleep, __enter__):
        timeout = 5
        chk_func = mock.Mock(side_effect=[False,False,False,Timeout.Timeout()])
        self.assertFalse(self.adaptor.wait_on_state(chk_func, timeout))
        self.assertEquals(3, _sleep.call_count)
        #is 6 because the last call throw the exception Timeout.Timeout
        self.assertEquals(4, chk_func.call_count)

    @mock.patch("litpmnlibvirt.litp_libvirt_adaptor.Timeout.__exit__")
    @mock.patch("litpmnlibvirt.litp_libvirt_adaptor.Timeout.__enter__")
    @mock.patch("litpmnlibvirt.litp_libvirt_adaptor.LitpLibVirtAdaptor._sleep")
    def test_wait_on_state_returns_True_on_state(self, _sleep, __enter__, __exit__):
        timeout = 5
        chk_func = mock.Mock(side_effect=[False,False,False,False,True])
        self.assertTrue(self.adaptor.wait_on_state(chk_func, timeout))
        self.assertEquals(4, _sleep.call_count)
        self.assertEquals(5, chk_func.call_count)

    @mock.patch("litpmnlibvirt.litp_libvirt_adaptor.Timeout.__exit__")
    @mock.patch("litpmnlibvirt.litp_libvirt_adaptor.Timeout.__enter__")
    @mock.patch("litpmnlibvirt.litp_libvirt_adaptor.LitpLibVirtAdaptor._sleep")
    def test_wait_on_state_run_doesnt_sleep_on_good_value(self, _sleep, __enter__, __exit__):
        timeout = 5
        chk_func = mock.Mock(side_effect=[True])
        self.assertTrue(self.adaptor.wait_on_state(chk_func, timeout))
        self.assertEquals(0, _sleep.call_count)
        self.assertEquals(1, chk_func.call_count)

    def test_get_image_name_pos(self):
        self.adaptor.conf = mock.Mock()
        get_vm_data = mock.Mock()
        self.adaptor.conf.get_vm_data = get_vm_data
        get_vm_data.return_value = {
                'image': 'helpertest.qcow2',
                'ram': '2048M',
                'cpus': 4,
                }
        self.assertEquals('helpertest.qcow2', self.adaptor._get_image_name())

    def test_get_image_name_neg(self):
        self.adaptor.conf = mock.Mock()
        get_vm_data = mock.Mock()
        self.adaptor.conf.get_vm_data = get_vm_data
        get_vm_data.return_value = {
                'ram': '2048M',
                'cpus': 4,
                }
        self.assertEquals(None, self.adaptor._get_image_name())

class TestLitpLibVirtAdaptorPrintHelp(unittest.TestCase):

    @mock.patch("sys.stderr")
    @mock.patch("sys.exit")
    def test_print_help(self, _exit, _stderr):
        sys.argv = ['main']
        _exit.side_effect = SystemExit
        self.assertRaises(SystemExit, _main)

        _stderr.write.assert_called_with("main: error: too few arguments\n")

class TestLitpLibVirtAdaptorActionValidator(unittest.TestCase):
    """
    Tests various properties of litpmnlibvirt.litp_libvirt_adaptor.ActionValidator
    """
    def setUp(self):
        self.inst = mock.Mock()
        self.action_validator = ActionValidator(
            LitpLibVirtAdaptor("unittest"))

    @mock.patch(ADAPTOR_CLASS + ".stop")
    def test_action_parser_has_stop_command(self, _method):
        method, kwargs = self.action_validator.get_adaptor_method('stop', [])
        self.assertTrue(method is _method)

    @mock.patch(ADAPTOR_CLASS + ".start")
    def test_action_parser_has_start_command(self, _method):
        method, kwargs = self.action_validator.get_adaptor_method('start', [])
        self.assertTrue(method is _method)

    @mock.patch(ADAPTOR_CLASS + ".status")
    def test_action_parser_has_status_command(self, _method):
        method, kwargs = self.action_validator.get_adaptor_method(
            'status', [])
        self.assertTrue(method is _method)

    @mock.patch(ADAPTOR_CLASS + ".restart")
    def test_action_parser_has_restart_command(self, _method):
        method, kwargs = self.action_validator.get_adaptor_method(
            'restart', [])
        self.assertTrue(method is _method)

    @mock.patch(ADAPTOR_CLASS + ".force_stop")
    def test_action_parser_has_force_stop_command(self, _method):
        method, kwargs = self.action_validator.get_adaptor_method(
            'force-stop', [])
        self.assertTrue(method is _method)

    @mock.patch(ADAPTOR_CLASS + ".force_restart")
    def test_action_parser_has_force_restart_command(self, _method):
        method, kwargs = self.action_validator.get_adaptor_method(
            'force-restart', [])
        self.assertTrue(method is _method)

    @mock.patch(ADAPTOR_CLASS + ".force_stop_undefine")
    def test_action_parser_has_force_stop_undefine_command(self, _method):
        method, kwargs = self.action_validator.get_adaptor_method(
            'force-stop-undefine', [])
        self.assertTrue(method is _method)

    @mock.patch(ADAPTOR_CLASS + ".stop_undefine")
    @mock.patch("sys.exit")
    def test_action_parser_has_stop_undefine_command(self, _exit, _method):
        method, kwargs = self.action_validator.get_adaptor_method(
            'stop-undefine', ['--stop-timeout=1'])
        self.assertTrue(method is _method)
        self.assertEquals({'stop_timeout': 1}, kwargs)

    @mock.patch(ADAPTOR_CLASS + ".stop_undefine")
    @mock.patch("sys.stderr")
    @mock.patch("sys.exit")
    def test_stop_undefine_command_complains_on_error(self, _exit, _stderr, _method):
        method, kwargs = self.action_validator.get_adaptor_method(
            'stop-undefine', ['--blah'])
        self.assertTrue(method is _method)
        _exit.side_effect = SystemExit
        _exit.assert_called_with(2)
        _stderr.write.assert_called_with("stop-undefine: error: unrecognized arguments: --blah\n")

    @mock.patch("sys.stderr")
    @mock.patch("sys.exit")
    def test_incorrect_action_causes_sys_exit(self, _exit, _stderr):
        self.action_validator.get_adaptor_method('blah', [])
        _exit.side_effect = SystemExit
        self.assertRaises(SystemExit, _main)
        _exit.assert_called_with(2)
        _stderr.write.assert_called_with('##CMD## <instance_name> [start|stop|status|restart|force-stop|force-restart|stop-undefine|force-stop-undefine]\n')

    @mock.patch("sys.stderr")
    @mock.patch("sys.exit")
    def test_unsupported_argument_provided(self, _exit, _stderr):
        self.action_validator.get_adaptor_method('stop', ['--blah'])
        _exit.side_effect = SystemExit
        self.assertRaises(SystemExit, _main)
        _exit.assert_called_with(2)
        _stderr.write.assert_called_with('Unsupported argument provided.\n')

    def test_positive_integer_invalid_values(self):
        self.assertRaises(argparse.ArgumentTypeError,
                          self.action_validator.positive_integer, '-1')
        self.assertRaises(argparse.ArgumentTypeError,
                          self.action_validator.positive_integer, 'AA')

    def test_positive_integer(self):
        value = self.action_validator.positive_integer('5')
        self.assertEquals(5, value)

class TestLitpLibVirtAdaptorMainMethod(unittest.TestCase):

    @mock.patch("sys.stderr")
    @mock.patch("sys.exit")
    def test_main_complains_when_it_gets_no_args(self, _exit, _stderr):
        # So this involves magic. If we don't raise an exception, we carry
        # on to code that shouldn't be hit when we call sys.exit
        # BUT instead of just not mocking it and calling just assertRaises
        # we also want to make sure the proper exit code is called
        sys.argv = ['main']
        _exit.side_effect = SystemExit
        self.assertRaises(SystemExit, _main)

        _exit.assert_called_with(2)
        _stderr.write.assert_called_with("main: error: too few arguments\n")

    @mock.patch("sys.stderr")
    @mock.patch("sys.exit")
    def test_main_complains_when_it_gets_one_arg(self, _exit, _stderr):
        sys.argv = ['main', 'main_test']
        _exit.side_effect = SystemExit
        self.assertRaises(SystemExit, _main)

        _exit.assert_called_with(2)
        _stderr.write.assert_called_with("main: error: too few arguments\n")

    @mock.patch(ADAPTOR_CLASS + ".can_read_conf")
    @mock.patch(ADAPTOR_CLASS + "._stop")
    @mock.patch(ADAPTOR_CLASS + "._get_domain")
    @mock.patch(ADAPTOR_CLASS + "._is_running")
    @mock.patch(ADAPTOR_CLASS + "._is_defined")
    @mock.patch("sys.stderr")
    @mock.patch("sys.exit")
    @mock.patch(ADAPTOR_MODULE + ".echo_failure")
    @mock.patch(ADAPTOR_MODULE + ".echo_success")
    def test_main_doesnt_complain_when_it_gets_two_args(self, _e_succ,
        _e_fail, _exit, _stderr, _is_def, _is_run, _get_domain, _stop,
        _can_read_conf):
        sys.argv = ['main', 'main_validator_test', 'stop']
        _exit.side_effect = SystemExit
        _can_read_conf.return_value = True
        self.assertRaises(SystemExit, _main)
        _stop.assert_called_once_with()

        # check exit called once ( with ``stop`` command return code )
        self.assertEquals(1, _exit.call_count)
        self.assertEquals(0, _stderr.write.call_count)

