# Web deletion request (store compliance companion)

**Status:** ARCHITECTURE · NON_SUBMISSION  
**Legal approval claimed:** NO

Apple requires a web-based account deletion path discoverable without installing the app.

## Surface

- Public URL placeholder: `https://app.nexus.example/account/delete`
- Must be linked from App Store listing privacy / support URL when submission is eventually authorized (not now)

## Flow

1. User opens web form (no app install required)
2. Provides account email + one-time verification code sent to that email
3. Optional: signed-in session cookie short-circuits email OTP
4. Creates same `DeletionRequest` resource as in-app path (`deletion_api_contract.yaml`)
5. Shows tracking page with `request_id` and status
6. Support escalation contact placeholder only (no fabricated support SLAs)

## Anti-abuse

- Rate-limit OTP
- CAPTCHA / bot resistance TBD before launch
- Do not expose whether an email exists beyond generic messaging where legally required to differ

## Ban reminder

Do not publish this URL as a live production customer portal from PUB-L CI.
