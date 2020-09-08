#
# Copyright (C) 2019 Red Hat, Inc.
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions of
# the GNU General Public License v.2, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY expressed or implied, including the implied warranties of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.  You should have received a copy of the
# GNU General Public License along with this program; if not, write to the
# Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.  Any Red Hat trademarks that are incorporated in the
# source code or documentation are not subject to the GNU General Public
# License and may only be used or replicated with the express permission of
# Red Hat, Inc.
#
import os
import re

from pyanaconda.bootloader.base import BootLoaderError
from pyanaconda.bootloader.grub2 import GRUB2
from pyanaconda.core import util
from pyanaconda.core.kernel import kernel_arguments
from pyanaconda.core.configuration.anaconda import conf
from pyanaconda.product import productName

from pyanaconda.anaconda_loggers import get_module_logger
log = get_module_logger(__name__)

__all__ = ["EFIBase", "EFIGRUB", "Aarch64EFIGRUB", "ArmEFIGRUB", "MacEFIGRUB"]


class EFIBase(object):
    """A base class for EFI-based boot loaders."""

    # In ROSA, the main Grub2 config is /boot/grub2/grub.cfg,
    # and the one by the path bellow just sets some variables and reuses it;
    # it is done by a patch in Grub2; grub2-instyall is executed to make
    # the config by the path bellow
    # But this variable is used bellow... So not removing it
    @property
    def _config_dir(self):
        return "efi/EFI/{}".format(conf.bootloader.efi_dir)

    def efibootmgr(self, *args, **kwargs):
        if not conf.target.is_hardware:
            log.info("Skipping efibootmgr for image/directory install.")
            return ""

        # XXX mostly useless in ROSA where Anaconda is patches to execute grub2-install
        # which executes efibootmgr; this code just won't be run
        if "noefi" in kernel_arguments:
            log.info("Skipping efibootmgr for noefi")
            return ""

        if kwargs.pop("capture", False):
            exec_func = util.execWithCapture
        else:
            exec_func = util.execWithRedirect
        if "root" not in kwargs:
            kwargs["root"] = conf.target.system_root

        return exec_func("efibootmgr", list(args), **kwargs)

    @property
    def efi_dir_as_efifs_dir(self):
        ret = self._config_dir.replace('efi/', '')
        return "\\" + ret.replace('/', '\\')

    def _add_single_efi_boot_target(self, partition):
        boot_disk = partition.disk
        boot_part_num = str(partition.parted_partition.number)

        rc = self.efibootmgr(
            "-c", "-w", "-L", productName.split("-")[0],  # pylint: disable=no-member
            "-d", boot_disk.path, "-p", boot_part_num,
            "-l", self.efi_dir_as_efifs_dir + self._efi_binary,  # pylint: disable=no-member
            root=conf.target.system_root
        )
        if rc:
            raise BootLoaderError("Failed to set new efi boot target. This is most "
                                  "likely a kernel or firmware bug.")

    def add_efi_boot_target(self):
        if self.stage1_device.type == "partition":  # pylint: disable=no-member
            self._add_single_efi_boot_target(self.stage1_device)  # pylint: disable=no-member
        elif self.stage1_device.type == "mdarray":  # pylint: disable=no-member
            for parent in self.stage1_device.parents:  # pylint: disable=no-member
                self._add_single_efi_boot_target(parent)

    def remove_efi_boot_target(self):
        buf = self.efibootmgr(capture=True)
        for line in buf.splitlines():
            try:
                (slot, _product) = line.split(None, 1)
            except ValueError:
                continue

            if _product == productName.split("-")[0]:           # pylint: disable=no-member
                slot_id = slot[4:8]
                # slot_id is hex, we can't use .isint and use this regex:
                if not re.match("^[0-9a-fA-F]+$", slot_id):
                    log.warning("failed to parse efi boot slot (%s)", slot)
                    continue

                rc = self.efibootmgr("-b", slot_id, "-B")
                if rc:
                    raise BootLoaderError("Failed to remove old efi boot entry. This is most "
                                          "likely a kernel or firmware bug.")

    def write(self):
        """ Write the bootloader configuration and install the bootloader. """
        if self.skip_bootloader:  # pylint: disable=no-member
            return

        try:
            os.sync()
            self.stage2_device.format.sync(root=conf.target.physical_root) # pylint: disable=no-member
            self.write_config()
        finally:
            self.install()  # pylint: disable=no-member

    def check(self):
        return True

    def install(self, args=None):
        if not self.keep_boot_order:  # pylint: disable=no-member
            self.remove_efi_boot_target()
        self.add_efi_boot_target()


class EFIGRUB(EFIBase, GRUB2):
    """EFI GRUBv2"""
    # XXX ROSA does not support 32 bit UEFI now!!!
    # We probably need to separate packages like Fedora
    _packages32 = [ "grub2-efi", "shim" ]
    _packages_common = [ "efibootmgr", "grub2" ]
    can_dual_boot = False
    stage2_is_valid_stage1 = False
    stage2_bootable = False
    is_efi_grub = True

    _is_32bit_firmware = False

    def __init__(self):
        super().__init__()
        self._packages64 = [ "grub2-efi", "shim" ]

        try:
            f = open("/sys/firmware/efi/fw_platform_size", "r")
            value = f.readline().strip()
        except IOError:
            log.info("Reading /sys/firmware/efi/fw_platform_size failed, "
                     "defaulting to 64-bit install.")
            value = '64'
        if value == '32':
            self._is_32bit_firmware = True

    @property
    def _efi_binary(self):
        if self._is_32bit_firmware:
            # XXX will it work?
            return "\\BOOTia32.efi"
        return "\\BOOTx64.efi"

    @property
    def packages(self):
        # XXX EFI 32 will not work right now
        if self._is_32bit_firmware:
            return self._packages32 + self._packages_common
        return self._packages64 + self._packages_common

    # In ROSA we do not want to follow the following, quote from Fedora wiki:
    # https://fedoraproject.org/wiki/GRUB_2
    # "grub2-install shouldn't be used on EFI systems. The grub2-efi package installs a prebaked grubx64.efi
    # on the EFI System partition, which looks for grub.cfg on the ESP in /EFI/fedora/ whereas the grub2-install
    # command creates a custom grubx64.efi, deletes the original installed one, and looks for grub.cfg in /boot/grub2/"
    # We, as Ubuntu, patch Grub2 to keep the config in /boot/grub2/grub.cfg, and /boot/efi/EFI/rosa/grub.cfg
    # is a super-minimal config which sets some params and loads /boot/grub2/grub.cfg
    # grub2 is patched to make that minimal config, so we have to run grub2-install inside the chroot.
    # Fedora does not run grub2-install at all, they just make a grub config and run efibootmgr.
    # XXX Maybe move to a simpler Fedora/RH sheme and keep grub.cfg in /boot/efi/EFI/rosa/grub.cfg?!
    # XXX /boot/grub2/grub.cfg will first be rsync'ed from LiveCD and then must be overwritten.
    def install(self, args=None):
        log.info("bootloader.py: installing grub2 in EFI mode")
        rc = util.execInSysroot("grub2-install", [])
        if rc:
            raise BootLoaderError("Bootloader install (grub2-install) in EFI mode failed")
        # update-grub2 is not an upstream script
        rc = util.execInSysroot("update-grub2", [])
        if rc:
            raise BootLoaderError("Bootloader config update (update-grub2) in EFI mode failed")


class Aarch64EFIGRUB(EFIGRUB):
    _serial_consoles = ["ttyAMA", "ttyS"]
    # XXX fix this name
    _efi_binary = "\\BOOTAA64.efi"

    def __init__(self):
        super().__init__()
        self._packages64 = ["grub2-efi", "shim"]


class ArmEFIGRUB(EFIGRUB):
    _serial_consoles = ["ttyAMA", "ttyS"]
    _efi_binary = "\\grubarm.efi"

    def __init__(self):
        super().__init__()
        self._packages32 = ["grub2-efi"]
        self._is_32bit_firmware = True


class MacEFIGRUB(EFIGRUB):
    # XXX not supported in ROSA (?)
    def __init__(self):
        super().__init__()
        self._packages64.extend(["grub2", "mactel-boot"])

    def mactel_config(self):
        if os.path.exists(conf.target.system_root + "/usr/libexec/mactel-boot-setup"):
            rc = util.execInSysroot("/usr/libexec/mactel-boot-setup", [])
            if rc:
                log.error("failed to configure Mac boot loader")

    def install(self, args=None):
        super().install()
        self.mactel_config()

    def is_valid_stage1_device(self, device, early=False):
        valid = super().is_valid_stage1_device(device, early)

        # Make sure we don't pick the OSX root partition
        if valid and getattr(device.format, "name", "") != "Linux HFS+ ESP":
            valid = False

        if hasattr(device.format, "name"):
            log.debug("device.format.name is '%s'", device.format.name)

        log.debug("MacEFIGRUB.is_valid_stage1_device(%s) returning %s", device.name, valid)
        return valid
