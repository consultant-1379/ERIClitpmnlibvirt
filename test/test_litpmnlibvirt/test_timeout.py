#!/usr/bin/env python
##############################################################################
# COPYRIGHT Ericsson AB 2014
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

import os
os.environ["TESTING_FLAG"] = "1"
from litpmnlibvirt.litp_libvirt_adaptor import Timeout
#from signal import SIGALRM
import unittest
import mock


class TestTimeout(unittest.TestCase):
    @mock.patch("signal.alarm")
    @mock.patch("signal.signal")
    @mock.patch("litpmnlibvirt.litp_libvirt_adaptor.Timeout._raise_timeout")
    def test_timeout(self, t_alarm, t_signal, t_raise_timeout):
        with Timeout(1):
            pass

        t_alarm.call_args_list = [mock.call(1), mock.call(0)]
        t_signal.assert_called()
