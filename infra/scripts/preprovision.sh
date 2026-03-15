#!/usr/bin/env sh
set -eu

echo "Running preprovision setup..."

get_azd_value() {
  azd env get-value "$1" 2>/dev/null || true
}

set_azd_value() {
  azd env set "$1" "$2" >/dev/null
}

enable_auth="$(get_azd_value ENABLE_AUTH)"
if [ "$enable_auth" = "true" ]; then
  echo
  echo "Entra ID authentication is enabled"
  auth_client_id="$(get_azd_value AUTH_CLIENT_ID)"
  auth_tenant_id="$(get_azd_value AUTH_TENANT_ID)"
  if [ -z "$auth_client_id" ]; then
    echo "WARNING: ENABLE_AUTH is true but AUTH_CLIENT_ID is not set"
  else
    echo "  Client ID: $auth_client_id"
    echo "  Tenant ID: ${auth_tenant_id:-"(deployment tenant)"}"
  fi
fi

echo
echo "Getting local developer object ID for Cosmos DB access..."
signed_in_user="$(az ad signed-in-user show --query id -o tsv 2>/dev/null || true)"
if [ -n "$signed_in_user" ]; then
  set_azd_value LOCAL_DEVELOPER_OBJECT_ID "$signed_in_user"
  echo "  LOCAL_DEVELOPER_OBJECT_ID set"
else
  set_azd_value LOCAL_DEVELOPER_OBJECT_ID ""
  echo "  WARNING: Could not determine LOCAL_DEVELOPER_OBJECT_ID"
fi

postgres_admin_login="$(get_azd_value POSTGRES_ADMIN_LOGIN)"
if [ -z "$postgres_admin_login" ]; then
  postgres_admin_login="agentmemoryadmin"
  set_azd_value POSTGRES_ADMIN_LOGIN "$postgres_admin_login"
  echo
  echo "Set default POSTGRES_ADMIN_LOGIN to $postgres_admin_login"
fi

postgres_location="$(get_azd_value POSTGRES_LOCATION)"
if [ -n "$postgres_location" ]; then
  echo
  echo "Using explicit POSTGRES_LOCATION override: $postgres_location"
else
  echo
  echo "POSTGRES_LOCATION not set; PostgreSQL will use AZURE_LOCATION."
fi

postgres_admin_password="$(get_azd_value POSTGRES_ADMIN_PASSWORD)"
if [ -z "$postgres_admin_password" ]; then
  generated_password="$(python - <<'PY'
import secrets
print(secrets.token_urlsafe(32) + "9!")
PY
)"
  set_azd_value POSTGRES_ADMIN_PASSWORD "$generated_password"
  echo "Generated and stored POSTGRES_ADMIN_PASSWORD in the local azd environment."
else
  echo
  echo "Using existing POSTGRES_ADMIN_PASSWORD from azd env."
fi

echo
echo "Detecting public IPv4 address for PostgreSQL firewall..."
local_public_ip="$(python - <<'PY'
import urllib.request

try:
    with urllib.request.urlopen("https://api.ipify.org", timeout=10) as response:
        print(response.read().decode().strip())
except Exception:
    print("")
PY
)"
set_azd_value LOCAL_DEVELOPER_PUBLIC_IP "$local_public_ip"
if [ -n "$local_public_ip" ]; then
  echo "  LOCAL_DEVELOPER_PUBLIC_IP set to $local_public_ip"
else
  echo "  WARNING: Could not determine public IP address"
fi

echo
echo "Preprovision setup complete!"
