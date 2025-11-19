# Entra ID Authentication Setup Guide

## Your App Registration Details

**Display name**: contoso_agent_demo  
**Application (client) ID**: `a72cc4b5-df6b-41c4-b5d2-aca151b6838d`  
**Directory (tenant) ID**: `16b3c013-d300-468d-ac64-7eda0820b6d3`  

## Deployment Steps

### Step 1: Configure azd Environment

```powershell
cd agent_memory

# Enable authentication
azd env set ENABLE_AUTH true

# Set your app registration details
azd env set AUTH_CLIENT_ID a72cc4b5-df6b-41c4-b5d2-aca151b6838d
azd env set AUTH_TENANT_ID 16b3c013-d300-468d-ac64-7eda0820b6d3
```

### Step 2: Deploy Infrastructure

```powershell
azd up
```

The deployment will:
- Provision all Azure resources
- Configure Easy Auth on Container Apps
- Show you the redirect URI to add

### Step 3: Configure Redirect URI in Entra ID

After deployment completes, you'll see:

```
========================================
  ENTRA ID CONFIGURATION REQUIRED
========================================

Add this Redirect URI to your Entra ID app registration:

  https://your-app-name-dev.region.azurecontainerapps.io/.auth/login/aad/callback
```

**Add the Redirect URI**:

1. Go to [Azure Portal](https://portal.azure.com)
2. Switch to the tenant: **16b3c013-d300-468d-ac64-7eda0820b6d3**
3. Navigate to: **Entra ID** > **App registrations** > **contoso_agent_demo**
4. Click: **Authentication**
5. Under **Platform configurations**, click **Add a platform**
6. Select **Web**
7. Paste the redirect URI from the deployment output
8. Optional: Check **ID tokens** if you need them
9. Click **Configure**
10. Click **Save**

### Step 4: Test Authentication

1. Open the demo URL (shown in deployment output)
2. You should be redirected to Microsoft login
3. Sign in with an account from the tenant `16b3c013-d300-468d-ac64-7eda0820b6d3`
4. After successful login, you'll be redirected to the demo app

## How It Works

### Easy Auth Flow

```
User → Demo URL
  ↓
Container Apps checks if authenticated
  ↓ (No)
Redirect to: login.microsoftonline.com/16b3c013-d300-468d-ac64-7eda0820b6d3
  ↓
User signs in with Entra ID
  ↓
Redirect back to: https://your-app/.auth/login/aad/callback
  ↓
Container Apps validates token
  ↓
User accesses demo app (authenticated)
```

### What Easy Auth Provides

✅ Automatic redirect to login page  
✅ Token validation  
✅ Session management  
✅ User identity in request headers  
✅ No code changes needed  
✅ Built-in logout endpoint: `/.auth/logout`  

### Security Features

- **Cross-tenant support**: App registered in tenant A, deployed in tenant B
- **Audience validation**: Only tokens for your client ID accepted
- **HTTPS enforced**: No insecure connections allowed
- **Session cookies**: Secure, HTTP-only cookies for session management

## Accessing User Identity in Code

If your demo app needs the authenticated user's information:

```python
import os
import json
import base64

# Get user identity from Easy Auth header
def get_user_identity():
    # Header set by Container Apps Easy Auth
    principal_header = os.environ.get('X-MS-CLIENT-PRINCIPAL')
    
    if not principal_header:
        return None
    
    # Decode base64
    decoded = base64.b64decode(principal_header)
    principal = json.loads(decoded)
    
    return {
        'user_id': principal['userId'],
        'name': principal.get('claims', [{}])[0].get('name'),
        'email': principal.get('claims', [{}])[0].get('email'),
        'roles': principal.get('claims', [{}])[0].get('roles', [])
    }
```

In Streamlit:
```python
import streamlit as st

user = get_user_identity()
if user:
    st.write(f"Welcome, {user['name']}!")
else:
    st.warning("Not authenticated")
```

## Troubleshooting

### "Redirect URI mismatch" Error

**Problem**: After login, you see an error about redirect URI mismatch.

**Solution**: 
1. Check the exact URL in the error message
2. Go to Entra ID app registration > Authentication
3. Ensure the redirect URI matches exactly (including https://)
4. Must end with: `/.auth/login/aad/callback`

### "Invalid audience" Error

**Problem**: Token validation fails.

**Solution**:
1. Verify `AUTH_CLIENT_ID` matches your app registration
2. Check `AUTH_TENANT_ID` is correct
3. Redeploy: `azd up`

### Users from Wrong Tenant Can't Sign In

**Problem**: Users from your deployment tenant try to sign in but can't.

**Solution**: This is expected! Your app registration is in tenant `16b3c013-d300-468d-ac64-7eda0820b6d3`.

Options:
1. Create guest users in that tenant
2. Change app to multi-tenant
3. Create new app registration in deployment tenant

### Disable Authentication

If you need to temporarily disable auth:

```powershell
azd env set ENABLE_AUTH false
azd up
```

## Advanced Configuration

### Multi-Tenant Support

To allow users from any tenant:

1. In Entra ID app registration:
   - Change **Supported account types** to "Any organizational directory"
2. Update deployment:
   ```powershell
   azd env set AUTH_TENANT_ID common
   azd up
   ```

### Custom Login Page

Easy Auth supports custom login flows. See:
https://learn.microsoft.com/azure/container-apps/authentication

### API Authentication

If exposing APIs, configure API permissions:
1. Entra ID > App registrations > contoso_agent_demo
2. Expose an API > Add a scope
3. Configure API permissions for client apps

## Cost Impact

Easy Auth has **no additional cost** - it's included in Container Apps pricing.

## Next Steps

1. ✅ Deploy with `azd up`
2. ✅ Add redirect URI to Entra ID
3. ✅ Test authentication
4. 🔧 (Optional) Update demo code to use user identity
5. 🔧 (Optional) Configure additional security policies

## References

- [Container Apps Authentication](https://learn.microsoft.com/azure/container-apps/authentication)
- [Entra ID App Registration](https://learn.microsoft.com/entra/identity-platform/quickstart-register-app)
- [Easy Auth Overview](https://learn.microsoft.com/azure/app-service/overview-authentication-authorization)
