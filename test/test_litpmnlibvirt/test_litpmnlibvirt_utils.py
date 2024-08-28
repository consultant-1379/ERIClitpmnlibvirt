##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

import os
import unittest
from StringIO import StringIO

import mock
from mock import MagicMock

os.environ["TESTING_FLAG"] = "1"
from litpmnlibvirt.litp_libvirt_utils import (Libvirt_vm_xml,
                                              Libvirt_vm_image,
                                              Libvirt_conf,
                                              Libvirt_cloud_init,
                                              LitpLibvirtException,
                                              log,
                                              load_file_containing_yaml,
                                              Libvirt_capabilities)

import xml.etree.ElementTree as ET

CONFIG = {"vm_data": {"image": "path/image_name",
                      "ram": "1024",
                      "cpu": "2",
                      "interfaces": {"eth0": {'host_device': 'br0'},
                                     "eth1": {'host_device': 'br1'}}},
          "adaptor_data": {'disk_mounts': []},
          }

USER_DATA = """#cloud-config
bootcmd:
- - cloud-init-per
  - instance
  - hostname
  - sh
  - -c
  - hostname ms-fmmed2
- - cloud-init-per
  - instance
  - alias0
  - sh
  - -c
  - echo 10.10.11.100 ms1 >> /etc/hosts
runcmd:
- /sbin/service rsyslog restart
timezone: Europe/Dublin
yum_repos:
  3pp:
    baseurl: http://ms1/3pp
    enabled: true
    gpgcheck: false
    name: 3pp"""


class TestLibvirtLogging(unittest.TestCase):
    def setUp(self):
        pass

    @mock.patch('litpmnlibvirt.litp_libvirt_utils.logger')
    def test_log(self, mock_logger):
        mock_logger.info = mock.Mock()
        mock_logger.debug = mock.Mock()
        mock_logger.error = mock.Mock()
        log('Message info')
        log('Message debug', level='DEBUG')
        log('Message error', level="ERROR")
        log('Message invalid', level="INVALID")
        mock_logger.info.assert_has_calls([mock.call('Message info')])
        mock_logger.debug.assert_has_calls([mock.call('Message debug')])
        mock_logger.error.assert_has_calls([mock.call('Message error'),
                                            mock.call('Invalid logging level:'
                                                      'INVALID message: '
                                                      'Message invalid')])

    @mock.patch('sys.stdout')
    @mock.patch('litpmnlibvirt.litp_libvirt_utils.logger')
    def test_log_echos(self, mock_logger, stdout):
        log('test with echo', echo=True)
        stdout.write.assert_any_call('test with echo')


class TestLibvirtConf(unittest.TestCase):
    def setUp(self):
        name = "vm"
        self.conf = Libvirt_conf(name)

    @mock.patch('litpmnlibvirt.litp_libvirt_utils.json')
    def test_read_conf_data(self, mock_json):
        def raise_ex(file_contents):
            raise (ValueError('No JSON object could be decoded'))

        mock_json.load = mock.Mock(side_effect=raise_ex)
        with mock.patch('__builtin__.open', mock.mock_open(read_data=''),
                        create=True) as m:
            self.assertRaises(LitpLibvirtException,
                              self.conf.read_conf_data)
            mock_json.reset_mock()
            mock_json.load = mock.Mock(return_value={"key": "value"})
            self.conf.read_conf_data()
            self.assertEqual(self.conf.conf, {"key": "value"})

    @mock.patch('litpmnlibvirt.litp_libvirt_utils.json')
    def test_get_live_conf(self, mock_json):
        def raise_ex(file_contents):
            raise (ValueError('No JSON object could be decoded'))

        mock_json.load = mock.Mock(side_effect=raise_ex)
        with mock.patch('__builtin__.open', mock.mock_open(read_data=''),
                        create=True) as m:
            self.assertRaises(LitpLibvirtException,
                              self.conf.get_live_conf)
            mock_json.reset_mock()
            mock_json.load = mock.Mock(return_value={"key": "value"})
            self.assertEqual(self.conf.get_live_conf(), {"key": "value"})

    @mock.patch('litpmnlibvirt.litp_libvirt_utils.json')
    @mock.patch('__builtin__.open')
    def test_save_conf_data(self, mock_open, mock_json):
        self.conf.conf = CONFIG

        def raise_ex(file_contents, filep):
            raise (IOError('No JSON object could be decoded'))

        mock_json.dump = mock.Mock(side_effect=raise_ex)
        self.assertRaises(LitpLibvirtException,
                          self.conf.save_conf_data)
        mock_json.reset_mock()
        mock_json.dump = mock.Mock()
        self.conf.save_conf_data()
        expected = mock.call.dump(CONFIG, mock_open())
        mock_json.assert_has_calls([expected])

    @mock.patch('litpmnlibvirt.litp_libvirt_utils.Libvirt_conf.read_conf_data')
    def test_get_conf_data(self, mock_read):
        def read_conf():
            self.conf.conf = CONFIG

        mock_read.side_effect = read_conf
        conf = self.conf.get_conf_data()
        self.assertEqual(conf, CONFIG)

    @mock.patch('litpmnlibvirt.litp_libvirt_utils.Libvirt_conf.read_conf_data')
    def test_get_vm_data(self, mock_read):
        def read_conf():
            self.conf.conf = CONFIG

        mock_read.side_effect = read_conf
        conf = self.conf.get_vm_data()
        self.assertEqual(conf, CONFIG["vm_data"])

    @mock.patch('litpmnlibvirt.litp_libvirt_utils.Libvirt_conf.read_conf_data')
    def test_get_adaptor_data(self, mock_read):
        def read_conf():
            self.conf.conf = CONFIG

        mock_read.side_effect = read_conf
        conf = self.conf.get_adaptor_data()
        self.assertEqual(conf, CONFIG["adaptor_data"])

    def test_get_conf_data_path(self):
        path = self.conf._get_conf_data_path()
        self.assertEqual("/var/lib/libvirt/instances/vm/config.json", path)

        live_path = self.conf._get_conf_data_path(True)
        self.assertEqual("/var/lib/libvirt/instances/vm/config.json.live",
                         live_path)

    @mock.patch('os.path.exists')
    def test_conf_live_exists(self, _exists):
        _exists.return_value = True
        self.assertTrue(self.conf.conf_live_exists())

    @mock.patch('litpmnlibvirt.litp_libvirt_utils.md5')
    def test_conf_same_false(self, _md5):
        # There are 8 files to compare
        side_effect = range(8)
        se_mock = mock.MagicMock(side_effect=side_effect)
        _md5.return_value.hexdigest = se_mock
        with mock.patch('__builtin__.open', mock.mock_open(read_data=''),
                        create=True) as m:
            self.assertFalse(self.conf.conf_same())

    @mock.patch('litpmnlibvirt.litp_libvirt_utils.md5')
    def test_conf_same_true(self, _md5):
        _md5.return_value.hexdigest.return_value = ''
        with mock.patch('__builtin__.open', mock.mock_open(read_data=''),
                        create=True) as m:
            result = self.conf.conf_same()
            self.assertTrue(result)

    @mock.patch('shutil.copy2')
    def test_conf_copy(self, _copy2):
        r = self.conf.conf_copy()
        self.assertTrue(r)

    @mock.patch('os.listdir')
    @mock.patch('os.unlink')
    @mock.patch('shutil.rmtree')
    @mock.patch('os.path.isdir')
    def test_cleanup_instance_dir_success(self, mockisdir, mockrmtree,
                                          mockunlink, mocklistdir):
        mocklistdir.return_value = ['meta-data', 'user-data', 'config.json',
                                    'network-config', 'cloud_init.iso']
        mockisdir.return_value = False
        self.conf.cleanup_instance_dir()
        mockunlink.assert_has_calls(
                [mock.call('/var/lib/libvirt/instances/vm/cloud_init.iso')])

        mocklistdir.return_value = ['test-directory']
        mockisdir.return_value = True
        self.conf.cleanup_instance_dir()
        mockrmtree.assert_has_calls(
                [mock.call('/var/lib/libvirt/instances/vm/test-directory')])

    @mock.patch('os.listdir')
    @mock.patch('os.unlink')
    def test_cleanup_instance_dir_fail(self, mockunlink, mocklistdir):
        mocklistdir.return_value = ['meta-data', 'user-data', 'config.json',
                                    'network-config', 'image.live', 'image.qcow2']
        mockunlink.side_effect = OSError

        self.assertRaises(OSError, self.conf.cleanup_instance_dir)

    @mock.patch('os.rename')
    @mock.patch('datetime.datetime')
    @mock.patch('os.path.isdir')
    @mock.patch('os.mkdir')
    @mock.patch('shutil.rmtree')
    @mock.patch('os.path.exists')
    def test_move_files(self, mockexists, mockrmtree,
                        mockmkdir, mockisdir, mockdatetime, mockrename):
        mockexists.return_value = True
        mockisdir.return_value = True
        strftime = mock.Mock()
        strftime.return_value = 'test'
        mocknow = mock.Mock()
        mocknow.strftime = strftime
        mockdatetime.now.return_value = mocknow

        self.conf.get_vm_data = mock.Mock()
        self.conf.get_vm_data.return_value = {'image': 'image.qcow2'}
        self.conf.move_files_to_last_undefined_vm_dir()

        self.assertEqual(mockrename.call_args_list, [
            mock.call('/var/lib/libvirt/instances/vm/image.qcow2',
                      '/var/lib/libvirt/instances/vm/last_undefined_vm/image.qcow2-test'),
            mock.call('/var/lib/libvirt/instances/vm/config.json.live',
                      '/var/lib/libvirt/instances/vm/last_undefined_vm/config.json.live-test'),
            mock.call('/var/lib/libvirt/instances/vm/user-data.live',
                      '/var/lib/libvirt/instances/vm/last_undefined_vm/user-data.live-test'),
            mock.call('/var/lib/libvirt/instances/vm/meta-data.live',
                      '/var/lib/libvirt/instances/vm/last_undefined_vm/meta-data.live-test'),
            mock.call('/var/lib/libvirt/instances/vm/network-config.live',
                      '/var/lib/libvirt/instances/vm/last_undefined_vm/network-config.live-test'),
        ])

    @mock.patch('litpmnlibvirt.litp_libvirt_utils.log')
    @mock.patch('os.rename')
    @mock.patch('datetime.datetime')
    @mock.patch('os.path.exists')
    @mock.patch('shutil.rmtree')
    def test_move_files_fails(self, mockrmtree, mockexists, mockdatetime,
                              mockrename, mocklog):
        # check if move_files_to_last_undefined_vm_dir not called
        # when ther's nothing to move
        mockexists.return_value = False

        self.conf.get_vm_data = mock.Mock()
        self.conf.get_vm_data.return_value = {'image': 'image.qcow2'}

        self.conf.move_files_to_last_undefined_vm_dir()
        mocklog.assert_has_calls([mock.call(
                'No image found in "{0}" for {1}. Nothing to save.'.format(
                        self.conf.instance_dir, self.conf.name))])
        self.assertEqual(mockrmtree.call_args_list, [])
        self.assertEqual(mockrename.call_args_list, [])


class TestLibvirtCloudInit(unittest.TestCase):
    def setUp(self):
        self.name = "vm"

    @mock.patch('yaml.safe_load')
    @mock.patch('__builtin__.open')
    def test_init(self, mock_open, mock_yaml_load):
        cloud = Libvirt_cloud_init(self.name, {})
        self.assertEqual(cloud.name, "vm")
        self.assertEqual(cloud._location, "/var/lib/libvirt/instances/vm")
        self.assertEqual(cloud._iso,
                         "/var/lib/libvirt/instances/vm/cloud_init.iso")

    @mock.patch('litpmnlibvirt.litp_libvirt_utils.exec_cmd')
    @mock.patch('yaml.safe_load')
    @mock.patch('__builtin__.open')
    @mock.patch('os.unlink')
    def test_create_cloud_init_iso(self, mock_unlink, mock_open,
                                   mock_yaml_load, mock_exec):
        cloud = Libvirt_cloud_init(self.name, {'disk_mounts': []})

        def raise_ex(file_contents):
            raise (ValueError('No JSON object could be decoded'))

        infile = mock.MagicMock()
        outfile = mock.MagicMock()
        mock_open.__enter__.side_effect = [infile, outfile]
        mock_yaml_load.return_value = {}
        self.assertEqual('/var/lib/libvirt/instances/vm/cloud_init.iso',
                         cloud._iso)
        cloud._get_updated_userdata_path = mock.Mock(
                return_value=cloud._userdata_path)
        cloud.create_cloud_init_iso()
        self.assertEqual("/".join(['/var/lib/libvirt/instances', cloud.name,
                                   'cloud_init.iso']),
                         cloud._iso)
        expected = mock.call('genisoimage -output '
                             '/var/lib/libvirt/instances/vm/cloud_init.iso'
                             ' -volid cidata -joliet -rock'
                             ' /var/lib/libvirt/instances/vm/user-data'
                             ' /var/lib/libvirt/instances/vm/meta-data'
                             ' ')
    
        mock_exec.assert_has_calls([expected])
        mock_exec.reset_mock()
        mock_exec.side_effect = raise_ex
        self.assertRaises(LitpLibvirtException,
                          cloud.create_cloud_init_iso)

    @mock.patch('__builtin__.open')
    def test_load_file_containing_yaml(self, mock_open):
        mock_open.return_value = mock.MagicMock(spec=file)
        mock_open.return_value.__enter__.return_value = StringIO(
                "#cloud-config\nmounts:\n- - UUID=68851d12-5a84-456a-a0f3-4befbc62c949\n  - /mnt\n  - ext4\n  - defaults\n  - '0'\n  - '0'\n"
        )
        result = load_file_containing_yaml('/path/to/user-data')
        mock_open.assert_called_once_with('/path/to/user-data', 'r')
        self.assertEqual(
                {'mounts': [
                    ['UUID=68851d12-5a84-456a-a0f3-4befbc62c949', '/mnt',
                     'ext4', 'defaults', '0', '0']]},
                result,
        )

    @mock.patch('litpmnlibvirt.litp_libvirt_utils.exec_cmd')
    @mock.patch('__builtin__.open')
    @mock.patch('tempfile.mkdtemp')
    @mock.patch('os.unlink')
    def test_get_updated_userdata_path(self, mock_unlink,
                                       mock_mktemp, mock_open, mock_exec):
        mock_mktemp.return_value = "/tmp_dir"

        mock_open.return_value = mock.MagicMock(spec=file)
        mock_open.return_value.__enter__.return_value = StringIO(USER_DATA)
        file_handle = mock_open.return_value.__enter__.return_value

        cloud = Libvirt_cloud_init(self.name, {"internal_status_check":
                                                   {"active": "off",
                                                    "ip_address": ""},
                                               "disk_mounts": [
                                                   ["/dev/vg_vm/vg1_vm1",
                                                    "/mnt/data"]]}
                                   )

        mock_exec.return_value = (
            '', '68851d12-5a84-456a-a0f3-4befbc62c949', '')
        updated_userdata_path = cloud._get_updated_userdata_path()

        self.assertEqual(updated_userdata_path, "/tmp_dir/user-data")
        self.assertEqual(
                file_handle.getvalue(),
                "#cloud-config\n"
                "bootcmd:\n- - cloud-init-per\n  - instance\n  - hostname\n  - "
                "sh\n  - -c\n  - hostname ms-fmmed2\n- - cloud-init-per\n  - instance\n  - alias0\n  - "
                "sh\n  - -c\n  - echo 10.10.11.100 ms1 >> /etc/hosts\n"
                "runcmd:\n- /sbin/service rsyslog restart\n"
                "timezone: Europe/Dublin\n"
                "yum_repos:\n  3pp:\n    baseurl: http://ms1/3pp\n    enabled: true\n    gpgcheck: false\n    name: 3pp"
                "#cloud-config\n"
                "bootcmd:\n- - cloud-init-per\n  - instance\n  - hostname\n  - "
                "sh\n  - -c\n  - hostname ms-fmmed2\n- - cloud-init-per\n  - instance\n  - alias0\n  - "
                "sh\n  - -c\n  - echo 10.10.11.100 ms1 >> /etc/hosts\n"
                "mounts:\n- - UUID=68851d12-5a84-456a-a0f3-4befbc62c949\n  - /mnt/data\n  - ext4\n  - defaults\n  - '0'\n  - '0'\n"
                "runcmd:\n- /sbin/service rsyslog restart\n"
                "timezone: Europe/Dublin\nyum_repos:\n  3pp:\n    baseurl: http://ms1/3pp\n    enabled: true\n    gpgcheck: false\n    name: 3pp\n"
        )

    @mock.patch('litpmnlibvirt.litp_libvirt_utils.exec_cmd')
    @mock.patch('__builtin__.open')
    @mock.patch('tempfile.mkdtemp')
    @mock.patch('os.unlink')
    def test_get_updated_userdata_path_err(self, mock_unlink,
                                           mock_mktemp, mock_open, mock_exec):
        mock_open.return_value = mock.MagicMock(spec=file)
        mock_open.return_value.__enter__.return_value = StringIO(USER_DATA)
        file_handle = mock_open.return_value.__enter__.return_value

        cloud = Libvirt_cloud_init(self.name, {"internal_status_check":
                                                   {"active": "off",
                                                    "ip_address": ""},
                                               "disk_mounts": [
                                                   ["/dev/vg_vm/vg1_vm1",
                                                    "/mnt/data"]]}
                                   )
        mock_exec.return_value = ('', 'broken-uuid', '')
        mock_open.return_value.__enter__.return_value = StringIO(USER_DATA)
        self.assertRaises(LitpLibvirtException,
                          cloud._get_updated_userdata_path)


class TestLibvirtImage(unittest.TestCase):
    def setUp(self):
        # Using these for assertions later
        self.img_name = 'fmmed.qcow2'
        self.name = 'instance'
        self.img = Libvirt_vm_image(self.name, self.img_name)

    def test_get_base_img_path(self):
        self.assertEquals("/var/lib/libvirt/images/fmmed.qcow2",
                          self.img.get_base_img_path())

    def test_get_live_img_path(self):
        self.assertEquals(os.path.join('/var/lib/libvirt/instances', self.name,
                                       self.img_name),
                          self.img.get_live_img_path())

    @mock.patch("shutil.copy")
    def test_copy_image(self, _copy):
        self.img.copy_image()
        _copy.assert_called_once_with(
                os.path.join('/var/lib/libvirt/images', self.img_name),
                os.path.join('/var/lib/libvirt/instances', self.name,
                             self.img_name)
        )

    @mock.patch("os.path.isfile")
    def test_base_img_exists(self, _isfile):
        self.assertEquals(_isfile.return_value, self.img.base_image_exists())
        _isfile.assert_called_with(os.path.join('/var/lib/libvirt/images',
                                                self.img_name))

    @mock.patch("os.path.isfile")
    def test_live_img_exists(self, _isfile):
        self.assertEquals(_isfile.return_value, self.img.live_image_exists())
        _isfile.assert_called_with(os.path.join('/var/lib/libvirt/instances',
                                                self.name, self.img_name))


class TestLibvirtVmXml(unittest.TestCase):
    def setUp(self):
        name = "vm_name"
        self.xml = Libvirt_vm_xml(name)

    def test_add_image_device(self):
        devices = ET.Element("devices")
        image = "imagefile"
        self.xml._add_image_device(devices, image)
        result = ET.tostring(devices, encoding='utf-8')
        expected = ('<devices><disk device="disk" type="file">'
                    '<driver cache="none" name="qemu" type="qcow2" />'
                    '<source file="/var/lib/libvirt/instances/vm_name/imagefile" />'
                    '<target bus="virtio" dev="vda" />'
                    '<alias name="virtio_disk0" />'
                    '</disk></devices>')
        self.assertEquals(result, expected)

    def test_add_usb_device(self):
        devices = ET.Element("devices")
        self.xml._add_usb_device(devices)
        result = ET.tostring(devices, encoding='utf-8')
        expected = ('<devices><controller index="0" type="usb">'
                    '<alias name="usb0" />'
                    '</controller></devices>')
        self.assertEquals(result, expected)

    def test_add_serial_device(self):
        devices = ET.Element("devices")
        self.xml._add_serial_device(devices)
        result = ET.tostring(devices, encoding='utf-8')
        expected = ('<devices><serial type="pty">'
                    '<source path="/dev/pts/3" />'
                    '<target port="0" />'
                    '<alias name="serial0" />'
                    '</serial></devices>')
        self.assertEquals(result, expected)

    def test_add_console_device(self):
        devices = ET.Element("devices")
        self.xml._add_console_device(devices)
        result = ET.tostring(devices, encoding='utf-8')
        expected = ('<devices><console tty="/dev/pts/3" type="pty">'
                    '<source path="/dev/pts/3" />'
                    '<target port="0" type="serial" />'
                    '<alias name="serial0" />'
                    '</console></devices>')
        self.assertEquals(result, expected)

    def test_add_input_device(self):
        devices = ET.Element("devices")
        self.xml._add_input_device(devices)
        result = ET.tostring(devices, encoding='utf-8')
        expected = ('<devices>'
                    '<input bus="usb" type="tablet">'
                    '<alias name="input00" />'
                    '</input>'
                    '<input bus="ps2" type="mouse" />'
                    '</devices>')
        self.assertEquals(result, expected)

    def test_add_graphics_device(self):
        devices = ET.Element("devices")
        self.xml._add_graphics_device(devices)
        result = ET.tostring(devices, encoding='utf-8')
        expected = ('<devices>'
                    '<graphics autoport="yes" listen="127.0.0.1"'
                    ' port="5902" type="vnc">'
                    '<listen address="127.0.0.1" type="address" />'
                    '</graphics>'
                    '</devices>')
        self.assertEquals(result, expected)

    def test_add_video_device(self):
        devices = ET.Element("devices")
        self.xml._add_video_device(devices)
        result = ET.tostring(devices, encoding='utf-8')
        expected = ('<devices>'
                    '<video><model heads="1" type="cirrus" vram="9216" />'
                    '<alias name="video0" />'
                    '</video>'
                    '</devices>')
        self.assertEquals(result, expected)

    def test_add_memballoon_device(self):
        devices = ET.Element("devices")
        self.xml._add_memballoon_device(devices)
        result = ET.tostring(devices, encoding='utf-8')
        expected = ('<devices>'
                    '<memballoon model="virtio">'
                    '<alias name="balloon0" />'
                    '</memballoon>'
                    '</devices>')
        self.assertEquals(result, expected)

    def test_add_net_interface_device(self):
        devices = ET.Element("devices")
        device = "br1"
        mac = '52:54:00:83:a2:53'
        self.xml._add_net_interface_device(devices, device, mac)
        result = ET.tostring(devices, encoding='utf-8')
        expected = ('<devices>'
                    '<interface type="bridge">'
                    '<source bridge="br1" />'
                    '<model type="virtio" />'
                    '<mac address="52:54:00:83:a2:53" />'
                    '</interface>'
                    '</devices>')
        self.assertEquals(result, expected)

    def test_add_net_interface_device_no_mac(self):
        devices = ET.Element("devices")
        device = "br1"
        mac = None
        self.xml._add_net_interface_device(devices, device, mac)
        result = ET.tostring(devices, encoding='utf-8')
        expected = ('<devices>'
                    '<interface type="bridge">'
                    '<source bridge="br1" />'
                    '<model type="virtio" />'
                    '</interface>'
                    '</devices>')
        self.assertEquals(result, expected)

    def test_add_cdrom_device(self):
        devices = ET.Element("devices")
        src_file = "CD_FILE"
        self.xml._add_cdrom_device(devices, src_file)
        result = ET.tostring(devices, encoding='utf-8')
        expected = ('<devices>'
                    '<disk device="cdrom" type="file">'
                    '<driver name="qemu" type="raw" />'
                    '<source file="CD_FILE" />'
                    '<target bus="ide" dev="hda" />'
                    '<readonly />'
                    '<alias name="ide0-0-0" />'
                    '</disk>'
                    '</devices>')
        self.assertEquals(result, expected)

    def test_add_seclabel(self):
        domain = ET.Element("domain")
        self.xml._add_seclabel(domain)
        result = ET.tostring(domain, encoding='utf-8')
        expected = ('<domain>'
                    '<seclabel model="selinux" relabel="yes" type="dynamic">'
                    '<label>unconfined_u:system_r:svirt_t:s0:c805,c993</label>'
                    '<imagelabel>'
                    'unconfined_u:object_r:svirt_image_t:s0:c805,c993'
                    '</imagelabel>'
                    '</seclabel>'
                    '</domain>')
        self.assertEquals(result, expected)

    @mock.patch('litpmnlibvirt.litp_libvirt_utils.exec_cmd')
    @mock.patch(
            "litpmnlibvirt.litp_libvirt_utils.Libvirt_vm_xml._add_image_device")
    @mock.patch(
            "litpmnlibvirt.litp_libvirt_utils.Libvirt_vm_xml._add_usb_device")
    @mock.patch(
            "litpmnlibvirt.litp_libvirt_utils.Libvirt_vm_xml._add_serial_device")
    @mock.patch(
            "litpmnlibvirt.litp_libvirt_utils.Libvirt_vm_xml._add_console_device")
    @mock.patch(
            "litpmnlibvirt.litp_libvirt_utils.Libvirt_vm_xml._add_input_device")
    @mock.patch(
            "litpmnlibvirt.litp_libvirt_utils.Libvirt_vm_xml._add_graphics_device")
    @mock.patch(
            "litpmnlibvirt.litp_libvirt_utils.Libvirt_vm_xml._add_video_device")
    @mock.patch(
            "litpmnlibvirt.litp_libvirt_utils.Libvirt_vm_xml._add_memballoon_device")
    @mock.patch(
            "litpmnlibvirt.litp_libvirt_utils.Libvirt_vm_xml._add_net_interface_device")
    @mock.patch(
            "litpmnlibvirt.litp_libvirt_utils.Libvirt_vm_xml._add_cdrom_device")
    def test_define_domain(self, mock_cd, mock_net_if, mock_memb,
                           mock_vid, mock_gphics, mock_input, mock_cnsl,
                           mock_serial, mock_usb, mock_disk, mock_exec):
        name = "machine_name"
        ram_size = "1024M"
        cpus = "2"
        image = "image_file"
        netwks = None
        nics = {}
        block_devices = []
        # test case for physical machine
        mock_exec.side_effect = [['0', '', '']]
        domain = self.xml._define_domain(name, ram_size, cpus, image, nics,
                                         block_devices)
        result = ET.tostring(domain, encoding='utf-8')
        expected = ('<domain type="kvm">'
                    '<name>machine_name</name>'
                    '<memory unit="MiB">1024</memory>'
                    '<cpu mode="host-passthrough" />'
                    '<vcpu placement="static">2</vcpu>'
                    '<os><type arch="x86_64" machine="rhel6.6.0">hvm</type>'
                    '<boot dev="hd" /></os>'
                    '<features><acpi /><apic /><pae /></features>'
                    '<clock offset="utc" />'
                    '<on_poweroff>destroy</on_poweroff>'
                    '<reboot>restart</reboot>'
                    '<on_crash>restart</on_crash>'
                    '<devices>'
                    '<emulator>/usr/libexec/qemu-kvm</emulator>'
                    '<rng model="virtio"><rate bytes="1234" period="2000" />'
                    '<backend model="random">/dev/random</backend></rng>'
                    '</devices>'
                    '</domain>')

        self.assertEquals(result, expected)
        mock_exec.reset_mock()

        # test case for virtual machine
        mock_exec.side_effect = [['0', 'vmware', '']]
        domain = self.xml._define_domain(name, ram_size, cpus, image, nics,
                                         block_devices)
        result = ET.tostring(domain, encoding='utf-8')
        expected = ('<domain type="kvm">'
                    '<name>machine_name</name>'
                    '<memory unit="MiB">1024</memory>'
                    '<vcpu placement="static">2</vcpu>'
                    '<os><type arch="x86_64" machine="rhel6.6.0">hvm</type>'
                    '<boot dev="hd" /></os>'
                    '<features><acpi /><apic /><pae /></features>'
                    '<clock offset="utc" />'
                    '<on_poweroff>destroy</on_poweroff>'
                    '<reboot>restart</reboot>'
                    '<on_crash>restart</on_crash>'
                    '<devices>'
                    '<emulator>/usr/libexec/qemu-kvm</emulator>'
                    '</devices>'
                    '</domain>')
        self.assertEquals(result, expected)

    @mock.patch("litpmnlibvirt.litp_libvirt_utils.ET.SubElement")
    def test_define_domain_with_nics(self, mock_et_sub):
        et_subtree_mock = mock.Mock(text="my_text")
        mock_et_sub.return_value = et_subtree_mock
        name = "machine_name"
        ram_size = "1024M"
        cpus = "2"
        image = "image_file"
        netwks = None
        block_devices = []

        with mock.patch(
                "litpmnlibvirt.litp_libvirt_utils.Libvirt_vm_xml._add_net_interface_device") \
                as mock_net_if:
            nics = {'eth1': {'host_device': 'br1'},
                    'eth0': {'host_device': 'br0'}}
            domain = self.xml._define_domain(name, ram_size, cpus, image, nics,
                                             block_devices)
            self.assertEqual(mock_net_if.call_args_list, [
                mock.call(et_subtree_mock, "br0", None),
                mock.call(et_subtree_mock, "br1", None)])

        with mock.patch(
                "litpmnlibvirt.litp_libvirt_utils.Libvirt_vm_xml._add_net_interface_device") \
                as mock_net_if:
            nics = {
                'eth13': {'host_device': 'br3',
                          "mac_address": "52:54:00:c3:fa:16"},
                'eth2': {'host_device': 'br2',
                         "mac_address": "52:54:00:c3:fa:15"},
                'eth1': {'host_device': 'br1',
                         "mac_address": "52:54:00:c3:fa:14"},
                'eth0': {'host_device': 'br0',
                         "mac_address": "52:54:00:e2:8d:65"}}
            domain = self.xml._define_domain(name, ram_size, cpus, image, nics,
                                             block_devices)
            self.assertEqual(mock_net_if.call_args_list, [
                mock.call(et_subtree_mock, "br0", '52:54:00:e2:8d:65'),
                mock.call(et_subtree_mock, "br1", '52:54:00:c3:fa:14'),
                mock.call(et_subtree_mock, "br2", '52:54:00:c3:fa:15'),
                mock.call(et_subtree_mock, "br3", '52:54:00:c3:fa:16')])

    def test_define_domain_raises_exception_on_bad_mem(self):
        ram_size = "64k"
        self.assertRaises(LitpLibvirtException, self.xml._define_domain,
                          "name", ram_size, "2", "img", [], [])

    @mock.patch('xml.etree.ElementTree.tostring')
    @mock.patch(
            'litpmnlibvirt.litp_libvirt_utils.Libvirt_vm_xml._define_domain')
    @mock.patch('litpmnlibvirt.litp_libvirt_utils.Libvirt_conf')
    def test_build_machine_xml(self, mock_conf, mock_def_domain,
                               mock_et):
        def raise_ex(name):
            raise (LitpLibvirtException('Failed to read conf'))

        mock_conf.side_effect = raise_ex
        self.assertRaises(LitpLibvirtException,
                          self.xml.build_machine_xml)
        mock_conf.reset_mock()
        mock_conf_inst = mock.Mock()
        mock_conf_inst.get_vm_data = mock.Mock(return_value=CONFIG["vm_data"])
        mock_conf_inst.get_adaptor_data = mock.Mock(
                return_value={'disk_mounts': []})

        def instantiate(name):
            return mock_conf_inst

        mock_conf.side_effect = instantiate
        mock_def_domain.return_value = "<xml_stuff/>"
        mock_et.return_value = "expected"
        result = self.xml.build_machine_xml()
        self.assertEquals(result, "expected")
        mock_def_domain.assert_has_calls(
                [mock.call('vm_name', '1024', '2', 'path/image_name',
                           {'eth1': {'host_device': 'br1'},
                            'eth0': {'host_device': 'br0'}}, [],
                           cpuset=None, cpunodebind=None)])

    def test_find_free_device_name(self):
        root = ET.parse(StringIO("""<root><devices>
        <disk device="disk" type="file">
            <target bus="virtio" dev="vda"/>
        </disk>
        <disk device="disk" type="block">
            <target bus="virtio" dev="vdc"/>
        </disk>
        <disk device="disk" type="block">
            <target bus="virtio" dev="vdd"/>
        </disk>
        </devices></root>"""))
        self.assertEqual(
                self.xml._find_free_device_name(root.find("devices")),
                'vdb'
        )

    def assert_cpuset(self, expected_value):
        domain = ET.fromstring(self.xml.build_machine_xml())
        vcpu = domain.findall('vcpu')
        self.assertEqual(1, len(vcpu))
        self.assertEquals(expected_value, vcpu[0].get('cpuset'))

    @mock.patch('litpmnlibvirt.litp_libvirt_utils.Libvirt_conf')
    def test_build_machine_xml_cpuset(self, m_libvirt_conf):
        config = {
            'vm_data': {
                'image': 'path/image_name',
                'ram': '1024M',
                'cpu': '2',
                'interfaces': {}},
            'adaptor_data': {'disk_mounts': []}
        }

        mock_conf_inst = mock.Mock()
        mock_conf_inst.get_vm_data.return_value = config['vm_data']
        mock_conf_inst.get_adaptor_data.return_value = config['adaptor_data']
        m_libvirt_conf.return_value = mock_conf_inst

        # No cpuset in config -> no cpuset in xml
        self.assert_cpuset(None)

        # Empty cpuset vvalue in config -> no cpuset in xml
        config['vm_data']['cpuset'] = ''
        self.assert_cpuset(None)

        # cpuset in config -> cpuset in vcpu element
        config['vm_data']['cpuset'] = '0-2'
        self.assert_cpuset('0-2')

    @mock.patch('litpmnlibvirt.litp_libvirt_utils.Libvirt_capabilities.'
                'get_cpu_capabilities')
    @mock.patch('litpmnlibvirt.litp_libvirt_utils.Libvirt_conf')
    def test_build_machine_xml_cpunodebind(self, m_libvirt_conf,
                                           m_get_cpu_capabilities):
        config = {
            'vm_data': {
                'image': 'path/image_name',
                'ram': '1024M',
                'cpu': '2',
                'interfaces': {}},
            'adaptor_data': {'disk_mounts': []}
        }

        mock_conf_inst = mock.Mock()
        mock_conf_inst.get_vm_data.return_value = config['vm_data']
        mock_conf_inst.get_adaptor_data.return_value = config['adaptor_data']
        m_libvirt_conf.return_value = mock_conf_inst

        m_get_cpu_capabilities.return_value = {'1': '0-5', '2': '20-25'}

        # No cpunodebind in config -> no cpuset in xml
        self.assert_cpuset(None)

        data = [
            # Empty cpunodebind value in config -> no cpuset in xml
            ('', None),

            # cpunodebind in config -> cpuset in vcpu element
            ('1', '0-5'),

            # invalid cpunodebind node in config -> no cpuset in xml
            ('10', None),

            # cpunodebind in config -> cpuset in vcpu element
            ('1,2', '0-5,20-25'),

            # both valie and invalid cpunodebind in config ->
            #  cpuset in vcpu element
            ('2,0', '20-25')
        ]
        for test_value, expected in data:
            config['vm_data']['cpunodebind'] = test_value
            self.assert_cpuset(expected)


class TestLibvirt_capabilities(unittest.TestCase):
    # Taken from a Gen9/Gen10 rack
    CAPS_PHYSICAL = """
<capabilities>
  <host>
    <topology>
      <cells num='2'>
        <cell id='0'>
          <cpus num='4'>
            <cpu id='0' socket_id='0' core_id='0' siblings='0,20'/>
            <cpu id='1' socket_id='0' core_id='1' siblings='1,21'/>
            <cpu id='20' socket_id='0' core_id='0' siblings='0,20'/>
            <cpu id='21' socket_id='0' core_id='1' siblings='1,21'/>
          </cpus>
        </cell>
        <cell id='1'>
          <cpus num='4'>
            <cpu id='18' socket_id='1' core_id='11' siblings='18,38'/>
            <cpu id='19' socket_id='1' core_id='12' siblings='19,39'/>
            <cpu id='38' socket_id='1' core_id='11' siblings='18,38'/>
            <cpu id='39' socket_id='1' core_id='12' siblings='19,39'/>
            <cpu id='40' socket_id='1' core_id='12' siblings='19,39'/>
            <cpu id='41' socket_id='1' core_id='12' siblings='19,39'/>
          </cpus>
        </cell>
      </cells>
    </topology>
  </host>
</capabilities>
        """

    # Taken from LITP KGB vApp
    CAPS_CLOUD = """
<capabilities>
  <host>
    <topology>
      <cells num='1'>
        <cell id='0'>
          <cpus num='2'>
            <cpu id='0' socket_id='0' core_id='0' siblings='0'/>
            <cpu id='1' socket_id='2' core_id='0' siblings='1'/>
          </cpus>
        </cell>
      </cells>
    </topology>
  </host>
</capabilities>
        """

    def setUp(self):
        self.caps = Libvirt_capabilities()

    @mock.patch('litpmnlibvirt.litp_libvirt_utils.get_handle')
    def test_get_cpu_capabilities(self, p_get_handle):
        m_conn = MagicMock(name='m_conn')
        p_get_handle.return_value = m_conn
        m_conn.getCapabilities.return_value = \
            TestLibvirt_capabilities.CAPS_PHYSICAL

        mappings = self.caps.get_cpu_capabilities()
        self.assertEqual(2, len(mappings))
        self.assertTrue('0' in mappings)
        self.assertEqual('0-1,20-21', mappings['0'])
        self.assertTrue('1' in mappings)
        self.assertEqual('18-19,38-41', mappings['1'])

        m_conn.getCapabilities.return_value = \
            TestLibvirt_capabilities.CAPS_CLOUD
        mappings = self.caps.get_cpu_capabilities()
        self.assertEqual(1, len(mappings))
        self.assertTrue('0' in mappings)
        self.assertEqual('0-1', mappings['0'])
