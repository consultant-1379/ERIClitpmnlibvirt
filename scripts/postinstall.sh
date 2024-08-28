#!/bin/bash

SITE=`python -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())"`
echo "/opt/ericsson/nms/litp/lib" > $SITE/litp_libvirt_adaptor.pth

mkdir -p /var/log/litp

exit 0

