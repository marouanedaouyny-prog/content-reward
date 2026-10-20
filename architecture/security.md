# Security Architecture

**Based on:** `research/content_rewards.md` (Terms §14, §15, §16, Privacy §4, §6, §7)

---

## 9.1 OAuth Token Storage

### Encryption
```python
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import os

class TokenEncryption:
    def __init__(self, master_key: bytes = None):
        if master_key:
            self.key = master_key
        else:
            # Derive from environment variable + salt
            password = os.environ.get("TOKEN_ENCRYPTION_PASSWORD", "").encode()
            salt = os.environ.get("TOKEN_ENCRYPTION_SALT", "static-salt").encode()
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            self.key = base64.urlsafe_b64encode(kdf.derive(password))
        self.cipher = Fernet(self.key)
    
    def encrypt(self, token: str) -> str:
        return self.cipher.encrypt(token.encode()).decode()
    
    def decrypt(self, encrypted: str) -> str:
        return self.cipher.decrypt(encrypted.encode()).decode()
```

### Storage Schema
```sql
-- social_accounts table (from database.md)
access_token_encrypted TEXT NOT NULL,
refresh_token_encrypted TEXT,
token_expires_at TIMESTAMP WITH TIME ZONE,
```

### Key Management
| Key | Source | Rotation |
|-----|--------|----------|
| **Master encryption key** | `TOKEN_ENCRYPTION_PASSWORD` + `TOKEN_ENCRYPTION_SALT` env vars | Annual (re-encrypt all tokens) |
| **Database encryption** | SQLite: `sqlcipher` / PostgreSQL: `pgcrypto` | Per deployment |
| **Secrets** | `.env` (never committed) | Per environment |

---

## 9.2 Token Lifecycle

```python
class TokenManager:
    def __init__(self, db: Session, encryption: TokenEncryption):
        self.db = db
        self.encryption = encryption
    
    def get_valid_token(self, account: SocialAccount) -> str:
        """Returns valid access token, refreshing if needed."""
        if account.token_expires_at and account.token_expires_at < now() + timedelta(hours=2):
            return self.refresh_token(account)
        return self.encryption.decrypt(account.access_token_encrypted)
    
    def refresh_token(self, account: SocialAccount) -> str:
        """Refresh using platform-specific endpoint."""
        refresh_token = self.encryption.decrypt(account.refresh_token_encrypted)
        new_tokens = PLATFORM_REFRESH[account.platform](refresh_token)
        
        account.access_token_encrypted = self.encryption.encrypt(new_tokens.access_token)
        if new_tokens.refresh_token:
            account.refresh_token_encrypted = self.encryption.encrypt(new_tokens.refresh_token)
        account.token_expires_at = new_tokens.expires_at
        self.db.commit()
        
        return new_tokens.access_token
    
    def revoke_token(self, account: SocialAccount):
        """Revoke at platform + local cleanup."""
        PLATFORM_REVOKE[account.platform](account)
        account.status = "REVOKED"
        account.access_token_encrypted = ""
        account.refresh_token_encrypted = ""
        self.db.commit()
```

---

## 9.3 Secrets Management

| Secret | Storage | Access |
|--------|---------|--------|
| Platform `CLIENT_ID`/`CLIENT_SECRET` | `.env` (gitignored) | Config loader |
| `TOKEN_ENCRYPTION_PASSWORD` | `.env` | TokenEncryption init |
| `API_KEY` (Hermes auth) | `.env` | Auth middleware |
| Whop API key | `.env` | Payout tracking |
| Database password | `.env` | DB connection |

**Never in code, never in logs, never in DB.**

---

## 9.4 Least-Privilege OAuth Scopes

| Platform | Scopes Requested | Justification |
|----------|------------------|---------------|
| **TikTok** | `video.upload`, `video.publish`, `user.info.basic` | Upload + publish + verify ownership |
| **Instagram** | `instagram_business_basic`, `instagram_business_content_publish`, `instagram_manage_insights` | Publish + analytics (requires FB Login) |
| **Facebook** | `pages_show_list`, `pages_read_engagement`, `pages_manage_posts` | Page management + insights |
| **YouTube** | `youtube.upload`, `youtube.readonly`, `yt-analytics.readonly` | Upload + read stats + analytics |
| **X** | `tweet.write`, `tweet.read`, `users.read`, `offline.access`, `media.write` | Post + read metrics + media upload |

**Validation at connect time:**
```python
def validate_scopes(account: SocialAccount) -> bool:
    required = REQUIRED_SCOPES[account.platform]
    granted = set(account.scopes)
    return required.issubset(granted)
```

---

## 9.5 Audit Logging (Every Sensitive Action)

```sql
-- audit_logs table (from database.md)
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    action VARCHAR(50) NOT NULL,
    actor_type VARCHAR(30) NOT NULL,
    actor_id VARCHAR(255),
    input JSONB,
    output JSONB,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
```

**Logged Actions:**
| Action | Entity | Input (Redacted) | Output |
|--------|--------|------------------|--------|
| `TOKEN_REFRESH` | SocialAccount | `{account_id, platform}` | `{success, new_expires_at}` |
| `TOKEN_REVOKE` | SocialAccount | `{account_id, platform, reason}` | `{success}` |
| `MEDIA_UPLOAD` | SocialPost | `{clip_id, platform, account_id}` | `{media_id, success}` |
| `VIDEO_PUBLISH` | SocialPost | `{clip_id, platform, post_id}` | `{post_url, platform_post_id}` |
| `URL_SUBMIT` | Submission | `{campaign_id, clip_url_hash}` | `{submission_id, status}` |
| `PAYOUT_CHECK` | Payout | `{submission_id}` | `{status, amount}` |
| `COMPLIANCE_CHECK` | QAReport | `{clip_id, platform, rules_hash}` | `{score, passed, failed_gates}` |

**Redaction Rules:**
- Never log: `access_token`, `refresh_token`, `client_secret`, `api_key`
- Hash: `clip_url` → `clip_url_hash` (first 8 chars of SHA-256)
- Truncate: long JSON → first 500 chars

---

## 9.6 Account Isolation

```python
class AccountIsolation:
    """Enforce per-creator, per-platform isolation."""
    
    def can_access(self, actor: Actor, account: SocialAccount) -> bool:
        if actor.type == "creator":
            return actor.creator_id == account.creator_id
        elif actor.type == "system":
            return True  # internal operations
        elif actor.type == "operator":
            return actor.has_permission("social_accounts.manage")
        return False
    
    def get_accounts_for_creator(self, creator_id: UUID) -> List[SocialAccount]:
        return self.db.query(SocialAccount).filter(
            SocialAccount.creator_id == creator_id,
            SocialAccount.status == "ACTIVE"
        ).all()
```

---

## 9.7 Retry Limits & Destructive Action Protection

| Protection | Implementation |
|------------|----------------|
| **Max publish retries** | `jobs.max_attempts = 3` (configurable) |
| **Max submit retries** | `jobs.max_attempts = 3` |
| **Rate limit compliance** | Respect `x-rate-limit-*` headers, exponential backoff |
| **Destructive actions** | `DELETE` / `REVOKE` require human confirmation (operator gate) |
| **Duplicate prevention** | Idempotency keys on ALL external calls (unique constraints) |
| **Circuit breaker** | After 5 consecutive 429/5xx → pause platform for 15 min |

---

## 9.8 Sanctions & Compliance Screening

```python
def screen_creator(creator: Creator) -> ScreeningResult:
    """Check OFAC SDN + sanctioned jurisdictions (Terms §15)."""
    # 1. Name screening against OFAC SDN list (download daily)
    # 2. Jurisdiction check: creator.country not in SANCTIONED_COUNTRIES
    # 3. Ownership check: beneficial owners not on SDN
    
    return ScreeningResult(
        passed=all_checks_passed,
        flags=flags,
        screened_at=now()
    )
```

---

## 9.9 Data Retention (Privacy §4.6, §5)

| Data | Retention | Deletion Trigger |
|------|-----------|------------------|
| OAuth tokens | Until revoked + 24h | User revokes or account deleted |
| YouTube API data | ≤30 days | Auto-purge job (Privacy §4.6) |
| Analytics snapshots | 2 years | Rolling window |
| Audit logs | 7 years | Compliance requirement |
| Submissions | 7 years | Financial record |
| Payouts | 7 years | Tax compliance |
| Clip files | 90 days post-payout | Storage cleanup |

---

## 9.10 Security Checklist (Pre-Launch)

- [ ] `.env` in `.gitignore`
- [ ] `TOKEN_ENCRYPTION_PASSWORD` generated (32+ chars)
- [ ] `TOKEN_ENCRYPTION_SALT` unique per deployment
- [ ] Database encrypted at rest (SQLCipher / pgcrypto)
- [ ] TLS enforced for all external API calls
- [ ] OAuth redirect URIs validated against allowlist
- [ ] Rate limit headers parsed and respected
- [ ] Audit logging enabled for all sensitive actions
- [ ] Token refresh tested for all 5 platforms
- [ ] Token revocation tested for all 5 platforms
- [ ] Sanctions screening integrated
- [ ] Data retention jobs scheduled
- [ ] Penetration test on auth flow
- [ ] Incident response plan documented

---

*End of Phase 9. Next: Phase 10 — Cost Plan.*