# Admin device last-seen and versions

Approved scope: store and show last-seen/version information in Administration.
No alerts, new device polling, OTA enablement or gate commands.

Existing authenticated maintenance messages persist app/base versions and receipt
time; existing OTA reports persist a separate version pair and receipt time.
Persist common lastSeenAtMs on authenticated maintenance/OTA API contact. Use
server time and preserve a newer stored timestamp during transactional retries.
Admin overview exposes an allowlisted observation: lastSeenAtMs (latest contact,
with existing-report fallback) and firmware (latest report's appVersion,
baseVersion, reportedAtMs). Never mix pairs, infer a base from a target, or claim
that last HTTP contact establishes current MQTT/physical gate state. Preserve
independent OTA target/state. Missing/invalid data stays explicitly unreported.

Show last-seen local date/time and app/base versions on every device card,
including non-OTA boards. Keep manual Refresh administration behavior and existing
reset-only polling. Legacy data works without a migration or USB installation.
No secrets in the observation DTO; existing admin authentication remains required.

1. Add failing backend, real-local-emulator and mobile-browser regressions for
   persisted contact times, newest snapshot selection, legacy/missing data,
   no mixed bases, secret exclusion, and refresh without commands.
2. Implement server observation projection and common contact timestamp writes;
   add compact last-seen/version rows to the existing admin cards.
3. Run full web tests, host checks and hooks. Review diff. Deploy Functions,
   generated Hosting and rules; verify all entry/auth/API paths and the attached
   board's naturally arriving metadata without resetting or commanding it.
4. Update operational docs, commit and push. Leave scratch .superpowers intact.


Added user scope: the website QR shortcut keeps the normal dark Drawbridge
header and centers the QR below it. No hold countdown, reboot selector or button
hint appears in that view. D0/D1 return/20-second timeout and D2 behavior remain;
the ordinary status screen is unchanged. This explicitly authorized USB display
base change requires base 1.0.14, its note, host display/layout checks, intentional
idle USB installation, native rendering checks and passive hardware observation.
