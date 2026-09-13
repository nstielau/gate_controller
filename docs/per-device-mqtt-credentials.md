# Future plan: per-device MQTT credentials

The current system uses one MQTT username and password for the XIAO and the
Firebase callable function. This is adequate for the first gate, but a leaked
device file would expose the shared account. The next security improvement is
to issue a separate broker identity for every device.

## Proposed design

1. Give each device a stable ID, such as `b3640c` (the XIAO chip suffix).
2. During enrollment, generate a random password and create an EMQX built-in
   authentication user named `xiao-b3640c`.
3. Add least-privilege authorization rules for that identity:
   - Subscribe to `gate/v1/devices/b3640c/command`.
   - Publish to `gate/v1/devices/b3640c/status`.
   - Deny unrelated topics and administrative operations.
4. Write the resulting username/password to the device's `settings.toml` over
   USB. Keep the broker CA on the device for verified TLS.
5. Store the enrollment record and a credential version in Firestore. Keep the
   EMQX deployment API App Secret only in Firebase Secret Manager.

EMQX provides HTTP API operations for users in its built-in password database.
The likely v5 endpoint is
`/api/v5/authentication/password_based%3Abuilt_in_database/users`; the exact
path and permissions must be confirmed against the deployment before coding.

## Enrollment and rotation

Enrollment should be an administrator-only Firebase operation. It should
validate the device ID, create the EMQX user, create its topic ACL, and return
the credentials only once for immediate USB provisioning. Re-enrollment should
disable the previous account before issuing a replacement. Lost or serviced
hardware should be revocable without changing other gates.

The browser must never call EMQX directly or receive the deployment App
Secret. Firebase Secret Manager should hold the EMQX API credentials, and the
callable function should log only the device ID and operation result, never a
password.

## Prerequisites and checks

- Confirm whether this deployment plan exposes the user and authorization API;
  EMQX Serverless has fewer customization options than Dedicated deployments.
- Create a narrowly scoped EMQX deployment API key if the plan supports it.
- Test create, ACL, connect, publish, subscribe, revoke, and rotate operations
  on a synthetic device topic before touching the gate.
- Update firmware provisioning and `make deploy` to select credentials by
  device ID, while retaining a safe migration path from the shared account.

Until these checks are complete, keep the existing shared account and rotate
it if the board or its USB-readable settings are exposed.
