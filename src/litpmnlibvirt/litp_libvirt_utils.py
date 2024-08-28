##############################################################################
# COPYRIGHT Ericsson AB 2014
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

import xml.etree.ElementTree as ET
import json

import itertools
from lxml import etree

import yaml
import sys
import os
import logging.config
import subprocess
import shutil
from hashlib import md5
import datetime
import tempfile
import uuid
import string
import re

from litpmnlibvirt.litp_libvirt_connector import get_handle

LIBVIRT_CONFPATH = "/var/lib/libvirt/instances"
LIBVIRT_CONFFILE = "config.json"
LIBVIRT_BASE_IMGPATH = "/var/lib/libvirt/images"
LIBVIRT_LAST_UNDEFINED_VM_DIRECTORY = 'last_undefined_vm'
LIBVIRT_CAPABILITIES_XPATH = '/capabilities/host/topology/cells/cell'

if not os.environ.get('TESTING_FLAG', None):  # pragma: no cover
    logging.config.fileConfig('/etc/litp_libvirt_logging.conf')
else:
    # Don't try reading logging conf for unit tests
    pass
logger = logging.getLogger("litp_libvirt")

ANSI_MOVE_CURSOR = '\033[60G'
ANSI_FAILURE_COLOR = '\033[1;31m'
ANSI_SUCCESS_COLOR = '\033[1;32m'
ANSI_NO_COLOR = '\033[0m'

SYSTEMCTL_PATH = "/bin/systemctl"


class LitpLibvirtException(Exception):
    pass


def exec_cmd(cmd):
    p = subprocess.Popen(cmd,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         shell=True)
    out, err = p.communicate()
    return (p.returncode, out.strip(), err.strip())


def echo_success(msg='', state='OK'):
    """
    Port of standard RHEL function, echos success
    message with the following format "<msg> [  <state>  ]"
    """
    log_msg = "%s [  %s  ]" % (msg, state)
    log(log_msg)
    if len(msg) > 59:
        msg = msg + '\n'
    formatted_msg = "%s%s[  %s%s%s  ]"\
             % (msg, ANSI_MOVE_CURSOR, ANSI_SUCCESS_COLOR,
                state, ANSI_NO_COLOR)
    if sys.stdout.isatty():
        print formatted_msg
    else:
        print log_msg


def echo_failure(msg='', state='FAILED'):
    """
    Port of standard RHEL function, echos failure
    message with the following format "<msg> [  <state>  ]"
    """
    log_msg = "%s [  %s  ]" % (msg, state)
    log(log_msg, level='ERROR')
    if len(msg) > 59:
        msg = msg + '\n'
    formatted_msg = "%s%s[%s%s%s]"\
            % (msg, ANSI_MOVE_CURSOR, ANSI_FAILURE_COLOR,
               state, ANSI_NO_COLOR)
    if sys.stdout.isatty():
        print formatted_msg
    else:
        print log_msg


def log(message, level='INFO', echo=False):
    """
    Print and log the supplied message
    """
    prefix = ''
    #seperator = ' - '
    #if instance_name is not None:
    #    prefix = prefix + str(instance_name) + seperator

    if echo:
        print str(message)

    if level == 'INFO':
        logger.info(str(prefix) + str(message))
    elif level == 'DEBUG':
        logger.debug(str(prefix) + str(message))
    elif level == 'ERROR':
        logger.error(str(prefix) + str(message))
    else:
        msg = "Invalid logging level:" + str(level) + " message: " \
                      + str(message)
        logger.error(str(prefix) + str(msg))


def load_file_containing_yaml(path):
    """
    Reads contents of file by provided ``path`` and returns
    deserialized object.
    """
    try:
        with open(path, 'r') as fd:
            result = yaml.safe_load(fd)
    except OSError as ex:
        raise LitpLibvirtException('Failed to read {0}: {1}'.format(path,
            str(ex)))
    except Exception as ex:
        raise LitpLibvirtException('Failed to parse user-data file:'
                                    '{0}'.format(str(ex)))
    return result


class Libvirt_capabilities(object):
    def __init__(self):
        super(Libvirt_capabilities, self).__init__()

    @staticmethod
    def __compress_list(number_list):
        def group(int_list):
            for _, b in itertools.groupby(enumerate(int_list.split(',')),
                                          lambda (x, y): int(y) - int(x)):
                b = list(b)
                yield b[0][1], b[-1][1]

        ranges = []
        for ngroup in list(group(number_list)):
            ranges.append('-'.join(ngroup))

        return ','.join(ranges)

    @staticmethod
    def get_cpu_capabilities():
        conn = get_handle()
        caps = conn.getCapabilities()
        root = etree.fromstring(caps)

        mappings = {}
        for cell in root.xpath(LIBVIRT_CAPABILITIES_XPATH):
            cellid = cell.get('id')
            cpuset = []
            for cpu in cell.xpath('.//cpu'):
                cpuset.append(cpu.get('id'))
            cpuset = ','.join(cpuset)
            mappings[cellid] = Libvirt_capabilities.__compress_list(cpuset)
            log('Compressed cell capabilities from {0} to {1}'.format(
                    cpuset, mappings[cellid]))

        return mappings


class Libvirt_conf(object):
    def __init__(self, name):
        self.name = name
        self.instance_dir = LIBVIRT_CONFPATH + "/" + name
        self.conf_file = LIBVIRT_CONFPATH + "/" + name + "/" + LIBVIRT_CONFFILE
        self.conf = None
        self.config_files = (
            (self.conf_file, self.conf_file + '.live'),
            ('/'.join([LIBVIRT_CONFPATH, name, 'user-data']),
             '/'.join([LIBVIRT_CONFPATH, name, 'user-data.live'])),
            ('/'.join([LIBVIRT_CONFPATH, name, 'meta-data']),
             '/'.join([LIBVIRT_CONFPATH, name, 'meta-data.live'])),
            ('/'.join([LIBVIRT_CONFPATH, name, 'network-config']),
             '/'.join([LIBVIRT_CONFPATH, name, 'network-config.live']))
        )

    def read_conf_data(self):
        try:
            if self.conf == None:
                with open(self.conf_file, "r") as config_file:
                    self.conf = json.load(config_file)
        except (IOError, ValueError) as ex:
            raise LitpLibvirtException('Problem opening config '
                                       'for Domain "{0}": '
                                       '{1}'.format(self.name,
                                                    str(ex)))

    def save_conf_data(self):
        try:
            json.dump(self.conf, open(self.conf_file, "w"))
        except IOError as ex:
            raise LitpLibvirtException('Problem writing to config '
                                       'for Domain "{0}": '
                                       '{1}'.format(self.name,
                                                    str(ex)))

    def _get_conf_data_path(self, live=False):
        return self.conf_file if not live else self.conf_file + '.live'

    def conf_live_exists(self):
        live_conf = self._get_conf_data_path(True)
        return os.path.exists(live_conf)

    def get_live_conf(self):
        """
        Returns the json live config file.
        When it's called the function we know that json config exist, this
        means self.conf_live_exists() returns true
        """
        try:
            with open(self._get_conf_data_path(True), "r") as conf_file:
                return json.load(conf_file)
        except (IOError, ValueError) as ex:
            raise LitpLibvirtException(
                'The file "{0}" for the domain "{1}" cannot be accessed: {2}'
                ''.format(self._get_conf_data_path(True), self.name, str(ex)))

    def conf_same(self):
        checksums = []
        try:
            for i in self.config_files:
                with open(i[0]) as cdp:
                    checksum = md5(cdp.read()).hexdigest()
                with open(i[1]) as cdpl:
                    live_checksum = md5(cdpl.read()).hexdigest()
                checksums.append(checksum == live_checksum)
        except IOError:
            log('Error while checking the checksum of the configuration.')
            # Say it's different anyway. We're going to attempt copying
            return False
        return all(checksums)

    def conf_copy(self):
        try:
            for i in self.config_files:
                shutil.copy2(i[0], i[1])
        except IOError:
            log('Error while copying the configuration.')
            return False
        return True

    def get_conf_data(self):
        self.read_conf_data()
        return self.conf

    def get_vm_data(self):
        self.read_conf_data()
        return self.conf["vm_data"]

    def get_adaptor_data(self):
        self.read_conf_data()
        return self.conf["adaptor_data"]

    def cleanup_instance_dir(self):
        """
        Removes all files in VM instance directory, excluding
        ``LIBVIRT_LAST_UNDEFINED_VM_DIRECTORY``, user-data, meta-data,
        network-config  and config.json.
        """
        for f in os.listdir(self.instance_dir):
            if f in [LIBVIRT_CONFFILE, "user-data", "meta-data",
                     "network-config", LIBVIRT_LAST_UNDEFINED_VM_DIRECTORY]:
                continue
            fpath = os.path.join(self.instance_dir, f)
            if os.path.isdir(fpath):
                log('Removing directory "{0}".'.format(fpath), level="DEBUG")
                try:
                    shutil.rmtree(fpath)
                except OSError as ex:
                    log('Failed to delete directory "{0}": {1}.'.format(
                        fpath, str(ex)))
                    raise ex
            else:
                try:
                    log('Removing file "{0}".'.format(fpath), level="DEBUG")
                    os.unlink(fpath)
                except OSError as ex:
                    log('Failed to delete file "{0}": {1}.'.format(fpath,
                                                                    str(ex)))
                    raise ex

    def _create_dir(self, path):
        try:
            os.mkdir(path)
        except OSError as ex:
            # it must be permission denied
            log('Error while storing virtual machine: {0}'.format(str(ex)))
            raise ex

    def move_files_to_last_undefined_vm_dir(self):
        """
        Moves all 4 .live files and the qcow2 image to
        empty ``LIBVIRT_LAST_UNDEFINED_VM_DIRECTORY`` directory.
        """
        backup_dir = os.path.join(self.instance_dir,
            LIBVIRT_LAST_UNDEFINED_VM_DIRECTORY)
        try:
            image = self.get_vm_data()['image']
        except (KeyError, LitpLibvirtException) as ex:
            raise LitpLibvirtException('Problem reading config '
                                       'for Domain "{0}: '
                                       '{1}'.format(self.name,
                                                    str(ex)))

        image_file = os.path.join(self.instance_dir, image)
        if not os.path.exists(image_file):
            log('No image found in "{0}" for {1}. Nothing to save.'.format(
                self.instance_dir, self.name))
            return

        if not os.path.isdir(backup_dir):
            self._create_dir(backup_dir)
        else:
            log('Removing directory "{0}".'.format(backup_dir), level="DEBUG")
            try:
                shutil.rmtree(backup_dir)
            except OSError as ex:
                log('Failed to delete directory "{0}": {1}.'.format(
                    backup_dir, str(ex)))
                raise ex
            else:
                self._create_dir(backup_dir)

        current_time = datetime.datetime.now()
        for fpath in [image_file] + [i[1] for i in self.config_files]:
            fn = os.path.basename(fpath)
            fn = "%s-%s" % (fn, current_time.strftime("%Y%m%d%H%M%S"))
            tpath = os.path.join(backup_dir, fn)
            try:
                log('Moving file "{0}" to {1}.'.format(
                    fpath, backup_dir), level="DEBUG")
                os.rename(fpath, tpath)
            except OSError as ex:
                log('Failed to move file "{0}": {1}.'.format(fpath, str(ex)))


class Libvirt_systemd(object):

    def __init__(self, name):
        self.name = name

    def is_service_inactive(self):
        _, out, _ = exec_cmd("{0} is-active {1}".format(SYSTEMCTL_PATH,
                                                         self.name))
        log('Service "{0}" is in state {1}'.format(self.name, out.strip()))
        return out.strip() == 'unknown' or out.strip() == 'activating'

    def stop_service(self, verbose=True):
        log('Attempting to stop service "{0}" with systemctl'.format(
            self.name))
        rc, _, _ = exec_cmd("{0} stop {1}".format(SYSTEMCTL_PATH,
                                                  self.name))
        if verbose:
            msg_str = 'Service stop for "{0}"'.format(self.name)
            if rc == 0:
                echo_success(msg_str)
            else:
                echo_failure(msg_str)
        return rc

    def start_service(self, verbose=True):
        log('Attempting to start service "{0}" with systemctl'.format(
            self.name))
        rc, _, _ = exec_cmd("{0} start {1}".format(SYSTEMCTL_PATH,
                                                   self.name))
        if verbose:
            msg_str = 'Service start for "{0}"'.format(self.name)
            if rc == 0:
                echo_success(msg_str)
            else:
                echo_failure(msg_str)
        return rc

    def restart_service(self, verbose=True):
        log('Attempting to restart service "{0}" with systemctl'.format(
            self.name))
        rc, _, _ = exec_cmd("{0} restart {1}".format(SYSTEMCTL_PATH,
                                                   self.name))
        if verbose:
            msg_str = 'Service restart for "{0}"'.format(self.name)
            if rc == 0:
                echo_success(msg_str)
            else:
                echo_failure(msg_str)
        return rc


class Libvirt_cloud_init(object):
    def __init__(self, name, adaptor_data):
        self.name = name
        self._location = os.path.join(LIBVIRT_CONFPATH, self.name)
        self._iso = os.path.join(self._location, "cloud_init.iso")
        self._adaptor_data = adaptor_data
        self._userdata_path = os.path.join(self._location, 'user-data')

    def _get_updated_disk_mounts(self, disk_mounts):
        updated_disk_mounts = []
        for bd_path, mount_point in disk_mounts:
            try:
                _, bd_uuid, _ = exec_cmd("/bin/lsblk -nf -o UUID %s" % bd_path)
            except Exception as ex:
                raise LitpLibvirtException('Problem executing lsblk: '
                                       '{0}'.format(str(ex)))
            try:
                uuid.UUID(bd_uuid)
            except (ValueError, TypeError) as ex:
                raise LitpLibvirtException('Invalid UUID {0}: {1}'.format(
                    bd_uuid, str(ex)))

            updated_disk_mounts.append(['UUID=%s' % bd_uuid, mount_point,
                'ext4', 'defaults', '0', '0'])
        return updated_disk_mounts

    def _get_updated_userdata_path(self):
        """
        Returns path to ``user-data`` file with updated device paths, that are
        subject to mounting inside virtual machine.
        """
        user_data = load_file_containing_yaml(self._userdata_path)
        disk_mounts = self._adaptor_data.get('disk_mounts', [])
        path_to_userdata = tempfile.mkdtemp(prefix='user-data')
        path_to_userdata = os.path.join(path_to_userdata, 'user-data')

        mounts = (user_data.get('mounts', []) +
                  self._get_updated_disk_mounts(disk_mounts))
        user_data['mounts'] = mounts

        try:
            with open(path_to_userdata, 'w') as tmp_fd:
                # yaml strips off comments, so we have to add cloud-init
                # header manually
                tmp_fd.write('#cloud-config\n' + yaml.safe_dump(user_data,
                    default_flow_style=False))
        except OSError as ex:
            raise LitpLibvirtException('Failed to write temporary file {0}:'
                                       '{0}'.format(str(ex)))
        return path_to_userdata

    def create_cloud_init_iso(self):
        userdata_path = self._userdata_path
        if self._adaptor_data.get('disk_mounts'):
            userdata_path = self._get_updated_userdata_path()

        networkconfig_path = os.path.join(self._location, 'network-config')
        if not os.path.isfile(networkconfig_path):
            networkconfig_path = ''

        cmd = ("genisoimage -output {0}/cloud_init.iso -volid cidata -joliet"
               " -rock {1} {0}/meta-data {2}"
                  .format(self._location, userdata_path, networkconfig_path))

        try:
            exec_cmd(cmd)
        except Exception as ex:
            raise LitpLibvirtException('Problem executing genisoimage: '
                                       '{0}'.format(str(ex)))
        finally:
            if userdata_path.startswith(tempfile.gettempdir()):
                try:
                    shutil.rmtree(os.path.dirname(userdata_path))
                except OSError as ex:
                    raise LitpLibvirtException('Problem removing temporary '
                        'user-data file: {0}'.format(str(ex)))


class Libvirt_vm_image(object):
    def __init__(self, name, image_name):
        self.name = name
        self.inst_loc = os.path.join(LIBVIRT_CONFPATH, name)
        self.image_name = image_name

    def get_base_img_path(self):
        base_image_loc = os.path.join(LIBVIRT_BASE_IMGPATH, self.image_name)
        return base_image_loc

    def get_live_img_path(self):
        return os.path.join(self.inst_loc, self.image_name)

    def copy_image(self):
        shutil.copy(self.get_base_img_path(), self.get_live_img_path())

    def base_image_exists(self):
        image = self.get_base_img_path()
        return os.path.isfile(image)

    def live_image_exists(self):
        return os.path.isfile(self.get_live_img_path())


class Libvirt_vm_xml(object):
    def __init__(self, name):
        self.name = name

    def _add_image_device(self, devices, image):
        disk_img = Libvirt_vm_image(self.name, image)
        disk = ET.SubElement(devices, "disk",
                             {'type': 'file',
                              'device': 'disk'})
        ET.SubElement(disk, "driver",
                          {'name': 'qemu',
                           'type': 'qcow2',
                           'cache': 'none'})
        live_img = disk_img.get_live_img_path()
        ET.SubElement(disk, "source",
                          {'file': live_img})
        ET.SubElement(disk, "target",
                          {'dev': 'vda',
                           'bus': 'virtio'})
        ET.SubElement(disk, "alias",
                          {'name': 'virtio_disk0'})

    @staticmethod
    def _find_free_device_name(devices_node):
        """
        Goes through ``disk`` nodes in devices section of libvirt XML
        and returns block device name, that is not taken.
        """
        letters = list(string.lowercase)
        for d in devices_node.findall('disk'):
            target = d.find('target')
            if target is not None:
                name = target.attrib.get('dev')
                if name.startswith('vd') and name[2] in letters:
                    letters.remove(name[2])
        return 'vd%s' % letters[0]

    def _add_disk_device(self, devices_node, device_path):
        disk = ET.SubElement(devices_node, "disk",
                             {'type': 'block',
                              'device': 'disk'})
        ET.SubElement(disk, "driver",
                          {'name': 'qemu',
                           'type': 'raw',
                           'cache': 'none'})
        ET.SubElement(disk, "source",
                          {'dev': device_path})
        ET.SubElement(disk, "target",
                          {'dev': self._find_free_device_name(devices_node),
                           'bus': 'virtio'})

    def _add_usb_device(self, devices):
        controller = ET.SubElement(devices, "controller",
                                   {'type': 'usb',
                                    'index': '0'})
        ET.SubElement(controller, "alias",
                          {'name': 'usb0'})

    def _add_serial_device(self, devices):
        serial = ET.SubElement(devices, "serial",
                                   {'type': 'pty'})
        ET.SubElement(serial, "source",
                          {'path': '/dev/pts/3'})
        ET.SubElement(serial, "target",
                          {'port': '0'})
        ET.SubElement(serial, "alias",
                          {'name': 'serial0'})

    def _add_console_device(self, devices):
        console = ET.SubElement(devices, "console",
                                   {'type': 'pty',
                                    'tty': '/dev/pts/3'})
        ET.SubElement(console, "source",
                          {'path': '/dev/pts/3'})
        ET.SubElement(console, "target",
                          {'type': 'serial',
                           'port': '0'})
        ET.SubElement(console, "alias",
                          {'name': 'serial0'})

    def _add_input_device(self, devices):
        input_dev = ET.SubElement(devices, "input",
                               {'type': 'tablet',
                                'bus': 'usb'})
        ET.SubElement(input_dev, "alias",
                          {'name': 'input00'})
        ET.SubElement(devices, "input",
                          {'type': 'mouse',
                           'bus': 'ps2'})

    def _add_graphics_device(self, devices):
        graphics = ET.SubElement(devices, "graphics",
                               {'type': 'vnc',
                                'port': '5902',
                                'autoport': 'yes',
                                'listen': '127.0.0.1'})
        ET.SubElement(graphics, "listen",
                          {'type': 'address',
                           'address': '127.0.0.1'})

    def _add_video_device(self, devices):
        video = ET.SubElement(devices, "video")
        ET.SubElement(video, "model",
                          {'type': 'cirrus',
                           'vram': '9216',
                           'heads': '1'})
        ET.SubElement(video, "alias",
                          {'name': 'video0'})

    def _add_memballoon_device(self, devices):
        mem = ET.SubElement(devices, "memballoon",
                            {'model': 'virtio'})
        ET.SubElement(mem, "alias",
                          {'name': 'balloon0'})

    def _add_rng_device(self, devices):
        rng = ET.SubElement(devices, "rng",
                             {'model': 'virtio'})
        ET.SubElement(rng, "rate",
                          {'bytes': '1234',
                           'period': '2000'})
        backend = ET.SubElement(rng, "backend",
                          {'model': 'random'})
        backend.text = '/dev/random'

    def _add_net_interface_device(self, devices, shared_dev, mac_address):
        # Generalise for multiple net interfaces
        iface = ET.SubElement(devices, "interface",
                              {'type': 'bridge'})
        ET.SubElement(iface, "source",
                          {'bridge': shared_dev})

        ET.SubElement(iface, "model",
                          {'type': 'virtio'})

        if mac_address:
            ET.SubElement(iface, "mac",
                              {'address': mac_address})

    def _add_cdrom_device(self, devices, src_file):
        cd = ET.SubElement(devices, "disk",
                           {'type': 'file',
                            'device': 'cdrom'})
        ET.SubElement(cd, "driver",
                          {'name': 'qemu',
                           'type': 'raw'})
        ET.SubElement(cd, "source",
                          {'file': src_file})
        ET.SubElement(cd, "target",
                          {'dev': 'hda',
                           'bus': 'ide'})
        ET.SubElement(cd, "readonly")
        ET.SubElement(cd, "alias",
                          {'name': 'ide0-0-0'})

    def _define_domain(self, name, ram_size, cpus, image,
                       nics, block_devices, cpuset=None, cpunodebind=None):
        allowed_units = {'M': 'MiB'}
        ram_units = ram_size[-1]
        ram_val = ram_size[:-1]
        if ram_units not in allowed_units.keys():
            raise LitpLibvirtException('Ram size {0} has incorrect '
                                       'format'.format(ram_size))

        domain = ET.Element("domain", {"type": "kvm"})
        machine_name = ET.SubElement(domain, "name")
        machine_name.text = name
        memory = ET.SubElement(domain, "memory",
                               {"unit": allowed_units[ram_units]})
        memory.text = ram_val

        virt_what_command = "/usr/sbin/virt-what"
        is_bare_metal = exec_cmd(virt_what_command)[1] == ''
        # check if it is virtual or physical machine
        if is_bare_metal:
            ET.SubElement(domain, "cpu",
                          {"mode": "host-passthrough"})

        cpus_attrs = {"placement": "static"}
        if cpuset:
            cpus_attrs["cpuset"] = cpuset
        elif cpunodebind:
            available_cpusets = Libvirt_capabilities.get_cpu_capabilities()
            allocated = []
            for nodeid in cpunodebind.split(','):
                if nodeid in available_cpusets:
                    allocated.append(available_cpusets[nodeid])
            if allocated:
                cpus_attrs["cpuset"] = ','.join(allocated)
            else:
                log('{0}: cpunodebind value of "{1}" does not resolve '
                    'to any known numa nodes!'.format(name, cpunodebind),
                    level='INFO')

        cpu = ET.SubElement(domain, "vcpu", cpus_attrs)
        cpu.text = cpus

        op_sys = ET.SubElement(domain, "os")
        arch = ET.SubElement(op_sys, "type",
                             {'arch': 'x86_64',
                              'machine': 'rhel6.6.0'})
        arch.text = "hvm"
        ET.SubElement(op_sys, "boot", {"dev": "hd"})
        features = ET.SubElement(domain, "features")
        ET.SubElement(features, "acpi")
        ET.SubElement(features, "apic")
        ET.SubElement(features, "pae")
        ET.SubElement(domain, "clock",
                          {'offset': 'utc'})
        pwr_off = ET.SubElement(domain, "on_poweroff")
        pwr_off.text = "destroy"
        reboot = ET.SubElement(domain, "reboot")
        reboot.text = "restart"
        on_crash = ET.SubElement(domain, "on_crash")
        on_crash.text = "restart"

        devices = ET.SubElement(domain, "devices")
        emu = ET.SubElement(devices, "emulator")
        emu.text = "/usr/libexec/qemu-kvm"
        self._add_image_device(devices, image)
        for block_device_path in block_devices:
            self._add_disk_device(devices, block_device_path)
        self._add_usb_device(devices)

        for dev in sorted(nics, key=self.network_sort):
            nic = nics[dev]
            nic_mac_address = None
            if "mac_address" in nic:
                nic_mac_address = nic["mac_address"]
            self._add_net_interface_device(devices,
                                           nic["host_device"],
                                           nic_mac_address)

        self._add_serial_device(devices)
        self._add_console_device(devices)
        self._add_input_device(devices)
        self._add_graphics_device(devices)
        self._add_video_device(devices)
        cloud_init_iso = LIBVIRT_CONFPATH + "/" + name + "/cloud_init.iso"
        self._add_cdrom_device(devices, cloud_init_iso)
        if is_bare_metal:
            self._add_rng_device(devices)
        #self._add_seclabel(domain)

        return domain

    def network_sort(self, key):
        convert = lambda text: int(text) if text.isdigit() else text.lower()
        return  [convert(c) for c in re.split('([0-9]+)', key)]

    def _add_seclabel(self, domain):
        seclabel = ET.SubElement(domain, "seclabel",
                                 {'type': 'dynamic',
                                  'model': 'selinux',
                                  'relabel': 'yes'})
        label = ET.SubElement(seclabel, "label")
        label.text = "unconfined_u:system_r:svirt_t:s0:c805,c993"
        imagelabel = ET.SubElement(seclabel, "imagelabel")
        imagelabel.text = "unconfined_u:object_r:svirt_image_t:s0:c805,c993"

    def build_machine_xml(self):
        try:
            conf = Libvirt_conf(self.name)
            vm_data = conf.get_vm_data()
            adaptor_data = conf.get_adaptor_data()
            num_cpus = vm_data["cpu"]
            cpuset = vm_data.get("cpuset", None)
            cpunodebind = vm_data.get("cpunodebind", None)
            ram_size = vm_data["ram"]
            image = vm_data["image"]
            nics = vm_data["interfaces"]
            block_devices = [d[0] for d in adaptor_data.get('disk_mounts', [])]
        except (KeyError, LitpLibvirtException) as ex:
            raise LitpLibvirtException('Problem reading config '
                                       'for Domain "{0}: '
                                       '{1}'.format(self.name,
                                                    str(ex)))
        domain = self._define_domain(self.name, ram_size, num_cpus,
                                     image, nics, block_devices,
                                     cpuset=cpuset, cpunodebind=cpunodebind)
        return ET.tostring(domain, encoding='utf-8')
