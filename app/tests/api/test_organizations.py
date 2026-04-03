import pytest
from httpx import AsyncClient
from app.core.config import settings
from app.models import User, Organization
import uuid

@pytest.mark.asyncio
async def test_get_my_organization(client: AsyncClient, org_super_admin: User):
    """Test retrieving 'my' organization details."""
    from app.tests.conftest import get_auth_headers
    headers = get_auth_headers(org_super_admin)
    
    # Path: GET /organizations/me
    response = await client.get(f"{settings.API_V1_STR}/organizations/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Org"
    assert "id" in data

@pytest.mark.asyncio
async def test_get_organization_team_members(client: AsyncClient, org_super_admin: User):
    """Test listing team members of an organization."""
    from app.tests.conftest import get_auth_headers
    headers = get_auth_headers(org_super_admin)
    
    # First get org_id
    org_response = await client.get(f"{settings.API_V1_STR}/organizations/me", headers=headers)
    org_id = org_response.json()["id"]
    
    # Path: GET /organizations/{org_id}/team
    response = await client.get(f"{settings.API_V1_STR}/organizations/{org_id}/team", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert len(data["list"]) >= 1 # Just the owner/OSA

@pytest.mark.asyncio
async def test_invite_member_to_organization(client: AsyncClient, org_super_admin: User, normal_user: User):
    """Test inviting a member to an organization."""
    from app.tests.conftest import get_auth_headers
    headers = get_auth_headers(org_super_admin)
    
    # Get org_id
    org_response = await client.get(f"{settings.API_V1_STR}/organizations/me", headers=headers)
    org_id = org_response.json()["id"]
    
    # Path: POST /organizations/{org_id}/team/invite
    invite_data = {
        "email": normal_user.email,
        "role": "org_member"
    }
    
    response = await client.post(
        f"{settings.API_V1_STR}/organizations/{org_id}/team/invite",
        json=invite_data,
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == normal_user.email
    assert data["role"] == "org_member"

@pytest.mark.asyncio
async def test_update_member_role(client: AsyncClient, org_super_admin: User, normal_user: User):
    """Test updating a member's role."""
    from app.tests.conftest import get_auth_headers
    headers = get_auth_headers(org_super_admin)
    
    # Get org_id
    org_response = await client.get(f"{settings.API_V1_STR}/organizations/me", headers=headers)
    org_id = org_response.json()["id"]
    
    # First invite
    invite_resp = await client.post(
        f"{settings.API_V1_STR}/organizations/{org_id}/team/invite",
        json={"email": normal_user.email, "role": "org_member"},
        headers=headers
    )
    # The invite response actually returns the OrganizationMemberPublic which has CACHEABLE 'id' (the member ID)
    member_id = invite_resp.json()["id"]
    
    # Path: PUT /organizations/{org_id}/team/{member_id}
    update_data = {"role": "org_admin"}
    response = await client.put(
        f"{settings.API_V1_STR}/organizations/{org_id}/team/{member_id}",
        json=update_data,
        headers=headers
    )
    assert response.status_code == 200
    assert response.json()["role"] == "org_admin"

@pytest.mark.asyncio
async def test_admin_list_organizations(client: AsyncClient, platform_super_admin: User):
    """Test platform admin listing all organizations."""
    from app.tests.conftest import get_auth_headers
    headers = get_auth_headers(platform_super_admin)
    
    # Path: GET /admin/organizations
    response = await client.get(f"{settings.API_V1_STR}/admin/organizations", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert isinstance(data["list"], list)

@pytest.mark.asyncio
async def test_admin_delete_organization(client: AsyncClient, platform_super_admin: User, org_super_admin: User):
    """Test platform admin deleting an organization."""
    from app.tests.conftest import get_auth_headers
    # Login as OSA to find their org ID
    osa_headers = get_auth_headers(org_super_admin)
    org_response = await client.get(f"{settings.API_V1_STR}/organizations/me", headers=osa_headers)
    org_id = org_response.json()["id"]
    
    # Login as PSA to delete
    psa_headers = get_auth_headers(platform_super_admin)
    
    # Path: DELETE /admin/organizations/{org_id}
    response = await client.delete(f"{settings.API_V1_STR}/admin/organizations/{org_id}", headers=psa_headers)
    assert response.status_code == 200
    assert "deleted successfully" in response.json()["message"].lower()
