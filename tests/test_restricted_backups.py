"""Tests for restricted user backup functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from io import BytesIO

# Mock the storage decorators and settings
with patch('api.storage.restricted_users.BACKUP_SSH_CONFIG', 'test-config'):
  from api.storage.restricted_users import (
    list_user_backups,
    get_user_backup_file,
    get_user_backup_file_size,
    get_user_backup_info,
  )


class TestRestrictedUserBackups:
  """Test restricted user backup functions."""

  @patch('api.storage.restricted_users.subprocess.run')
  def test_list_user_backups(self, mock_run):
    """Test listing user backups."""
    # Mock successful subprocess call
    mock_run.return_value = Mock(
      returncode=0,
      stdout='backup_2024_01_15.tar.gz\nbackup_2024_02_15.tar.gz\n',
    )

    backups = list_user_backups('test_user')

    assert len(backups) == 2
    assert 'backup_2024_01_15.tar.gz' in backups[0]
    assert 'backup_2024_02_15.tar.gz' in backups[1]

  @patch('api.storage.restricted_users.subprocess.run')
  def test_list_user_backups_empty(self, mock_run):
    """Test listing backups when none exist."""
    mock_run.return_value = Mock(returncode=0, stdout='')

    backups = list_user_backups('test_user')

    assert len(backups) == 0

  @patch('api.storage.restricted_users.subprocess.run')
  def test_list_user_backups_with_subfolder(self, mock_run):
    """Test listing backups in a subfolder."""
    mock_run.return_value = Mock(
      returncode=0,
      stdout='sub_backup_1.tar.gz\n',
    )

    backups = list_user_backups('test_user', subfolder='archived')

    # Verify the path includes the subfolder
    call_args = mock_run.call_args[0][0]
    assert 'archived' in ' '.join(call_args)

  def test_get_user_backup_file_invalid_filename(self):
    """Test that directory traversal attempts are blocked."""
    with pytest.raises(ValueError, match='path separators not allowed'):
      get_user_backup_file('test_user', '../../../etc/passwd')

    with pytest.raises(ValueError, match='path separators not allowed'):
      get_user_backup_file('test_user', 'sub\\folder\\file.tar.gz')

    with pytest.raises(ValueError, match='path separators not allowed'):
      get_user_backup_file('test_user', 'file with ../ in name.tar.gz')

  @patch('api.storage.restricted_users.subprocess.run')
  def test_get_user_backup_file(self, mock_run):
    """Test downloading a backup file."""
    expected_content = b'test backup content'
    mock_run.return_value = Mock(returncode=0, stdout=expected_content)

    content = get_user_backup_file('test_user', 'backup.tar.gz')

    assert content == expected_content

  @patch('api.storage.restricted_users.subprocess.run')
  def test_get_user_backup_file_not_found(self, mock_run):
    """Test downloading a non-existent file."""
    mock_run.return_value = Mock(returncode=1)

    with pytest.raises(FileNotFoundError):
      get_user_backup_file('test_user', 'nonexistent.tar.gz')

  @patch('api.storage.restricted_users.subprocess.run')
  def test_get_user_backup_file_size(self, mock_run):
    """Test getting file size without download."""
    mock_run.return_value = Mock(returncode=0, stdout='1048576\n')

    size = get_user_backup_file_size('test_user', 'backup.tar.gz')

    assert size == 1048576  # 1 MB

  @patch('api.storage.restricted_users.subprocess.run')
  def test_get_user_backup_file_size_not_found(self, mock_run):
    """Test getting size of non-existent file."""
    mock_run.return_value = Mock(returncode=0, stdout='')

    size = get_user_backup_file_size('test_user', 'nonexistent.tar.gz')

    assert size == 0

  @patch('api.storage.restricted_users.get_user_backup_file_size')
  @patch('api.storage.restricted_users.list_user_backups')
  def test_get_user_backup_info(self, mock_list, mock_size):
    """Test getting aggregate backup info."""
    mock_list.return_value = [
      '/backup/users/test_user/backup/backup_1.tar.gz',
      '/backup/users/test_user/backup/backup_2.tar.gz',
    ]
    mock_size.side_effect = [1048576, 2097152]  # 1 MB, 2 MB

    info = get_user_backup_info('test_user')

    assert info['username'] == 'test_user'
    assert info['total_files'] == 2
    assert info['total_size'] == 3145728  # 3 MB
    assert info['total_size_mb'] == 3.0
    assert len(info['files']) == 2
    assert info['files'][0]['filename'] == 'backup_1.tar.gz'
    assert info['files'][0]['size_mb'] == 1.0


class TestRestrictedBackupsAPI:
  """Test Flask API endpoints."""

  @pytest.fixture
  def client(self):
    """Create a Flask test client."""
    from flask import Flask
    from api.users.restricted_backups import init_restricted_backups_api

    app = Flask(__name__)
    app.config['TESTING'] = True
    init_restricted_backups_api(app)

    return app.test_client()

  def test_list_endpoint_missing_username(self, client):
    """Test /list endpoint without username."""
    response = client.get('/api/restricted-backups/list')
    assert response.status_code == 400
    assert 'username' in response.get_json()['error']

  @patch('api.users.restricted_backups.list_user_backups')
  def test_list_endpoint(self, mock_list, client):
    """Test /list endpoint with valid username."""
    mock_list.return_value = [
      '/backup/users/test_user/backup/backup_1.tar.gz',
    ]

    response = client.get('/api/restricted-backups/list?username=test_user')
    assert response.status_code == 200
    data = response.get_json()
    assert data['username'] == 'test_user'
    assert len(data['files']) == 1

  def test_info_endpoint_missing_username(self, client):
    """Test /info endpoint without username."""
    response = client.get('/api/restricted-backups/info')
    assert response.status_code == 400

  @patch('api.users.restricted_backups.get_user_backup_info')
  def test_info_endpoint(self, mock_info, client):
    """Test /info endpoint with valid username."""
    mock_info.return_value = {
      'username': 'test_user',
      'total_files': 2,
      'total_size': 3145728,
      'total_size_mb': 3.0,
      'files': [],
    }

    response = client.get('/api/restricted-backups/info?username=test_user')
    assert response.status_code == 200
    data = response.get_json()
    assert data['username'] == 'test_user'
    assert data['total_files'] == 2

  def test_download_endpoint_missing_params(self, client):
    """Test /download endpoint without required params."""
    response = client.get('/api/restricted-backups/download')
    assert response.status_code == 400
    assert 'username' in response.get_json()['error']

    response = client.get('/api/restricted-backups/download?username=test_user')
    assert response.status_code == 400
    assert 'filename' in response.get_json()['error']

  @patch('api.users.restricted_backups.get_user_backup_file')
  def test_download_endpoint(self, mock_download, client):
    """Test /download endpoint with valid params."""
    mock_download.return_value = b'test backup content'

    response = client.get(
      '/api/restricted-backups/download?username=test_user&filename=backup.tar.gz'
    )
    assert response.status_code == 200
    assert response.get_data() == b'test backup content'

  @patch('api.users.restricted_backups.get_user_backup_file')
  def test_download_endpoint_not_found(self, mock_download, client):
    """Test /download endpoint when file not found."""
    mock_download.side_effect = FileNotFoundError('File not found')

    response = client.get(
      '/api/restricted-backups/download?username=test_user&filename=nonexistent.tar.gz'
    )
    assert response.status_code == 404


if __name__ == '__main__':
  pytest.main([__file__])
