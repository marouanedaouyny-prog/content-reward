# Compliance Engine Architecture

**Based on:** `research/content_rewards.md` (Terms §12, §7.5, §8, §9, §14)

---

## 4.1 Compliance Gates (Automated, Deterministic)

Every clip must pass ALL gates before `PUBLISH` state.

| Gate ID | Requirement Source | Check | Tool | Failure State |
|---------|-------------------|-------|------|---------------|
| **DURATION** | Platform limits + Campaign rules | `min_duration ≤ clip.duration ≤ max_duration` | `ffprobe` | `QC_FAILED:DURATION` |
| **RESOLUTION** | Platform min (720p TT/IG/YT Shorts, 1080p YT) | `width ≥ min_w AND height ≥ min_h` | `ffprobe` | `QC_FAILED:RESOLUTION` |
| **ASPECT_RATIO** | Campaign requirement | `clip.aspect_ratio ∈ campaign.required_aspect_ratios` | `ffprobe` | `QC_FAILED:ASPECT` |
| **CODEC** | All platforms: H.264/AAC | `video_codec=h264 AND audio_codec=aac` | `ffprobe` | `QC_FAILED:CODEC` |
| **FILE_SIZE** | Platform max (TT 4GB, IG 4GB, YT 256GB, X 512MB/16GB) | `file_size ≤ platform_max_bytes` | `os.path.getsize` | `QC_FAILED:SIZE` |
| **DISCLOSURE** | FTC + Campaign (§12.9) | `required_disclosure_text IN caption.text[:200]` | String match | `QC_FAILED:DISCLOSURE` |
| **HASHTAGS** | Campaign `required_tags` (§12) | `all(tag IN caption.hashtags FOR tag IN campaign.required_tags)` | Set containment | `QC_FAILED:HASHTAGS` |
| **MENTIONS** | Campaign `required_mentions` | `all(mention IN caption.mentions FOR mention IN campaign.required_mentions)` | Set containment | `QC_FAILED:MENTIONS` |
| **COPOSTING** | Terms §12.6 | `clip.platform NOT IN ["INSTAGRAM_COLLAB", "TIKTOK_DUET"]` | Metadata | `QC_FAILED:COPOST` |
| **REUSED_CONTENT** | Terms §12.2, Repost limit | `clip_hash NOT IN recent_submission_hashes(30d)` | DB lookup | `QC_FAILED:REUSED` |
| **AUDIO_LEVEL** | Platform loudness norms | `-18 LUFS ≤ integrated_loudness ≤ -14 LUFS` | `ffmpeg -af loudnorm=print_format=json` | `QC_FAILED:AUDIO` |
| **VISUAL_QUALITY** | No corruption | `blackdetect < 0.5s AND freezedetect < 1s` | `ffmpeg` | `QC_FAILED:VISUAL` |
| **PLATFORM_RULES** | Terms §12.1 | Platform-specific policy check (e.g., TT political ban, YT community guidelines) | Rules engine | `QC_FAILED:PLATFORM_RULES` |
| **REGULATED_VERTICAL** | Terms §12.5 | If campaign.vertical ∈ [CRYPTO, FINANCE, SUPPLEMENTS, GAMBLING] → extra disclosures present | Keyword check | `QC_FAILED:REGULATED` |
| **POLITICAL_CONTENT** | Terms §12.11 | If political → disclosure present + not on TT/X | Keyword + platform check | `QC_FAILED:POLITICAL` |

---

## 4.2 Campaign Requirements Parser

```python
def parse_campaign_requirements(campaign: Campaign) -> ComplianceRules:
    """
    Extract enforceable requirements from Campaign Description + Campaign Requirements
    ONLY in-platform requirements are enforceable (Terms §7.5)
    """
    rules = ComplianceRules()
    
    # From structured fields
    rules.required_tags = campaign.required_tags or []
    rules.required_mentions = campaign.required_mentions or []
    rules.required_disclosure = campaign.required_disclosure or "Sponsored"
    rules.platforms = campaign.platforms or []
    rules.aspect_ratios = campaign.required_aspect_ratios or ["9:16"]
    rules.min_duration = campaign.min_duration or 5
    rules.max_duration = campaign.max_duration or 60
    
    # From description (NLP extraction for structured rules)
    # Only explicit requirements in description are enforceable
    description_rules = extract_structured_rules(campaign.description)
    rules.merge(description_rules)
    
    # Platform-specific rules
    for platform in rules.platforms:
        rules.merge(PLATFORM_RULES[platform])
    
    # Vertical-specific rules
    if campaign.vertical:
        rules.merge(VERTICAL_RULES.get(campaign.vertical, {}))
    
    return rules
```

---

## 4.3 Fraud Prevention (Never Automate)

| Prohibited Activity | Terms Reference | Automation Policy |
|---------------------|-----------------|-------------------|
| **Bot views/likes** | §12.2 | **NEVER** - permanent ban |
| **View farms** | §12.2 | **NEVER** |
| **Click farms** | §12.2 | **NEVER** |
| **Engagement pods** | §12.2 | **NEVER** |
| **Artificial inflation** | §12.2 | **NEVER** |
| **Coordinated inauthentic behavior** | §12.2 | **NEVER** |

**Bot Score Integration:**
- CR runs Bot Score (0-100, third-party, proprietary) on submissions
- Our system: **read-only** — we submit URL, CR computes score
- If flagged → `FLAGGED` state, human appeal (10 biz days)
- We do NOT attempt to influence or predict Bot Score

---

## 4.4 Account & Connection Compliance

| Check | Requirement | Enforcement |
|-------|-------------|-------------|
| **OAuth scopes read-only** | Terms §14.2, Privacy §4 | Verify token scopes at connect time; reject if write scopes present |
| **IG Professional account** | Terms §14.1 | Validate at connect; if personal → `CONNECTION_FAILED:IG_PERSONAL` |
| **Token revocation** | Terms §14.3 | Monitor token health; pause submissions if revoked |
| **Related accounts** | Terms §9.4 | Flag if same creator operates multiple accounts in same campaign |
| **Sanctions screening** | Terms §15 | Check creator against OFAC SDN at onboarding |

---

## 4.5 Compliance Engine Interface

```python
class ComplianceEngine:
    def check_clip(self, clip: Clip, campaign: Campaign, caption: Caption) -> QAReport:
        """Run all automated gates. Returns QAReport with pass/fail per check."""
        rules = parse_campaign_requirements(campaign)
        platform_rules = PLATFORM_RULES[campaign.platform]
        all_rules = rules.merge(platform_rules)
        
        checks = []
        for gate in COMPLIANCE_GATES:
            result = gate.check(clip, caption, all_rules)
            checks.append(CheckResult(gate=gate.id, passed=result.passed, details=result.details))
        
        score = sum(c.passed for c in checks) / len(checks) * 100
        status = "QA_PASSED" if all(c.passed for c in checks) else "QA_FAILED"
        
        return QAReport(
            clip_id=clip.id,
            platform=campaign.platform,
            checks=checks,
            score=score,
            status=status,
            failed_gates=[c.gate for c in checks if not c.passed]
        )
    
    def check_account(self, account: SocialAccount) -> AccountCompliance:
        """Verify account meets platform + CR requirements."""
        checks = [
            ("oauth_readonly", account.scopes_write == []),
            ("ig_professional", account.platform != "INSTAGRAM" or account.account_type in ["BUSINESS", "CREATOR"]),
            ("token_valid", account.expires_at > now()),
            ("not_revoked", account.status == "ACTIVE"),
        ]
        return AccountCompliance(account_id=account.id, checks=checks)
```

---

## 4.6 Human Gates (Configurable)

| Gate | When | Action |
|------|------|--------|
| **CLIP_SELECTION_REVIEW** | High-value campaigns (>$500/clip) | Human approves clip candidates before edit |
| **CAPTION_REVIEW** | Regulated verticals, political | Human reviews generated caption |
| **PRE_POST_REVIEW** | Campaign enables (Terms §8) | Brand reviews Draft via CR platform |
| **HIGH_RISK_CONTENT** | Flagged by ML classifier | Human reviews before publish |

---

## 4.7 Audit Trail (Every Check)

```json
{
  "audit_id": "uuid",
  "clip_id": "uuid",
  "campaign_id": "uuid",
  "gate": "DISCLOSURE",
  "input": {"caption_text": "...", "required_disclosure": "Sponsored"},
  "result": "PASS",
  "details": "Found 'Sponsored' at position 0",
  "checked_at": "ISO8601",
  "engine_version": "1.0.0"
}
```

---

## 4.8 Cost Model

| Component | Cost |
|-----------|------|
| Gate checks (14 gates) | FREE (local FFmpeg + Python) |
| Rules engine | FREE (local) |
| Audit logging | FREE (local SQLite) |
| Human gates | Time cost only |

---

*End of Phase 4. Next: Phase 5 — State Machine.*