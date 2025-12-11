from ansible.plugins.inventory import BaseInventoryPlugin, Constructable
from ansible.errors import AnsibleError, AnsibleAuthenticationFailure
from ansible.module_utils.urls import open_url
from urllib.error import HTTPError
import json

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

    def _api(self, method, path, **kwargs):


        host = self.get_option("host")
        url = f"https://{host}:8006/api2/json{path}"
        verify_ssl = self.get_option("verify_ssl")
        body = json.dumps(kwargs) if kwargs else None
        try:
            r = open_url (
                    url,
                    method=method,
                    data=body,
                    headers=self.request_headers,
                    validate_certs=verify_ssl )
        except HTTPError as e:
            if e.code == 401:
                raise AnsibleAuthenticationFailure(e.reason)
            raise AnsibleConnectionFailure(e.reason)
        return json.loads(r.read().decode("utf-8"))["data"]

    def _post(self, path, **kwargs):

        return self._api("POST", path, **kwargs)

    def _get(self, path, **kwargs):

        return self._api("GET", path, **kwargs)

    def _put(self, path, **kwargs):

        return self._api("PUT", path, **kwargs)

    def _delete(self, path, **kwargs):

        return self._api("DELETE", path, **kwargs)

    def verify_file(self, path):

        return super().verify_file(path) and path.endswith(".proxmox.yml")

    def parse(self, inventory, loader, path, cache):

        super().parse(inventory, loader, path, cache)

        self._read_config_data(path)

        token_name = self.get_option("token")
        token_value = self.get_option("secret")
        user = self.get_option("user")
        self.request_headers = {
                "Authorization": f"PVEAPIToken={user}!{token_name}={token_value}",
                "Content-Type": "application/json"
        }

        hosts =  [
            { "vmid" : int(host["vmid"]),
              "name" : host["name"],
              "status" : host["status"],
              "node" : node["node"],
              "type" : proxmox_type }
            for proxmox_type in ("qemu", )
            for node in self._get("/nodes")
            for host in self._get(f"/nodes/{node['node']}/{proxmox_type}") 
            if not host.get("template") ]

        for host in hosts:
            self.inventory.add_host(host["name"])
            if self.get_option("config_facts"):
                config = self._get(f"/nodes/{host['node']}/{host['type']}/{host['vmid']}/config")
                host.update(config)
            if host["type"] == "qemu" and self.get_option("agent_facts") and host["status"] == "running":
                ifaces = self._get(f"/nodes/{host['node']}/qemu/{host['vmid']}/agent/network-get-interfaces")["result"]
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

