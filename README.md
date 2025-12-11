This is an Ansible collection of plugins for managing hosts in Proxmox using
the web API to query hosts and control them through QEMU guest agent and LXC.
Sice querrying and controlling Proxmox hosts through the API does not require
any IP addresses or domain names, these plugins can be convenient for managing
them even when offline or behind a firewall.

Currently, Windows and Linux hosts are supported through QEMU guest agent, and
LXC is not implemented at all yet.

## Plugins

* inventories
  * `pgsocks.proxmox.proxmox`
* connections
  * `pgsocks.proxmox.qemu`
  * `pgsocks.proxmox.lxc` **(coming soon)**

# Quickstart

Install the collection.

```bash
ansible-galaxy collection install https://github.com/pgsocks/pgsocks.proxmox.git
```

Write a an inventory file called `hosts.proxmox.yml`.

```yml
plugin: pgsocks.proxmox.proxmox
host: myproxmox.com
user: root@pam
verify_ssl: no
```

Set variables for Proxmox authentication. These can be in the hosts file or
`ansible.cfg`, but using environment variables is more secure.

```bash
export PROXMOX_TOKEN=token_name
export PROXMOX_SECRET=token_value
```

Now, the inventory should be populated with QEMU and LXC hosts in Proxmox. Any
hosts with the QEMU guest agent service can be pinged using the connection
plugin.

```bash
ansible-inventory -i hosts.proxmox.yml --list
ansible proxmox_qemu \
-i hosts.proxmox.yml \
-c pgsocks.proxmox.qemu \
-m ping

```

For Windows guests, continue to use the Windows modules and shell settings, for
example:

```bash
ansible proxmox_qemu \
-i hosts.proxmox.yml \
-c pgsocks.proxmox.qemu \
-e ansible_shell_type=powershell \
-m win_ping
```

