"""Fail-closed publication eligibility without platform or scraping dependencies."""

import math
import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from campaigns.models import platform_name


class Eligibility(BaseModel):
    eligible: bool
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def validate_campaign(campaign, clip, metadata, platform, *, source=None, for_publication=False, now=None):
    rules, violations, warnings = campaign.rules, [], []
    platform = platform_name(platform)
    duration = clip.get('duration_seconds')
    if (isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration)
            or not rules.min_duration <= duration <= rules.max_duration):
        violations.append('duration_outside_campaign_bounds')
    if platform not in rules.allowed_platforms:
        violations.append('destination_not_allowed')
    text = metadata.get('caption', '')
    title = metadata.get('title', '')
    if (not isinstance(text, str) or not isinstance(title, str)
            or len(text) > 10000 or len(title) > 300):
        return Eligibility(eligible=False, violations=['invalid_publication_text'])
    tags = {tag.casefold() for tag in re.findall(r'#[\w]+', text)}
    if any(tag.casefold() not in tags for tag in rules.required_hashtags):
        violations.append('required_hashtags_missing')
    content = clip.get('transcript', '') + ' ' + text + ' ' + title
    if any(re.search(r'(?<!\w)' + re.escape(topic) + r'(?!\w)', content, re.I) for topic in rules.forbidden_topics):
        violations.append('forbidden_topic_detected')
    if rules.allowed_source_ids and clip.get('source_id') not in rules.allowed_source_ids:
        violations.append('source_not_allowed')
    if rules.required_creator and (source or {}).get('creator') != rules.required_creator:
        violations.append('creator_requirement_not_verified')
    if campaign.deadline and (now or datetime.now(timezone.utc)) >= campaign.deadline:
        violations.append('campaign_deadline_passed')
    if for_publication:
        if campaign.status != 'active':
            violations.append('campaign_not_active')
        if not campaign.rules_reviewed:
            violations.append('campaign_rules_need_review')
        if not campaign.rights_confirmed:
            violations.append('source_rights_not_confirmed')
        if rules.forbidden_topics and not clip.get('transcript'):
            violations.append('content_transcript_missing')
    else:
        warnings.append('Preparation eligibility does not establish publication permission.')
    if rules.minimum_views:
        warnings.append(f'Campaign requires {rules.minimum_views} actual post views; this cannot be guaranteed before posting.')
    return Eligibility(eligible=not violations, violations=violations, warnings=warnings)
