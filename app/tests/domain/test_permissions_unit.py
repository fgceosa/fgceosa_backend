import pytest
from unittest.mock import MagicMock
from app.utils.permissions import user_has_permission, user_has_role

class MockUser:
    def __init__(self, id, is_superuser=False):
        self.id = id
        self.is_superuser = is_superuser

def test_superuser_has_all_permissions():
    """Superusers bypass all permission checks."""
    mock_session = MagicMock()
    super_user = MockUser(id=1, is_superuser=True)
    
    assert user_has_permission(mock_session, super_user, "any:permission") is True
    assert user_has_permission(mock_session, super_user, "admin:delete_everything") is True

def test_user_has_permission_logic():
    """Test standard permission resolution (mocking DB calls)."""
    mock_session = MagicMock()
    normal_user = MockUser(id=2, is_superuser=False)
    
    # Mock get_user_permissions to return specific permissions
    with (
        pytest.MonkeyPatch.context() as mp 
    ):
        mp.setattr("app.utils.permissions.get_user_permissions", lambda s, u: ["chat:read", "workspace:write"])
        
        assert user_has_permission(mock_session, normal_user, "chat:read") is True
        assert user_has_permission(mock_session, normal_user, "workspace:write") is True
        assert user_has_permission(mock_session, normal_user, "admin:delete") is False

def test_user_has_role_logic():
    """Test standard role resolution."""
    mock_session = MagicMock()
    normal_user = MockUser(id=3, is_superuser=False)
    
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.utils.permissions.get_user_roles", lambda s, u: ["member", "editor"])
        
        assert user_has_role(mock_session, normal_user, "member") is True
        assert user_has_role(mock_session, normal_user, "editor") is True
        assert user_has_role(mock_session, normal_user, "admin") is False
