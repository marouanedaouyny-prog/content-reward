# Content Rewards Platform Research — End-to-End

**Source URLs (official):**
- Creator Terms of Service: `https://b4e0vdqv6zgqeqj4pfgm.apps.whop.com/terms` (last updated Sep 24, 2026)
- Privacy Policy: `https://b4e0vdqv6zgqeqj4pfgm.apps.whop.com/privacy-policy` (last updated Sep 20, 2026)
- FAQs: `https://b4e0vdqv6zgqeqj4pfgm.apps.whop.com/faqs` and `https://contentrewards.com/faqs` (Whop-hosted legacy)
- Creator landing: `https://b4e0vdqv6zgqeqj4pfgm.apps.whop.com/creators`
- Brand landing: `https://b4e0vdqv6zgqeqj4pfgm.apps.whop.com/brand`

> **Note on platform versions:** The current Content Rewards web application runs at `b4e0vdqv6zgqeqj4pfgm.apps.whop.com`. An earlier Whop-hosted experience (governed by prior "Clippers Terms") still runs some campaigns. This research covers the **current platform** per the Creator Terms (Section "Scope; legacy experience").

---

## 1. Campaign Mechanics

### 1.1 Campaign Types (Terms §6)

| Type | Mechanics | Minimum Budget | Key Characteristics |
|------|-----------|----------------|---------------------|
| **CPM** | Paid per 1,000 **verified views**. Brand sets per-clip min/max earnings. | $1,000 | Views continue to accrue post-approval while campaign funded & open. |
| **Per-post** | Flat amount per approved Clip, credited at approval. No post-approval view-based accrual. | $1,000 | If min-view requirement not met in Brand-set monitoring period, reserved payout returns to budget. |
| **Retainer** | Cycle-based subscription; paid per Cycle. Per-Cycle amount < total budget. | $1,000 | Deliverables produced on work-for-hire/assignment basis (Terms §17.3). |

### 1.2 Budget Flow (Terms §6.4–6.5)
- **Budget utilization:** Campaign draws down funded budget as Submissions are approved/validated; remainder stays available until exhausted.
- **Budget reservation:**
  - Per-post & Retainer: payout reserved at approval.
  - CPM: budget drawn incrementally as verified views accrue.
  - If approved Submission later rejected or flag upheld → unsettled reserved amount returns to campaign budget (§11).

### 1.3 Campaign Visibility (FAQ, Brand page)
- Campaigns can be **Public**, **Application-only**, or **Private**.
- Creators discover Public campaigns on the **Discover** page (Terms §1 Definitions).
- Brand page notes: "Run CPM, retainer or per-post campaigns: public, application-only or private."

---

## 2. Submission Lifecycle

### 2.1 Submission Definition (Terms §1)
> **Submission** — the act of submitting a posted Clip's URL (or a Draft, where required) for review and payout.

### 2.2 Submission Method (FAQ, Creators page)
1. Join a campaign.
2. Link your social account(s) (see §7).
3. Post the Clip on the platform the campaign requires.
4. Submit the **public URL** of the posted Clip within the campaign (tap "Submit Video").
5. Where Pre-post Review is enabled: upload a raw **Draft** (MP4) before posting (§8.1).

### 2.3 Submission Rules (FAQ, Terms §12)
- Submissions must come from **public accounts** (FAQ: "No. All submissions must come from public accounts.")
- **Co-posting** (Instagram Collab, equivalent features) prohibited unless explicitly permitted in Campaign Requirements/Description (§12.6).
- **Repost limit:** Same unmodified video may not be posted to >5 different accounts for the same Campaign without prior written Brand approval documented in-platform (legacy Clippers Terms §14.2).

### 2.4 Submission Statuses (FAQ)
- **Submitted** — Brand moderator has not reviewed yet.
- **Approved** — passes to Validation Window.
- **Rejected** — Brand rejected (grounds must be in Campaign Requirements/Description on Platform; external requirements unenforceable per Terms §7.5).
- **Flagged** — Bot Score ≥ threshold triggers human review; payout paused (Terms §9.2).

---

## 3. Approval Lifecycle

### 3.1 Review Flow (Terms §7)
1. **Bot Score triage** runs first (§9).
2. **Brand moderator** approves or rejects. CR Support **cannot** approve/reject on Brand's behalf; CR only resolves flags (§7.2).
3. **Validation Window** — approved payouts held while CR verifies views & runs fraud checks (§7.3).

### 3.2 Validation Window Duration (Terms §7.3)
| Campaign Type | Validation Window |
|---------------|-------------------|
| **CPM** | 7-day earning period post-approval + 3-day hold → **~10 days after approval** |
| **Per-post** | Settles **shortly after approval** |
| **Retainer** | Settles **after end of each Cycle** |

> CR may adjust periods; open fraud flag pauses settlement until resolved (§9).

### 3.3 Auto-Approval (Legacy Clippers Terms §10.1–10.2)
> Brands have 7 days to act; if no action, submission may be auto-approved. Brands may appeal auto-approval within 14 days with documented evidence.

> **Note:** Current Creator Terms §7.2 states "Brand moderator approves or rejects" — no explicit auto-approval mentioned. The legacy terms may still govern Whop-hosted campaigns.

### 3.4 Grounds for Rejection (Terms §7.5)
> Brand may only reject for failing a requirement **stated in the Campaign Requirements or Campaign Description on the Platform**. Requirements given only in other channels (Discord, email, etc.) are **not enforceable**.

### 3.5 Draft Approval ≠ Final Approval (Terms §8.4)
> Draft approval is not final approval. Brand may still reject posted Clip for brief non-compliance (missing disclosure, deviation from approved brief) even if Draft was approved.

---

## 4. Analytics / View Verification

### 4.1 Verification Method (Terms §4.1, §7.3, Privacy §4.2)
- CR verifies views **through the social platforms' APIs** (read-only OAuth scopes).
- **Verified views** = views confirmed via platform APIs, post-Bot Score filtering.
- CPM pays per **1,000 verified views**.

### 4.2 Data Accessed per Platform (Privacy §4.2)
| Platform | Metrics Accessed |
|----------|------------------|
| **Instagram** | Reach, likes, comments, shares, saves (instagram_business_basic, instagram_business_manage_insights) |
| **Facebook** | Page posts & engagement, linked Instagram professional account insights |
| **TikTok** | Public video view/like/comment/share counts (video.list) |
| **YouTube** | Video statistics & analytics (youtube.readonly, yt-analytics.readonly) |
| **X** | Profile & public post metrics (where API available) |

### 4.3 YouTube Data Retention (Privacy §4.6)
> YouTube API data stored ≤30 days unless refreshed via API (per YouTube API policies).

### 4.4 View Attribution Issues (Terms §12.6)
> Co-posted Clips split view attribution between accounts → prevents accurate view tracking → may be rejected.

---

## 5. Payout Lifecycle

### 5.1 Money Flow (Terms §4.1)
1. Brand funds campaign budget via Whop.
2. Creator posts Clip → submits URL (or Draft).
3. Bot Score triage → Brand moderator approves/rejects.
4. CR verifies views via platform APIs → applies Validation Window.
5. Payout credited to **Platform balance** (Available Balance).
6. Creator withdraws **through Whop**.

### 5.2 Payout Timing (Terms §7.3–7.4, Creators page)
| Stage | Timing |
|-------|--------|
| CPM earning period | 7 days post-approval |
| CPM hold | 3 days |
| **CPM total to Available Balance** | **~10 days after approval** |
| Per-post | Shortly after approval |
| Retainer | After each Cycle ends |
| Whop withdrawal | **Whop-controlled**: ~3–5 business days (or instant for Whop fee) |

> CR does not control/guarantee Whop withdrawal timing (§7.4).

### 5.3 Minimum/Maximum Payouts (Terms §6.1, FAQ)
- **CPM:** Brand sets per-clip minimum earning before payout + maximum earning ceiling.
- **Per-post:** Minimum view requirement may apply; if not met in monitoring period, reserved payout returns to budget.
- **Campaign minimum budget:** $1,000 for all types.

### 5.4 Payout Reversals / Clawbacks (Terms §11)
| Scenario | Outcome |
|----------|---------|
| Approved Submission later rejected | Unsettled amount reversed to campaign budget |
| Fraud/policy flag upheld | Unsettled amount reversed |
| Payout already settled to Available Balance | **Not reversed** through this process (§11.2) |
| Documented fraud discovered ≤30 days post-payout (legacy §9.6) | May be clawed back after review |

### 5.5 Payout Protection (Legacy §11)
- High Trust Score (≥80%) creators may receive payment for unreviewed submissions if brand requests refund.
- Not eligible if Bot Score exceeds suspicious threshold.

---

## 6. Creator Fees

### 6.1 Fee Structure (Terms §5, Pricing page)
| Campaign Type | Fee |
|---------------|-----|
| **CPM** | **Flat 10%** on every payout |
| **Per-post / Retainer** (budget < $5,000) | **10%** |
| **Per-post / Retainer** (budget ≥ $5,000 = **Premium**) | **0%** |
| **Promotional discounts** | Override flat fees for that campaign (§5.3) |

> Fee is flat — does not vary with lifetime earnings, campaign budget, or payout size (§5.1).
> Withdrawing to Whop balance is **free**, no minimum (Pricing page).

---

## 7. Campaign Requirements

### 7.1 Enforceable Requirements (Terms §7.5)
> Only requirements **stated in the Campaign Requirements or Campaign Description on the Platform** are enforceable. External-channel requirements (Discord, email, courses) are **not enforceable**.

### 7.2 Standard Requirements (Terms §12, FAQ)
- Clip must be posted on the platform(s) the campaign specifies (TikTok, Instagram, YouTube, X).
- Required disclosures (FTC) must be clear, conspicuous, at beginning of video (§12.9).
- No co-posting unless permitted (§12.6).
- No artificial inflation: no bots, view farms, click farms, engagement pods (§12.2).
- Content must comply with platform rules where posted (§12.1).
- Regulated verticals (crypto, finance, supplements, gambling): comply with advertising laws + Brand disclosures (§12.5).
- Political content: disclosure required; prohibited on TikTok/X (platform policy) (§12.11).

### 7.3 Pre-post Review (Drafts) (Terms §8)
- Brand may enable **optional Pre-post Review** for any campaign type.
- Creator uploads raw Draft (MP4) before posting.
- Brand can approve, reject, or request changes with **multi-round inline chat**.
- Drafts + chat retained as evidence even if campaign deleted (§8.3).
- Draft approval ≠ final Clip approval (§8.4).

---

## 8. Fraud Detection

### 8.1 Bot Score (Terms §9, Privacy §6)
- **0–100 fraud-risk score** produced with third-party fraud-detection provider.
- Signals, weights, methods: **proprietary**, may change without notice.
- **Purpose:** Estimate likelihood views/engagement are non-genuine.

### 8.2 How Bot Score Is Used (Terms §9.2, Privacy §6.3)
- Displayed to Brand & CR moderators as **input to manual review**.
- If score ≥ fraud threshold (set by CR or configured per campaign by Brand) → **automatically flagged for human review**, payout paused.
- **Flag does not reject** Submission.
- **Final decision always human** (Brand moderator for approval/rejection; CR for flag resolution).

### 8.3 Appeals (Terms §10)
- 1 appeal per flagged Submission.
- Must include written explanation + may need supporting evidence.
- CR aims to respond within **10 business days**.
- Successful appeal → flag dismissed, payout resumes.
- Unsuccessful → flag upheld, may reverse unsettled payout (§11).
- Rejected Submissions: raise with CR Support; Brand decides whether to change decision (§10.5).

### 8.4 Related Accounts (Terms §9.4)
> CR may consider behavior across accounts that appear related/operated by same person; may act on all together.

### 8.5 Bans for Fraud (Terms §13.2–13.3)
- Buying/generating views/likes/followers/engagement → **permanent ban** (appealable once).
- Permanent ban → connected social accounts may be **blocked from Platform reuse**, including under different email/Creator account.

---

## 9. Account Linking (Social Connections)

### 9.1 Connection Method (Terms §14, Privacy §4)
- Link via **each platform's official OAuth flow** OR (where offered) **verification code in bio**.
- **Connectable platforms:** Instagram, Facebook, TikTok, YouTube, X.
- **Instagram requirement:** Professional/Business or Creator account only (§14.1).

### 9.2 Scopes & Permissions (Terms §14.2, Privacy §4)
> **Scopes are read-only.**
> - Verify post ownership.
> - Read public post analytics (views, engagement, metadata).
> - **CR does NOT post on your behalf.**

### 9.3 Token Control (Terms §14.3, Privacy §4.3)
- Tokens stored server-side.
- Revocable **at any time**: at source platform or from "Connected accounts" in settings.
- Revoking → stops tracking & payouts for that platform; CR invalidates token within 24 hours.

### 9.4 Migration (Terms §14.4)
> CR may require existing links to move to OAuth; gives ≥2 weeks notice + deadline. Non-connected accounts may have tracking/payouts paused.

### 9.5 Data Shared with Brands (Privacy §7)
> When participating in a Brand's Campaign, CR shares: your profile info (username, display name, profile picture, follower/subscriber count), your Submissions & Drafts, and view/engagement/fraud-signal data.

---

## 10. Supported Social Platforms

| Platform | Connection Method | Account Requirement | Key Scopes (Privacy §4.2) |
|----------|-------------------|---------------------|---------------------------|
| **Instagram** | OAuth | Professional/Business or Creator account only | instagram_business_basic, instagram_business_manage_insights |
| **Facebook** | OAuth | Facebook Page you administer (not personal profile) | pages_show_list, pages_read_engagement, instagram_basic, instagram_manage_insights |
| **TikTok** | OAuth | Standard TikTok account | user.info.basic, user.info.profile, user.info.stats, video.list |
| **YouTube** | OAuth (Google) | YouTube channel | openid, profile, email, youtube.readonly, yt-analytics.readonly |
| **X (Twitter)** | OAuth | Standard X account | Profile & public post metrics (where API available) |

> Also supports optional **Discord** linking (identifies Discord account, adds to CR Discord server; not used to read messages or post) — Privacy §4.5.

---

## 11. Whop Relationship (Payments Only)

### 11.1 Role Separation (Terms §3)
| Whop Handles | Content Rewards Handles |
|--------------|-------------------------|
| Withdrawals of Platform balance (Whop Finance page) | Earning, Submissions, view verification |
| KYC for withdrawals | Fraud detection & flagging |
| | Campaign operation |

### 11.2 Key Implications (Terms §16)
- Sign-in credentials managed by Whop (Whop's terms).
- **Platform balance** = CR ledger record of amounts payable; paid out via Whop when you withdraw.
- If Whop bans you / you lose Whop access → may be unable to withdraw. CR retains validated balance records; contact CR Support for alternative payout (subject to ID verification & sanctions screening).
- Whop is a **third-party payment processor**; CR cannot bind Whop.

---

## 12. Other Key Policies

### 12.1 FTC Compliance (Terms §12.9)
- Creator **solely responsible** for FTC endorsement compliance (clear, conspicuous disclosure at beginning of video).
- CR does **not** pre-approve for FTC compliance, does **not** monitor for it, **not liable** for non-compliant content.
- Non-compliance → rejection + loss of payment.

### 12.2 Intellectual Property (Terms §17)
- **Approved Clip/Draft** → perpetual, worldwide, royalty-free, non-exclusive, sublicensable license to CR & Brand (host, use, edit, adapt, repost, promote, paid ads).
- **Brand-provided footage** → limited license to create/post Campaign Clip only.
- **Unapproved Drafts** → Creator keeps ownership; CR retains only as evidence.
- **Brand-provided content campaigns** → Brand owns final edited Clip; Creator assigns rights upon approval (§17.6).

### 12.3 Geographic Eligibility & Sanctions (Terms §15)
- Must not be on OFAC SDN list, owned/controlled by such person, or in comprehensively sanctioned jurisdiction.
- CR performs independent sanctions screening; may withhold payouts/suspend/terminate.

### 12.4 Non-Consensual Intimate Imagery (Terms §12.8)
- Strictly prohibited. 48-hour removal + payout stop/reverse + ban + report to platform + NCMEC reporting for CSAM.

### 12.5 Dispute Resolution (Terms §18)
- Binding arbitration (AAA, Delaware), class-action waiver, 30-day opt-out, small-claims carve-out, EU/UK geographic carve-out.

---

## 13. Summary for Automation System Design

| Area | Key Facts for Automation |
|------|---------------------------|
| **Submission** | Submit public Clip URL (or Draft if Pre-post Review on). Must be from linked, public account. |
| **Approval** | Brand moderator decides; CR only resolves fraud flags. 7-day review window (legacy auto-approval). |
| **Validation** | CPM: 7-day earn + 3-day hold (~10 days). Per-post: shortly after. Retainer: post-Cycle. |
| **Payout** | Credited to CR Platform balance → withdraw via Whop (~3–5 days). CR doesn't control Whop timing. |
| **Fees** | CPM: 10%. Per-post/Retainer <$5k: 10%. ≥$5k (Premium): 0%. |
| **Fraud** | Bot Score 0–100, third-party, proprietary. Auto-flag at threshold → human review. Appeals: 10 biz days. |
| **Accounts** | OAuth read-only (IG, FB, TT, YT, X). IG requires Pro/Creator. Revocable anytime. |
| **View verification** | Via platform APIs only. Co-posting breaks attribution. |
| **Requirements** | Only in-platform Campaign Requirements/Description enforceable. |
| **Legacy vs Current** | Whop-hosted = old Clippers Terms. Current = b4e0vdqv6zgqeqj4pfgm.apps.whop.com Creator Terms. |

---

## 14. Open Questions / Gaps

1. **API Documentation** — No public API docs found at official URLs. Automation may need browser automation or internal API discovery.
2. **Real-time Bot Score access** — Terms say creators "may view Bot Score percentage for their own submissions" (legacy §4.4); current terms don't specify creator visibility.
3. **Creator Trust Score** — Referenced in legacy terms (§5) for auto-approval, faster payouts, refund protection; not in current Creator Terms.
4. **Campaign application flow** — For application-only/private campaigns, exact acceptance mechanics not detailed.
5. **Webhook / event notifications** — No documentation of real-time events (submission approved, payout settled, flag raised).
6. **Rate limits / quotas** — Not documented in public terms.

---

*Generated from official Content Rewards sources. Last verified: Terms (Sep 24, 2026), Privacy (Sep 20, 2026).*