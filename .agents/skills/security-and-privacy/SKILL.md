---
name: security-and-privacy
description: SSRF prevention, private network isolation, privacy boundaries, and secret protection.
---

# Security and Privacy Rules

## SSRF Guard Rules
- Strict URL validation before any network request:
  - Allowed schemes: `http` and `https` only. Disallow `file://`, `ftp://`, `gopher://`, `dict://`.
  - DNS resolution check: Resolve hostname to all candidate IP addresses before connecting.
  - Forbidden IP ranges (IPv4 & IPv6):
    - Loopback: `127.0.0.0/8`, `::1`
    - Private networks: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
    - Carrier-grade NAT: `100.64.0.0/10`
    - Link-local: `169.254.0.0/16`, `fe80::/10`
    - Unique local: `fc00::/7`
    - Multicast & broadcast: `224.0.0.0/4`, `255.255.255.255/32`, `ff00::/8`
  - Cloud metadata endpoints: Explicitly block `169.254.169.254` and `metadata.google.internal`.

## Privacy & Profile Protection
- User profile data (name, college, company, income) strictly stored locally in client `localStorage`.
- Never transmit user's name, college, or company to external LLM APIs.
- Queries composed for LLM extraction use only abstract category, level, and general goal.

## Input Sanitization & Secrets
- Never log API keys, Bearer tokens, or raw credentials.
- Limit user-submitted URLs to valid RFC 3986 format with max 2048 characters.
- Restrict file upload / text paste sizes to maximum 2MB per document.
