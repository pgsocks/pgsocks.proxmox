from ansible.plugins.inventory import BaseInventoryPlugin
from ansible.errors import AnsibleError

try:
    import requests
    import proxmoxer
    IMPORT_ERROR = False
except ImportError:
    IMPORT_ERROR = True

__metaclass__ = type

DOCUMENTATION = """
name: proxmox
short_description: Proxmox inventory host
description:
  - Proxmox inventory plugin.
  - Acquires hosts from Proxmox API
  - Uses configuration file ending with C(.proxmox.yml)
options:
  plugin:
    description: Always C(pgsocks.proxmox.proxmox)
    required: yes
    type: str
    choices:
      - pgsocks.proxmox.proxmox
  host:
    description: Hostname for Proxmox API url
    required: yes
    type: str
    env:
      - name: PROXMOX_HOST
  user:
    description: Proxmox user to authenticate as
    required: yes
    type: str
    env:
      - name: PROXMOX_USER
  token:
    description: Name of token to authenticate with
    required: yes
    type: str
    env:
      - name: PROXMOX_TOKEN
  secret:
    description: Token value to authenticate with
    required: yes
    type: str
    env:
      - name: PROXMOX_SECRET
  verify_ssl:
    description: Set C(no) to skip certificate validation
    default: yes
    type: bool
"""

class InventoryModule(BaseInventoryPlugin):

    NAME = "pgsocks.proxmox.proxmox"

    def verify_file(self, path):

        return super().verify_file(path) and path.endswith(".proxmox.yml")

    def parse(self, inventory, loader, path, cache):

        if IMPORT_ERROR:
            raise AnsibleError("This module requires Requests and Proxmoxer")

        super().parse(inventory, loader, path, cache)
        self._read_config_data(path)

        session = proxmoxer.ProxmoxAPI (
            self.get_option("host"),
            user = self.get_option("user"),
            token_name = self.get_option("token"),
            token_value = self.get_option("secret"),
            verify_ssl = self.get_option("verify_ssl")
        )

        qemu_group = "proxmox_qemu"
        self.inventory.add_group(qemu_group)
        lxc_group = "proxmox_lxc"
        self.inventory.add_group(lxc_group)
        running_group = "proxmox_running"
        self.inventory.add_group(running_group)
        guest_group = "proxmox_guest"
        self.inventory.add_group(guest_group)
        self.inventory.add_child(guest_group, qemu_group)
        self.inventory.add_child(guest_group, lxc_group)
        self.inventory.add_child(guest_group, running_group)
        self.inventory.set_variable (
            guest_group,
            "ansible_proxmox_host",
            self.get_option("host") )
        self.inventory.set_variable (
            guest_group,
            "ansible_proxmox_user",
            self.get_option("user") )
        self.inventory.set_variable (
            guest_group,
            "ansible_proxmox_token",
            self.get_option("token") )
        self.inventory.set_variable (
            guest_group,
            "ansible_proxmox_secret",
            self.get_option("secret") )
        self.inventory.set_variable (
            guest_group,
            "ansible_proxmox_verify_ssl",
            self.get_option("verify_ssl") )

        for node in session.get("nodes"):
            for vm in session.get(f"nodes/{node['node']}/qemu"):
                if vm["template"]:
                    continue
                self.inventory.add_host(vm["name"])
                self.inventory.add_child(qemu_group, vm["name"])
                self.inventory.set_variable(vm["name"], f"proxmox_node", node["node"])
                for key, val in vm.items():
                    self.inventory.set_variable(vm["name"], f"proxmox_{key}", val)
                if vm["status"] != "running":
                    continue
                self.inventory.add_child(running_group, vm["name"])
                ifaces = session.get(f"nodes/{node['node']}/qemu/{vm['vmid']}/agent/network-get-interfaces")["result"]
                ifaces = [{"name" : iface["name"], "hwaddr" : iface.get("hardware-address", ""), "addresses" : [f"{ip['ip-address']}/{ip['prefix']}" for ip in iface.get("ip-addresses", [])]} for iface in ifaces]
                self.inventory.set_variable(vm["name"], f"proxmox_interfaces", ifaces)
                for key, val in session.get(f"nodes/{node['node']}/qemu/{vm['vmid']}/config").items():
                    self.inventory.set_variable(vm["name"], f"proxmox_{key}", val)

            for lxc in session.get(f"nodes/{node['node']}/lxc"):
                self.inventory.add_host(lxc["name"])
                self.inventory.add_child(lxc_group, lxc["name"])
                self.inventory.set_variable(lxc["name"], f"proxmox_node", node["node"])
                for key, val in lxc.items():
                    self.inventory.set_variable(lxc["name"], f"proxmox_{key}", val)
                if lxc["status"] != "running":
                    continue
                self.inventory.add_child(running_group, lxc["name"])
                for key, val in session.get(f"nodes/{node['node']}/lxc/{lxc['vmid']}/config").items():
                    self.inventory.set_variable(lxc["name"], f"proxmox_{key}", val)

