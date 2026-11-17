# Multiple saved Wi-Fi networks

Approved workflow: hold Feather D1 during startup to open the local setup AP;
manage up to five saved networks without exposing passwords. No saved networks
opens setup automatically. Saved-network failures retry station mode, never
silently open an AP. Keep gate inactive during explicit setup, preserve XIAO
pins/OTA, registration identity and legacy GATE1/GATE2/GATE3 records.

Implementation:
1. Test pure profile migration/add/update/forget, validation and ordering.
2. Test runtime fallthrough, identity preservation and D1 input polarity.
3. Implement profile helpers, bounded NVM storage, portal and startup entry.
4. Update display instructions, base version/note and operations instructions.
5. Run host checks/review; USB deploy preserving NVM, then passive hardware check.

NVM uses up to 4096 available bytes with the existing length-prefixed GATE3
record. Existing shorter records remain readable. Writes validate capacity
before touching NVM. Last-connected network is persisted only when it changes.
