
class ModuleDocFragment:

    DOCUMENTATION = """
    options:
      host:
        description: Hostname for Proxmox API url
        required: yes
        type: str
        env:
          - name: PROXMOX_HOST
        vars:
          - name: ansible_proxmox_host
        ini:
          - section: proxmox
            key: host
      user:
        description: Proxmox user to authenticate as
        required: yes
        type: str
        env:
          - name: PROXMOX_USER
        vars:
          - name: ansible_proxmox_user
        ini:
          - section: proxmox
            key: user
      token:
        description: Name of token to authenticate with
        required: yes
        type: str
        env:
          - name: PROXMOX_TOKEN
        vars:
          - name: ansible_proxmox_token
        ini:
          - section: proxmox
            key: token
      secret:
        description: Token value to authenticate with
        required: yes
        type: str
        env:
          - name: PROXMOX_SECRET
        vars:
          - name: ansible_proxmox_secret
        ini:
          - section: proxmox
            key: secret
      verify_ssl:
        description: Set C(no) to skip certificate validation
        default: yes
        type: bool
        vars:
          - name: ansible_proxmox_verify_ssl
        ini:
          - section: proxmox
            key: verify_ssl
    """
