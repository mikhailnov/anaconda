%post --nochroot
# Schedule eject of CD/DVD ROM if we have installed the system successfully.
# Some hyvervisors, e.g. VirtualBox, treat eject as removing the virtual drive.
# This will prevent further boot of the installed system from the installation media.
# Systemd will run tne created script after unmounting all other filesystems.
set -e
set -u
systemd_dir=""
if mount | grep -qE '^/dev/(sr|cd|dvd).*/run/initramfs/live' ; then
	if [ -d /usr/lib/systemd/system-shutdown ]; then
		systemd_dir=/usr/lib/systemd/system-shutdown
	elif [ -d /lib/systemd/system-shutdown ]; then
		systemd_dir=/lib/systemd/system-shutdown
	fi
	if [ -n "$systemd_dir" ] && [ -x /usr/bin/eject ]; then
		echo '#!/bin/sh' > "$systemd_dir"/eject-on-shutdown
		echo '/usr/bin/eject -m' >> "$systemd_dir"/eject-on-shutdown
		chmod +x "$systemd_dir"/eject-on-shutdown
	fi
fi
%end
