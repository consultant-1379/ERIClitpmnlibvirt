##############################################################################
# COPYRIGHT Ericsson AB 2014
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

import functools
import libvirt


URI = "qemu:///system"


def cache_connection(func):
    uri_to_handler = {}

    @functools.wraps(func)
    def dec(uri=URI):
        if uri_to_handler.get(uri) is None:
            uri_to_handler[uri] = func(uri)
        return uri_to_handler[uri]
    # Clears the cache - useful for tests
    dec.clear = uri_to_handler.clear
    return dec


@cache_connection
def get_handle(uri=URI):
    return libvirt.open(uri)
