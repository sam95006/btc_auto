# Age rating questionnaire — DRAFT

**Status:** ENGINEERING_DRAFT · NOT_LEGAL_ADVICE · NO_LEGAL_APPROVAL_CLAIMED  
**Submission authorized:** NO

## Anticipated rating posture (unvalidated)

| Platform | Draft target | Rationale (engineering) |
|----------|--------------|-------------------------|
| Apple | 17+ (Infrequent/Mild Mature/Suggestive Themes may not apply; financial content) | Financial decision-support content; adult users |
| Google | PEGI/ESRB-equivalent Mature or Teen depending on final content | Market data + research language; no graphic violence |

Final rating is determined by store questionnaires and counsel — **do not treat this as the filed rating**.

## Draft questionnaire answers

| Topic | Draft |
|-------|-------|
| Unrestricted web access | No (in-app controlled navigation) |
| Gambling | No |
| Contests | No |
| Horror / violence | No |
| Mature sexual content | No |
| Medical info | No |
| Alcohol / tobacco | No |
| Profanity | No |
| User-generated content | Possible thesis/notes — moderation policy TBD before submission |
| Made for Kids | No — explicitly not for children |

## Age gate architecture (pre-submission)

- Account signup age attestation field (architecture only)
- Regional flags may raise minimum age (see `regional/feature_flags.yaml`)
- Review demo accounts use adult synthetic personas only
