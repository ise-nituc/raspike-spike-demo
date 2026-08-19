# Raspberry Pi clone setup

After booting a cloned IoT01 microSD card, update the repository and assign the
new two-digit robot ID:

```bash
cd ~/raspike-spike-demo
git switch main
git pull
cd scripts
./setup 02
sudo reboot
```

For normal updates from the public repository, an HTTPS `origin` is recommended.
It does not need to be reset on every update. If `git pull` fails with
`git@github.com: Permission denied (publickey)`, inspect and change the remote:

```bash
git remote -v
git remote set-url origin https://github.com/ise-nituc/raspike-spike-demo.git
```

`setup` accepts IDs from `01` through `99`. It previews all derived addresses
and asks for confirmation. It saves NetworkManager settings without cycling
connections, so the current SSH session should remain available until reboot.

The script manages only `raspike-eth` and the existing `raspike-ap`. It neither
changes nor deletes school Wi-Fi connections such as `netplan-wlan0-isepr`.
When `/etc/raspike-id` records a different ID, clone-specific machine and SSH
host identities are regenerated once. If no prior ID is recorded, identities
are left unchanged; inspect the machine before deciding whether regeneration is
needed.

## Verification after reboot

For ID `02`, the expected checks are:

```bash
hostnamectl hostname
cat /etc/raspike-id
nmcli -f connection.id,connection.interface-name,connection.autoconnect,connection.autoconnect-priority,ipv4.method,ipv4.addresses connection show raspike-eth
nmcli -f connection.id,connection.interface-name,connection.autoconnect,connection.autoconnect-priority,802-11-wireless.ssid,802-11-wireless.mode,ipv4.method,ipv4.addresses connection show raspike-ap
ip -4 address show dev eth0
ip -4 address show dev wlan0
```

Expected values are hostname `IoT02`, Ethernet `192.168.50.102/24`, AP SSID
`iot02`, and AP address `192.168.60.102/24`. The script intentionally does not
delete legacy `netplan-eth0`, `Wired connection 1`, or anything under
`/var/lib/NetworkManager`; `raspike-eth` has priority 100 and is selected after
reboot without risking unrelated or secret connection data.

As in the previous `/home/iot/setup`, completion output also includes the
port-8082 dashboard addresses, current runtime interface information, host-key
cleanup commands after clone identity regeneration, and an optional reboot
prompt.
