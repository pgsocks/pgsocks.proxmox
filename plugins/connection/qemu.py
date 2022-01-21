
DOCUMENTATION = """
name: qemu
short_description: Proxmox QEMU agent connection
description:
  - Execute Ansible tasks via QEMU agent connection in Proxmox API
extends_documentation_fragment: pgsocks.proxmox.proxmox
options:
  vmid:
    description: Agent hostname/vmid to connect to
    required: yes
    vars:
      - name: proxmox_vmid
  node:
    description: Proxmox node that hosts given agent
    required: yes
    vars:
      - name: proxmox_node
"""

try:
    import proxmoxer
    IMPORT_ERROR = False
except ImportError:
    IMPORT_ERROR = True

from ansible.errors import AnsibleError, AnsibleConnectionFailure
from ansible.plugins.connection import ConnectionBase
from ansible.plugins.shell.powershell import _parse_clixml
from ansible.module_utils._text import to_bytes, to_native, to_text
from ansible.utils.hashing import secure_hash
import os
import json
import re
import base64

class Connection(ConnectionBase):
    """ QEMU agent through Proxmox API connection """

    transport = "qemu"

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.proxmox = None
        self.node = None
        self.module_implementation_preferences = (".ps1", ".exe", "")
        self.allow_executable = False
        self.allow_extras = True

    def _connect(self):

        if IMPORT_ERROR:
            raise AnsibleError("This module requires Requests and Proxmoxer")

        if not getattr(self._shell, "_IS_WINDOWS", False):
            raise AnsibleConnectionFailure (
                f"{self.transport} currently only supports Windows" )

        self.session = proxmoxer.ProxmoxAPI (
            self.get_option("host"),
            user = self.get_option("user"),
            token_name = self.get_option("token"),
            token_value = self.get_option("secret"),
            verify_ssl = self.get_option("verify_ssl")
        )
        self.node = self.get_option("node")
        self.vmid = self.get_option("vmid")
        self.host = self._play_context.remote_addr

        return self

    def exec_command(self, cmd, in_data=None, sudoable=True):
        
        super().exec_command(cmd, in_data, sudoable)

        # Double encode command for safe API call
        cmd = self._shell._encode_script (
            cmd,
            as_list = False,
            strict_mode = False,
            preserve_rc = False )
        self._display.vvv(f"EXEC {cmd}", host=self.host)

        # POST execute request to Proxmox API
        proc = self.session.post (
            f"nodes/{self.node}/qemu/{self.vmid}/agent/exec",
            **{"command" : cmd, "input-data" : in_data} )

        # Poll process status for exit
        while True:
            res = self.session.get (
                f"nodes/{self.node}/qemu/{self.vmid}/agent/exec-status",
                pid = proc["pid"] )
            self._display.vvvv(f"EXEC polling {proc['pid']}", host=self.host)
            if res["exited"]:
                break

        # Clean and return process output
        stdout = to_bytes(res.get("out-data", ""))
        stderr = to_bytes(res.get("err-data", ""))
        exitcode = int(res.get("exitcode", 1))
        if stderr.startswith(b"#< CLIXML"):
            stderr = _parse_clixml(stderr)

        return exitcode, stdout, stderr

    def put_file(self, in_path, out_path):

        super().put_file(in_path, out_path)

        # Error out if source file does not exist
        if not os.path.exists(in_path):
            raise AnsibleError(f"{in_path} does not exist")

        # Escape remote path
        out_path = self._shell._escape(self._shell._unquote(out_path))
        self._display.vvv(f"PUT {in_path} => {out_path}", host=self.host)

        # Format script to assemble pieces of base64 encoded file
        append_script = f"""
            $path = '{out_path}'
            $bytes = [System.Convert]::FromBase64String($input)
            $fd = [System.IO.File]::OpenWrite($path)
            $fd.Seek(0, 2)
            $fd.Write($bytes, 0, $bytes.Length)
            $fd.Close()
        """
        append_cmd = self._shell._encode_script (
            append_script,
            as_list=False,
            strict_mode=False,
            preserve_rc=True )

        # Send base64 encoded parts of file to be assembled remotely
        with open(in_path, "rb") as f:
            BUFFER = 1024 * 32
            for chunk in iter(lambda: f.read(BUFFER), b''):
                content = base64.b64encode(chunk) + b"\r\n"
                self.exec_command(append_script, content, sudoable = False)

    def fetch_file(self, in_path, out_path):

        super().fetch_file(in_path, out_path)
        in_path = self._shell._escape(self._shell._unquote(in_path))
        self._display.vvv(f"FETCH {out_path} <= {in_path}", host=self.host)
        BUFFER = 1024 * 32
        script = """
            $path = '%(path)s'
            If (Test-Path -Path $path -PathType Leaf)
            {
                $buffer_size = %(buffer)d
                $offset = %(offset)d

                $stream = New-Object -TypeName IO.FileStream($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
                $stream.Seek($offset, [System.IO.SeekOrigin]::Begin) > $null
                $buffer = New-Object -TypeName byte[] $buffer_size
                $bytes_read = $stream.Read($buffer, 0, $buffer_size)
                if ($bytes_read -gt 0) {
                    $bytes = $buffer[0..($bytes_read - 1)]
                    [System.Convert]::ToBase64String($bytes)
                }
                $stream.Close() > $null
            }
            ElseIf (Test-Path -Path $path -PathType Container)
            {
                Write-Host "[DIR]";
            }
            Else
            {
                Write-Error "$path does not exist";
                Exit 1;
            }
        """
        with open(out_path, "wb") as f:
            offset = 0
            while True:
                cmd = self._shell._encode_script(script % {"buffer" : BUFFER, "path" : in_path, "offset" : offset}, as_list=False, preserve_rc=False)
                status, stdout, stderr = self.exec_command(cmd)
                if status != 0:
                    raise AnsiibleError(to_native(stderr))
                if stdout.strip() == "[DIR]":
                    data = None
                else:
                    data = base64.b64decode(stdout.strip())
                if data is None:
                    break
                else:
                    f.write(data)
                    if len(data) < BUFFER:
                        break
                    offset += len(data)

    def close(sef):
        self._connected = False
