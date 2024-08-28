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

import sys
import os
import time
from urllib2 import urlopen, URLError, HTTPError
import argparse
import signal

from libvirt import (VIR_DOMAIN_RUNNING, VIR_DOMAIN_SHUTOFF,
                     VIR_CONNECT_LIST_DOMAINS_ACTIVE,
                     VIR_CONNECT_LIST_DOMAINS_INACTIVE, libvirtError)

from litpmnlibvirt.litp_libvirt_connector import get_handle
from litpmnlibvirt.litp_libvirt_utils import (Libvirt_conf, Libvirt_vm_xml,
                                              Libvirt_vm_image, log,
                                              Libvirt_cloud_init,
                                              Libvirt_systemd, echo_success,
                                              echo_failure,
                                              LitpLibvirtException)

LITP_LIBVIRT_SUCCESS = 0
LITP_LIBVIRT_FAILURE = 1
LITP_LIBVIRT_UNKNOWN_CMD = 2
LITP_LIBVIRT_BAD_CONFIG = 3
LITP_LIBVIRT_STATUS_CHK_PORT = 12987
LITP_LIBVIRT_STATUS_CHK_SLEEP = 5

INTERNAL_STATUS_OK = 0
INTERNAL_STATUS_NOK = 1
INTERNAL_STATUS_FAIL = 2

INTERNAL_CHECK_FAIL_CODE = 503

# A timeout value of 0 means that a timeout exception will never be raised
SERVICE_STOP_TIMEOUT = 0

SECONDS_BEFORE_SHUTDOWN_RETRY = 30

USAGE = "##CMD## <instance_name> [" + \
    "|".join(['start', 'stop', 'status', 'restart',
        'force-stop', 'force-restart', 'stop-undefine',
        'force-stop-undefine']) + "]\n"


class Timeout(object):
    """ Timeout class using ALARM signal. """
    class Timeout(Exception):
        pass

    def __init__(self, seconds):
        self.seconds = seconds

    def __enter__(self):
        signal.signal(signal.SIGALRM, self._raise_timeout)
        signal.alarm(self.seconds)

    def __exit__(self, *args):
        signal.alarm(0)

    def _raise_timeout(self, *args):
        # pylint: disable=W0613
        raise Timeout.Timeout()


class LitpLibVirtAdaptor(object):

    def __init__(self, instance_name, base_os='7'):
        self.instance_name = instance_name
        self.conf = Libvirt_conf(instance_name)
        self.systemd = Libvirt_systemd(instance_name)
        self.base_os = base_os

    def _is_defined(self):
        conn = get_handle()
        def_doms = [vm.name() for vm in
                        conn.listAllDomains(VIR_CONNECT_LIST_DOMAINS_ACTIVE |
                                            VIR_CONNECT_LIST_DOMAINS_INACTIVE)]
        return self.instance_name in def_doms

    def _is_running(self):
        conn = get_handle()
        running_doms = [vm.name() for vm in
                        conn.listAllDomains(VIR_CONNECT_LIST_DOMAINS_ACTIVE)]
        return self.instance_name in running_doms

    def _get_domain_state(self):
        domain = self._get_domain()
        return domain.info()[0]

    def _get_domain(self):
        conn = get_handle()
        domain = conn.lookupByName(self.instance_name)
        return domain

    def _get_image_name(self):
        vm_data = self.conf.get_vm_data()
        return vm_data.get("image")

    def _define(self):
        log('Defining Domain "{0}"'.format(self.instance_name))
        conn = get_handle()
        image_name = self._get_image_name()
        img_mgr = Libvirt_vm_image(self.instance_name, image_name)
        log('Creating cloud init ISO for Domain "{0}"'.format(
                                                        self.instance_name))

        adaptor_data = self.conf.get_adaptor_data()
        c_init = Libvirt_cloud_init(self.instance_name, adaptor_data)
        c_init.create_cloud_init_iso()
        log('Copying base image "{image_name}" to instance directory for '
            'Domain "{instance_name}"'.format(image_name=image_name,
                instance_name=self.instance_name))
        img_mgr.copy_image()
        log('Adding XML definition for Domain "{0}"'.format(
                                                        self.instance_name))
        xml = Libvirt_vm_xml(self.instance_name)
        conn.defineXML(xml.build_machine_xml())
        log('Domain "{0}" defined'.format(self.instance_name))

    def _is_started(self):
        return self._get_domain_state() == VIR_DOMAIN_RUNNING

    def _start(self):
        log('Attempting to start service "{0}"'.format(self.instance_name))
        if self._is_running():
            log('Domain "{0}" is already running, nothing to do'.format(
                self.instance_name))
            return LITP_LIBVIRT_SUCCESS

        if not self._is_defined():
            try:
                self._define()
            except (LitpLibvirtException, OSError) as ex:
                log('Domain "{0}" could not be defined.'
                    ''.format(self.instance_name), echo=True)
                log(str(ex), level='ERROR')
                return LITP_LIBVIRT_FAILURE
        else:
            log('Domain "{0}" is already defined'.format(self.instance_name))
        dom = self._get_domain()
        try:
            log('Defining libvirt domain {0}'.format(self.instance_name))
            dom.create()
        except libvirtError as ex:
            log('Domain "{0}" could not be created'.format(self.instance_name),
                echo=True)
            log(str(ex), level='ERROR')
            return LITP_LIBVIRT_FAILURE
        log('Waiting for domain {0} to start'.format(self.instance_name))
        startup_time = self.conf.get_adaptor_data().get("start-timeout", 45)
        if not self.wait_on_state(self._is_started, startup_time):
            log('Domain "{0}" failed to start'.format(self.instance_name))
            return LITP_LIBVIRT_FAILURE
        log('Domain {0} has been started successfully'.format(
            self.instance_name))
        internal_status = self._internal_status()
        while internal_status != INTERNAL_STATUS_OK:
            self._sleep(LITP_LIBVIRT_STATUS_CHK_SLEEP)
            internal_status = self._internal_status()
        return LITP_LIBVIRT_SUCCESS

    def start(self):
        """
        Attempts to start the container. This function will report
        unsuccessful, if it takes longer to reach a running state than the time
        defined in the 'startup-timeout' property in the 'adaptor_data'
        section of the config.json.
        """
        config_changed = self._check_config_changed()
        if not self.check_startup_requirements():
            return LITP_LIBVIRT_BAD_CONFIG
        msg_str = 'Service start for "{0}"'.format(self.instance_name)
        result = self._start()
        if result == LITP_LIBVIRT_SUCCESS:
            if config_changed:
                log('Attempt copying of config files to .live.', level="DEBUG")
                self.conf.conf_copy()
            echo_success(msg_str)
        else:
            echo_failure(msg_str)
        return result

    def check_startup_requirements(self):
        """
        Container method to hold validation for startup
        """
        results = []
        results.extend(self._check_disk_images())

        for result in results:
            log(result, level="ERROR", echo=True)
        return not bool(results)

    def _shutdown_domain(self):
        dom = self._get_domain()
        try:
            dom.shutdown()
        except libvirtError as ex:
            log('Shutdown failed on "{0}" due to "{1}"'.format( \
                self.instance_name, ex))

    def _stop(self, stop_timeout=SERVICE_STOP_TIMEOUT):
        """
        Attempts to stop virtual machine.
        ``stop_timeout`` -- the number of seconds to wait until stopping
                            virtual machine forcefully. If 0 provided,
                            waits infinetly.
        """
        log('Attempting to stop service "{0}"'.format(self.instance_name))
        if not self._is_running():
            log('Domain "{0}" is not running - nothing to do'.format(
                self.instance_name))
            return LITP_LIBVIRT_SUCCESS

        log('Calling ACPI shutdown on Domain '
                '"{0}"'.format(self.instance_name))
        self._shutdown_domain()

        if not stop_timeout:
            stop_timeout = self.conf.get_adaptor_data().get("stop-timeout",
                SERVICE_STOP_TIMEOUT)

        if stop_timeout:
            log('Waiting {0} seconds for Domain "{1}" to shut down'.format(
                stop_timeout, self.instance_name))
        else:
            log('Waiting for Domain "{0}" to shut down'.format(
                    self.instance_name))

        if not self.wait_for_shutdown(stop_timeout):
            log('ACPI shutdown of Domain "{0}" unsuccessful -'
                ' calling force-stop'.format(self.instance_name))
            return self._force_stop()

        return LITP_LIBVIRT_SUCCESS

    def wait_for_shutdown(self, timeout):
        """
        Waits for the VM shutdown to complete. Checks every second.
        Every 30 seconds, the shutdown is resent in case the first
        shutdown was sent during boot-up and ACPI is not ready to respond
        """
        try:
            with Timeout(timeout):
                while True:
                    for _ in range(SECONDS_BEFORE_SHUTDOWN_RETRY):
                        if self._is_stopped():
                            return True
                        self._sleep(1)
                    self._shutdown_domain()
        except Timeout.Timeout:
            return False

    def stop(self):
        """
        Will attempt an ACPI shutdown of the domain. If the shutdown
        takes more than the amount of time specified in the stop-timeout
        property set in the adaptor_data section of the config.json, the
        adaptor will forcefully stop the domain.
        """
        msg_str = 'Service stop for "{0}"'.format(self.instance_name)
        result = self._stop()
        if result == LITP_LIBVIRT_SUCCESS:
            echo_success(msg_str)
        else:
            echo_failure(msg_str)
        return result

    def _is_stopped(self):
        return self._get_domain_state() == VIR_DOMAIN_SHUTOFF

    def wait_on_state(self, check_func, timeout):
        """
        Blocking method that returns when a state is reached or
        raises an exception if the timeout is exceeded
        """
        try:
            with Timeout(timeout):
                while not check_func():
                    self._sleep(1)
        except Timeout.Timeout:
            return False
        return True

    def _sleep(self, secs):
        """
        Utility method for sleeping
        """
        time.sleep(secs)

    def _force_stop(self):
        log('Attempting to destroy Service "{0}"'.format(self.instance_name))
        if not self._is_defined():
            log('Domain "{0}" is not defined - nothing to '
                    'destroy'.format(self.instance_name))
            return LITP_LIBVIRT_SUCCESS
        if not self._is_running():
            log('Domain "{0}" is not running - nothing to '
                    'destroy'.format(self.instance_name))

            return LITP_LIBVIRT_SUCCESS
        dom = self._get_domain()
        log('Calling destroy on Domain "{0}"'.format(self.instance_name))
        # TORF-481022: Retry mechanism in force stop to avoid
        # race condition with Puppet
        try:
            for retries in range(0, 3):
                if not self._is_running():
                    log('Retrying if domain {0} is not running.'
                        '  Attempt {1} of 3.'
                        .format(self.instance_name, retries))
                    time.sleep(5)
                    continue
                else:
                    break
            if not self._is_running():
                log('All retries attempts used, VM {0} is still down'
                    .format(self.instance_name))
                raise libvirtError('instance is not running')
            dom.destroy()
        except libvirtError as ex:
            log('Force Shutdown failed on "{0}" due to "{1}"'.format( \
                self.instance_name, ex))

        return LITP_LIBVIRT_SUCCESS

    def force_stop(self):
        """
        Forcefully stops the domain (using libvirt.destroy)
        """
        msg_str = 'Service force-stop for "{0}"'.format(
            self.instance_name)
        result = self._force_stop()
        if '6' != self.base_os:
            self.systemd.stop_service()
        if result == LITP_LIBVIRT_SUCCESS:
            echo_success(msg_str)
        else:
            echo_failure(msg_str)
        return result

    def restart(self):
        """
        Restarts the domain using an ACPI shutdown, with a force-stop backup
        and starts it again normally.
        """
        # We use the high-level functions so we can report status
        if '6' != self.base_os:
            return self.systemd.restart_service()
        else:
            self.stop()
            return self.start()

    def force_restart(self):
        """
        Force-stops the domain then starts it again normally
        """
        # We use the high-level functions so we can report status
        self.force_stop()
        if '6' != self.base_os:
            return self.systemd.start_service()
        else:
            return self.start()

    def _get_url(self, ipaddress):
        url = 'http://{0}:{1}'.format(ipaddress, LITP_LIBVIRT_STATUS_CHK_PORT)
        log('Checking Domain "{0}" status from URL: "{1}"'.format(
                self.instance_name, url),
            level='DEBUG')
        return url

    def _internal_status(self, log_success=True):
        adaptor_data = self.conf.get_adaptor_data()
        if 'internal_status_check' in adaptor_data:
            chk = adaptor_data['internal_status_check']
            if chk['active'] == 'off':
                if log_success:
                    log('Domain "{0}" internal status check not active'.format(
                        self.instance_name))
                return INTERNAL_STATUS_OK
            url = self._get_url(chk['ip_address'])

            try:
                connection = urlopen(url)
                connection.close()
            except HTTPError as ex:
                if ex.getcode() == INTERNAL_CHECK_FAIL_CODE:
                    log('Domain "{0}" internal status check failed. A '
                        'HTTPError occured with code "{1}". The HTTPError was '
                        '"{2}"'.format(self.instance_name,
                            INTERNAL_CHECK_FAIL_CODE, str(ex)))
                    return INTERNAL_STATUS_NOK
                else:
                    log('Domain "{0}" internal status check failed. A unknown '
                        'HTTPError occured. The HTTPError was "{1}"'.format(
                            self.instance_name, str(ex)))
                    return INTERNAL_STATUS_FAIL
            except URLError as url_ex:
                log('Domain "{0}" internal status check failed. A unknown '
                    'URLError occured. The URLError was "{1}"'.format(
                        self.instance_name, str(url_ex)))
                return INTERNAL_STATUS_FAIL
            else:
                retcode = connection.getcode()
                if retcode != 200:
                    log('Domain "{0}" internal status check failed'.format(
                            self.instance_name))
                    log('Domain "{0}" internal status check failed. Return '
                        'code was not "200", it was "{1}"'.format(
                            self.instance_name, retcode),
                        level='DEBUG')
                    return INTERNAL_STATUS_NOK

        if log_success:
            log('Domain "{0}" internal status check OK'.format(
                self.instance_name))
        return INTERNAL_STATUS_OK

    def _status(self):
        if not self._is_defined():
            return LITP_LIBVIRT_FAILURE
        if not self._is_running():
            return LITP_LIBVIRT_FAILURE
        if not self._internal_status(log_success=False) == INTERNAL_STATUS_OK:
            log('Status: Domain "{0}" failed internal check'.format(
                    self.instance_name))
            return LITP_LIBVIRT_FAILURE
        return LITP_LIBVIRT_SUCCESS

    def status(self):
        """
        Checks the status of the domain by checking if it's:
            * defined
            * running
        """
        result = self._status()
        if result == LITP_LIBVIRT_SUCCESS:
            msg_str = 'is running...'
        else:
            msg_str = 'is stopped'
        print '{0} {1}'.format(self.instance_name, msg_str)
        return result

    def can_read_conf(self):
        try:
            self.conf.read_conf_data()
        except LitpLibvirtException as ex:
            log(str(ex), level="ERROR", echo=True)
            return False
        return True

    def _check_disk_images(self):
        """
        If the machine is not defined, check that the base image exists.
        If the machine is defined, check that the instance image exists.
        """
        results = []
        image_name = self._get_image_name()
        img_mgr = Libvirt_vm_image(self.instance_name, image_name)
        if self._is_defined():
            if not img_mgr.live_image_exists():
                results.append('Instance image for Domain "{0}" does '
                        'not exist'.format(self.instance_name))
        else:
            if not img_mgr.base_image_exists():
                results.append('Base image for Domain "{0}" does not '
                        'exist'.format(self.instance_name))
        return results

    def _check_config_changed(self):
        """
        Check if config exists and copy it to the live files if it doesn't.
        Otherwise compare them and if they are not the same, undefine the
        domain, then perform a cleanup by deleting the image in the instance
        directory on the managed node, copy the config files.
        """
        success = True
        if not self.conf.conf_live_exists():
            # If instance is defined with no live files, we're in a bad state
            if self._is_defined():
                log('Domain "{0}" exists without live files. Forcefully '
                        'stopping and undefining.'.format(self.instance_name))
                self._force_stop_undefine()
        else:
            if not self.conf.conf_same():
                self._stop()
                self._undefine()
                try:
                    self.conf.cleanup_instance_dir()
                except OSError:
                    success = False
        return success

    def _undefine(self):
        if self._is_defined():
            log('Attempting to undefine the domain "{0}"'.format(
                self.instance_name))
            dom = self._get_domain()
            _stderr = sys.stderr
            _stdout = sys.stdout
            null = open(os.devnull, 'wb')
            sys.stdout = sys.stderr = null
            dom.undefine()
            sys.stderr = _stderr
            sys.stdout = _stdout
        return LITP_LIBVIRT_SUCCESS

    def _force_stop_undefine(self):
        """
        Internal helper for _force_stop_undefine so it can be called
        internally without LSB decoration
        """
        self._force_stop()
        result = self._undefine()
        try:
            self.conf.move_files_to_last_undefined_vm_dir()
            self.conf.cleanup_instance_dir()
        except OSError:
            pass
        return result

    def force_stop_undefine(self):
        """
        Will forcefully shutdown the domain and remove its XML config.
        """
        msg_str = 'Service force-stop-undefine for "{0}"'.format(
            self.instance_name)

        result = self._force_stop_undefine()
        if '6' != self.base_os:
            self.systemd.stop_service(verbose=False)
        if result == LITP_LIBVIRT_SUCCESS:
            echo_success(msg_str)
        else:
            echo_failure(msg_str)
        return result

    def stop_undefine(self, stop_timeout=SERVICE_STOP_TIMEOUT):
        """
        Will shutdown the domain and remove its XML config.
        """
        msg_str = 'Service stop-undefine for "{0}"'.format(
            self.instance_name)
        result = self._stop(stop_timeout=stop_timeout)
        if '6' != self.base_os:
            self.systemd.stop_service(verbose=False)
        self._undefine()
        try:
            self.conf.move_files_to_last_undefined_vm_dir()
            self.conf.cleanup_instance_dir()
        except OSError:
            pass
        if result == LITP_LIBVIRT_SUCCESS:
            echo_success(msg_str)
        else:
            echo_failure(msg_str)


class ActionValidator(object):
    """
    This class defines methods, that are used to parse additional arguments.
    """
    ALLOWED_ACTIONS_MAP = {
        'stop': 'stop',
        'start': 'start',
        'status': 'status',
        'restart': 'restart',
        'force-stop': 'force_stop',
        'force-restart': 'force_restart',
        'force-stop-undefine': 'force_stop_undefine',
        'stop-undefine': 'stop_undefine'
    }

    def __init__(self, adaptor):
        self.adaptor = adaptor

    @staticmethod
    def positive_integer(value):
        try:
            result = int(value)
        except ValueError:
            msg = "invalid value: %s" % value
            raise argparse.ArgumentTypeError(msg)
        if result <= 0:
            msg = "invalid value: %s" % value
            raise argparse.ArgumentTypeError(msg)
        return result

    def get_adaptor_method(self, action, options):
        """
        Checks that provided ``action`` is supported one and that the third
        additional argument, for example --timeout, is a valid one. Raises
        error otherwise.

        Returns bounded method of LitpLibVirtAdaptor with keyword arguments.

        ``options`` -- truncated ``sys.argv``
        """
        action = action.lower()
        if action not in self.ALLOWED_ACTIONS_MAP:
            sys.stderr.write(USAGE)
            sys.exit(LITP_LIBVIRT_UNKNOWN_CMD)
        else:
            method_name = self.ALLOWED_ACTIONS_MAP[action]

            kwargs = {}
            if hasattr(self, method_name):
                # calling special parser
                cmd, kwargs = getattr(self, method_name)(
                    action, options=options)
            else:
                # raise error if any unsupported arguments were specified
                if len(options) > 0:
                    sys.stderr.write("Unsupported argument provided.\n")
                    sys.exit(2)
                cmd = getattr(self.adaptor, method_name)
            return cmd, kwargs

    def stop_undefine(self, action, options=None):
        parser = argparse.ArgumentParser(add_help=False, prog=action)
        parser.add_argument(
            '--stop-timeout', help='Time in seconds. Once the '
            '"timeout" time elapses the stop-undefine which calls a '
            'graceful shut down of a VM should call a destroy, '
            'followed by undefining of the VM.', default=SERVICE_STOP_TIMEOUT,
            metavar='positive_integer', type=ActionValidator.positive_integer,
            dest='stop_timeout')
        args = parser.parse_args(options)
        return self.adaptor.stop_undefine, {'stop_timeout': args.stop_timeout}


def _main():
    parser = argparse.ArgumentParser(add_help=False, usage=USAGE)
    parser.add_argument('instance_name', help='VM instance name.')
    parser.add_argument('action', help='VM instance action.')
    args = parser.parse_args(sys.argv[1:3])

    instance_name = args.instance_name
    fn = '/etc/redhat-release'
    with open(fn, 'r') as f:
        redhat_release = f.readlines()
    base_os = redhat_release[0].split('release')[1].split('.')[0].strip(' ')
    adaptor = LitpLibVirtAdaptor(instance_name, base_os)
    validator = ActionValidator(adaptor)

    method, kwargs = validator.get_adaptor_method(args.action, sys.argv[3:])
    if not adaptor.can_read_conf():
        log('Error: cannot read config file: {0}'.format(
            adaptor.conf.conf_file), level='ERROR', echo=True)
        sys.exit(LITP_LIBVIRT_UNKNOWN_CMD)

    retcode = method(**kwargs)
    sys.exit(retcode)


if __name__ == "__main__":    # pragma: no cover
    _main()
