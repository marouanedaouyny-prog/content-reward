"""Conservative extraction; prose always requires a human structured-rule review."""

import re

from pydantic import BaseModel, Field

from campaigns.models import Rules


class ParsedRules(BaseModel):
    rules: Rules
    requires_review: bool
    warnings: list[str] = Field(default_factory=list)


def parse_rules(value):
    if isinstance(value, dict):
        return ParsedRules(rules=Rules.model_validate(value), requires_review=False)
    if not isinstance(value, str) or not value.strip() or len(value) > 20000:
        raise ValueError('Supply structured rules or bounded campaign text')
    fields = {}
    window = re.search(r'between\s+(\d+)\s+and\s+(\d+)\s*(?:seconds|secs|s)\b', value, re.I)
    if window:
        fields.update(min_duration=int(window[1]), max_duration=int(window[2]))
    for key, expression in [('min_duration', r'(?:minimum|min|at least)\s+(\d+)\s*(?:seconds|secs|s)\b'),
                            ('max_duration', r'(?:maximum|max|at most)\s+(\d+)\s*(?:seconds|secs|s)\b')]:
        match = re.search(expression, value, re.I)
        if match:
            fields[key] = int(match[1])
    if re.search(r'(?:must|required|include)', value, re.I):
        fields['required_hashtags'] = list(dict.fromkeys(re.findall(r'#[\w]+', value)))
    return ParsedRules(rules=Rules(**fields), requires_review=True,
                       warnings=['Prose extraction is partial. Review every rule and confirm rights before publication.'])
