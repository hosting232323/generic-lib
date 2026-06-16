import os
import subprocess
import tempfile

from ..settings import BACKUP_SSH_CONFIG, BACKUP_SSH_HOSTNAME


def _ssh_run(script: str) -> subprocess.CompletedProcess:
  if not BACKUP_SSH_CONFIG:
    raise ValueError('BACKUP_SSH_CONFIG non configurato')

  return subprocess.run(
    ['ssh', BACKUP_SSH_CONFIG, 'sudo bash -s'],
    input=script,
    check=True,
    capture_output=True,
    text=True,
  )


def _ssh_cmd(cmd: str) -> subprocess.CompletedProcess:
  if not BACKUP_SSH_CONFIG:
    raise ValueError('BACKUP_SSH_CONFIG non configurato')

  return subprocess.run(
    ['ssh', BACKUP_SSH_CONFIG, cmd],
    check=True,
    capture_output=True,
    text=True,
  )


def create_client_user(username: str, project_name: str) -> dict:
  """
  Crea un utente SFTP-only su rattata con accesso read-only a /mnt/<project_name>/.
  Ritorna la chiave privata da consegnare al cliente e le istruzioni di connessione.
  """
  if not BACKUP_SSH_HOSTNAME:
    raise ValueError('BACKUP_SSH_HOSTNAME non configurato')

  chroot_dir = f'/mnt/{project_name}'

  with tempfile.TemporaryDirectory() as tmpdir:
    key_path = os.path.join(tmpdir, 'id_ed25519')
    subprocess.run(
      ['ssh-keygen', '-t', 'ed25519', '-f', key_path, '-N', '', '-C', f'{username}@rattata'],
      check=True,
      capture_output=True,
    )
    with open(key_path) as f:
      private_key = f.read()
    with open(f'{key_path}.pub') as f:
      public_key = f.read().strip()

  script = f"""
set -e

# Crea utente senza shell se non esiste
id '{username}' &>/dev/null || useradd -r -s /usr/sbin/nologin -d /home/{username} '{username}'

# ChrootDirectory deve essere owned root (requisito sshd)
mkdir -p /home/{username}
chown root:root /home/{username}
chmod 755 /home/{username}

# Setup .ssh
mkdir -p /home/{username}/.ssh
chown {username}:{username} /home/{username}/.ssh
chmod 700 /home/{username}/.ssh

# Authorized key
echo '{public_key}' > /home/{username}/.ssh/authorized_keys
chown {username}:{username} /home/{username}/.ssh/authorized_keys
chmod 600 /home/{username}/.ssh/authorized_keys

# Assicura che la cartella dati esista con permessi corretti per chroot
mkdir -p {chroot_dir}
chown root:root {chroot_dir}
chmod 755 {chroot_dir}

# Permessi read-only per il client user (setfacl se disponibile, altrimenti other+r)
if command -v setfacl &>/dev/null; then
  setfacl -R -m u:{username}:r-X {chroot_dir}
  setfacl -R -d -m u:{username}:r-X {chroot_dir}
else
  find {chroot_dir} -type f -exec chmod o+r {{}} \\;
  find {chroot_dir} -type d -exec chmod o+rx {{}} \\;
fi

# Drop-in sshd per questo utente
mkdir -p /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/sftp-{username}.conf << 'SSHEOF'
Match User {username}
    ChrootDirectory {chroot_dir}
    ForceCommand internal-sftp
    AllowTcpForwarding no
    X11Forwarding no
    PermitTunnel no
SSHEOF

# Ricarica sshd
systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
"""

  _ssh_run(script)

  hostname = BACKUP_SSH_HOSTNAME
  return {
    'username': username,
    'project_name': project_name,
    'chroot_dir': chroot_dir,
    'private_key': private_key,
    'connection': {
      'sftp_command': (
        f'sftp -i id_ed25519_{username}'
        f' -o "ProxyCommand cloudflared access ssh --hostname {hostname}"'
        f' {username}@{hostname}'
      ),
      'scp_example': (
        f'scp -i id_ed25519_{username}'
        f' -o "ProxyCommand cloudflared access ssh --hostname {hostname}"'
        f' {username}@{hostname}:/file.pdf ./file.pdf'
      ),
    },
  }


def delete_client_user(username: str) -> None:
  """Rimuove l'utente client e la sua configurazione sshd da rattata."""
  script = f"""
set -e
userdel -r '{username}' 2>/dev/null || true
rm -f /etc/ssh/sshd_config.d/sftp-{username}.conf
systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
"""
  _ssh_run(script)
