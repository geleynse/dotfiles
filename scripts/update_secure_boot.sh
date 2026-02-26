#!/bin/sh
#
# Update secure boot components (bootloader, initramfs, signed UKI)
# Use --reset-totp to also re-initialize TPM2-TOTP (invalidates current authenticator entry)
#

set -e

# Require root
if [ "$(id -u)" -ne 0 ]; then
    echo "Error: must run as root" >&2
    exit 1
fi

echo "Regenerating initramfs..."
mkinitcpio -P

echo "Updating bootloader..."
bootctl update

echo "Creating signed UKI and signing bootloader..."
sbupdate

# Verify signed UKI exists
if [ ! -f /boot/EFI/Linux/linux-signed.efi ]; then
    echo "Error: signed UKI not found" >&2
    exit 1
fi

echo "Secure boot components updated successfully"

if [ "$1" = "--reset-totp" ]; then
    echo "Re-initializing TPM2-TOTP..."
    tpm2-totp clean
    tpm2-totp --pcrs=0,7 init
    echo "Add the new QR code to your authenticator app"
else
    echo "Note: TPM2-TOTP not reset. If PCR values changed, run with --reset-totp"
fi
