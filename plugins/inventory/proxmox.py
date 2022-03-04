from ansible.plugins.inventory import BaseInventoryPlugin, Constructable
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
extends_documentation_fragment:
  - pgsocks.proxmox.proxmox
  - constructed
options:
  plugin:
    description: Always C(pgsocks.proxmox.proxmox)
    required: yes
    type: str
    choices:
      - pgsocks.proxmox.proxmox
  config_facts:
    description: Gather host config facts for LXC and QEMU guests.
    type: bool
    default: yes
  agent_facts:
    description: Gather QEMU guest agent facts.
    type: bool
    default: no
  pass_connection_options:
    description:
      - Pass the connection options to each host's vars
      - Convenient for connections or actions that need them.
      - To avoid leaking sensitive data, this must be enabled conciously.
    type: bool
    default: no
"""

class InventoryModule(BaseInventoryPlugin, Constructable):

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

        hosts =  [
            { "vmid" : int(host["vmid"]),
              "name" : host["name"],
              "status" : host["status"],
              "node" : node["node"],
              "type" : proxmox_type }
            for proxmox_type in ("qemu", "lxc")
            for node in session.get("nodes")
            for host in session.get(f"nodes/{node['node']}/{proxmox_type}") 
            if not host["template"] ]

        for host in hosts:
            self.inventory.add_host(host["name"])
            if self.get_option("config_facts"):
                config = session.get(f"nodes/{host['node']}/{host['type']}/{host['vmid']}/config")
                host.update(config)
            if host["type"] == "qemu" and self.get_option("agent_facts") and host["status"] == "running":
                ifaces = session.get(f"nodes/{host['node']}/qemu/{host['vmid']}/agent/network-get-interfaces")["result"]
                ifaces = [{"name" : iface["name"], "hwaddr" : iface.get("hardware-address", ""), "addresses" : [f"{ip['ip-address']}/{ip['prefix']}" for ip in iface.get("ip-addresses", [])]} for iface in ifaces]
                host["interfaces"] = ifaces
            for key, val in host.items():
                if key == "name":
                    continue
                # Fix disk images since they have no key
                if key.startswith(("rootfs", "virtio", "sata", "ide", "scsi")):
                    val = f"image={val}"
                # Fix qemu net devices since the model key is inconsistent
                if type(val) == str and "," in val:
                    val = dict(opt.split("=") for opt in val.split(",") if "=" in opt)
                    if key.startswith("net"):
                        ip = val.pop("ip", None)
                        if ip:
                            val["addresses"] = [ip]
                        for model in ["virtio", "e1000", "rtl8139", "vmxnet3"]:
                            mac = val.pop(model, None)
                            if mac:
                                val["hwaddr"] = mac
                                val["model"] = model
                        for iface in host.get("interfaces", []):
                            if iface["hwaddr"].lower() == val["hwaddr"].lower():
                                val.update(iface)
                self.inventory.set_variable(host["name"], f"proxmox_{key}", val)
            if self.get_option("pass_connection_options"):
                for option in ("host", "user", "token", "secret", "verify_ssl"):
                    self.inventory.set_variable (
                        host["name"],
                        f"ansible_proxmox_{option}",
                        self.get_option(option) )

            strict = self.get_option("strict")
            host_vars = self.inventory.get_host(host["name"]).get_vars()
            self._add_host_to_composed_groups(self.get_option("groups"), host_vars, host["name"], strict=strict)
            self._add_host_to_keyed_groups(self.get_option("keyed_groups"), host_vars, host["name"], strict=strict)
            self._set_composite_vars(self.get_option("compose"), host_vars, host["name"], strict=strict)

